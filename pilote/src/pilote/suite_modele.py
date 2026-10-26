"""Le modèle de l'Aide : une couche FACULTATIVE qui traduit une phrase libre en appel de fonction (spécification 11). Il choisit la fonction ;
il n'écrit jamais le texte affiché, qui vient du retour de la fonction. Pas de modèle, ou modèle qui répond n'importe quoi : la phrase est
refusée poliment et les trois puces continuent de marcher.

Le modèle visé est un serveur local de type Ollama (QUESTIONS suite-4 : le modèle d'IA n'est pas tranché). L'adresse se règle dans
`pilote.yaml` (suite.modele_url) ; vide = aucun modèle."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

FONCTIONS = ("lister_sources", "lire_plan", "proposer_plan", "verifier_plan", "definir", "ouvrir")
DELAI_S = 20


def _appel(url: str, corps: dict[str, Any] | None = None, delai: float = DELAI_S) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=None if corps is None else json.dumps(corps).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=delai) as r:
        return json.loads(r.read().decode())


def disponible(url: str) -> bool:
    if not url:
        return False
    try:
        return bool(_appel(url.rstrip("/") + "/api/tags", None, 1.5).get("models"))
    except (OSError, ValueError, urllib.error.URLError):
        return False


def choisir_fonction(url: str, phrase: str) -> dict[str, Any] | None:
    """{fonction, args} ou None. Tout ce que le modèle rend est vérifié : une fonction hors de la liste des six est ignorée."""
    base = url.rstrip("/")
    try:
        modeles = _appel(base + "/api/tags", None, 1.5).get("models") or []
        consigne = (
            'Tu aides à se servir de grappes. Réponds par UN objet JSON {"fonction": ..., "args": {...}} et rien d\'autre. Fonctions : '
            "lister_sources(role, pays, etat), lire_plan(), proposer_plan(objectif, pays), verifier_plan(), definir(mot), ouvrir(ecran). "
            'Si la phrase ne correspond à aucune, réponds {"fonction": null}.'
        )
        rep = _appel(base + "/api/chat", {"model": modeles[0]["name"], "stream": False, "format": "json",
                                           "messages": [{"role": "system", "content": consigne}, {"role": "user", "content": phrase[:500]}]})  # fmt: skip
        choix = json.loads(rep["message"]["content"])
    except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError):
        return None
    if not isinstance(choix, dict) or choix.get("fonction") not in FONCTIONS:
        return None
    args = choix.get("args")
    return {"fonction": choix["fonction"], "args": args if isinstance(args, dict) else {}}
