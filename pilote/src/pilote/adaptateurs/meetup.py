"""Meetup : les groupes (clubs, associations informelles) trouvés par mot-clé, par l'API GraphQL de Meetup. Il faut un jeton d'accès
(OAuth gratuit) : MEETUP_ACCESS_TOKEN. Seconde main. Schéma GraphQL publié par Meetup, contrôlé sur serveur simulé."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource

URL = "https://api.meetup.com/gql-ext"
REQUETE = """query ($q: String!, $n: Int!) { keywordSearch(filter: {query: $q, source: GROUPS}, input: {first: $n}) {
  edges { node { result { ... on Group { name link city country } } } } } }"""


def convertir(rep: Any) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "data" not in rep:
        raise ErreurSource("La réponse de Meetup n'a pas la forme attendue.")
    out = []
    for e in (((rep.get("data") or {}).get("keywordSearch")) or {}).get("edges") or []:
        g = ((e.get("node") or {}).get("result")) or {}
        nom = str(g.get("name") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": "Meetup (groupe)", "site": str(g.get("link") or ""), "ville": str(g.get("city") or ""),
                        "pays": str(g.get("country") or "").upper(), "genre": "club"})  # fmt: skip
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    jeton = str(parametres.get("_cle", "")).strip()
    if not jeton:
        raise ErreurSource("Le jeton de Meetup est absent : la source reste éteinte sans lui.")
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or []), str(entree.get("lieu", "")).strip()]).strip()
    if not mots:
        return []
    n = min(int(entree.get("limite") or 25), 50)
    rep = client.post_json(str(parametres.get("api", URL)), {"query": REQUETE, "variables": {"q": mots, "n": n}}, headers={"Authorization": f"Bearer {jeton}"})
    if isinstance(rep, dict) and rep.get("errors") and not rep.get("data"):
        raise ErreurSource("Meetup a refusé la demande (jeton invalide ou droits insuffisants).")
    return convertir(rep)[:n]
