"""Catalogue de l'État (data.gouv.fr, MCP) pour la page Ajout : chercher une API ou un jeu de données et préremplir une prise.

Les réponses de l'outil sont du TEXTE : on y lit seulement des champs étiquetés (ID, titre, URL, format), jamais d'instruction.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from pilote.config import Config

PONT = Path(__file__).resolve().parent / "pont" / "catalogue_mcp.py"
SRC_PILOTE = Path(__file__).resolve().parents[1]
MOTS_REQUETE = ("q", "query", "search", "recherche", "text", "texte", "nom", "name", "mots", "keywords", "terms", "where")


class CatalogueIndisponible(RuntimeError):
    pass


def appeler(cfg: Config, outil: str, arguments: dict[str, Any]) -> str:
    py = cfg.python_grappes
    if not py.exists():
        raise CatalogueIndisponible(f"l'interpréteur de grappes est introuvable ({py})")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(cfg.grappes_racine / "src"), str(SRC_PILOTE)]))
    spec = {"url": cfg.catalogue_mcp, "outil": outil, "arguments": arguments, "delai_s": cfg.catalogue_delai_s}
    try:
        r = subprocess.run([str(py), str(PONT), json.dumps(spec)], capture_output=True, text=True, timeout=cfg.catalogue_delai_s + 15, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise CatalogueIndisponible("le catalogue de l'État n'a pas répondu à temps") from exc
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise CatalogueIndisponible("réponse illisible du catalogue") from exc
    if not out.get("ok"):
        raise CatalogueIndisponible(f"le catalogue de l'État est injoignable ({out.get('erreur', '?')})")
    return str(out["texte"])


def _champ(bloc: str, etiquette: str) -> str:
    m = re.search(rf"^\s*{re.escape(etiquette)}:\s*(.*)$", bloc, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _blocs(texte: str) -> list[tuple[str, str]]:
    """[(titre, bloc)] pour chaque entrée numérotée « 1. Titre »."""
    out = []
    for blk in re.split(r"\n\n(?=\d+\. )", texte):
        m = re.match(r"\s*\d+\.\s+(.*)", blk)
        if m:
            out.append((m.group(1).strip(), blk))
    return out


def lire_jeux(texte: str) -> list[dict[str, Any]]:
    return [
        {"genre": "jeu", "id": _champ(b, "ID"), "titre": t, "organisation": _champ(b, "Organization"), "page": _champ(b, "URL"), "nb_ressources": _champ(b, "Resources")}
        for t, b in _blocs(texte) if _champ(b, "ID")
    ]  # fmt: skip


def lire_apis(texte: str) -> list[dict[str, Any]]:
    return [
        {"genre": "api", "id": _champ(b, "ID"), "titre": t, "organisation": _champ(b, "Organization"), "page": _champ(b, "URL"), "base": _champ(b, "Base API URL")}
        for t, b in _blocs(texte) if _champ(b, "ID")
    ]  # fmt: skip


def lire_ressources(texte: str) -> list[dict[str, Any]]:
    return [
        {"id": _champ(b, "Resource ID"), "titre": t, "format": _champ(b, "Format").lower(), "taille": _champ(b, "Size"), "url": _champ(b, "URL")}
        for t, b in _blocs(texte) if _champ(b, "URL")
    ]  # fmt: skip


def lire_openapi(texte: str) -> dict[str, Any]:
    """Serveur et points d'accès GET (avec leurs paramètres de requête) du résumé OpenAPI rendu par le catalogue."""
    serveur = re.search(r"Servers:\s*\n\s*-\s*(\S+)", texte)
    base = serveur.group(1).rstrip("/") if serveur else _champ(texte, "Base API URL").rstrip("/")
    points: list[dict[str, Any]] = []
    for m in re.finditer(r"^\s{2}(GET)\s+(/\S*)\s*\n((?:\s{4,}.*\n?)*)", texte, re.MULTILINE):
        corps = m.group(3).splitlines()
        resume = corps[0].strip() if corps and not corps[0].strip().startswith("-") else ""
        params = [{"nom": p.group(1), "type": p.group(2).strip(), "requis": "(required)" in p.group(3)} for p in re.finditer(r"^\s*-\s+(\w+)\s+\[query,\s*([^\]]*)\](.*)$", m.group(3), re.MULTILINE)]
        points.append({"chemin": m.group(2), "resume": resume, "parametres": params})
    for p in points:
        texte_p = [x for x in p["parametres"] if x["type"] == "string"]
        pref = next((x["nom"] for x in texte_p if x["nom"].lower() in MOTS_REQUETE), "")
        p["parametre_requete"] = pref
    return {"base": base, "points": points}


def chercher(cfg: Config, mots: str) -> dict[str, Any]:
    apis = lire_apis(appeler(cfg, "search_dataservices", {"query": mots, "page_size": 8}))
    jeux = lire_jeux(appeler(cfg, "search_datasets", {"query": mots, "page_size": 8}))
    return {"apis": apis, "jeux": jeux}


def ressources(cfg: Config, jeu_id: str) -> list[dict[str, Any]]:
    return [r for r in lire_ressources(appeler(cfg, "list_dataset_resources", {"dataset_id": jeu_id})) if r["format"] in ("csv", "json", "xml", "")]


def api(cfg: Config, api_id: str) -> dict[str, Any]:
    return lire_openapi(appeler(cfg, "get_dataservice_openapi_spec", {"dataservice_id": api_id}))
