"""Bluesky : comptes trouvés par mot-clé, par la recherche publique (sans clé). Seconde main."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource

URL = "https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors"


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "actors" not in rep:
        raise ErreurSource("La réponse de Bluesky n'a pas la forme attendue.")
    out = []
    for a in rep.get("actors") or []:
        nom = str(a.get("displayName") or a.get("handle") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": "Bluesky (compte public)", "site": "https://bsky.app/profile/" + str(a.get("handle", "")), "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or []), str(entree.get("lieu", "")).strip()]).strip()
    if not mots:
        return []
    n = min(int(entree.get("limite") or 25), 100)
    return convertir(client.get_json(str(parametres.get("api", URL)), {"q": mots, "limit": n}))[:n]
