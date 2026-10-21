"""Format de sortie « GeoJSON » (fiche 14) : les noms qui ont des coordonnées (preset Lieux), en points. S'ouvre dans uMap, QGIS, Google Earth.
Norme RFC 7946 : [longitude, latitude]. Les noms sans coordonnées ne sont pas des points : leur nombre est dit dans la trace. La trace est un membre
« trace » de la collection (les logiciels l'ignorent)."""

from __future__ import annotations

import json
from pathlib import Path

FORMAT = {
    "id": "geojson",
    "nom": "GeoJSON",
    "description": "Les noms avec leurs coordonnées : s'ouvre dans uMap, QGIS, Google Earth et affiche les points sur une carte.",
    "extension": ".geojson",
    "famille": "fichier",
    "contenus": ["detail"],
    "contenus_defaut": ["detail"],
}


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path) -> dict:
    points, sans = [], 0
    for r in jeu["lignes"]:
        c = r.get("coordonnees")
        if not c:
            sans += 1
            continue
        points.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(c["lon"]), float(c["lat"])]},
                       "properties": {"nom": r["nom"], "ville": r["ville"], "pays": r["pays"], "origine": r["origine_phrase"], "site": r["site"], "decision": r["decision"] or ""}})  # fmt: skip
    trace = {**jeu["trace"], "points": len(points), "sans_coordonnees": sans}
    chemin.write_text(json.dumps({"type": "FeatureCollection", "trace": trace, "features": points}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"fichiers": [chemin]}
