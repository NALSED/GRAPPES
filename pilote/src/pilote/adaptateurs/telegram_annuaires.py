"""Telegram par annuaires : les canaux et groupes publics qui ont une page publique (t.me, annuaires de canaux), trouvés par un
méta-moteur de recherche (SearXNG, auto-hébergé) avec `site:`. Aucune clé, aucun compte Telegram. Seconde main : on lit le titre
d'une page d'annuaire, pas le registre de Telegram. Les canaux privés ne sont pas visibles."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from pilote.adaptateurs import Client, ErreurSource

URL = "http://127.0.0.1:8888/search"
DOMAINES = ("t.me",)
SUFFIXES = re.compile(r"\s*[–—|-]\s*Telegram.*$|\s*:\s*Telegram.*$|^Telegram\s*[:–—-]\s*|\s*[–—-]\s*Contact @\S+$", re.IGNORECASE)


def _nom(titre: str) -> str:
    t = SUFFIXES.sub("", titre.strip()).strip()
    t = re.sub(r"^(Join group chat|Join channel|Rejoindre)\s*[:–—-]?\s*", "", t, flags=re.IGNORECASE).strip()
    return re.sub(r"^(View|Voir|Contact)\s+(@\S+)$", r"\2", t, flags=re.IGNORECASE)  # « View @canal » : la page n'a pas de titre, le nom du canal en tient lieu


def _canal(chemin: str) -> str:
    """Nom du canal dans le chemin d'une page t.me (« /canal », « /s/canal?before=12 » : l'aperçu web du canal)."""
    morceaux = [m for m in chemin.strip("/").split("/") if m]
    if morceaux and morceaux[0] == "s":
        morceaux = morceaux[1:]
    return morceaux[0] if morceaux else ""


def convertir(rep: Any) -> list[dict[str, Any]]:
    """Réponse JSON de SearXNG -> comptes Telegram (un titre propre et l'adresse publique)."""
    if not isinstance(rep, dict) or "results" not in rep:
        raise ErreurSource("La réponse du moteur n'a pas la forme attendue.")
    out, vus = [], set()
    for r in rep.get("results") or []:
        url = str(r.get("url") or "")
        h = urlsplit(url)
        canal = _canal(h.path)
        if not h.netloc or not canal:
            continue
        nom = _nom(str(r.get("title") or ""))
        if not nom or canal.lower() in vus:
            continue
        vus.add(canal.lower())
        out.append({"nom": nom, "origine": "annuaire Telegram (page publique du canal ou du groupe)", "site": f"https://{h.netloc}/{canal}", "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or []), str(entree.get("lieu", "")).strip()]).strip()
    if not mots:
        return []
    out: list[dict[str, Any]] = []
    vus: set[str] = set()
    for dom in parametres.get("domaines") or DOMAINES:
        rep = client.get_json(str(parametres.get("moteur", URL)), {"q": f"site:{dom} {mots}", "format": "json"})
        for e in convertir(rep):
            if e["site"] not in vus:
                vus.add(e["site"])
                out.append(e)
    return out[: int(entree.get("limite") or 25)]
