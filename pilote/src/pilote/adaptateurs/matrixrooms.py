"""MatrixRooms.info : annuaire des salons Matrix publics. Sa recherche rend du texte markdown (`/md/search/<terme>`) : un titre et un lien par salon, son alias `#salon:serveur`, le nombre
de membres, une description. robots.txt autorise les robots (`Allow: /`, relevé le 27/10/2026). Sans clé. Un salon est une communauté, jamais un compte nommé (règle 8). Seconde main."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs

URL = "https://matrixrooms.info/md/search/"
SALON = re.compile(r"^## \[(?P<titre>.+?)\]\(<(?P<lien>https://matrixrooms\.info/room/[^>\s]+)>\)(?: \((?P<membres>\d+) members?\))?\s*$", re.MULTILINE)
ECHAPPEMENT = re.compile(r"\\(.)")


def _propre(t: str) -> str:
    return ECHAPPEMENT.sub(r"\1", t).strip()


def convertir(texte: str) -> list[dict[str, Any]]:
    if not isinstance(texte, str) or "Search results" not in texte[:200]:
        raise ErreurSource("La réponse de MatrixRooms.info n'a pas la forme attendue.")
    out = []
    for m in SALON.finditer(texte):
        titre = _propre(m["titre"])
        if titre:
            out.append({"nom": titre, "origine": "MatrixRooms.info (salon Matrix public" + (f", {m['membres']} membres" if m["membres"] else "") + ")", "site": m["lien"], "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    mots = mots_significatifs(" ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])]), 3)
    if not mots:
        return []
    limite = int(entree.get("limite") or 25)
    vus: dict[str, dict[str, Any]] = {}
    for mot in mots:
        for e in convertir(client.get_texte(URL + urllib.parse.quote(mot, safe=""), None, {"Accept": "text/markdown"})):
            vus.setdefault(e["site"], e)
        if len(vus) >= limite:
            break
    return list(vus.values())[:limite]
