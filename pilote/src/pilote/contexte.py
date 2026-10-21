"""Encadré « Contexte » (fiche 09, voie 2) : les titres, journaux et dates des articles que la recherche A DÉJÀ récupérés.

Aucune source de plus, aucune collecte de plus : on ne fait que LIRE la base de la recherche (jamais le réseau). Sans IA, on liste ; le résumé
automatique viendra avec l'IA (fiche 15) et sera alors étiqueté « résumé automatique, à vérifier ». Ce que montre l'encadré n'influence JAMAIS la
fiabilité des noms."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

ECOSYSTEMES_PRESSE = ("rss", "presse")  # étiquettes que posent les sources de presse (flux RSS, GDELT, NewsData...) sur les articles
MAX_ARTICLES = 50
NOTE = "Titres des articles déjà collectés par cette recherche. Aucune nouvelle collecte n'est faite pour les afficher."


def titre_de(texte: str) -> str:
    """Le titre est le début du texte de l'article (grappes garde « titre. résumé »)."""
    t = " ".join(texte.split())
    coupe = t.find(". ")
    return (t[:coupe] if 0 < coupe <= 220 else t[:220]).strip()


def lire(dossier_recherche: Path) -> dict[str, Any]:
    f = dossier_recherche / "donnees" / "grappes.db"
    vide = {"articles": [], "nombre": 0, "note": NOTE}
    if not f.exists():
        return vide
    c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)  # lecture seule
    try:
        marques = ",".join("?" for _ in ECOSYSTEMES_PRESSE)
        rows = c.execute(
            f"SELECT o.text, o.ts, o.raw_ref, s.display_name, s.ident FROM observations o JOIN sources s ON s.ref_key = o.source_key "
            f"WHERE s.ecosystem IN ({marques}) ORDER BY o.ts IS NULL, o.ts DESC, o.rowid DESC LIMIT ?",
            (*ECOSYSTEMES_PRESSE, MAX_ARTICLES),
        ).fetchall()
        total = c.execute(f"SELECT COUNT(*) FROM observations o JOIN sources s ON s.ref_key = o.source_key WHERE s.ecosystem IN ({marques})", ECOSYSTEMES_PRESSE).fetchone()[0]
    except sqlite3.Error:
        return vide
    finally:
        c.close()
    return {
        "articles": [{"titre": titre_de(t or ""), "source": nom or ident, "date": (ts or "")[:10], "url": url or ""} for t, ts, url, nom, ident in rows],
        "nombre": total, "note": NOTE,
    }  # fmt: skip
