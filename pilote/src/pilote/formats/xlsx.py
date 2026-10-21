"""Format de sortie « Excel » (fiche 14) : un classeur à plusieurs onglets — noms, détail, sources, trace. Pour qui ne travaille qu'avec Excel.
Bibliothèque : openpyxl (MIT). Les cellules qui commenceraient par = + - @ sont neutralisées (injection de formule)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pilote.formats._commun import COLONNES_DETAIL, cellule, ligne_detail, phrase_trace

FORMAT = {
    "id": "xlsx",
    "nom": "Excel",
    "description": "Un classeur à plusieurs onglets : noms gardés, détail, sources, trace.",
    "extension": ".xlsx",
    "famille": "fichier",
    "contenus": ["nom", "detail"],
    "contenus_defaut": ["detail"],
}


def _onglet(wb, titre: str, entete: list[str], lignes: list[list[str]]):
    ws = wb.create_sheet(titre)
    ws.append(entete)
    for ligne in lignes:
        ws.append([cellule(c) for c in ligne])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(60, max(10, *(len(str(c.value or "")) for c in col)) + 2)
    ws.freeze_panes = "A2"
    return ws


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path) -> dict:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    _onglet(wb, "Noms", ["nom", "ville", "pays"], [[r["nom"], r["ville"], r["pays"]] for r in jeu["lignes"]])
    if contenu != "nom":
        _onglet(wb, "Détail", COLONNES_DETAIL, [ligne_detail(r) for r in jeu["lignes"]])
        compte = Counter(s for r in jeu["lignes"] for s in r["sources"])
        _onglet(wb, "Sources", ["source", "noms"], [[s, str(n)] for s, n in sorted(compte.items(), key=lambda x: (-x[1], x[0]))])
    _onglet(wb, "Trace", ["trace"], [[x] for x in phrase_trace(jeu["trace"])])
    wb.save(chemin)
    return {"fichiers": [chemin]}
