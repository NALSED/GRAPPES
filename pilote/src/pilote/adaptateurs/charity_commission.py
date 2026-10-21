"""Charity Commission pour l'Angleterre et le pays de Galles : registre officiel des organisations caritatives. Première main.
Il faut une clé gratuite du portail des développeurs (api-portal.charitycommission.gov.uk), envoyée dans l'en-tête de chaque appel."""

from __future__ import annotations

from typing import Any

from pilote import cles as _cles  # noqa: F401  (la clé est lue par l'exécuteur et transmise en paramètre ; jamais lue ici)
from pilote.adaptateurs import Client, ErreurSource, singulier

BASE = "https://api.charitycommission.gov.uk/register/api"
ENTETE = "Ocp-Apim-Subscription-Key"


def convertir(rep: Any) -> list[dict[str, Any]]:
    """Liste de résultats de `searchCharityName` : « charity_name » et « reg_charity_number » (champs du schéma publié)."""
    if isinstance(rep, dict):
        rep = rep.get("results") or rep.get("charities") or []
    if not isinstance(rep, list):
        raise ErreurSource("La réponse de la Charity Commission n'a pas la forme attendue.")
    out = []
    for c in rep:
        if not isinstance(c, dict):
            continue
        nom = str(c.get("charity_name") or c.get("name") or "").strip()
        if nom:
            out.append({"nom": nom.title() if nom.isupper() else nom, "origine": "Charity Commission (registre officiel des organisations caritatives)",
                        "numero": str(c.get("reg_charity_number") or c.get("registered_charity_number") or ""), "pays": "GB", "genre": "association"})  # fmt: skip
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    pays = str(entree.get("pays") or "").upper()
    if pays and pays != "GB":
        return []
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("La clé d'API de la Charity Commission est absente : la source reste éteinte sans elle.")
    base = str(parametres.get("base", BASE)).rstrip("/")
    q = singulier(str(entree.get("quoi", "")).strip())
    if not q:
        return []
    from urllib.parse import quote

    rep = client.get_json(f"{base}/searchCharityName/{quote(q)}", headers={ENTETE: cle})
    return convertir(rep)[: int(entree.get("limite") or 25)]
