"""Classements de la page Tri (D70) : CLASSER ET GROUPER SONT LA MÊME COMMANDE. Choisir un classement, c'est choisir des paquets.

Un classement est un petit fichier YAML ordinaire : un nom, les FAITS sur lesquels on groupe, l'ordre des paquets, l'ordre des
noms dans un paquet. On en crée par un petit formulaire, on les duplique, on les exporte (le fichier lui-même). Ceux livrés
avec pilote et ceux créés vivent dans deux dossiers distincts mais ont exactement la même forme.

Un classement ne lit QUE des faits : d'où vient le nom, à combien d'endroits, ce qui l'a trouvé, son nom, son genre de chose,
sa ville, son pays, son site, son numéro officiel, les décisions déjà prises, et la ressemblance avec un autre nom. Jamais
un avis du programme.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from pilote.config import Config

ORIGINES = (
    ("registre", "dans un registre officiel"),
    ("presse", "cité par la presse"),
    ("encyclo", "dans une encyclopédie"),
    ("web", "trouvé sur le web"),
    ("texte", "lu dans un texte"),
)
ORIGINE_RANG = {k: i for i, (k, _) in enumerate(ORIGINES)}
ORIGINE_LIBELLE = dict(ORIGINES)
DECISIONS_LIBELLE = {"garder": "gardés", "rejeter": "rejetés", "plus_tard": "mis de côté", None: "pas encore décidés"}
FONCTIONS = ("maison mère", "siège", "filiale", "établissement")
DECISIONS_RANG = {None: 0, "garder": 1, "plus_tard": 2, "rejeter": 3}
ORDRES_PAQUETS = {"solidite": "les plus solides d'abord", "fragilite": "les plus fragiles d'abord", "nombre": "les plus nombreux d'abord", "alphabetique": "par ordre alphabétique"}
ORDRES_NOMS = {"alphabetique": "par ordre alphabétique", "endroits": "les plus cités d'abord", "sans": "dans l'ordre trouvé"}

# Les faits sur lesquels un classement peut grouper : identifiant -> phrase en français courant.
FAITS = {
    "origine": "d'où vient le nom",
    "endroits": "à combien d'endroits il a été trouvé",
    "trouve_par": "ce qui l'a trouvé",
    "genre_de_chose": "le genre de chose",
    "ville": "la ville",
    "pays": "le pays",
    "site": "avoir un site web",
    "numero_officiel": "avoir un numéro officiel",
    "initiale": "la première lettre du nom",
    "ressemblance": "la ressemblance avec un autre nom",
    "decision": "la décision déjà prise",
    "fonction": "la fonction (siège, établissement, filiale...)",
    "groupe": "le groupe d'entreprises (siège, établissements et filiales ensemble)",
}


class ClassementInvalide(ValueError):
    pass


@dataclass(slots=True)
class Classement:
    id: str
    nom: str
    grouper_par: list[str]
    ordre_paquets: str = "solidite"
    ordre_noms: str = "alphabetique"
    livre: bool = False

    def vue(self) -> dict[str, Any]:
        return {
            "id": self.id, "nom": self.nom, "livre": self.livre, "grouper_par": self.grouper_par,
            "grouper_par_phrase": " puis ".join(FAITS[f] for f in self.grouper_par),
            "ordre_paquets": self.ordre_paquets, "ordre_noms": self.ordre_noms,
        }  # fmt: skip

    def yaml(self) -> str:
        return yaml.safe_dump({"nom": self.nom, "grouper_par": self.grouper_par, "ordre_paquets": self.ordre_paquets, "ordre_noms": self.ordre_noms}, allow_unicode=True, sort_keys=False)


def identifiant_depuis(nom: str) -> str:
    t = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:48] or "classement"


def valider(grouper_par: list[str], ordre_paquets: str, ordre_noms: str, nom: str) -> None:
    if not nom.strip():
        raise ClassementInvalide("Donnez un nom à ce classement.")
    if not grouper_par:
        raise ClassementInvalide("Choisissez au moins une chose pour former les paquets.")
    for f in grouper_par:
        if f not in FAITS:
            raise ClassementInvalide("On ne peut grouper que sur des faits connus ; « " + f + " » n'en est pas un.")
    if ordre_paquets not in ORDRES_PAQUETS:
        raise ClassementInvalide("Cet ordre des paquets n'existe pas.")
    if ordre_noms not in ORDRES_NOMS:
        raise ClassementInvalide("Cet ordre des noms n'existe pas.")


def _lire(chemin: Path, livre: bool) -> Classement:
    try:
        y = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        gp = [str(x) for x in (y.get("grouper_par") or [])]
        valider(gp, str(y.get("ordre_paquets", "solidite")), str(y.get("ordre_noms", "alphabetique")), str(y.get("nom", "")))
    except (OSError, yaml.YAMLError) as exc:
        raise ClassementInvalide(f"{chemin.name} : illisible ({exc})") from exc
    return Classement(chemin.stem, str(y["nom"]), gp, str(y.get("ordre_paquets", "solidite")), str(y.get("ordre_noms", "alphabetique")), livre)


def lister(cfg: Config) -> list[Classement]:
    """Classements livrés puis créés, chacun lu dans son fichier. Un fichier illisible est ignoré (il ne casse pas la page)."""
    out: list[Classement] = []
    for dossier, livre in ((cfg.dossier_classements_livres, True), (cfg.dossier_classements_perso, False)):
        for f in sorted(dossier.glob("*.yaml")) if dossier.is_dir() else []:
            try:
                out.append(_lire(f, livre))
            except ClassementInvalide:
                continue
    return out


def trouver(cfg: Config, ident: str) -> Classement:
    for c in lister(cfg):
        if c.id == ident:
            return c
    raise KeyError(ident)


def creer(cfg: Config, nom: str, grouper_par: list[str], ordre_paquets: str = "solidite", ordre_noms: str = "alphabetique") -> Classement:
    valider(grouper_par, ordre_paquets, ordre_noms, nom)
    existants = {c.id for c in lister(cfg)}
    base = identifiant_depuis(nom)
    ident, n = base, 2
    while ident in existants:  # jamais d'écrasement d'un classement existant
        ident, n = f"{base}-{n}", n + 1
    c = Classement(ident, nom.strip(), list(grouper_par), ordre_paquets, ordre_noms, False)
    d = cfg.dossier_classements_perso
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ident}.yaml").write_text(c.yaml(), encoding="utf-8")
    return c


def dupliquer(cfg: Config, ident: str) -> Classement:
    c = trouver(cfg, ident)
    return creer(cfg, f"{c.nom} (copie)", c.grouper_par, c.ordre_paquets, c.ordre_noms)


def fichier(cfg: Config, ident: str) -> tuple[str, str]:
    """(nom de fichier, contenu) pour l'exporter."""
    c = trouver(cfg, ident)
    return f"{c.id}.yaml", c.yaml()


