"""API JSON ou CSV générique, SANS code propre à un fournisseur (page Ajout, fiche 11) : l'adresse, les paramètres (avec les mots de la
recherche), la façon d'envoyer la clé, le chemin de la liste de résultats et la correspondance des champs sont des RÉGLAGES de la
source (`moteur.parametres`). Sert à brancher le registre d'un pays sans écrire une ligne de code.

Réglages : `url`, `methode` (GET), `params` (valeurs avec {quoi}, {mots_cles}, {lieu}, {sujet}, {mots_et_lieu}, {limite}, {pays}), `auth`
({type: header|bearer|basic|query, nom, prefixe}), `format` (json|csv), `delimiteur`, `liste` (chemin pointé de la liste), `champs`
({nom, ville, genre, numero, site, pays}: chemins pointés), `genres` (valeur de la source -> genre générique), `genre` (défaut),
`origine_texte`, `pays` (code ajouté aux noms), `site_prefixe` (adresse à placer devant un `site` qui n'est qu'un identifiant), `filtre_local` (csv/fichiers entiers : ne garder que les lignes dont le nom contient un mot)."""

from __future__ import annotations

import base64
import csv
import io
from datetime import date, timedelta
from typing import Any

from pilote.adaptateurs import Client, ErreurSource, alias_de, mots_significatifs, nom_normalise
from pilote.adaptateurs.mcp_generique import _lire, _liste, remplir

LIT_PARAMETRES = True


def _entetes(auth: dict[str, Any], cle: str) -> tuple[dict[str, str], dict[str, str]]:
    """(en-têtes, paramètres d'adresse) qui portent la clé. Sans `auth`, rien n'est envoyé."""
    if not auth or not cle:
        return {}, {}
    t = str(auth.get("type", "header"))
    nom = str(auth.get("nom") or "Authorization")
    if t == "bearer":
        return {"Authorization": f"Bearer {cle}"}, {}
    if t == "basic":  # clé en identifiant, mot de passe vide (usage courant : Companies House)
        return {"Authorization": "Basic " + base64.b64encode(f"{cle}:".encode()).decode()}, {}
    if t == "query":
        return {}, {nom: cle}
    return {nom: f"{auth.get('prefixe', '')}{cle}"}, {}


def convertir(brut: Any, parametres: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    p = parametres or {}
    champs = p.get("champs") or {}
    if "nom" not in champs:
        raise ErreurSource("Cette source ne dit pas quel champ contient le nom.")
    if isinstance(brut, str):  # csv
        delim = str(p.get("delimiteur") or ";")
        elements: list[Any] = list(csv.DictReader(io.StringIO(brut.lstrip("﻿")), delimiter=delim))
    else:
        elements = _liste(brut, str(p.get("liste", "")))
    genres = {str(k).lower(): v for k, v in (p.get("genres") or {}).items()}
    origine = str(p.get("origine_texte") or "source ajoutée par l'utilisateur")
    out: list[dict[str, Any]] = []
    for it in elements:
        if not isinstance(it, dict):
            continue
        lu = {k: str(_lire(it, c)).strip() for k, c in champs.items() if isinstance(c, str) and c and _lire(it, c) not in (None, "")}
        if not lu.get("nom"):
            continue
        genre = genres.get(lu.get("genre", "").lower(), "") or str(p.get("genre") or "")
        e: dict[str, Any] = {"nom": lu["nom"], "origine": origine}
        for k in ("ville", "site", "pays"):
            if lu.get(k):
                e[k] = lu[k]
        if e.get("site") and p.get("site_prefixe") and not e["site"].startswith(("http://", "https://")):
            e["site"] = str(p["site_prefixe"]) + e["site"]  # le service ne rend qu'un identifiant ou un slug (chaîne YouTube, agenda OpenAgenda) : l'adresse s'en déduit
        if lu.get("numero"):
            e["numero"] = lu["numero"]
        if isinstance(champs.get("alias"), str) and champs["alias"] and (autres := alias_de(lu["nom"], _lire(it, champs["alias"]))):  # les autres noms déclarés (texte ou liste)
            e["alias"] = autres
        if genre:
            e["genre"] = genre
        if p.get("pays") and "pays" not in e:
            e["pays"] = str(p["pays"])
        out.append(e)
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    url = str(parametres.get("url", "")).strip()
    if not url and not parametres.get("fichier"):
        raise ErreurSource("Cette source n'a pas d'adresse.")
    pays = str(parametres.get("pays") or "").upper()
    if pays and str(entree.get("pays") or "").upper() not in ("", pays):
        return []
    mots = [str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or [])]
    quoi = " ".join(m for m in mots if m).strip() or str(entree.get("sujet", "")).strip()
    if not quoi:
        return []
    limite = min(int(entree.get("limite") or 25), 200)
    valeurs = {"quoi": quoi, "mots_cles": " ".join(mots_significatifs(quoi)) or quoi, "lieu": str(entree.get("lieu", "")).strip(), "sujet": str(entree.get("sujet", "")).strip(),
               "limite": limite, "pays": str(entree.get("pays") or "").upper(), "mots_et_lieu": f"{quoi} {entree.get('lieu', '')}".strip(),
               "aujourdhui": date.today().isoformat(), "il_y_a_30_jours": (date.today() - timedelta(days=30)).isoformat(), "il_y_a_un_an": (date.today() - timedelta(days=365)).isoformat()}  # fmt: skip
    if parametres.get("fichier"):  # fichier local : lu en entier, filtré sur le nom
        return _fichier(parametres, quoi, limite)
    entetes, extra = _entetes(parametres.get("auth") or {}, str(parametres.get("_cle", "")))
    if parametres.get("auth") and not parametres.get("_cle"):
        raise ErreurSource("La clé d'API de cette source est absente : elle reste éteinte sans elle.")
    params = {**{k: v for k, v in remplir(parametres.get("params") or {}, valeurs).items() if v not in ("", None)}, **extra}
    fmt = str(parametres.get("format", "json"))
    if fmt == "csv":
        texte = client.get_texte(url, params or None, entetes)
        noms = convertir(texte, parametres)
        if parametres.get("filtre_local", True):
            mots_f = [m.lower() for m in mots_significatifs(quoi, 6)] or [quoi.lower()]
            noms = [n for n in noms if any(m in n["nom"].lower() for m in mots_f)]
        return noms[:limite]
    if str(parametres.get("methode", "GET")).upper() == "POST":
        brut = client.post_json(url, remplir(parametres.get("corps") or {}, valeurs), entetes, params or None)
    else:
        brut = client.get_json(url, params or None, entetes)
    return _exactes(convertir(brut, parametres), parametres, entree)[:limite]


