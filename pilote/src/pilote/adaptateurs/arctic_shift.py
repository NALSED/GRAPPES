"""Arctic Shift : archive communautaire de Reddit (non officielle), sans clé. Recherche de communautés par PRÉFIXE de nom, mot significatif
par mot significatif, comme alternative à l'application Reddit (accès durci). Seconde main. Les communautés pour adultes sont écartées."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs, singulier

URL = "https://arctic-shift.photon-reddit.com/api/subreddits/search"


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or not isinstance(rep.get("data"), list):
        raise ErreurSource("La réponse d'Arctic Shift n'a pas la forme attendue.")
    out = []
    for d in rep["data"]:
        if not isinstance(d, dict) or d.get("over18"):
            continue
        nom = str(d.get("title") or d.get("display_name") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": "Arctic Shift (archive de communautés Reddit)", "site": "https://www.reddit.com" + str(d.get("url") or ""), "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    mots = mots_significatifs(singulier(" ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])])).lower(), 3)
    limite = int(entree.get("limite") or 25)
    vus: dict[str, dict[str, Any]] = {}
    for mot in mots:
        for e in convertir(client.get_json(URL, {"subreddit_prefix": mot.replace(" ", ""), "limit": min(limite, 100)})):
            vus.setdefault(e["site"], e)
        if len(vus) >= limite:
            break
    return list(vus.values())[:limite]
