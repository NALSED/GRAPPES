"""CourtListener : jurisprudence et dossiers judiciaires des États-Unis. Sert à VÉRIFIER le nom d'une ORGANISATION déjà trouvée (jamais à
chercher, jamais pour des personnes). Un résultat est une INFORMATION (« ce nom apparaît dans N affaires américaines »), pas une alerte :
une entreprise est mêlée à des procès sans que cela dise rien de sa fiabilité. Seule une partie dont le nom est EXACTEMENT celui du
candidat compte (casse, accents et ponctuation mis à part) ; une affaire qui ne fait que citer le mot est ignorée.

Utile seulement pour une recherche aux États-Unis (ou sans pays) : ailleurs la source ne dit rien et ne fait aucun appel."""

from __future__ import annotations

import re
from typing import Any

from pilote.adaptateurs import Client, ErreurSource, nom_normalise

URL = "https://www.courtlistener.com/api/rest/v4/search/"
SITE = "https://www.courtlistener.com"
SEPARATEUR = re.compile(r"\s+v(?:s)?\.?\s+", re.IGNORECASE)  # « A v. B », « A vs B »


def _parties(nom_affaire: str) -> list[str]:
    return [p.strip() for p in SEPARATEUR.split(nom_affaire) if p.strip()]


def convertir(rep: Any, nom: str) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or not isinstance(rep.get("results"), list):
        raise ErreurSource("La réponse de CourtListener n'a pas la forme attendue.")
    voulu = nom_normalise(nom)
    if not voulu:
        return []
    affaires = [r for r in rep["results"] if isinstance(r, dict) and voulu in {nom_normalise(p) for p in _parties(str(r.get("caseName") or ""))}]
    if not affaires:
        return []
    premiere = affaires[0]
    lien = str(premiere.get("absolute_url") or "")
    n = len(affaires)
    return [{"nom": nom, "numero": SITE + lien if lien.startswith("/") else "", "signal": "information",
             "origine": f"CourtListener : ce nom apparaît dans {n} affaire{'s' if n > 1 else ''} américaine{'s' if n > 1 else ''} "
                        f"(par exemple « {str(premiere.get('caseName') or '')[:80]} »), à lire avant d'en conclure quoi que ce soit"}]  # fmt: skip


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    nom = str(entree.get("nom") or entree.get("quoi") or "").strip()
    pays = str(entree.get("pays") or "").strip().upper()
    if not nom or (pays and pays != "US"):
        return []  # hors des États-Unis, aucun appel
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("La clé de CourtListener est absente : la source reste éteinte sans elle.")
    rep = client.get_json(URL, {"q": f'caseName:"{nom}"', "type": "o", "page_size": 10}, headers={"Authorization": f"Token {cle}"})
    return convertir(rep, nom)
