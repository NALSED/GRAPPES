"""Outils communs aux formats de sortie (fiche 14) : les colonnes du détail, la trace, la neutralisation des formules. Ce module n'est pas un
format (son nom commence par « _ ») : le programme ne le liste jamais."""

from __future__ import annotations

import re

COLONNES_DETAIL = ["nom", "ville", "pays", "origine", "confirmations", "fonction", "genre", "site", "numero_officiel", "decision", "motif_rejet", "sources", "relations"]
DECISIONS_MOTS = {"garder": "gardé", "rejeter": "rejeté", "plus_tard": "mis de côté", None: ""}
ILLEGAUX_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def cellule(t: object) -> str:
    """Texte neutralisé contre l'injection de formule d'un tableur (une cellule qui commence par = + - @ serait exécutée)."""
    s = str(t if t is not None else "").replace("\r", " ").replace("\n", " ")
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t") else s


def propre_xml(t: object) -> str:
    return ILLEGAUX_XML.sub("", str(t if t is not None else ""))


def ligne_detail(r: dict) -> list[str]:
    return [r["nom"], r["ville"], r["pays"], r["origine_phrase"], str(r["confirmations"]) if r["confirmations"] is not None else "", r["fonction"], r["genre"], r["site"], r["numero_officiel"],
            DECISIONS_MOTS.get(r["decision"], ""), r["motif_rejet"], " | ".join(r["sources"]), " | ".join(f"{x['type'].replace('_', ' ')} : {x['vers']}" for x in r["relations"])]  # fmt: skip


def phrase_trace(t: dict) -> list[str]:
    """La trace en lignes lisibles : de quoi rejouer le résultat (quand, quoi, avec quelles sources, quel filtre)."""
    return [
        f"Exporté le {t['date']} par pilote",
        f"Sujet cherché : {t['sujet']}",
        f"Recherche : {t['recherche']} ({t['nombre']} nom{'s' if t['nombre'] > 1 else ''} exporté{'s' if t['nombre'] > 1 else ''}, {t['filtre']})",
        "Sources utilisées : " + (", ".join(s["nom"] for s in t["sources"]) or "aucune"),
    ]


def suffixe(contenu: str, contenus: list[str], defaut: list[str] | None = None) -> str:
    """Le contenu principal du format (le premier de ses contenus par défaut) garde le nom de base (resultat.csv, resultat.json) ; les autres ajoutent
    leur mot (resultat_tsites.csv, resultat_detail.csv) ; un format à un seul contenu n'en ajoute jamais."""
    principal = (defaut or contenus)[0]
    return "" if contenu == principal or len(contenus) == 1 else "_" + contenu