# ---------------------------------------------------------------------------------------------------------------------
# Les faits d'un nom, tels que les classements les lisent


def normaliser(nom: str) -> str:
    t = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_PETITS_MOTS = frozenset({"de", "du", "des", "la", "le", "les", "et", "d", "l", "au", "aux", "en", "a"})


def ressemblances(noms: dict[int, str], separes: set[int] | None = None) -> dict[int, str]:
    """id -> nom d'un autre candidat qui lui ressemble (sans doute le même, écrit autrement). Prudent, et rapide (plusieurs
    milliers de noms en moins d'une seconde) :
    * un nom (deux mots au moins) qui est le DÉBUT ou la FIN d'un autre (« Fenix Toulouse » / « Fenix Toulouse Handball »),
      petits mots (de, du, la...) mis à part ; des mots dispersés ne suffisent pas (« Paris Handball » n'est pas
      « Paris Saint-Germain Handball ») ;
    * deux noms presque identiques (même début, longueurs voisines, ressemblance >= 0,92).
    Rien n'est fusionné : on SIGNALE."""
    separes = separes or set()
    jetons = {i: tuple(m for m in normaliser(n).split() if m not in _PETITS_MOTS) for i, n in noms.items() if i not in separes}
    par_forme: dict[tuple[str, ...], list[int]] = {}
    for i, t in jetons.items():
        if t:
            par_forme.setdefault(t, []).append(i)
    out: dict[int, str] = {}
    for i, t in jetons.items():
        if len(t) < 3:
            continue
        for k in range(2, len(t)):  # préfixes et suffixes plus courts, d'au moins deux mots
            for sous in (t[:k], t[-k:]):
                for j in par_forme.get(sous, ()):
                    if j != i:
                        out.setdefault(i, noms[j])
                        out.setdefault(j, noms[i])
    # presque identiques : seaux par début, comparaison fine seulement entre voisins de longueur
    seaux: dict[str, list[int]] = {}
    for i, t in jetons.items():
        plat = "".join(t)
        if len(plat) >= 6:
            seaux.setdefault(plat[:4], []).append(i)
    for membres in seaux.values():
        if not 1 < len(membres) <= 120:
            continue
        plats = {i: "".join(jetons[i]) for i in membres}
        for a_i, a in enumerate(membres):
            for b in membres[a_i + 1 :]:
                if plats[a] == plats[b] or abs(len(plats[a]) - len(plats[b])) > 3:
                    continue
                sm = SequenceMatcher(None, plats[a], plats[b])
                if sm.real_quick_ratio() >= 0.92 and sm.quick_ratio() >= 0.92 and sm.ratio() >= 0.92:
                    out.setdefault(a, noms[b])
                    out.setdefault(b, noms[a])
    return out


