"""Mastodon : comptes trouvés par mot-clé sur une instance (paramètre `instance`, par défaut mastodon.social), sans clé. Seconde main."""

from __future__ import annotations

import re
from typing import Any

from pilote.adaptateurs import Client, ErreurSource

INSTANCE = "https://mastodon.social"
BALISES = re.compile(r"<[^>]+>")


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "accounts" not in rep:
        raise ErreurSource("La réponse de Mastodon n'a pas la forme attendue.")
    out = []
    for a in rep.get("accounts") or []:
        nom = BALISES.sub("", str(a.get("display_name") or a.get("username") or "")).strip()
        if nom:
            out.append({"nom": nom, "origine": "Mastodon (compte public)", "site": str(a.get("url") or ""), "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or []), str(entree.get("lieu", "")).strip()]).strip()
    if not mots:
        return []
    n = min(int(entree.get("limite") or 25), 40)
    base = str(parametres.get("instance", INSTANCE)).rstrip("/")
    return convertir(client.get_json(f"{base}/api/v2/search", {"q": mots, "type": "accounts", "limit": n}))[:n]
