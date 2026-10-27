"""Les autres noms d'une entité (document 24, point 2) : le sigle « CEA » est déclaré par les registres, il doit traverser les adaptateurs jusqu'à la fiche.
Un alias est une PREUVE, jamais une identité : le Commissariat à l'énergie atomique et la société qui s'appelle littéralement « CEA » (même ville) ne fusionnent pas."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pilote import rapprochements
from pilote.adaptateurs import alias_de, gleif, mcp_generique, recherche_entreprises, ror
from pilote.adaptateurs.api_json import _exactes
from pilote.app import creer_app
from pilote.base import Candidat, Rapprochement, Recherche
from pilote.grappes_lib import brancher

COMMISSARIAT = "Commissariat à l'énergie atomique et aux énergies alternatives"


def test_alias_de_ne_garde_que_les_autres_noms():
    assert alias_de("CEA", ["CEA", " cea ", "", None, "Commissariat"], "Commissariat") == ["Commissariat"]  # ni le nom lui-même, ni doublon, ni vide
    assert alias_de("X", "AP-HP") == ["AP-HP"] and alias_de("X", None) == []


def test_ror_garde_les_noms_de_type_acronym_et_alias():
    """Réponse ROR v2 relevée sur le service réel (api.ror.org, requête « CEA » filtrée sur la France)."""
    rep = {"items": [{"id": "https://ror.org/00jjx8s55", "types": ["government"], "names": [
        {"value": "Atomic Energy and Alternative Energies Commission", "types": ["alias"]},
        {"value": "CEA", "types": ["acronym"]},
        {"value": "Commissariat à l'Énergie Atomique et aux Énergies Alternatives", "types": ["ror_display", "label"]},
        {"value": "Commissariat en anglais", "types": ["label"]}],
        "locations": [{"geonames_details": {"name": "Paris", "country_code": "FR"}}]}]}
    [e] = ror.convertir(rep)
    assert e["nom"].startswith("Commissariat à l'Énergie Atomique") and e["alias"] == ["Atomic Energy and Alternative Energies Commission", "CEA"]


def test_l_annuaire_des_entreprises_rend_le_sigle_declare():
    """Réponse relevée sur l'annuaire (siren 775685019) : `sigle: CEA`, et `nom_complet` qui ne le porte que collé entre parenthèses."""
    rep = {"results": [{"siren": "775685019", "nom_complet": "COMMISSARIAT A L' ENERGIE ATOMIQUE ET AUX ENERGIES ALTERNATIVES (CEA)", "sigle": "CEA", "siege": {"libelle_commune": "PARIS"}, "complements": {}},
                       {"siren": "515361517", "nom_complet": "CEA", "sigle": None, "siege": {"libelle_commune": "PARIS"}, "complements": {}}]}
    commissariat, societe = recherche_entreprises.convertir(rep)
    assert commissariat["alias"] == ["CEA"] and "alias" not in societe  # la société « CEA » n'a pas de sigle : son nom est « CEA »


def test_gleif_rend_les_autres_noms_de_l_entite():
    rep = {"data": [{"attributes": {"lei": "L", "entity": {"legalName": {"name": "DANONE OY"}, "otherNames": [{"name": "NUTRICIA MEDICAL OY", "type": "PREVIOUS_LEGAL_NAME"}], "transliteratedOtherNames": [], "legalAddress": {"city": "ESPOO", "country": "FI"}}}, "relationships": {}}]}
    assert gleif.convertir(rep)[0]["alias"] == ["NUTRICIA MEDICAL OY"]


def test_une_source_generique_lit_les_alias_dans_le_champ_declare():
    brut = json.dumps([{"name": "Commissariat", "aka": ["CEA", "Commissariat"]}, {"name": "Autre", "aka": "AUT"}])
    out = mcp_generique.convertir(brut, {"champs": {"nom": "name"}, "alias": "aka", "genre": "administration"})
    assert [e.get("alias") for e in out] == [["CEA"], ["AUT"]]


# --- retrouver : une source interrogée sur « CEA » reconnaît l'entité dont c'est le sigle déclaré
NOMS = [{"nom": "CEA IMMOBILIER", "numero": "1"}, {"nom": COMMISSARIAT, "numero": "775685019", "alias": ["CEA"]}, {"nom": "CEA", "numero": "515361517"}]


def test_une_verification_par_nom_confirme_l_entite_dont_le_sigle_est_celui_cherche():
    res = _exactes(NOMS, {"correspondance_exacte": True}, {"nom": "CEA"})
    assert [n["numero"] for n in res] == ["515361517", "775685019"]  # le nom identique d'abord, puis l'entité qui déclare ce sigle ; jamais « CEA IMMOBILIER »
    assert [n["numero"] for n in _exactes(NOMS[:2], {"correspondance_exacte": True}, {"nom": "CEA"})] == ["775685019"]  # c'était l'échec de la v1 : rien n'était trouvé


