"""Mesure de l'ordre des résultats (document 24, point 5) : l'outil tourne dans l'interpréteur de grappes, qui porte `pytrec_eval`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
OUTIL = RACINE / "outils" / "mesurer_classement.py"


def lancer(cfg, *args):
    return subprocess.run([str(cfg.python_grappes), str(OUTIL), *args], capture_output=True, text=True, check=True, timeout=120).stdout


def test_l_ordre_d_un_cas_connu_est_mesure_a_la_main(cfg, tmp_path):
    """5 résultats rendus, 3 attendus : juste, faux, juste, non vérifiable, faux. Dans les 3 premiers : 2 justes, donc R-précision 2/3.
    Paires juste/faux : (1er, 2e) oui, (1er, 5e) oui, (3e, 2e) non, (3e, 5e) oui : AUC 3/4."""
    cas = {"id": "essai", "phrase": "cas à la main", "attendus": 3, "rendus": [{"nom": n, "verdict": v} for n, v in [("a", "juste"), ("b", "faux"), ("c", "juste"), ("d", "non_verifiable"), ("e", "faux")]]}
    f = tmp_path / "cas.jsonl"
    f.write_text(json.dumps(cas) + "\n", encoding="utf-8")
    sortie = lancer(cfg, "--cas", str(f))
    ligne = next(x for x in sortie.splitlines() if x.startswith("essai"))
    assert "0.667" in ligne and "0.750" in ligne, ligne


def test_le_jeu_francais_vide_se_mesure_sans_planter(cfg):
    assert "MOYENNE" in lancer(cfg, "--cas", str(RACINE / "autocal_classement_fr" / "cas.jsonl"))  # un jeu vide ne produit qu'une ligne de moyenne sans valeur


def test_un_rejeu_de_l_autocalibrage_est_lu_sans_etre_modifie(cfg, tmp_path):
    rejeu = {"sujets": [{"id": "s1", "phrase": "p", "R": 4, "Rprec": 0.25, "bpref": 0.2, "rang": [{"nom": "x", "verdict": "juste"}, {"nom": "y", "verdict": "faux"}]},
                        {"id": "temoin", "phrase": "t"}]}
    f = tmp_path / "rejeu.json"
    f.write_text(json.dumps(rejeu), encoding="utf-8")
    avant = f.read_bytes()
    sortie = lancer(cfg, "--rejeu", str(f))
    assert "0.250" in sortie and "0.200" in sortie and "1.000" in sortie  # R-précision et bpref du fichier repris tels quels ; le juste est avant le faux
    assert f.read_bytes() == avant
