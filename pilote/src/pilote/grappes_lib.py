"""Accès à grappes comme BIBLIOTHÈQUE (D70) : la racine vient de la configuration, rien n'est écrit en dur."""

from __future__ import annotations

import sys

from pilote.config import Config


def brancher(cfg: Config) -> None:
    """Rend `import grappes` possible : ajoute `<racine de grappes>/src` au chemin d'import (une seule fois)."""
    src = str(cfg.grappes_racine / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
