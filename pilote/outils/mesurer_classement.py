"""Mesure de l'ORDRE des résultats : R-précision, bpref (`pytrec_eval`, via `grappes.autocal.metriques`) et, à côté, la probabilité qu'un résultat juste soit placé
avant un résultat faux (AUC, sur les seuls résultats jugés).

Pourquoi deux familles : la R-précision plafonne avec le RAPPEL des candidats (au test du 12/10, 11 acteurs de la référence sur 356 sont dans les candidats : le
plafond est d'environ 0,03 quel que soit l'ordre). Elle ne dit donc pas si l'ordre vaut quelque chose. L'AUC, elle, ne regarde que l'ordre entre un juste et un faux.

Entrées (deux formes, mêmes mesures) :
  --rejeu <fichier>   un rejeu de l'autocalibrage de grappes (`donnees/autocal/*_rejeu1.json`) : LECTURE SEULE, le jeu test n'est pas rouvert, rien n'y est écrit. Rprec et bpref
                      sont ceux du fichier (calculés par entité) ; l'AUC est calculée ici sur les candidats rendus (`rang`, 200 au plus), où deux candidats peuvent désigner la
                      même entité : à lire comme un ordre de grandeur, pas comme une mesure exacte ;
  --cas <fichier>     un jeu français rejouable (`autocal_classement_fr/cas.jsonl`), une ligne par sujet :
                      {"id", "phrase", "attendus": <nombre d'entités attendues>, "rendus": [{"nom", "verdict": "juste"|"faux"|"non_verifiable"}, ...]}  (dans l'ordre rendu)

À lancer avec l'interpréteur de grappes (il porte `pytrec_eval`) :
  /opt/grappes/.venv/bin/python outils/mesurer_classement.py --rejeu /opt/grappes/donnees/autocal/test_rejeu1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE.parent / "grappes" / "src") not in sys.path and (Path("/opt/grappes/src")).exists():
    sys.path.insert(0, "/opt/grappes/src")


def auc(rendus: list[dict]) -> tuple[float | None, int, int]:
    """(probabilité qu'un juste soit rendu avant un faux, nombre de justes, nombre de faux). Les non vérifiables sont écartés : on ne sait pas ce qu'ils valent."""
    rang = {i: r for i, r in enumerate(rendus)}
    justes = [i for i, r in rang.items() if r["verdict"] == "juste"]
    faux = [i for i, r in rang.items() if r["verdict"] == "faux"]
    if not justes or not faux:
        return None, len(justes), len(faux)
    gagnees = sum(1 for j in justes for f in faux if j < f)  # rang plus petit = rendu avant
    return gagnees / (len(justes) * len(faux)), len(justes), len(faux)


def qrels_et_run(sujet: str, attendus: int, rendus: list[dict]) -> tuple[dict, dict]:
    """Un attendu retrouvé est pertinent (1) ; un faux est jugé non pertinent (0) ; un non vérifiable n'est pas jugé ; les attendus jamais retrouvés comptent dans R."""
    qrels: dict[str, int] = {}
    run: dict[str, float] = {}
    n = len(rendus)
    for i, r in enumerate(rendus):
        doc = f"d{i:05d}"
        run[doc] = float(n - i)  # le rang rendu devient un score décroissant
        if r["verdict"] == "juste":
            qrels[doc] = 1
        elif r["verdict"] == "faux":
            qrels[doc] = 0
    retrouves = sum(1 for r in rendus if r["verdict"] == "juste")
    for k in range(max(0, attendus - retrouves)):
        qrels[f"manquant{k:04d}"] = 1
    return {sujet: qrels}, {sujet: run}


def mesurer(sujets: list[dict]) -> list[dict]:
    from grappes.autocal.metriques import evaluer

    out = []
    for s in sujets:
        rendus = s["rendus"]
        a, nj, nf = auc(rendus)
        ligne = {"id": s["id"], "phrase": s.get("phrase", ""), "R": s["attendus"], "rendus": len(rendus), "justes": nj, "faux": nf,
                 "non_verifiables": sum(r["verdict"] == "non_verifiable" for r in rendus), "auc": a, "Rprec": None, "bpref": None}  # fmt: skip
        if s.get("officiel"):  # rejeu de l'autocalibrage : ses mesures sont déjà calculées par entité (qrels officiels), on les reprend telles quelles
            ligne.update(Rprec=s["officiel"]["Rprec"], bpref=s["officiel"]["bpref"])
        elif s["attendus"] > 0:
            qrels, run = qrels_et_run(s["id"], s["attendus"], rendus)
            m = evaluer(qrels, run)[s["id"]]
            ligne.update(Rprec=m["Rprec"], bpref=m["bpref"])
        out.append(ligne)
    return out


def depuis_rejeu(chemin: Path) -> list[dict]:
    d = json.loads(chemin.read_text(encoding="utf-8"))
    return [{"id": s["id"], "phrase": s.get("phrase", ""), "attendus": s["R"], "officiel": {"Rprec": s["Rprec"], "bpref": s["bpref"]},
             "rendus": [{"nom": r["nom"], "verdict": r["verdict"]} for r in s["rang"]]} for s in d["sujets"] if s.get("rang")]  # fmt: skip


def depuis_cas(chemin: Path) -> list[dict]:
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()]


