"""Télécharge (reprise possible) puis verse en base locale la copie d'une source « fichier_local » (document 22).

    .venv/bin/python outils/importer_base_locale.py <id-de-la-source> [--garder] [--sans-telecharger]

La déclaration de la source (`config/sources/<id>.yaml`) porte, dans `moteur.parametres.installation`, les adresses à télécharger et la façon de
lire le fichier. Une base absente n'est jamais devinée : sans accord enregistré (`accord`), rien n'est téléchargé. Les zips sont supprimés après
un import réussi (on garde la base, pas l'archive), sauf `--garder`."""

from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pilote import fichier_local as fl
from pilote.config import charger

UA = "pilote/0.1 (copie locale ; usage personnel)"
MARGE_INCONNUE_GO = 10  # place exigée quand le serveur n'annonce aucune taille (extrait SPARQL, HEAD refusée) : on ne part pas en supposant zéro


SIGNATURES = {".zip": b"PK\x03\x04", ".gz": b"\x1f\x8b", ".bz2": b"BZh"}


def verifier_contenu(fichier: Path) -> None:
    """Une archive doit commencer par sa signature. Un serveur qui répond une page d'erreur avec le code 200 (quota, maintenance,
    adresse périmée) écrivait sinon du HTML sous le nom du zip, et l'import échouait beaucoup plus loin, sur une autre erreur."""
    attendue = SIGNATURES.get(fichier.suffix.lower())
    if not attendue:
        return
    with open(fichier, "rb") as f:
        debut = f.read(len(attendue))
    if debut != attendue:
        apercu = debut.decode("utf-8", "replace")
        fichier.unlink(missing_ok=True)
        raise SystemExit(f"{fichier.name} n'est pas une archive {fichier.suffix} (reçu « {apercu} »…) : adresse périmée, quota, ou page d'erreur du serveur.")


def telecharger(url: str, dest: Path, attendu: int | None = None) -> None:
    """Téléchargement avec reprise (en-tête Range) : une coupure ne repart pas de zéro."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partiel = dest.with_suffix(dest.suffix + ".partiel")
    for tentative in range(8):
        deja = partiel.stat().st_size if partiel.exists() else 0
        req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": f"bytes={deja}-"} if deja else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if deja and r.status != 206:  # le serveur ne reprend pas : on recommence proprement
                    deja = 0
                    partiel.unlink(missing_ok=True)
                with open(partiel, "ab" if deja else "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
            break
        except OSError as exc:
            print(f"  coupure ({exc}) — reprise {tentative + 1}/8", flush=True)
            time.sleep(5)
    else:
        raise SystemExit(f"Le téléchargement de {url} n'a pas abouti.")
    if attendu and partiel.stat().st_size != attendu:
        raise SystemExit(f"Taille reçue {partiel.stat().st_size} ≠ taille annoncée {attendu} : {url}")
    partiel.replace(dest)
    verifier_contenu(dest)  # taille inconnue (le serveur n'annonce rien) : au moins, ce n'est pas une page d'erreur


def extraire_sparql(sp: dict, dest: Path) -> None:
    """Extrait paginé d'un point d'accès SPARQL (QLever pour Wikidata : le dump complet fait 1,4 To, on ne prend que le filtre voulu, par CLASSE, jamais des
    personnes physiques). La requête contient `{decalage}` ; on avance par pages jusqu'à une page incomplète. Le CSV n'apparaît qu'entier."""
    import csv
    import io

    dest.parent.mkdir(parents=True, exist_ok=True)
    page, decalage, entetes = int(sp.get("page", 50000)), 0, None
    partiel = dest.with_suffix(dest.suffix + ".partiel")
    with open(partiel, "w", encoding="utf-8", newline="") as sortie:
        w = csv.writer(sortie)
        while True:
            corps = urllib.parse.urlencode({"query": sp["requete"].replace("{decalage}", str(decalage))}).encode()
            req = urllib.request.Request(sp["url"], data=corps, headers={"User-Agent": UA, "Accept": "text/csv"})
            for tentative in range(5):
                try:
                    with urllib.request.urlopen(req, timeout=170) as r:
                        lignes = list(csv.reader(io.StringIO(r.read().decode("utf-8"))))
                    break
                except OSError as exc:
                    print(f"  requête {decalage}: {exc} — nouvel essai", flush=True)
                    time.sleep(10)
            else:
                raise SystemExit("Le point d'accès SPARQL ne répond pas.")
            if not lignes:
                break
            if entetes is None:
                entetes = lignes[0]
                w.writerow(entetes)
            w.writerows(lignes[1:])
            print(f"  SPARQL : {decalage + len(lignes) - 1:,} lignes".replace(",", " "), flush=True)
            if len(lignes) - 1 < page:
                break
            decalage += page
    partiel.replace(dest)


