"""GLEIF : base mondiale des entités qui ont un identifiant financier (LEI), AVEC leurs relations (maison mère directe, maison mère
ultime). Gratuit, sans clé. Première main. Un nom sans maison mère déclarée est un « siège » ; avec une maison mère, une « filiale »."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs, singulier

URL = "https://api.gleif.org/api/v1/lei-records"
ENTETE = {"Accept": "application/vnd.api+json"}


def _lien(r: dict[str, Any], relation: str) -> str:
    liens = ((r.get("relationships") or {}).get(relation) or {}).get("links") or {}
    return liens.get("lei-record") or liens.get("related") or ""  # « lei-record » est la clé réelle de GLEIF


def convertir(rep: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "data" not in rep:
        raise ErreurSource("La réponse de GLEIF n'a pas la forme attendue.")
    out = []
    for r in rep.get("data") or []:
        a = r.get("attributes") or {}
        e = a.get("entity") or {}
        nom = str((e.get("legalName") or {}).get("name") or "").strip()
        if not nom:
            continue
        adr = e.get("legalAddress") or {}
        out.append({
            "nom": nom.title() if nom.isupper() else nom, "origine": "GLEIF (identifiants d'entités juridiques)", "numero": str(e.get("registeredAs") or a.get("lei") or ""),
            "ville": str(adr.get("city") or "").title(), "pays": str(adr.get("country") or ""), "genre": "entreprise",
            "fonction": "filiale" if _lien(r, "direct-parent") else "siège", "relations": [],
            "_parent": _lien(r, "direct-parent"), "_ultime": _lien(r, "ultimate-parent"),
        })  # fmt: skip
    return out


def _nom_parent(client: Client, url: str) -> str:
    try:
        rep = client.get_json(url, headers=ENTETE)
    except ErreurSource:
        return ""  # une maison mère illisible ne fait pas perdre le nom
    nom = str((((rep.get("data") or {}).get("attributes") or {}).get("entity") or {}).get("legalName", {}).get("name", "")).strip()
    return nom.title() if nom.isupper() else nom


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    """Cherche par NOM (début du nom légal), mot significatif par mot significatif : GLEIF est un annuaire de noms, pas un moteur par thème."""
    mots = mots_significatifs(singulier(" ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])])), 3)
    if not mots:
        return []
    limite = int(entree.get("limite") or 25)
    vus: dict[str, dict[str, Any]] = {}
    for mot in mots:
        params: dict[str, Any] = {"filter[entity.legalName]": mot.upper(), "page[size]": min(limite, 50)}
        if entree.get("pays"):
            params["filter[entity.legalAddress.country]"] = str(entree["pays"]).upper()
        for e in convertir(client.get_json(URL, params, headers=ENTETE)):
            vus.setdefault(e["numero"] + "|" + e["nom"], e)
        if len(vus) >= limite:
            break
    noms = list(vus.values())[:limite]
    for e in noms[: int(parametres.get("relations_max", 10))]:  # les relations coûtent un appel chacune : on les demande pour les premiers résultats
        for cle, type_ in (("_parent", "maison_mere"), ("_ultime", "maison_mere_ultime")):
            if e.get(cle):
                vers = _nom_parent(client, e[cle])
                if vers:
                    e["relations"].append({"type": type_, "vers": vers})
    for e in noms:
        e.pop("_parent", None)
        e.pop("_ultime", None)
    return noms
