"""Pappers : registre français des sociétés, avec plus de détails que l'annuaire public. PAYANT. Première main. Clé : PAPPERS_API_TOKEN."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource, singulier

URL = "https://api.pappers.fr/v2/recherche"


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "resultats" not in rep:
        raise ErreurSource("La réponse de Pappers n'a pas la forme attendue.")
    out = []
    for r in rep.get("resultats") or []:
        nom = str(r.get("nom_entreprise") or r.get("denomination") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": "Pappers (registre des sociétés françaises)", "numero": str(r.get("siren") or ""),
                        "ville": str((r.get("siege") or {}).get("ville") or "").title(), "pays": "FR", "genre": "entreprise", "fonction": "siège"})  # fmt: skip
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    pays = str(entree.get("pays") or "").upper()
    if pays and pays != "FR":
        return []
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("Le jeton de Pappers est absent : la source reste éteinte sans lui.")
    q = singulier(str(entree.get("quoi", "")).strip())
    if not q:
        return []
    return convertir(client.get_json(URL, {"q": q, "api_token": cle, "par_page": min(int(entree.get("limite") or 25), 100)}))[: int(entree.get("limite") or 25)]
