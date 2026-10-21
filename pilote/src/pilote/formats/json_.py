"""Format de sortie « JSON » (fiche 14) : pour un autre programme. La trace est dans le fichier (clé `trace`)."""

from __future__ import annotations

import json
from pathlib import Path

FORMAT = {
    "id": "json",
    "nom": "JSON",
    "description": "Pour un autre programme : la trace, puis les noms (ou le détail complet).",
    "extension": ".json",
    "famille": "fichier",
    "contenus": ["nom", "detail"],
    "contenus_defaut": ["detail"],
}


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path) -> dict:
    noms = [r["nom"] for r in jeu["lignes"]] if contenu == "nom" else jeu["lignes"]
    chemin.write_text(json.dumps({"trace": jeu["trace"], "noms": noms}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"fichiers": [chemin]}