def test_les_alias_de_la_fiche_ne_font_pas_confirmer_une_autre_entite():
    """Le Commissariat (alias CEA) ne doit pas être « confirmé » par la société nommée CEA."""
    res = _exactes([{"nom": "CEA", "numero": "515361517"}], {"correspondance_exacte": True}, {"nom": COMMISSARIAT, "alias": ["CEA"]})
    assert res == []


def test_correspondance_exacte_ne_joue_pas_en_recherche_par_mots():
    noms = [{"nom": "Université de Grenoble Alpes"}, {"nom": "Université de Lyon"}]
    assert _exactes(noms, {"correspondance_exacte": True}, {"quoi": "université"}) == noms  # pas de nom à retrouver : la liste n'est pas vidée
    assert [n["nom"] for n in _exactes(noms, {"correspondance_exacte": True}, {"nom": "Université de Grenoble"})] == []  # vérifier « Université de Grenoble » : un nom voisin n'est pas une confirmation


# --- de la source à la fiche, puis au Tri
@pytest.fixture
def moteur(cfg):
    brancher(cfg)


def test_l_alias_traverse_la_decouverte_jusqu_aux_faits_de_la_fiche(moteur):
    from grappes.decouverte.registres import Decouvert

    from pilote.pont.faits import faits_candidat

    c = SimpleNamespace(nom=COMMISSARIAT, ref="reg:ror:1", ville="Paris", registres={"ror"}, citants=set(), ner_sites={})

    d = Decouvert(COMMISSARIAT, "ror", "1", "Paris", "", "", "", "administration", "", {"alias": json.dumps(["CEA", COMMISSARIAT])})
    assert faits_candidat(c, [d], lambda r: "", "FR")["faits"]["alias"] == ["CEA"]


def _app_avec(cfg, fiches):
    app = creer_app(cfg)
    with app.state.fabrique.begin() as s:
        r = Recherche(qui="test", sujet={"quoi": "x"}, parametres={}, etat="terminee")
        s.add(r)
        s.flush()
        for f in fiches:
            s.add(Candidat(recherche_id=r.id, genre_source="registre", nb_endroits=1, pays="FR", relations=[], trouve_par=["ror"], **f))
        return app, r.id


def _paires(app, rid):
    with app.state.fabrique() as s:
        return s.scalars(select(Rapprochement).where(Rapprochement.recherche_id == rid)).all()


def test_un_sigle_sans_numero_propose_une_paire_au_tri_avec_sa_raison_et_ne_fusionne_rien(cfg):
    fiches = [{"nom": "CEA", "ville": "Paris", "faits": {}},
              {"nom": COMMISSARIAT, "ville": "Paris", "numero_officiel": "775685019", "faits": {"alias": ["CEA"]}}]
    app, rid = _app_avec(cfg, fiches)
    with TestClient(app):
        assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 1
        [p] = _paires(app, rid)
        assert p.etat == "a_examiner" and "alias" in p.pourquoi and "sigle" in p.pourquoi["alias"]["niveau"]  # une personne tranche (règle 6) : rien n'est fusionné
        assert p.confiance < 0.9  # une preuve, pas une certitude


def test_la_societe_cea_et_le_commissariat_ne_sont_jamais_fusionnes(cfg, moteur):
    """Contrôle négatif obligatoire : même chaîne, même ville, seuls le numéro officiel et l'activité les séparent."""
    from grappes.classement.fusion import _groupes
    from grappes.decouverte.registres import Decouvert

    groupes = _groupes([Decouvert("CEA", "sirene", "515361517", "Paris", "", "515361517"),
                        Decouvert(COMMISSARIAT, "sirene", "775685019", "Paris", "", "775685019", liens={"alias": json.dumps(["CEA"])})])
    assert len(groupes) == 2  # le moteur regroupe par SIREN, sinon par nom : l'alias n'y entre pas
    fiches = [{"nom": "CEA", "ville": "Paris", "numero_officiel": "515361517", "faits": {}},
              {"nom": COMMISSARIAT, "ville": "Paris", "numero_officiel": "775685019", "faits": {"alias": ["CEA"]}}]
    app, rid = _app_avec(cfg, fiches)
    with TestClient(app):
        assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 0  # deux numéros officiels différents : deux entités
        assert _paires(app, rid) == []


def test_le_moteur_de_rapprochement_tourne_quand_aucune_fiche_n_a_d_alias():
    """Colonne d'alias entièrement vide : DuckDB la type en entiers ; sans conversion explicite la comparaison plantait (« moteur indisponible » pour toute recherche sans alias)."""
    from pilote.rapprochement_splink import scorer

    sans = [{"id": 1, "nom": "Club Alpin de Lyon", "ville": "Lyon", "numero": ""}, {"id": 2, "nom": "Club alpin Lyon", "ville": "Lyon", "numero": "", "alias": []}]
    assert len(scorer(sans, 0.2)) == 1
    avec = [{"id": 1, "nom": "CEA", "ville": "Paris", "numero": ""}, {"id": 2, "nom": COMMISSARIAT, "ville": "Paris", "numero": "775685019", "alias": ["CEA"]}]
    assert scorer(avec, 0.2)[0]["pourquoi"]["alias"]["niveau"].startswith("un nom déclaré en commun")
