"""data.gouv.fr par son serveur MCP officiel : les organisations qui publient des données (ministères, collectivités, établissements
publics, universités...). Les organisations « service public » portent le badge `public-service`. Première main. Le serveur rend du
TEXTE étiqueté : on n'y lit que des champs (nom, identifiant, badges, adresse), jamais d'instruction."""

from __future__ import annotations

import re
from typing import Any

from pilote.adaptateurs import Client, mots_significatifs

URL_MCP = "https://mcp.data.gouv.fr/mcp"


def _champ(bloc: str, etiquette: str) -> str:
    m = re.search(rf"^\s*{etiquette}:\s*(.*)$", bloc, re.MULTILINE)
    return m.group(1).strip() if m else ""


def lire(texte: str) -> list[dict[str, Any]]:
    out = []
    for bloc in re.split(r"\n\n(?=\d+\. )", texte):
        m = re.match(r"\s*\d+\.\s+(.*)", bloc)
        if m:
            out.append({"nom": m.group(1).strip(), "id": _champ(bloc, "ID"), "badges": [b.strip() for b in _champ(bloc, "Badges").split(",") if b.strip()],
                        "url": _champ(bloc, "URL")})  # fmt: skip
    return out


def convertir(texte: str) -> list[dict[str, Any]]:
    return [
        {"nom": o["nom"], "origine": "data.gouv.fr" + (" (organisation de service public certifiée)" if "public-service" in o["badges"] else ""),
         "numero": "", "site": o["url"], "pays": "FR", "genre": "administration", "_id": o["id"]}
        for o in lire(texte)
    ]  # fmt: skip


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    pays = str(entree.get("pays") or "").upper()
    if pays and pays != "FR":
        return []  # data.gouv.fr ne couvre que la France
    limite = int(entree.get("limite") or 20)
    vus: dict[str, dict[str, Any]] = {}
    for mot in mots_significatifs(" ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])])):
        for e in convertir(client.mcp(str(parametres.get("mcp", URL_MCP)), "search_organizations", {"query": mot, "page_size": min(limite, 20)})):
            if e["_id"] and e["_id"] not in vus:
                vus[e["_id"]] = {k: v for k, v in e.items() if k != "_id"}
        if len(vus) >= limite:
            break
    return list(vus.values())[:limite]
