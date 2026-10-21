"""Format de sortie « Texte simple » (fiche 14) : une ligne par nom, pour une lecture rapide. La trace est en tête, en lignes commençant par « # »."""

from __future__ import annotations

from pathlib import Path

from pilote.formats._commun import DECISIONS_MOTS, phrase_trace

FORMAT = {
    "id": "texte",
    "nom": "Texte simple",
    "description": "Un nom par ligne, pour une lecture rapide.",
    "extension": ".txt",
    "famille": "fichier",
    "contenus": ["nom", "detail"],
    "contenus_defaut": ["nom"],
}


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path) -> dict:
    sortie = ["# " + x for x in phrase_trace(jeu["trace"])] + [""]
    for r in jeu["lignes"]:
        if contenu == "nom":
            sortie.append(r["nom"].replace("\n", " "))
        else:
            morceaux = [r["nom"], r["ville"], r["origine_phrase"], f"{r['confirmations']} endroit(s)" if r["confirmations"] else "", DECISIONS_MOTS.get(r["decision"], "")]
            sortie.append(" — ".join(m.replace("\n", " ") for m in morceaux if m))
    chemin.write_text("\n".join(sortie) + "\n", encoding="utf-8")
    return {"fichiers": [chemin]}
