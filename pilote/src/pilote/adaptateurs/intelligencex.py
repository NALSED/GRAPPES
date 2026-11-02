"""Intelligence X, LIMITÉ à la recherche WHOIS / historique de domaine (cadrage du 27/10/2026, spécification 17 §5).

La partie « fuites » du service (identifiants volés, dark web) est hors cadre, sans exception : cet adaptateur n'interroge JAMAIS que le seau
« whois », et seulement pour un NOM DE DOMAINE déjà présent sur une fiche trouvée par ailleurs (rôle ENRICHIR). Une saisie qui n'est pas un nom de
domaine est refusée avant tout appel, et un appel sans seau explicite n'existe pas dans ce code : un nom de seau faux rend donc moins de résultats,
jamais des fuites. Forme des réponses d'après la documentation publique d'Intelligence X, pas encore contrôlée contre le service réel (clé absente)."""

from __future__ import annotations

import re
from typing import Any

from pilote.adaptateurs import Client, ErreurSource

URL = "https://2.intelx.io/intelligent/search"
RESULTATS = "https://2.intelx.io/intelligent/search/result"
SEAUX = ["whois"]  # le SEUL seau interrogé ; ne jamais en ajouter ni le laisser vide (vide = tous les seaux, fuites comprises)
DOMAINE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")


def domaine_de(site: str) -> str:
    """Le nom de domaine d'une adresse (sans schéma, chemin ni www), ou « » si ce n'en est pas un."""
    s = re.sub(r"^[a-z]+://", "", site.strip().lower()).split("/")[0].split("?")[0].split(":")[0]
    s = s.removeprefix("www.")
    return s if DOMAINE.match(s) else ""


def convertir(rep: Any, domaine: str | None = None, nom: str | None = None) -> list[dict[str, Any]]:
    """Lit la réponse du SECOND appel (`/intelligent/search/result`, celle qui porte les relevés) : forme vérifiable hors ligne
    sur un exemple enregistré. Le premier appel (lancement de la recherche, qui ne rend qu'un identifiant) n'a rien à convertir."""
    if not isinstance(rep, dict) or not isinstance(rep.get("records"), list):
        raise ErreurSource("La réponse d'Intelligence X n'a pas la forme attendue.")
    anciens = sorted({str(r.get("date", ""))[:10] for r in rep["records"] if isinstance(r, dict) and str(r.get("bucket", "")).lower() == "whois" and r.get("date")})
    if not anciens:
        return []
    domaine = domaine or "exemple.example"  # test hors ligne sur l'exemple : pas de vraie fiche, juste la forme de sortie
    return [{"nom": nom or domaine, "site": domaine,
             "origine": f"Intelligence X (WHOIS de {domaine}, {len(anciens)} relevé{'s' if len(anciens) > 1 else ''} du {anciens[0]} au {anciens[-1]})",
             "detail": f"WHOIS {anciens[0]} → {anciens[-1]}"}]  # fmt: skip


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    domaine = domaine_de(str(entree.get("site") or ""))
    if not domaine:
        return []  # pas de domaine sur la fiche : rien à enrichir, rien n'est cherché par un nom ou un mot
    cle = str(parametres.get("_cle", "")).strip()
    if not cle:
        raise ErreurSource("La clé d'Intelligence X est absente : la source reste éteinte sans elle.")
    en_tete = {"x-key": cle}
    lancee = client.post_json(URL, {"term": domaine, "buckets": SEAUX, "lookuplevel": 0, "maxresults": 10, "timeout": 5, "sort": 4, "media": 0, "terminate": []}, headers=en_tete)
    ident = lancee.get("id") if isinstance(lancee, dict) else None
    if not ident:
        raise ErreurSource("La réponse d'Intelligence X n'a pas la forme attendue.")
    rep = client.get_json(RESULTATS, {"id": ident, "limit": 10}, headers=en_tete)
    return convertir(rep, domaine, str(entree.get("nom") or domaine))
