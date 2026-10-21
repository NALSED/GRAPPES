"""Filtres de la page Tri (fiche 13) : des FACETTES construites depuis les résultats (idée de Datasette), une recherche de texte, et « nouveaux
noms ». Aucune facette n'est écrite à la main pour un jeu de résultats : on regarde les colonnes des noms, et celles qui ont peu de valeurs
différentes deviennent des filtres cliquables avec le nombre à côté. Ajouter une facette = ajouter une ligne à FACETTES.

Dans une facette, les valeurs cochées s'additionnent (OU) ; entre facettes elles se combinent (ET). Le compte d'une facette tient compte
des AUTRES filtres, pas des siens, pour qu'on voie ce qu'un clic de plus donnerait."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from pilote import classements as cl

MAX_VALEURS = 40  # au-delà, la colonne n'a plus « peu de valeurs différentes » : ce n'est pas un filtre utile
MOTS_VIDES = frozenset(["de", "du", "des", "la", "le", "les", "et", "en", "au", "aux", "un", "une", "pour", "par", "sur", "dans", "avec", "the", "of", "and", "for", "in", "on", "at", "to", "a", "an", "d", "l"])


def _confirmations(l: cl.Ligne) -> list[tuple[str, str]]:
    n = min(max(l.endroits, 1), 3)
    return [(str(n), "1 endroit" if n == 1 else "2 endroits" if n == 2 else "3 endroits ou plus")]


# (identifiant, libellé, fonction ligne -> [(valeur, libellé)])
FACETTES: list[tuple[str, str, Callable[[cl.Ligne, Callable[[str], str]], list[tuple[str, str]]]]] = [
    ("origine", "D'où vient le nom", lambda l, ns: [(l.origine, cl.ORIGINE_LIBELLE.get(l.origine, l.origine))]),
    ("pays", "Pays", lambda l, ns: [(l.pays, l.pays)] if l.pays else []),
    ("ville", "Ville", lambda l, ns: [(l.ville, l.ville)] if l.ville else []),
    ("genre", "Genre de chose", lambda l, ns: [(l.genre_de_chose, l.genre_de_chose)] if l.genre_de_chose else []),
    ("fonction", "Fonction", lambda l, ns: [(l.fonction, l.fonction)] if l.fonction else []),
    ("confirmations", "Confirmations", lambda l, ns: _confirmations(l)),
    ("source", "Trouvé par", lambda l, ns: [(t, ns(t)) for t in sorted(set(l.trouve_par))]),
    ("decision", "Décision", lambda l, ns: [(l.decision or "aucune", cl.DECISIONS_LIBELLE.get(l.decision, "pas encore décidés"))]),
]


def sans_accent(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.casefold()) if not unicodedata.combining(c))


def mots_de(texte: str) -> list[str]:
    return [m for m in re.findall(r"[^\W_]{2,}", sans_accent(texte)) if m not in MOTS_VIDES]


def lire_filtres(brut: list[str] | None) -> dict[str, set[str]]:
    """« origine:registre » -> {"origine": {"registre"}} ; une valeur peut contenir « : »."""
    out: dict[str, set[str]] = {}
    ids = {f[0] for f in FACETTES}
    for b in brut or []:
        k, _, v = b.partition(":")
        if k in ids and v:
            out.setdefault(k, set()).add(v)
    return out


def _valeurs(l: cl.Ligne, ns: Callable[[str], str], k: str) -> set[str]:
    f = next(f for f in FACETTES if f[0] == k)
    return {v for v, _ in f[2](l, ns)}


def correspond(l: cl.Ligne, filtres: dict[str, set[str]], q_mots: list[str], ns: Callable[[str], str], nouveau: set[str] | None, sauf: str | None = None) -> bool:
    for k, vals in filtres.items():
        if k != sauf and not (_valeurs(l, ns, k) & vals):
            return False
    if q_mots:
        nom = sans_accent(l.nom)
        if not all(m in nom for m in q_mots):
            return False
    return nouveau is None or cl.normaliser(l.nom) in nouveau


def appliquer(lignes: list[cl.Ligne], filtres: dict[str, set[str]], q: str, ns: Callable[[str], str], nouveau: set[str] | None) -> list[cl.Ligne]:
    q_mots = [sans_accent(m) for m in re.findall(r"[^\W_]+", q or "")]
    return [l for l in lignes if correspond(l, filtres, q_mots, ns, nouveau)]


def facettes(lignes: list[cl.Ligne], filtres: dict[str, set[str]], q: str, ns: Callable[[str], str], nouveau: set[str] | None) -> list[dict[str, Any]]:
    q_mots = [sans_accent(m) for m in re.findall(r"[^\W_]+", q or "")]
    out = []
    for k, libelle, fn in FACETTES:
        toutes: dict[str, str] = {}
        for l in lignes:
            for v, lib in fn(l, ns):
                toutes.setdefault(v, lib)
        actifs = filtres.get(k) or set()
        if not actifs and not 2 <= len(toutes) <= MAX_VALEURS:  # une colonne à une seule valeur, ou à des centaines, n'aide à rien : pas de filtre
            continue  # ... sauf si l'un de ses filtres est actif : sans son bouton, on ne pourrait plus le retirer
        for v in actifs:
            toutes.setdefault(v, v)
        compte: dict[str, int] = {}
        for l in lignes:
            if correspond(l, filtres, q_mots, ns, nouveau, sauf=k):
                for v in {v for v, _ in fn(l, ns)}:
                    compte[v] = compte.get(v, 0) + 1
        vals = [{"valeur": v, "libelle": lib, "n": compte.get(v, 0), "actif": v in filtres.get(k, set())} for v, lib in toutes.items()]
        if k == "confirmations":
            vals.sort(key=lambda x: x["valeur"])
        else:
            vals.sort(key=lambda x: (-x["n"], x["libelle"].casefold()))
        out.append({"id": k, "libelle": libelle, "valeurs": vals})
    return out