def taille_distante(url: str) -> int | None:
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA}), timeout=30) as r:
                if r.headers.get("Content-Length"):
                    return int(r.headers["Content-Length"])
        except OSError:
            time.sleep(2)
    return None


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    ident, garder, sans = argv[0], "--garder" in argv, "--sans-telecharger" in argv
    cfg = charger()
    decl = yaml.safe_load((cfg.dossier_config / "sources" / f"{ident}.yaml").read_text(encoding="utf-8"))
    params = decl["moteur"]["parametres"]
    base, inst = params["base"], params["installation"]
    if not inst.get("accord"):
        raise SystemExit("Aucun accord enregistré (« installation.accord ») : rien n'est téléchargé.")
    dossier_dl = cfg.dossier_copies / "telechargements" / base
    fichiers: dict[str, Path] = {}
    total = 0
    cibles = []
    for d in inst["telechargements"]:
        taille = 0 if d.get("sparql") else (taille_distante(d["url"]) or 0)
        total += taille
        cibles.append((d, taille))
    libre = shutil.disk_usage(cfg.dossier_copies).free
    # Tailles inconnues : un serveur qui n'annonce pas `Content-Length` (ou qui refuse la requête HEAD) donnait 0, et le contrôle de place
    # ci-dessous passait toujours — il ne protégeait rien justement dans le cas où l'on ignore ce qu'on va recevoir. On exige alors une marge
    # fixe, et `MARGE_INCONNUE_GO` dit laquelle plutôt que de faire comme si la taille était nulle.
    inconnues = [d["fichier"] for d, t in cibles if not t and not d.get("sparql")]
    annonce = f"{total / 1e9:.2f} Go à télécharger" if total else "taille non annoncée par le serveur"
    print(f"{base} : {annonce}, {libre / 1e9:.1f} Go libres" + (f" ; taille inconnue pour {', '.join(inconnues)}" if inconnues else ""))
    besoin = total * 3 if total else 0
    if inconnues or any(d.get("sparql") for d, _ in cibles):
        besoin = max(besoin, MARGE_INCONNUE_GO * 1_000_000_000)
    if besoin > libre:
        raise SystemExit(f"Pas assez de place : il faut environ {besoin / 1e9:.0f} Go libres (téléchargement + base indexée), il en reste {libre / 1e9:.1f}. Rien n'est téléchargé.")
    for d, taille in cibles:
        dest = dossier_dl / d["fichier"]
        fichiers[d["fichier"]] = dest
        if sans or dest.exists():
            print(f"  {d['fichier']} : déjà là")
            continue
        if d.get("sparql"):
            print(f"  extraction SPARQL {d['fichier']}…", flush=True)
            extraire_sparql(d["sparql"], dest)
            continue
        print(f"  téléchargement {d['fichier']} ({taille / 1e6:.0f} Mo)…", flush=True)
        telecharger(d["url"], dest, taille or None)
    spec = json.loads(json.dumps(inst["import"]))
    for j in spec.get("jointures") or []:
        j["fichier"] = str(fichiers[j["fichier"]])
    principaux = [fichiers[n] for n in inst["import"].get("fichiers", [d["fichier"] for d, _ in cibles[:1]])]
    print(f"  import de {', '.join(p.name for p in principaux)}…", flush=True)
    bilan = fl.importer(principaux, base, cfg.dossier_copies, spec, progres=lambda n: print(f"    {n:,} lignes".replace(",", " "), flush=True) if n % 1_000_000 < 20_000 else None)
    print(f"  fait : {bilan['lignes']:,} lignes, {bilan['ecartees']:,} écartées, {bilan['octets'] / 1e9:.2f} Go, {bilan['secondes']} s".replace(",", " "))
    registre = cfg.donnees / "bases_locales.json"
    liste = json.loads(registre.read_text(encoding="utf-8")) if registre.exists() else []
    liste = [x for x in liste if x["base"] != base] + [{"base": base, "source": ident, "date": time.strftime("%Y-%m-%d"), "accord": inst["accord"], **bilan}]
    registre.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")
    if not garder:
        shutil.rmtree(dossier_dl, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
