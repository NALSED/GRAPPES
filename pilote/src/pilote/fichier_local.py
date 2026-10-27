"""Bases en copie locale (document 22) : UN type de source, « fichier_local », pour brancher n'importe quelle base téléchargée comme on branche une API.

Un fichier (CSV, TSV, JSONL, ou SQLite déjà constitué, éventuellement dans un zip) est versé UNE fois dans une table SQLite indexée ; le moteur
l'interroge ensuite sans appel réseau, donc sans quota. Un nouveau dump = un nouveau fichier + une ligne de configuration, jamais un branchement
sur mesure. Ce module n'utilise que la bibliothèque standard : il tourne aussi dans l'interpréteur de grappes.

Règles en dur : une base locale apporte des DONNÉES, jamais un juge (le rapprochement reste dans Fusion/doublons) ; les personnes physiques ne sont
jamais versées (règle 8) : le filtre `exclure` de la déclaration les écarte À L'IMPORT, par classe, pas après coup."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import time
import unicodedata
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

CHAMPS = ("ville", "numero", "pays", "genre", "site", "themes", "detail")  # colonnes rendues, en plus du nom
LOT = 20_000
MOTS_VIDES = frozenset(["de", "du", "des", "la", "le", "les", "l", "d", "et", "en", "au", "aux", "un", "une", "pour", "par", "sur", "dans", "avec", "the", "of", "and", "for", "in"])


class BaseLocaleErreur(Exception):
    """Message en français, prêt à être montré."""


def nom_normalise(nom: str) -> str:
    """Même mise à plat que `adaptateurs.nom_normalise` : sans accents, sans majuscules, sans ponctuation."""
    sans = "".join(c for c in unicodedata.normalize("NFKD", str(nom)) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sans.casefold()).strip()


def chemin_base(dossier_copies: str | Path, base: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", base):
        raise BaseLocaleErreur("Le nom d'une base locale ne contient que des lettres minuscules, des chiffres, « - » et « _ ».")
    return Path(dossier_copies) / "bases" / f"{base}.sqlite"


# ================================================================ lecture des formats


def _flux(fichier: Path, membre: str, encodage: str) -> Iterator[tuple[io.TextIOBase, str]]:
    """Les fichiers à lire : le fichier lui-même, ou les membres d'un zip dont le nom correspond à `membre` (expression régulière ; tous si elle est vide)."""
    if fichier.suffix.lower() == ".zip":
        with zipfile.ZipFile(fichier) as z:
            noms = [n for n in z.namelist() if not n.endswith("/")]
            choisis = [n for n in noms if re.search(membre, n)] if membre else noms
            if not choisis:
                raise BaseLocaleErreur(f"Aucun fichier du zip ne correspond à « {membre} » (il contient : {', '.join(noms[:5])}).")
            for n in choisis:
                with z.open(n) as brut:
                    yield io.TextIOWrapper(brut, encoding=encodage, errors="replace", newline=""), n
        return
    with open(fichier, encoding=encodage, errors="replace", newline="") as f:
        yield f, fichier.name


def _geojson(texte: io.TextIOBase) -> Iterator[dict[str, Any]]:
    """Les entités d'un GeoJSON : leurs propriétés et l'emprise (minlon, minlat, maxlon, maxlat). La géométrie elle-même n'est pas gardée."""
    def points(c: Any) -> Iterator[tuple[float, float]]:
        if isinstance(c, list) and c and isinstance(c[0], (int, float)):
            yield float(c[0]), float(c[1])
        elif isinstance(c, list):
            for x in c:
                yield from points(x)

    doc = json.load(texte)
    for f in doc.get("features", []) if isinstance(doc, dict) else []:
        pts = list(points((f.get("geometry") or {}).get("coordinates")))
        emprise = f"{min(p[0] for p in pts):.4f},{min(p[1] for p in pts):.4f},{max(p[0] for p in pts):.4f},{max(p[1] for p in pts):.4f}" if pts else ""
        yield {**(f.get("properties") or {}), "emprise": emprise}


