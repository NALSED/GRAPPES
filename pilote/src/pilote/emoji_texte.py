"""Les emoji d'une saisie, selon la norme UTS #51 (Unicode Emoji) : bibliothèque standard seulement (les adaptateurs tournent aussi dans l'interpréteur de grappes).

Un emoji n'est pas un caractère : « ✊🏽 » est un poing (U+270A) et une teinte de peau (U+1F3FD) ; « 🏳️‍🌈 » est un drapeau, un sélecteur U+FE0F, un liant U+200D et un arc-en-ciel.
Quatre règles, une par fonction :

1. on ne jette jamais un emoji : `trouver` les rend d'un seul morceau, séquence entière ;
2. à une source, on envoie la forme tapée (U+FE0F compris) : `trouver` ne réécrit rien ;
3. pour COMPARER seulement, `reduit` retire U+FE0F et la teinte de peau et garde la séquence ZWJ entière (« ✊🏽 » et « ✊🏿 » se comparent égaux) ; cette forme ne sort jamais vers une source ;
4. dans une adresse, un emoji est encodé (`%E2%9C%8A`) : le client HTTP des adaptateurs le fait.

Les points de code viennent de `emoji_donnees` (généré par `outils/generer_emoji.py` depuis le paquet `emoji`, que les tests utilisent comme oracle)."""

from __future__ import annotations

import re

from pilote.emoji_donnees import EMOJI_QUALIFIE, EMOJI_SEUL, EMOJI_TOUS

ZWJ, VS16 = "‍", "️"
PEAU = "\U0001f3fb-\U0001f3ff"
_ELEMENT = rf"(?:[{EMOJI_SEUL}][{PEAU}]?|[{EMOJI_QUALIFIE}](?:️[{PEAU}]?|[{PEAU}]))"
_LIE = rf"[{EMOJI_TOUS}]️?[{PEAU}]?"
EMOJI = re.compile(
    "|".join([
        r"\U0001f3f4[\U000e0061-\U000e007a]+\U000e007f",  # drapeau de subdivision (Écosse, Pays de Galles…)
        r"[0-9#*]️?⃣",  # touche
        r"[\U0001f1e6-\U0001f1ff]{2}",  # drapeau de pays : deux indicateurs régionaux
        rf"{_ELEMENT}(?:‍{_LIE})*",
    ])
)
_PEAU = re.compile(f"[{PEAU}]")


def trouver(texte: str) -> list[tuple[int, int, str]]:
    """(début, fin, emoji) de chaque emoji, dans l'ordre, séquences entières, tels que tapés."""
    return [(m.start(), m.end(), m.group()) for m in EMOJI.finditer(texte or "")]


def contient(texte: str) -> bool:
    return EMOJI.search(texte or "") is not None


def sans_emoji(texte: str) -> str:
    """Le texte privé de ses emoji (espaces refermés) : ce que reçoit une source qui ne déclare pas chercher l'emoji."""
    return re.sub(r"\s+", " ", EMOJI.sub(" ", texte or "")).strip()


def requete_pour(entree: dict, accepte_emoji: bool) -> dict:
    """La requête (`quoi`, `sujet`, `lieu`, `mots_cles`…) que reçoit une source : intacte si elle déclare chercher l'emoji, sinon privée de ses emoji, champ par champ."""
    if accepte_emoji:
        return entree
    return {k: (sans_emoji(v) if isinstance(v, str) else [sans_emoji(x) for x in v] if isinstance(v, list) and all(isinstance(x, str) for x in v) else v) for k, v in entree.items()}


def reduit(emoji: str) -> str:
    """Forme de COMPARAISON : sans sélecteur U+FE0F ni teinte de peau, séquence ZWJ conservée. Jamais envoyée à une source."""
    return _PEAU.sub("", emoji.replace(VS16, "")) or emoji
