"""OpenSanctions : listes de sanctions et de personnes politiquement exposées. Sert à VÉRIFIER le nom d'une ORGANISATION déjà trouvée (jamais à
chercher, jamais pour des personnes : on demande le type Organization). Un résultat est une ALERTE, pas une confirmation, et seule une
correspondance EXACTE du nom (casse, accents et ponctuation mis à part) compte : pas de correspondance floue, qui accuserait à tort des
homonymes proches."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource
from pilote.adaptateurs import nom_normalise as _norme

URL = "https://api.opensanctions.org/search/default"
# Le service renvoie le type le plus précis, pas « Organization » : une société est « Company » (contrôlé en réel le 19/10, « PMC Wagner »).
# Accepter seulement « Organization » laissait passer en silence les entreprises sanctionnées. Jamais « Person » ni « LegalEntity » (ambigu).
TYPES_ORGANISATION = frozenset({"Organization", "Company", "PublicBody"})
FICHE = "https://www.opensanctions.org/entities/"
THEMES_GRAVES = ("sanction", "crime", "debarment", "poi", "wanted", "asset.freeze")  # thèmes OpenSanctions qui font une alerte ; les autres (risque d'export, propriété…) sont une information


def convertir(rep: Any, nom: str) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or not isinstance(rep.get("results"), list):
        raise ErreurSource("La réponse d'OpenSanctions n'a pas la forme attendue.")
    voulu = _norme(nom)
    if not voulu:
        return []
    out = []
    for r in rep["results"]:
        if not isinstance(r, dict) or r.get("schema") not in TYPES_ORGANISATION:
            continue
        noms = [str(r.get("caption") or ""), *map(str, (r.get("properties") or {}).get("name") or [])]
        if voulu in {_norme(n) for n in noms if n}:
            listes = ", ".join(map(str, r.get("datasets") or []))
            themes = [str(x) for x in (r.get("properties") or {}).get("topics") or []]
            grave = not themes or any(x.startswith(THEMES_GRAVES) for x in themes)  # sanction, crime, exclusion : une alerte ; un registre de risque ou d'exposition n'en est pas une. Thèmes absents : on ne sait pas, donc on alerte
            texte = ("OpenSanctions : ce nom figure sur une liste de sanctions ou de criminalité" if grave else "OpenSanctions : ce nom figure sur une liste qui n'est pas une sanction")
            out.append({"nom": nom, "numero": FICHE + str(r.get("id", "")), "signal": "alerte" if grave else "information",
                        "origine": texte + (f" ({', '.join(themes)})" if themes else "") + (f" [{listes}]" if listes else "") + ", à vérifier à la main"})  # fmt: skip
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    nom = str(entree.get("nom") or entree.get("quoi") or "").strip()
    if not nom:
        return []
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("La clé d'OpenSanctions est absente : la source reste éteinte sans elle.")
    rep = client.get_json(URL, {"q": nom, "schema": "Organization", "limit": 5}, headers={"Authorization": f"ApiKey {cle}"})
    return convertir(rep, nom)
