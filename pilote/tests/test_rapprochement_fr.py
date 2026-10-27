"""Non-régression de Fusion/doublons sur le jeu de cas difficiles français (document 20 : on n'ajuste jamais un seuil sur un seul exemple)."""

import sys

import pytest

from pilote.rapprochements import SEUIL

sys.path.insert(0, "outils")
from mesurer_rapprochement_fr import mesurer

CONNUS_OUVERTS: set[str] = set()  # faux positifs connus : proposés à la personne dans le Tri, jamais fusionnés seuls. « croix-rouge-delegation » (57 %) en est sorti le 27/10 : un mot de structure (délégation) d'un seul côté.


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


def test_les_sigles_declares_par_un_registre_sont_proposes(res):
    """Document 25 : la classe qui avait produit l'échec franc du test réel (CEA). Elle passe grâce aux alias, pas parce que le seuil a baissé."""
    sigles = [r for r in res if r["id"].startswith("sigle-")]
    assert len(sigles) == 6 and all(r["confiance"] >= SEUIL for r in sigles), [(r["id"], r["confiance"]) for r in sigles]


def test_le_sigle_d_un_registre_ne_fusionne_pas_une_autre_entite_qui_porte_ce_nom(res):
    """L'alias est une preuve, pas une identité : seul le numéro officiel sépare le Commissariat et la société « CEA »."""
    cas = next(r for r in res if r["id"] == "cea-contre-societe-cea")
    assert cas["confiance"] < SEUIL


def test_les_homonymes_exacts_sont_departages_par_le_numero(res):
    assert all(r["confiance"] < SEUIL for r in res if r["id"].startswith("homonyme-"))


def test_le_jeu_porte_ses_trois_classes_de_cas_ajoutees():
    import json
    from pathlib import Path

    cas = [json.loads(ligne) for ligne in Path("autocal_rapprochement_fr/cas.jsonl").read_text(encoding="utf-8").splitlines() if ligne.strip()]
    assert len(cas) == 38 and sum(c["verdict"] == "meme" for c in cas) == 18 and sum(c["verdict"] == "differentes" for c in cas) == 20
    assert all("numero" in c["a"] and "numero" in c["b"] for c in cas if c["id"].startswith("homonyme-"))  # un cas d'homonymes sans numéro serait indécidable (document 25, § 4)