def moyennes(res: list[dict]) -> dict:
    """Moyenne simple par sujet (comme l'autocalibrage) et AUC pondérée par le nombre de paires juste/faux (un sujet sans juste n'apporte aucune paire)."""
    def moy(k):
        v = [r[k] for r in res if r[k] is not None]
        return sum(v) / len(v) if v else None

    paires = [(r["auc"] * r["justes"] * r["faux"], r["justes"] * r["faux"]) for r in res if r["auc"] is not None]
    n = sum(p for _, p in paires)
    nj, nf = sum(r["justes"] for r in res), sum(r["faux"] for r in res)
    a = sum(g for g, _ in paires) / n if n else None
    return {"Rprec": moy("Rprec"), "bpref": moy("bpref"), "auc": a, "paires": n, "justes": nj, "faux": nf, "marge": _marge(a, nj, nf)}


def _marge(a: float | None, nj: int, nf: int) -> float | None:
    """Demi-largeur approchée d'un intervalle à 95 % de l'AUC (Hanley et McNeil, 1982), en comptant justes et faux comme un seul échantillon : un ordre de grandeur, pas une garantie.
    Avec peu de justes elle est grande, et c'est ce qu'elle doit dire."""
    if a is None or nj < 2 or nf < 2:
        return None
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return 1.96 * (((a * (1 - a)) + (nj - 1) * (q1 - a * a) + (nf - 1) * (q2 - a * a)) / (nj * nf)) ** 0.5


def tableau(res: list[dict]) -> str:
    def f(v, largeur=6):
        return f"{v:{largeur}.3f}" if v is not None else "     -"

    lignes = ["sujet                           R  rendus  justes  faux  non vérif.   Rprec   bpref    AUC"]
    for r in res:
        lignes.append(f"{r['id'][:28]:28} {r['R']:5d}  {r['rendus']:6d}  {r['justes']:6d}  {r['faux']:4d}  {r['non_verifiables']:10d}  {f(r['Rprec'])}  {f(r['bpref'])}  {f(r['auc'])}")
    m = moyennes(res)
    marge = f", ±{m['marge']:.2f} environ" if m["marge"] is not None else ""
    lignes.append(f"{'MOYENNE (par sujet)':28} {'':5}  {'':6}  {m['justes']:6d}  {m['faux']:4d}  {'':10}  {f(m['Rprec'])}  {f(m['bpref'])}  {f(m['auc'])}  (AUC sur {m['paires']} paires juste/faux{marge})")
    return "\n".join(lignes)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--rejeu", type=Path, action="append", default=[])
    p.add_argument("--cas", type=Path, action="append", default=[])
    a = p.parse_args()
    if not a.rejeu and not a.cas:
        p.error("donnez au moins --rejeu ou --cas")
    for f in a.rejeu:
        print(f"== {f.name}\n{tableau(mesurer(depuis_rejeu(f)))}\n")
    for f in a.cas:
        print(f"== {f}\n{tableau(mesurer(depuis_cas(f)))}\n")
