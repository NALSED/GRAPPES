"""Mentions obligatoires des sources (licences) : certaines sources n'autorisent l'usage libre qu'à condition de les citer (GDELT : « GDELT Project »
avec un lien vers gdeltproject.org). La mention vient de la DÉCLARATION de la source (`attribution`), jamais écrite en dur ici : toute source qui en
déclare une est citée dans les sorties de la recherche qui s'en est servie."""

from __future__ import annotations

import json
from pathlib import Path

from pilote.config import Config
from pilote.sources import charger_sources

FICHIER = "SOURCES.txt"


def mentions(cfg: Config, ids: list[str]) -> list[dict[str, str]]:
    decls, _ = charger_sources(cfg)
    return [{"source": d.id, "nom": d.nom, **d.attribution} for i in ids if (d := decls.get(i)) and d.attribution]


def sources_de_la_recherche(dossier_recherche: Path) -> list[str]:
    f = dossier_recherche / "lancement.json"
    if not f.exists():
        return []
    try:
        return [str(s) for s in json.loads(f.read_text(encoding="utf-8")).get("sources", [])]
    except ValueError:
        return []


def ecrire(cfg: Config, dossier_recherche: Path, dossier_sortie: Path) -> Path | None:
    """Écrit `SOURCES.txt` à côté des sorties si au moins une source utilisée impose une mention. Sinon rien."""
    m = mentions(cfg, sources_de_la_recherche(dossier_recherche))
    if not m:
        return None
    lignes = ["Sources utilisées dans cette recherche qui demandent d'être citées :", ""] + [f"- {x['texte']} — {x['url']}" for x in m] + [""]
    f = dossier_sortie / FICHIER
    f.write_text("\n".join(lignes), encoding="utf-8")
    return f
