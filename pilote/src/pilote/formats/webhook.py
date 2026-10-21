"""Format de sortie « Webhook » (fiche 14) : le programme envoie le résultat (JSON, avec sa trace) à une adresse donnée par l'utilisateur. Une seule
fonction, et grappes se branche sur n8n, un script ou un autre serveur. Aucun fichier n'est écrit."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FORMAT = {
    "id": "webhook",
    "nom": "Webhook",
    "description": "Envoie le résultat à une adresse donnée (n8n, un script, un autre serveur).",
    "extension": "",
    "famille": "outil",
    "contenus": ["nom", "detail"],
    "contenus_defaut": ["detail"],
    "besoin": ["url"],
}


class EnvoiRefuse(Exception):
    pass


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path | None = None) -> dict:
    url = str(options.get("url", "")).strip()
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise EnvoiRefuse("L'adresse du webhook doit commencer par http:// ou https://.")
    noms = [r["nom"] for r in jeu["lignes"]] if contenu == "nom" else jeu["lignes"]
    corps = json.dumps({"trace": jeu["trace"], "noms": noms}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=corps, method="POST", headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "pilote/0.1 (sortie webhook)"})
    try:
        with urllib.request.urlopen(req, timeout=float(options.get("delai_s", 15))) as r:
            statut = r.status
    except urllib.error.HTTPError as exc:
        raise EnvoiRefuse(f"Le webhook a répondu une erreur ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EnvoiRefuse("Le webhook ne répond pas.") from exc
    return {"fichiers": [], "envoye": {"adresse": url, "statut": statut, "noms": len(jeu["lignes"])}}