def lignes_du_fichier(fichier: Path, spec: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Les enregistrements du fichier sous forme de dictionnaires, un à un (jamais tout en mémoire)."""
    fmt = str(spec.get("format") or "").lower()
    if fmt not in ("csv", "tsv", "jsonl", "geojson"):
        raise BaseLocaleErreur("Le format d'une base locale est « csv », « tsv », « jsonl », « geojson » ou « sqlite ».")
    csv.field_size_limit(1 << 24)
    for texte, _ in _flux(fichier, str(spec.get("membre_zip") or ""), str(spec.get("encodage") or "utf-8")):
        if fmt == "geojson":
            yield from _geojson(texte)
        elif fmt == "jsonl":
            for ligne in texte:
                if ligne.strip():
                    try:
                        obj = json.loads(ligne)
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        yield obj
        else:
            delim = str(spec.get("delimiteur") or ("\t" if fmt == "tsv" else ","))
            entetes = spec.get("entetes")
            yield from (csv.DictReader(texte, delimiter=delim, fieldnames=entetes) if entetes else csv.DictReader(texte, delimiter=delim))


def _valeur(ligne: dict[str, Any], cle: Any) -> str:
    """Une colonne ; plusieurs (liste) mises bout à bout avec un espace ; « a|b » = la première non vide (deux fichiers qui nomment la même chose
    autrement) ; {premier: [colonnes], motif: regex} = la première valeur qui correspond au motif. Les valeurs manquantes sont ignorées."""
    if isinstance(cle, dict):
        return next((v for c in cle.get("premier", []) if (v := _valeur(ligne, c)) and re.search(str(cle.get("motif", "")), v)), "")
    if isinstance(cle, str) and "|" in cle:
        return next((v for c in cle.split("|") if (v := _valeur(ligne, c))), "")
    if isinstance(cle, list):
        return " ".join(v for c in cle if (v := _valeur(ligne, c)))
    v = ligne.get(str(cle))
    if isinstance(v, list):
        v = "; ".join(map(str, v))
    return "" if v is None else str(v).strip()


def _poids(ligne: dict[str, Any], regle: dict[str, Any] | None) -> int:
    """Le poids sert à CLASSER les homonymes (la vraie « Renault » avant ses 40 homonymes) : chiffres d'une colonne (ex. tranche d'effectif), plus un bonus si
    une autre colonne vaut la valeur voulue (ex. unité encore active). Absent = 0 : le classement retombe sur la longueur du nom."""
    if not regle:
        return 0
    chiffres = re.sub(r"\D", "", _valeur(ligne, regle.get("colonne", "")))
    p = int(chiffres) if chiffres else 0
    a = regle.get("actif")
    return p + (int(a.get("bonus", 100)) if a and _valeur(ligne, a["colonne"]) == str(a["valeur"]) else 0)


def _passe(ligne: dict[str, Any], regles: dict[str, Any] | None, *, garder: bool) -> bool:
    """`garder: True` → toutes les règles doivent être vraies ; sinon (exclure) → AUCUNE ne doit l'être. Une règle : colonne → expression régulière."""
    if not regles:
        return True
    vues = [bool(re.search(str(rx), _valeur(ligne, col))) for col, rx in regles.items()]
    return all(vues) if garder else not any(vues)


# ================================================================ import


