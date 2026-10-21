"""Source MCP générique, sans code propre à un prestataire : l'adresse du serveur, l'outil, ses arguments (avec les mots de la
recherche) et la correspondance des champs sont des RÉGLAGES de la source (`moteur.parametres`). Sert aux prestataires (Apify,
Bright Data...) et à tout serveur MCP ajouté depuis la page Ajout. Le serveur rend du texte : du JSON (liste, ou objet contenant une
liste), sinon des liens « [titre](adresse) ». On n'y lit que des champs, jamais d'instruction. Seconde main."""

from __future__ import annotations

import json
import re
from typing import Any

from pilote.adaptateurs import Client, ErreurSource

LIT_PARAMETRES = True
LIEN = re.compile(r"\[([^\]\n]{2,200})\]\((https?://[^)\s]+)\)")
CHAMPS = {"nom": ["fullName", "name", "title", "displayName", "username"], "site": ["url", "link", "profileUrl", "inputUrl"], "ville": ["city", "locationName"],
          "pays": ["country", "countryCode"]}  # fmt: skip


def remplir(modele: Any, valeurs: dict[str, Any]) -> Any:
    """Remplace {mots_cles}, {lieu}, {quoi}, {sujet}, {limite} dans un modèle d'arguments (une chaîne seule garde le type : entier pour {limite})."""
    if isinstance(modele, str):
        m = re.fullmatch(r"\{(\w+)\}", modele)
        if m and m.group(1) in valeurs:
            return valeurs[m.group(1)]
        return re.sub(r"\{(\w+)\}", lambda x: str(valeurs.get(x.group(1), "")), modele).strip()
    if isinstance(modele, dict):
        return {k: remplir(v, valeurs) for k, v in modele.items()}
    if isinstance(modele, list):
        return [remplir(v, valeurs) for v in modele]
    return modele


def _lire(it: Any, chemin: str) -> Any:
    """Valeur d'un champ, avec un chemin pointé pour les champs imbriqués (« location.lat »)."""
    for p in chemin.split("."):
        it = it.get(p) if isinstance(it, dict) else None
    return it


def _liste(v: Any, chemin: str) -> list[Any]:
    for p in [x for x in chemin.split(".") if x]:
        v = v.get(p) if isinstance(v, dict) else None
    if isinstance(v, dict):
        v = next((x for x in v.values() if isinstance(x, list)), [])
    return v if isinstance(v, list) else []


def convertir(brut: Any, parametres: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    p = parametres or {}
    champs = {**{k: list(v) for k, v in CHAMPS.items()}, **{k: [v] if isinstance(v, str) else list(v) for k, v in (p.get("champs") or {}).items()}}
    origine = str(p.get("origine_texte", "")) or "prestataire (réseau social)"
    genre = str(p.get("genre", "compte"))
    try:
        v = json.loads(brut) if isinstance(brut, str) else brut
    except ValueError:
        v = None
    out: list[dict[str, Any]] = []
    if v is not None:
        for it in _liste(v, str(p.get("liste", ""))):
            if not isinstance(it, dict):
                continue
            lu = {k: next((str(_lire(it, c)).strip() for c in champs.get(k, []) if _lire(it, c) not in (None, "")), "") for k in ("nom", "site", "ville", "pays")}
            if lu["nom"]:
                e = {"nom": lu["nom"], "origine": origine, "genre": genre, **{k: v for k, v in lu.items() if k != "nom" and v}}
                coord = p.get("coordonnees") or {}  # ex. {lat: location.lat, lon: location.lng}
                try:
                    if coord:
                        e["coordonnees"] = {"lat": float(_lire(it, coord["lat"])), "lon": float(_lire(it, coord["lon"]))}
                except (KeyError, TypeError, ValueError):
                    pass
                out.append(e)
        return out
    if not isinstance(brut, str):
        raise ErreurSource("La réponse du serveur n'est ni du JSON ni du texte lisible.")
    vus = set()
    for titre, url in LIEN.findall(brut):
        if url not in vus:
            vus.add(url)
            out.append({"nom": titre.strip(), "origine": origine, "site": url, "genre": genre})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    url, outil = str(parametres.get("mcp", "")).strip(), str(parametres.get("outil", "")).strip()
    if not url or not outil:
        raise ErreurSource("La source MCP doit indiquer l'adresse du serveur (« mcp ») et l'outil à appeler (« outil »).")
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or [])]).strip()
    if not mots:
        return []
    limite = int(entree.get("limite") or 25)
    valeurs = {"mots_cles": mots, "quoi": str(entree.get("quoi", "")), "lieu": str(entree.get("lieu", "")), "sujet": str(entree.get("sujet", "")), "limite": limite,
               "mots_et_lieu": f"{mots} {entree.get('lieu', '')}".strip()}  # fmt: skip
    en_tete: dict[str, str] = {}
    cle = str(parametres.get("_cle", "")).strip()
    if cle:  # la valeur contient déjà son préfixe éventuel (« Bearer »), posé par la copie de configuration de la recherche
        en_tete[str(parametres.get("en_tete", "Authorization"))] = cle
    elif parametres.get("cle_requise"):
        raise ErreurSource("La clé du prestataire est absente : la source reste éteinte sans elle.")
    texte = client.mcp(url, outil, remplir(parametres.get("arguments") or {}, valeurs), headers=en_tete)
    return convertir(texte, parametres)[:limite]
