"""Non-régression de Fusion/doublons sur le jeu de cas difficiles français (document 20 : on n'ajuste jamais un seuil sur un seul exemple)."""

import sys

import pytest

from pilote.rapprochements import SEUIL

sys.path.insert(0, "outils")
from mesurer_rapprochement_fr import mesurer

CONNUS_OUVERTS = {"croix-rouge-delegation"}  # faux positif connu (57 %) : proposé à la personne dans le Tri, jamais fusionné seul. Il sort de cette liste le jour où il est réglé.


@pytest.fixture(scope="module")
def res():
    return mesurer()


def test_aucune_paire_de_personnes_morales_distinctes_n_est_proposee_hors_cas_connus(res):
    faux = {r["id"] for r in res if r["verdict"] == "differentes" and r["confiance"] >= SEUIL}
    assert faux == CONNUS_OUVERTS, faux


def test_les_memes_entites_sont_proposees(res):
    manques = [r["id"] for r in res if r["verdict"] == "meme" and r["confiance"] < SEUIL]
    assert manques == []


def test_la_fondation_abbe_pierre_n_est_pas_emmaus(res):
    assert all(r["confiance"] < SEUIL for r in res if r["id"].startswith("fondation-abbe-pierre-emmaus"))
