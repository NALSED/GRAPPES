"""Sources P1 de la spécification 17 branchées le 26/10 : chacune se charge, son test local passe sur l'exemple enregistré, elle est éteinte à la livraison."""

import pytest

from pilote import reglages as rg
from pilote.sources import charger_sources
from pilote import tests_source

IDS = ["propublica-nonprofit", "photon", "radio-browser", "lemmy", "sepiasearch"]


@pytest.mark.parametrize("ident", IDS)
def test_source_p1_charge_teste_et_eteinte(cfg, ident):
    decls, problemes = charger_sources(cfg)
    assert not problemes and ident in decls
    d = decls[ident]
    assert rg.choix_source(rg.charger_tolerant(cfg)[0], d)["chercher"] is False  # éteinte à la livraison
    assert "personne" not in d.genres  # règle 8 : jamais une recherche par nom de personne physique
    res = tests_source.tester(cfg, d)
    assert res["statut"] == "ok" and res["noms_exemple"], res


NOUVELLES = ["serper", "firecrawl", "guardian", "nyt", "bodacc", "prh-finlande", "amf-info-financiere", "nz-charities", "acnc", "mobilizon", "universites", "mediacloud"]


@pytest.mark.parametrize("ident", NOUVELLES)
def test_source_p1_deuxieme_lot(cfg, ident, monkeypatch):
    decls, problemes = charger_sources(cfg)
    assert not problemes and ident in decls
    d = decls[ident]
    for cle in d.cles:
        monkeypatch.setenv(cle, "cle-de-test")  # le test local ne l'envoie jamais ; il exige seulement qu'elle soit présente
    assert rg.choix_source(rg.charger_tolerant(cfg)[0], d)["chercher"] is False and rg.choix_source(rg.charger_tolerant(cfg)[0], d)["verifier"] is False
    assert "personne" not in d.genres
    res = tests_source.tester(cfg, d)
    assert res["statut"] == "ok", res
    if d.moteur.get("adaptateur"):  # les sources de type « adaptateur » rendent des noms ; les autres passent par le moteur de collecte
        assert res["noms_exemple"]


def test_une_verification_exacte_ne_confirme_que_le_meme_nom():
    from pilote.adaptateurs.api_json import _exactes

    noms = [{"nom": "DUPONT & DUPONT"}, {"nom": "Dupont Sports SAS"}, {"nom": "SAS DUPONT & DUPONT"}]
    assert [n["nom"] for n in _exactes(noms, {"correspondance_exacte": True}, {"nom": "Dupont & Dupont"})] == ["DUPONT & DUPONT", "SAS DUPONT & DUPONT"]  # forme juridique et casse mises à part
    assert _exactes(noms, {}, {"nom": "x"}) == noms  # sans l'option, rien n'est filtré
    assert _exactes(noms, {"correspondance_exacte": True}, {"nom": ""}) == []  # sans nom à vérifier, rien n'est confirmé


def test_un_chemin_peut_viser_le_premier_element_d_une_liste():
    from pilote.adaptateurs.mcp_generique import _lire

    assert _lire({"names": [{"name": "A"}, {"name": "B"}]}, "names.0.name") == "A" and _lire({"names": []}, "names.0.name") is None


# --- [ ] Une source choisie n'est jamais mangée en silence par la collecte web : elle garde un appel, et si elle n'est pas appelée, c'est dit.
def test_une_reserve_d_appels_est_gardee_pour_les_sources_par_adaptateur(cfg, tmp_path):
    import json

    from pilote.executeur_grappes import preparer

    class FauxContexte:
        recherche_id, qui = "r23", "test"
        sujet = {"quoi": "red cross"}
        parametres = {"sources": ["nz-charities", "acnc", "wikipedia"], "profondeur": "normal"}
        dossier = tmp_path / "travail"
        _fabrique = None

        def __init__(self):
            self.dossier.mkdir(parents=True, exist_ok=True)

    spec = preparer(cfg, FauxContexte())
    assert spec["reserve_sources"] == 2 == len(spec["adaptateurs"])  # un appel gardé par source interrogée par adaptateur
    auto = json.loads(json.dumps(spec))  # la spécification écrite est bien celle qui part au pont
    assert auto["limites"]["appels"] >= spec["reserve_sources"]
