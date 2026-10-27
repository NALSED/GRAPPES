"""ROR (Research Organization Registry) : universités, instituts de recherche, hôpitaux universitaires dans le monde. Données en CC0.
Interrogeable par nom ET par pays. Première main."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, alias_de, singulier

URL = "https://api.ror.org/v2/organizations"
# vocabulaire de ROR -> genres génériques du programme
GENRES = {"education": "administration", "healthcare": "administration", "government": "administration", "funder": "administration",
          "company": "entreprise", "nonprofit": "association", "archive": "lieu", "facility": "lieu"}  # fmt: skip
RELATIONS = {"parent": "fait_partie_de", "child": "comprend", "related": "lie_a", "predecessor": "predecesseur", "successor": "successeur"}


def _nom(item: dict[str, Any]) -> str:
    noms = item.get("names") or []
    for n in noms:
        if "ror_display" in (n.get("types") or []):
            return str(n.get("value", "")).strip()
    return str((noms[0] if noms else {}).get("value", "")).strip()


def _alias(item: dict[str, Any], nom: str) -> list[str]:
    """Les noms de type `acronym` et `alias` (ROR v2 en documente quatre : acronym, alias, label, ror_display). « CEA » est un `acronym`."""
    return alias_de(nom, [n.get("value", "") for n in item.get("names") or [] if {"acronym", "alias"} & set(n.get("types") or [])])


def convertir(rep: dict[str, Any]) -> list[dict[str, Any]]:
    """Réponse de ROR -> noms (convention des adaptateurs)."""
    out = []
    for it in rep.get("items") or []:
        nom = _nom(it)
        if not nom:
            continue
        loc = ((it.get("locations") or [{}])[0]).get("geonames_details") or {}
        site = next((l.get("value", "") for l in it.get("links") or [] if l.get("type") == "website"), "")
        types = it.get("types") or []
        e: dict[str, Any] = {
            "nom": nom, "origine": "ROR (registre des organisations de recherche)", "numero": str(it.get("id", "")), "site": site,
            "ville": str(loc.get("name", "")), "pays": str(loc.get("country_code", "")),
            "genre": next((GENRES[t] for t in types if t in GENRES), ""),
            "relations": [{"type": RELATIONS.get(r.get("type", ""), r.get("type", "")), "vers": str(r.get("label", ""))} for r in it.get("relationships") or [] if r.get("label")],
        }  # fmt: skip
        if alias := _alias(it, nom):
            e["alias"] = alias
        if loc.get("lat") is not None and loc.get("lng") is not None:
            e["coordonnees"] = {"lat": loc["lat"], "lon": loc["lng"]}
        out.append(e)
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    q = singulier(" ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or [])]).strip())
    if not q:
        return []
    pays = str(entree.get("pays") or "").upper()
    limite = int(entree.get("limite") or 20)
    out: list[dict[str, Any]] = []
    for page in (1, 2, 3):
        rep = client.get_json(URL, {"query": q, "page": page, **({"filter": f"country.country_code:{pays}"} if pays else {})})
        out += convertir(rep)
        if len(out) >= limite or len(rep.get("items") or []) < 20:
            break
    return out[:limite]
