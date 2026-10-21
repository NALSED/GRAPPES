"""Formats de sortie (fiche 14) : AUCUNE liste figée dans le cœur. Chaque format est un petit module de ce dossier (ou du dossier
`formats_perso` de la configuration) qui se déclare lui-même avec un dictionnaire `FORMAT` ; ajouter un format = ajouter un fichier."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from pilote.config import Config

CHAMPS = {"id", "nom", "description", "extension", "famille", "contenus", "contenus_defaut", "besoin"}


def _declaration(m: ModuleType) -> dict[str, Any] | None:
    f = getattr(m, "FORMAT", None)
    if not isinstance(f, dict) or not CHAMPS >= set(f) or not {"id", "nom", "description"} <= set(f):
        return None
    d = {"contenus": ["nom", "detail"], "besoin": [], "famille": "fichier", "extension": "", **f, "module": m}
    d.setdefault("contenus_defaut", d["contenus"][:1])
    if not callable(getattr(m, "ecrire", None)) or not d["contenus"] or not set(d["contenus_defaut"]) <= set(d["contenus"]):
        return None  # un format qui ne sait pas écrire n'est pas un format
    return d


def decouvrir(cfg: Config | None = None) -> dict[str, dict[str, Any]]:
    """Tous les formats disponibles : ceux du dossier `formats` du programme, puis ceux de l'utilisateur."""
    out: dict[str, dict[str, Any]] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):  # type: ignore[name-defined]
        if info.name.startswith("_"):
            continue
        d = _declaration(importlib.import_module(f"{__name__}.{info.name}"))
        if d:
            out[d["id"]] = d
    dossier = getattr(cfg, "dossier_formats_perso", None) if cfg else None
    for f in sorted(Path(dossier).glob("*.py")) if dossier and Path(dossier).is_dir() else []:
        if f.name.startswith("_"):
            continue
        nom = f"pilote_format_perso_{f.stem}"
        spec = importlib.util.spec_from_file_location(nom, f)
        if spec is None or spec.loader is None:
            continue
        try:
            m = importlib.util.module_from_spec(spec)
            sys.modules[nom] = m
            spec.loader.exec_module(m)
        except Exception:  # noqa: BLE001 - un format cassé est ignoré, il n'arrête pas les autres
            sys.modules.pop(nom, None)
            continue
        d = _declaration(m)
        if d:
            out[d["id"]] = {**d, "perso": True}
    return out


def vue(cfg: Config | None = None) -> list[dict[str, Any]]:
    return [{k: v for k, v in d.items() if k != "module"} for d in decouvrir(cfg).values()]
