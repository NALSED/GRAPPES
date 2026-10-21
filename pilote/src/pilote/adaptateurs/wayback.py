"""Wayback Machine : prouve qu'une adresse a existé (capture la plus proche). Gratuit, sans clé. Ne cherche PAS de noms : on lui donne
l'adresse d'un site (`site`, ou `quoi` si c'est une adresse) et il rend un nom seulement si une capture existe. Sert à la vérification."""

from __future__ import annotations

import re
from typing import Any

from pilote.adaptateurs import Client, ErreurSource

URL = "https://archive.org/wayback/available"
ADRESSE = re.compile(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(/\S*)?$", re.IGNORECASE)


def _date(horodatage: str) -> str:
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})\d{6}", horodatage)
    return f"{m[3]}/{m[2]}/{m[1]}" if m else horodatage


def convertir(rep: dict[str, Any], adresse: str, nom: str) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "archived_snapshots" not in rep:
        raise ErreurSource("La réponse de la Wayback Machine n'a pas la forme attendue.")
    capture = (rep.get("archived_snapshots") or {}).get("closest") or {}
    if not capture.get("available") or str(capture.get("status", "")).startswith(("4", "5")):
        return []
    return [{"nom": nom, "site": adresse, "numero": str(capture.get("url", "")), "origine": f"Wayback Machine (capture du {_date(str(capture.get('timestamp', '')))})"}]


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    quoi = str(entree.get("quoi", "")).strip()
    adresse = str(entree.get("site") or (quoi if ADRESSE.match(quoi) else "")).strip()
    if not adresse:
        return []  # pas d'adresse à vérifier : la Wayback Machine ne cherche pas par nom
    nom = str(entree.get("nom") or quoi or adresse)
    return convertir(client.get_json(URL, {"url": adresse}), adresse, nom)
