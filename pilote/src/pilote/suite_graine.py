"""État de départ de la suite : les dix outils livrés, tels que la maquette `Main.dc.html` les montre. Les SOURCES ne sont plus ici : elles viennent des
déclarations réelles de pilote (`suite_reel.py`).

Ce sont des DONNÉES de départ : dès le premier enregistrement, l'état vit dans `donnees/suite/etat.json` et ce fichier n'est plus relu
que pour réparer un état abîmé. Rien ici n'est un résultat de test : `test_reussi` ne vaut vrai que là où la maquette montre
« opérationnelle » (historique de la maquette), jamais pour une source créée dans l'interface."""

from __future__ import annotations

import copy
import re
from typing import Any

CATEGORIES: list[tuple[str, str]] = [
    ("web", "Web"), ("orgs", "Organisations officielles"), ("assos", "Associations"), ("entreprises", "Entreprises"),
    ("rs", "Réseaux sociaux"), ("lieux", "Lieux"), ("presse", "Presse"), ("perso", "Personnalisé"),
]  # fmt: skip
ROLES = ("CHERCHER", "VERIFIER", "ENRICHIR", "CATALOGUE", "OUTIL", "RAPPROCHER")
ETATS = ("ok", "warn", "off")
EFFETS = ("rien", "compteur", "journal", "alerte")

_CODE = 'def run(resultats):\n    # resultats : liste de dictionnaires\n    return [r for r in resultats if r.get("pays") == "FR"]'

AVERTISSEMENT_IA = [
    "Ce que cette tuile produit ne vient d'aucune source : c'est une IA qui l'écrit.",
    "Le résultat peut changer d'un lancement à l'autre, avec la même question et les mêmes données.",
    "Une IA peut écrire quelque chose de faux avec assurance. Rien de ce qu'elle produit ne compte comme un fait vérifié.",
    "Tout ce qui sort de cette tuile est marqué « IA » dans la grappe, et le reste à chaque étape.",
]

# (id, nom, rôle, état, fait, reçoit, renvoie, effet, options, entrée de test, sortie de test)
_OUTILS: list[tuple[Any, ...]] = [
    ("format", "Format JSON / CSV", "OUTIL", "ok", "Convertit une réponse brute en tableau propre.", "Une réponse brute (JSON)", "Un tableau (CSV)", "journal",
     [["Format de sortie", "CSV"], ["Séparateur", ";"]], '{"nom": "Club A", "ville": "Lyon"}', "nom;ville\nClub A;Lyon"),
    ("traduction", "Traduction", "OUTIL", "ok", "Traduit la requête ou les résultats, et garde toujours l'original à côté.", "Un texte, ou une liste de résultats",
     "Le même contenu, avec la traduction ajoutée à côté de l'original", "journal",
     [["Langue d'entrée", "détecter"], ["Traduire vers", "français, anglais, allemand"], ["Ne pas traduire", "les noms propres"]],
     "charpentier (français)", "charpentier (fr, original)\nZimmermann (de)\ncarpenter (en)"),
    ("si", "Condition « si »", "OUTIL", "ok", "Envoie les résultats vers une branche ou une autre selon un test.", "Une liste de résultats", "Deux listes : oui et non", "compteur",
     [["Si le champ", "catégorie"], ["est égal à", "association"]], "3 résultats : 2 associations, 1 entreprise", "oui : 2 résultats\nnon : 1 résultat"),
    ("boucle", "Boucle", "OUTIL", "ok", "Répète une recherche pour chaque élément d'une liste.", "Une liste (villes, noms…)", "Les résultats de chaque tour, regroupés", "journal",
     [["Répéter pour chaque", "ville de la liste"], ["Maximum de tours", "50"]], "Liste de 3 villes", "3 recherches lancées\n3 réponses regroupées"),
    ("fusion", "Fusion / doublons", "RAPPROCHER", "ok", "Regroupe les résultats qui parlent de la même entité.", "Plusieurs listes de résultats", "Une seule liste sans doublons", "compteur",
     [["Même entité si", "nom et ville identiques"], ["En cas de doublon, garder", "la source la plus fiable"]], "5 résultats dont 2 doublons", "3 résultats"),
    ("filtre", "Filtre", "OUTIL", "ok", "Garde seulement les résultats qui répondent à un critère.", "Une liste de résultats", "La même liste, réduite", "compteur",
     [["Garder si le champ", "pays"], ["est égal à", "FR"]], "3 résultats : FR, FR, UK", "2 résultats : FR, FR"),
    ("attente", "Attente (quota)", "OUTIL", "off", "Fait patienter la recherche quand un quota est atteint.", "Une recherche en cours", "La même recherche, reprise après l'attente", "journal",
     [["Quand le quota est atteint", "attendre"], ["Attente maximale", "10 minutes"]], "Quota atteint à 14:02", "Reprise à 14:12"),
    ("budget", "Compteur budget", "OUTIL", "off", "Arrête la recherche avant de dépasser le budget fixé.", "Le coût de chaque appel payant", "Le même flux, ou un arrêt", "alerte",
     [["Budget maximum", "5 € par mois"], ["À partir de 80 %", "prévenir"]], "Dépensé ce mois : 4,10 €", "Alerte : 82 % du budget"),
    ("ia", "Assistant IA", "OUTIL", "off", "Applique une opération d'IA à ce qui a déjà été collecté. N'ajoute aucune information nouvelle.", "Une liste de résultats",
     "Les mêmes résultats, avec un champ ajouté et marqué « IA »", "alerte",
     [["Opération", "résumer"], ["Modèle", "local (Ollama)"], ["Marquer les résultats", "oui — « produit par IA »"]], "3 articles de presse",
     "3 articles + un résumé marqué « IA »\nAucun fait ajouté"),
    ("rsshub", "RSSHub", "OUTIL", "off", "Transforme un site sans flux en flux RSS lisible.", "L'adresse d'un site", "Un flux RSS", "rien",
     [["Site à transformer", "adresse du site"], ["Rafraîchir toutes les", "30 minutes"]], "Un site sans flux", "Un flux RSS avec 20 articles"),
]  # fmt: skip


def identifiant(nom: str) -> str:
    """Identifiant stable d'un nom : minuscules, tirets (« Finlande — PRH » -> « finlande-prh »)."""
    import unicodedata

    plat = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plat.lower()).strip("-") or "sans-nom"


def _outil(t: tuple) -> dict[str, Any]:
    ident, nom, role, etat, fait, recoit, renvoie, effet, options, entree, sortie = t
    return {
        "id": ident, "nom": nom, "nature": "modele", "modele": ident, "role": role, "fait": fait, "recoit": recoit, "renvoie": renvoie,
        "effet": effet, "options": copy.deepcopy(options), "code": "", "test_entree": entree, "test_sortie": sortie, "etat": etat,
        "test_reussi": True, "livre": True, "retire": False, "cle": False,
    }  # fmt: skip


def graine() -> dict[str, Any]:
    return {
        "version": 2,
        "surcouche": {},  # ce que la suite ajoute aux sources réelles : {id: {langue, role, cat, retiree}} (voir suite_reel.py)
        "outils": [_outil(t) for t in _OUTILS],
        "plan": {"nodes": [], "edges": [], "cats": [], "saisies": {}},
        "simple": {"preset": "entreprises", "pays": "Tous", "ov": {}, "saisie": ""},
        "recherches": [],
    }  # fmt: skip


def code_modele() -> str:
    return _CODE
