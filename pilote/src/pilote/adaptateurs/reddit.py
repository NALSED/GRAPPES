"""Reddit : recherche de communautés (subreddits) par mot-clé. Il faut une clé gratuite (une « application » Reddit, type script ou
web) : identifiant et secret, échangés contre un jeton d'application (OAuth « client_credentials »). Seconde main."""

from __future__ import annotations

import base64
from typing import Any

from pilote.adaptateurs import Client, ErreurSource

TOKEN = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or not isinstance(rep.get("data"), dict):
        raise ErreurSource("La réponse de Reddit n'a pas la forme attendue.")
    out = []
    for c in rep["data"].get("children") or []:
        d = c.get("data") or {}
        nom = str(d.get("title") or d.get("display_name_prefixed") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": "Reddit (communauté)", "site": "https://www.reddit.com" + str(d.get("url") or ""), "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    cles = parametres.get("_cles") or {}
    cid, secret = str(cles.get("REDDIT_CLIENT_ID", "")).strip(), str(cles.get("REDDIT_CLIENT_SECRET", "")).strip()
    if not cid or not secret:
        raise ErreurSource("Les clés de Reddit (identifiant et secret de l'application) sont absentes : la source reste éteinte sans elles.")
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or []), str(entree.get("lieu", "")).strip()]).strip()
    if not mots:
        return []
    base = str(parametres.get("api", API)).rstrip("/")
    jeton_url = str(parametres.get("jeton", TOKEN))
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    tok = client.post_texte(jeton_url, "grant_type=client_credentials", headers={"Authorization": f"Basic {auth}"})
    acces = str((tok or {}).get("access_token", ""))
    if not acces:
        raise ErreurSource("Reddit a refusé les clés (aucun jeton rendu).")
    rep = client.get_json(f"{base}/subreddits/search", {"q": mots, "limit": min(int(entree.get("limite") or 25), 100), "raw_json": 1}, headers={"Authorization": f"Bearer {acces}"})
    return convertir(rep)[: int(entree.get("limite") or 25)]
