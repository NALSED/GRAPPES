"""Google Places (API officielle, « Text Search ») : les lieux d'une zone par mot-clé, avec nom, adresse, site et coordonnées.
Il faut la clé de l'utilisateur (variable GOOGLE_PLACES_API_KEY) ; la recherche est PAYANTE au-delà du quota gratuit de Google.
La clé part dans un en-tête, jamais dans l'adresse. Seconde main (service commercial qui agrège des données de tiers)."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource

URL = "https://places.googleapis.com/v1/places:searchText"
CHAMPS = "places.displayName,places.formattedAddress,places.websiteUri,places.location,places.addressComponents,places.types"


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict):
        raise ErreurSource("La réponse de Google Places n'a pas la forme attendue.")
    out = []
    for p in rep.get("places") or []:
        nom = str((p.get("displayName") or {}).get("text") or "").strip()
        if not nom:
            continue
        compo = p.get("addressComponents") or []
        ville = next((str(c.get("longText", "")) for c in compo if "locality" in (c.get("types") or [])), "")
        pays = next((str(c.get("shortText", "")) for c in compo if "country" in (c.get("types") or [])), "")
        e: dict[str, Any] = {"nom": nom, "origine": "Google Places", "site": str(p.get("websiteUri") or ""), "ville": ville, "pays": pays.upper(), "genre": "lieu"}
        loc = p.get("location") or {}
        if loc.get("latitude") is not None and loc.get("longitude") is not None:
            e["coordonnees"] = {"lat": float(loc["latitude"]), "lon": float(loc["longitude"])}
        out.append(e)
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("La clé de Google Places est absente : la source reste éteinte sans elle.")
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or [])]).strip()
    lieu = str(entree.get("lieu") or "").strip()
    if not mots:
        return []
    limite = min(int(entree.get("limite") or 20), 20)  # 20 lieux par page au maximum
    corps: dict[str, Any] = {"textQuery": f"{mots} {lieu}".strip(), "pageSize": limite}
    if entree.get("pays"):
        corps["regionCode"] = str(entree["pays"]).upper()
    rep = client.post_json(str(parametres.get("url", URL)), corps, headers={"X-Goog-Api-Key": cle, "X-Goog-FieldMask": CHAMPS})
    return convertir(rep)[:limite]