def _schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE donnees (id INTEGER PRIMARY KEY, nom TEXT NOT NULL, nom_n TEXT NOT NULL, ville TEXT, numero TEXT, pays TEXT, genre TEXT, site TEXT, themes TEXT, detail TEXT, poids INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE noms (id INTEGER PRIMARY KEY, nom_n TEXT NOT NULL, donnee INTEGER NOT NULL);
        CREATE TABLE meta (cle TEXT PRIMARY KEY, valeur TEXT);
        """
    )


def importer(fichier: str | Path | list[str | Path], base: str, dossier_copies: str | Path, spec: dict[str, Any], progres: Callable[[int], None] | None = None) -> dict[str, Any]:
    """Verse `fichier` (ou la liste de fichiers, de même forme) dans `<dossier_copies>/bases/<base>.sqlite`, indexé. Rend le bilan {lignes, ecartees, octets, secondes}.

    `spec` : format, delimiteur, encodage, membre_zip, colonnes {nom, alias (liste), ville, numero, pays, genre, site, themes, detail},
    `defauts` {pays, genre…}, `garder` / `exclure` {colonne: regex}, `separateur_alias` (défaut « ; »)."""
    fichiers = [Path(f) for f in (fichier if isinstance(fichier, list) else [fichier])]
    fichier = fichiers[0]
    cible = chemin_base(dossier_copies, base)
    cible.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if str(spec.get("format") or "").lower() == "sqlite":
        return _adopter_sqlite(fichier, cible, t0)
    col = spec.get("colonnes") or {}
    if "nom" not in col:
        raise BaseLocaleErreur("Dites quelle colonne porte le nom : « colonnes: {nom: ...} ».")
    defauts = {k: str(v) for k, v in (spec.get("defauts") or {}).items()}
    sep = str(spec.get("separateur_alias") or ";")
    provisoire = cible.with_suffix(".sqlite.partiel")
    provisoire.unlink(missing_ok=True)
    con = sqlite3.connect(provisoire)
    try:
        con.execute("PRAGMA journal_mode = OFF")
        con.execute("PRAGMA synchronous = OFF")
        _schema(con)
        n = ecartees = 0
        lot_d: list[tuple] = []
        lot_n: list[tuple] = []
        prochain = 1

        def vider() -> None:
            con.executemany("INSERT INTO donnees(id, nom, nom_n, ville, numero, pays, genre, site, themes, detail, poids) VALUES (?,?,?,?,?,?,?,?,?,?,?)", lot_d)
            con.executemany("INSERT INTO noms(nom_n, donnee) VALUES (?,?)", lot_n)
            lot_d.clear()
            lot_n.clear()

        for ligne in (l for f in fichiers for l in lignes_du_fichier(f, spec)):
            if not (_passe(ligne, spec.get("garder"), garder=True) and _passe(ligne, spec.get("exclure"), garder=False)):
                ecartees += 1
                continue
            nom = _valeur(ligne, col["nom"])
            nom_n = nom_normalise(nom)
            if not nom_n:
                ecartees += 1
                continue
            alias = [a.strip() for c in ([col["alias"]] if isinstance(col.get("alias"), str) else col.get("alias") or []) for a in _valeur(ligne, c).split(sep)]
            champs = [(_valeur(ligne, col[c]) if c in col else defauts.get(c, "")) or defauts.get(c, "") for c in CHAMPS]
            lot_d.append((prochain, nom, nom_n, *champs, _poids(ligne, spec.get("poids"))))
            vus = {nom_n}
            lot_n.append((nom_n, prochain))
            for a in alias:
                an = nom_normalise(a)
                if an and an not in vus:
                    vus.add(an)
                    lot_n.append((an, prochain))
            prochain += 1
            n += 1
            if len(lot_d) >= LOT:
                vider()
                if progres:
                    progres(n)
        vider()
        for j in spec.get("jointures") or []:
            _jointure(con, fichier_jointure=Path(j["fichier"]), j=j)
        con.execute("CREATE INDEX i_noms_n ON noms(nom_n)")
        con.execute("CREATE INDEX IF NOT EXISTS i_donnees_numero ON donnees(numero)")
        con.execute("CREATE VIRTUAL TABLE fts USING fts5(nom_n, content='noms', content_rowid='id', tokenize='unicode61 remove_diacritics 2', prefix='3')")
        con.execute("INSERT INTO fts(fts) VALUES('rebuild')")
        con.execute("INSERT INTO meta VALUES ('lignes', ?), ('ecartees', ?), ('importe_le', ?), ('fichier', ?)", (str(n), str(ecartees), time.strftime("%Y-%m-%d"), ", ".join(f.name for f in fichiers)))
        con.commit()
    except BaseException:
        con.close()
        provisoire.unlink(missing_ok=True)
        raise
    con.close()
    provisoire.replace(cible)  # la base n'apparaît qu'entière : jamais une copie à moitié écrite sous le nom définitif
    return {"lignes": n, "ecartees": ecartees, "octets": cible.stat().st_size, "secondes": round(time.time() - t0, 1)}


def _jointure(con: sqlite3.Connection, fichier_jointure: Path, j: dict[str, Any]) -> None:
    """Complète des colonnes (ex. la ville du siège) depuis un second fichier, par une clé commune (le numéro)."""
    con.execute("CREATE INDEX IF NOT EXISTS i_donnees_numero ON donnees(numero)")
    cle, colonnes = str(j["cle"]), j["colonnes"]  # colonnes : {champ de la base: colonne du fichier}
    lot: list[tuple] = []
    for ligne in lignes_du_fichier(fichier_jointure, j):
        if not (_passe(ligne, j.get("garder"), garder=True) and _passe(ligne, j.get("exclure"), garder=False)):
            continue
        valeurs = [_valeur(ligne, c) for c in colonnes.values()]
        if any(valeurs):
            lot.append((*valeurs, _valeur(ligne, cle)))
        if len(lot) >= LOT:
            _appliquer(con, lot, list(colonnes))
            lot.clear()
    _appliquer(con, lot, list(colonnes))


def _appliquer(con: sqlite3.Connection, lot: list[tuple], champs: list[str]) -> None:
    for c in champs:
        if c not in CHAMPS:
            raise BaseLocaleErreur(f"« {c} » n'est pas une colonne d'une base locale ({', '.join(CHAMPS)}).")
    con.executemany(f"UPDATE donnees SET {', '.join(c + ' = ?' for c in champs)} WHERE numero = ?", lot)


def _adopter_sqlite(fichier: Path, cible: Path, t0: float) -> dict[str, Any]:
    """Une base SQLite déjà constituée : elle doit porter les tables `donnees`, `noms` et `fts` de ce module."""
    con = sqlite3.connect(f"file:{fichier.as_posix()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table')")}
        if not {"donnees", "noms"} <= tables:
            raise BaseLocaleErreur("Cette base SQLite n'a pas les tables « donnees » et « noms » attendues.")
        n = con.execute("SELECT count(*) FROM donnees").fetchone()[0]
    finally:
        con.close()
    cible.write_bytes(fichier.read_bytes())
    return {"lignes": n, "ecartees": 0, "octets": cible.stat().st_size, "secondes": round(time.time() - t0, 1)}


# ================================================================ interrogation


def _ouvrir(dossier_copies: str | Path, base: str) -> sqlite3.Connection:
    f = chemin_base(dossier_copies, base)
    if not f.is_file():
        raise BaseLocaleErreur(f"La copie locale « {base} » n'est pas installée sur cette machine (voir le document 22 : import d'une base locale).")
    con = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def meta(dossier_copies: str | Path, base: str) -> dict[str, str]:
    con = _ouvrir(dossier_copies, base)
    try:
        return {r["cle"]: r["valeur"] for r in con.execute("SELECT cle, valeur FROM meta")}
    finally:
        con.close()


def _ligne(r: sqlite3.Row) -> dict[str, Any]:
    return {k: r[k] for k in r.keys() if k not in ("id", "nom_n", "long", "poids") and r[k] not in (None, "")}  # noqa: SIM118 - sqlite3.Row



def exact(dossier_copies: str | Path, base: str, nom: str, limite: int = 20) -> list[dict[str, Any]]:
    """Les entrées dont UN des noms (nom ou alias), une fois mis à plat, est identique à `nom`. Jamais de ressemblance."""
    voulu = nom_normalise(nom)
    if not voulu:
        return []
    con = _ouvrir(dossier_copies, base)
    try:
        cur = con.execute("SELECT DISTINCT d.* FROM noms n JOIN donnees d ON d.id = n.donnee WHERE n.nom_n = ? ORDER BY d.poids DESC LIMIT ?", (voulu, limite))
        return [_ligne(r) for r in cur]
    finally:
        con.close()


def chercher_par_mots(dossier_copies: str | Path, base: str, texte: str, limite: int = 50) -> list[dict[str, Any]]:
    """Recherche d'une organisation par ses mots : l'égalité exacte d'abord, puis les noms qui contiennent tous les mots (le dernier en préfixe).
    Un numéro officiel (suite de chiffres) est cherché tel quel."""
    brut = re.sub(r"\s+", "", texte)
    con = _ouvrir(dossier_copies, base)
    try:
        if brut.isdigit() and len(brut) >= 5:
            return [_ligne(r) for r in con.execute("SELECT * FROM donnees WHERE numero = ? OR numero LIKE ? LIMIT ?", (brut, brut + "%", limite))]
        voulu = nom_normalise(texte)
        mots = [m for m in voulu.split() if m not in MOTS_VIDES and len(m) >= 2] or voulu.split()
        if not mots:
            return []
        vus: dict[int, dict[str, Any]] = {}
        for r in con.execute("SELECT DISTINCT d.* FROM noms n JOIN donnees d ON d.id = n.donnee WHERE n.nom_n = ? ORDER BY d.poids DESC LIMIT ?", (voulu, limite)):
            vus[r["id"]] = _ligne(r)
        requetes = []
        if len(mots) > 1:
            requetes.append('"' + " ".join(mots) + '" *')  # les mots à la suite, dans l'ordre (« Air France » avant « France Air »)
        requetes.append(" ".join(f'"{m}"' for m in mots[:-1]) + (" " if len(mots) > 1 else "") + f'"{mots[-1]}" *')
        for requete in requetes:
            if len(vus) >= limite:
                break
            cur = con.execute(
                "SELECT DISTINCT d.*, length(n.nom_n) AS long FROM fts JOIN noms n ON n.id = fts.rowid JOIN donnees d ON d.id = n.donnee WHERE fts MATCH ? LIMIT 5000",
                (requete,),
            )
            candidats = sorted((r for r in cur if r["id"] not in vus), key=lambda r: (-r["poids"], r["long"]))  # les mieux pesés d'abord, puis les noms les plus courts
            for r in candidats[: limite - len(vus)]:
                vus[r["id"]] = _ligne(r)
        return list(vus.values())
    except sqlite3.OperationalError as exc:
        raise BaseLocaleErreur(f"La copie locale « {base} » a refusé la recherche : {exc}") from exc
    finally:
        con.close()
