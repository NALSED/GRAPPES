"""Format de sortie « CSV » (fiche 14) : le format de base. Trois contenus : `nom` (une colonne NOM), `tsites` (nom;ville;pays : ce que lit trouver-sites,
sans autre colonne ni commentaire) et `detail` (tout ce que la page Tri sait du nom). Un fichier CSV ne peut pas porter de commentaire sans gêner l'outil qui
le lit : sa trace est dans un fichier voisin `<nom>.trace.json`."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pilote.formats._commun import COLONNES_DETAIL, cellule, ligne_detail

FORMAT = {
    "id": "csv",
    "nom": "CSV",
    "description": "Le format de base. « nom;ville;pays » alimente trouver-sites ; le détail complet est pour vous.",
    "extension": ".csv",
    "famille": "fichier",
    "contenus": ["nom", "tsites", "detail"],
    "contenus_defaut": ["nom", "tsites"],
}


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path) -> dict:
    lignes = jeu["lignes"]
    with chemin.open("w", encoding="utf-8", newline="") as f:
        if contenu == "nom":
            w = csv.writer(f, delimiter=",", lineterminator="\n")
            w.writerow(["NOM"])
            w.writerows([cellule(r["nom"])] for r in lignes)
        elif contenu == "tsites":
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(["nom", "ville", "pays"])
            w.writerows([cellule(r["nom"]), cellule(r["ville"]), cellule(r["pays"])] for r in lignes)
        else:
            w = csv.writer(f, delimiter=";", lineterminator="\n")
            w.writerow(COLONNES_DETAIL)
            w.writerows([cellule(c) for c in ligne_detail(r)] for r in lignes)
    trace = chemin.with_name(chemin.name + ".trace.json")
    trace.write_text(json.dumps(jeu["trace"], ensure_ascii=False, indent=1), encoding="utf-8")
    return {"fichiers": [chemin, trace]}
