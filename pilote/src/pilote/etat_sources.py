"""Dernier état connu de chaque source (fiche 01, règle 2) : écrit par un test ou par une recherche, JAMAIS en ouvrant la page.
La page affiche ce qui est connu avec sa date ; elle ne rafraîchit rien toute seule."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pilote.config import Config
from pilote.refus import ecrire_atomique, verrou


def maintenant_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def lire(cfg: Config) -> dict[str, dict[str, Any]]:
    try:
        d = json.loads(cfg.fichier_etat_sources.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def noter(cfg: Config, source_id: str, **champs: Any) -> None:
    """Fusionne des champs dans l'état d'une source (statut, raison, quota, dernier_appel, erreur...)."""
    with verrou(cfg.fichier_etat_sources):  # deux recherches en même temps : sans verrou, un compteur d'erreurs était perdu
        tout = lire(cfg)
        tout[source_id] = {**tout.get(source_id, {}), **champs}
        ecrire_atomique(cfg.fichier_etat_sources, json.dumps(tout, ensure_ascii=False, indent=1))