@dataclass(slots=True)
class Ligne:
    """Un nom avec ses faits, prêt à être groupé."""

    id: int
    nom: str
    origine: str
    endroits: int
    trouve_par: list[str]
    genre_de_chose: str
    ville: str
    pays: str
    site: str
    numero_officiel: str
    decision: str | None
    ressemble_a: str | None = None
    faits: dict[str, Any] = field(default_factory=dict)
    fonction: str = ""
    bloc: str = ""
    racine: str = ""
    rapproche: str = ""
    motif: str = ""  # motif du rejet courant, s'il y en a un


def valeur(fait: str, l: Ligne, nom_source) -> tuple[str, str, Any]:
    """(clé du paquet, phrase du paquet, rang) pour un fait."""
    if fait == "origine":
        return l.origine, ORIGINE_LIBELLE.get(l.origine, l.origine), ORIGINE_RANG.get(l.origine, 9)
    if fait == "endroits":
        return ("plusieurs", "à plusieurs endroits", 0) if l.endroits > 1 else ("un", "à un seul endroit", 1)
    if fait == "trouve_par":
        t = sorted(l.trouve_par, key=lambda x: (x in ("web", "texte", "rss", "wikipedia"), x))
        first = t[0] if t else ""
        return first, nom_source(first) if first else "source non indiquée", first
    if fait == "genre_de_chose":
        return (l.genre_de_chose, l.genre_de_chose, 0) if l.genre_de_chose else ("", "genre non indiqué", 1)
    if fait == "ville":
        return (l.ville, l.ville, 0) if l.ville else ("", "ville non indiquée", 1)
    if fait == "pays":
        return (l.pays, l.pays, 0) if l.pays else ("", "pays non indiqué", 1)
    if fait == "site":
        return ("avec", "ont un site web", 0) if l.site else ("sans", "pas de site trouvé", 1)
    if fait == "numero_officiel":
        return ("avec", "ont un numéro officiel", 0) if l.numero_officiel else ("sans", "pas de numéro officiel", 1)
    if fait == "initiale":
        c = (normaliser(l.nom)[:1] or "#").upper()
        return c, c, c
    if fait == "ressemblance":
        return ("proche", "sans doute le même, écrit différemment", 0) if l.ressemble_a else ("distinct", "noms distincts", 1)
    if fait == "decision":
        return str(l.decision), DECISIONS_LIBELLE[l.decision], DECISIONS_RANG[l.decision]
    if fait == "fonction":
        return (l.fonction, l.fonction, FONCTIONS.index(l.fonction) if l.fonction in FONCTIONS else 8) if l.fonction else ("", "fonction non indiquée", 9)
    if fait == "groupe":
        return (l.bloc, f"groupe de {l.racine}", 0) if l.bloc else ("", "isolés (aucun lien avec un autre nom)", 1)
    raise KeyError(fait)


def grouper(c: Classement, lignes: list[Ligne], nom_source) -> list[dict[str, Any]]:
    """Paquets dans l'ordre du classement. Chaque paquet : clé, phrase, noms (ids) dans l'ordre voulu."""
    paquets: dict[str, dict[str, Any]] = {}
    for l in lignes:
        vs = [valeur(f, l, nom_source) for f in c.grouper_par]
        cle = "|".join(v[0] for v in vs)
        p = paquets.setdefault(cle, {"cle": cle, "phrase": ", ".join(v[1] for v in vs), "rang": tuple(v[2] for v in vs), "lignes": []})
        p["lignes"].append(l)
    out = list(paquets.values())
    if c.ordre_paquets == "solidite":
        out.sort(key=lambda p: (p["rang"], -len(p["lignes"]), p["phrase"]))
    elif c.ordre_paquets == "fragilite":
        out.sort(key=lambda p: (-len(p["lignes"]), p["phrase"]))
        out.sort(key=lambda p: p["rang"], reverse=True)  # tri stable : à rang égal, les plus nombreux d'abord
    elif c.ordre_paquets == "nombre":
        out.sort(key=lambda p: (-len(p["lignes"]), p["phrase"]))
    else:
        out.sort(key=lambda p: normaliser(p["phrase"]))
    for p in out:
        if c.ordre_noms == "alphabetique":
            p["lignes"].sort(key=lambda l: (normaliser(l.nom), l.id))
        elif c.ordre_noms == "endroits":
            p["lignes"].sort(key=lambda l: (-l.endroits, normaliser(l.nom), l.id))
    return out
