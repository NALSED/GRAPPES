"""Sources P1 de la spécification 17 branchées le 26/10 : chacune se charge, son test local passe sur l'exemple enregistré, elle est éteinte à la livraison."""

import pytest

from pilote import reglages as rg
from pilote.sources import charger_sources
from pilote.tests_source import tester

IDS = ["propublica-nonprofit", "photon", "radio-browser", "lemmy", "sepiasearch"]


@pytest.mark.parametrize("ident", IDS)
def test_source_p1_charge_teste_et_eteinte(cfg, ident):
    decls, problemes = charger_sources(cfg)
    assert not problemes and ident in decls
    d = decls[ident]
    assert rg.choix_source(rg.charger_tolerant(cfg)[0], d)["chercher"] is False  # éteinte à la livraison
    assert "personne" not in d.genres  # règle 8 : jamais une recherche par nom de personne physique
    res = tester(cfg, d)
    assert res["statut"] == "ok" and res["noms_exemple"], res
