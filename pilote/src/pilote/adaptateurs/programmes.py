"""Programmes locaux (fiches 10 et 11) : n'importe quel programme (Python, JS, shell...) qui respecte la convention d'entrée et de
sortie. Il tourne dans un PROCESSUS SÉPARÉ avec une limite de temps ; il est tué au dépassement. Entrée : un JSON sur l'entrée standard.
Sortie : un JSON sur la sortie standard — une liste de noms, ou {"noms": [...]}, chaque nom ayant au minimum « nom » et « origine »."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from pilote.adaptateurs import ErreurSource

DELAI_DEFAUT_S = 10.0
DELAI_MAX_S = 120.0


def lire_sortie(texte: str) -> list[dict[str, Any]]:
    try:
        v = json.loads(texte)
    except ValueError as exc:
        raise ErreurSource("La sortie du programme n'est pas du JSON lisible.") from exc
    if isinstance(v, dict) and isinstance(v.get("noms"), list):
        v = v["noms"]
    if not isinstance(v, list) or not v:
        raise ErreurSource("Le programme doit rendre une liste de noms (au moins un).")
    for x in v:
        if not isinstance(x, dict) or not str(x.get("nom", "")).strip() or not str(x.get("origine", "")).strip():
            raise ErreurSource("Chaque nom rendu par le programme doit avoir au minimum un « nom » et une « origine ».")
    return v


def executer(script: dict[str, Any], entree: dict[str, Any], cwd: Path | None = None, delai_s: float | None = None) -> list[dict[str, Any]]:
    commande = [str(c) for c in script.get("commande") or []]
    if not commande:
        raise ErreurSource("Le programme local doit indiquer sa commande.")
    delai = min(float(delai_s or script.get("delai_s", DELAI_DEFAUT_S)), DELAI_MAX_S)
    try:
        r = subprocess.run(commande, input=json.dumps(entree, ensure_ascii=False), capture_output=True, text=True, timeout=delai, cwd=cwd, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ErreurSource(f"Le programme a dépassé sa limite de temps ({delai:g} s) et a été arrêté.") from exc
    except OSError as exc:
        raise ErreurSource("Le programme ne peut pas être lancé (commande introuvable).") from exc
    if r.returncode != 0:
        raise ErreurSource(f"Le programme s'est terminé en erreur (code {r.returncode}).")
    return lire_sortie(r.stdout)