def _exactes(noms: list[dict[str, Any]], parametres: dict[str, Any], entree: dict[str, Any]) -> list[dict[str, Any]]:
    """`correspondance_exacte` : une source qui VÉRIFIE ne confirme un nom que si la source rend EXACTEMENT ce nom (formes juridiques, casse, accents et ponctuation mis
    à part). Sans cela, la première réponse approchante serait prise pour une confirmation.
    Ne joue qu'en vérification et en enrichissement (l'entrée porte alors un `nom`) : en recherche par mots, il n'y a pas de nom à retrouver, et un filtre exact viderait toujours la liste."""
    if not parametres.get("correspondance_exacte") or "nom" not in entree:
        return noms
    voulu = nom_normalise(str(entree["nom"] or ""))  # sans cleanco : ce code tourne aussi dans l'interpréteur de grappes, qui ne l'a pas
    if not voulu:
        return []
    exacts = [n for n in noms if nom_normalise(n["nom"]) == voulu]
    # Un nom que le SERVICE déclare être un autre nom de l'entité (« CEA » est le sigle du Commissariat) est une preuve, rangée après les noms identiques. Les alias de la
    # fiche interrogée, eux, ne servent pas ici : ils feraient confirmer le Commissariat par la société qui s'appelle littéralement « CEA ».
    par_alias = [n for n in noms if n not in exacts and voulu in {nom_normalise(a) for a in n.get("alias") or []}]
    return exacts + par_alias


def _fichier(parametres: dict[str, Any], quoi: str, limite: int) -> list[dict[str, Any]]:
    import json as _json
    from pathlib import Path

    f = Path(str(parametres["fichier"])).expanduser()
    try:
        octets = f.read_bytes()
    except OSError as exc:
        raise ErreurSource("Le fichier de cette source est introuvable ou illisible.") from exc
    texte = octets.decode("utf-8-sig", "replace")
    try:
        brut: Any = texte if str(parametres.get("format", "json")) == "csv" else _json.loads(texte)
    except ValueError as exc:
        raise ErreurSource("Le fichier n'a pas le format annoncé.") from exc
    noms = convertir(brut, parametres)
    mots = [m.lower() for m in mots_significatifs(quoi, 6)] or [quoi.lower()]
    return [n for n in noms if any(m in n["nom"].lower() for m in mots)][:limite]
