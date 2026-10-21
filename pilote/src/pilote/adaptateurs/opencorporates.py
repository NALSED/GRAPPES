"""OpenCorporates : registre mondial des sociétés. TRÈS CHER (offre d'entrée à 225 £ par mois pour 500 appels, pas d'offre gratuite en
libre-service) ; accès gratuit sur demande pour journalistes, ONG, universités et chercheurs. Première main. Clé : OPENCORPORATES_API_TOKEN."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource, singulier

URL = "https://api.opencorporates.com/v0.4/companies/search"


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "results" not in rep:
        raise ErreurSource("La réponse d'OpenCorporates n'a pas la forme attendue.")
    out = []
    for c in ((rep.get("results") or {}).get("companies")) or []:
        c = c.get("company") or {}
        nom = str(c.get("name") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": "OpenCorporates (registre mondial des sociétés)", "numero": str(c.get("company_number") or ""),
                        "pays": str(c.get("jurisdiction_code") or "")[:2].upper(), "genre": "entreprise", "site": str(c.get("opencorporates_url") or ""),
                        "ville": "", "fonction": "siège"})  # fmt: skip
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("Le jeton d'OpenCorporates est absent : la source reste éteinte sans lui.")
    q = singulier(str(entree.get("quoi", "")).strip())
    if not q:
        return []
    p: dict[str, Any] = {"q": q, "api_token": cle, "per_page": min(int(entree.get("limite") or 25), 100)}
    if entree.get("pays"):
        p["jurisdiction_code"] = str(entree["pays"]).lower()
    return convertir(client.get_json(URL, p))[: int(entree.get("limite") or 25)]
