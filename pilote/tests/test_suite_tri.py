"""Onglet Tri (spécification 16) : Splink propose, une personne tranche. Ces tests font tourner le VRAI Splink (dans son processus à part)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pilote import rapprochements
from pilote.app import creer_app
from pilote.base import Candidat, Journal, Rapprochement, Recherche


@pytest.fixture
def app(cfg):
    return creer_app(cfg)


@pytest.fixture
def c(app):
    with TestClient(app) as client:
        yield client


def creer(app, noms):
    """Une recherche et ses noms ; `noms` : [dict(nom, ville, numero_officiel, genre_de_chose, trouve_par, relations)]. Rend (id de recherche, {nom: id})."""
    with app.state.fabrique.begin() as s:
        r = Recherche(qui="test", sujet={"quoi": "x"}, parametres={}, etat="terminee")
        s.add(r)
        s.flush()
        ids = {}
        for n in noms:
            cand = Candidat(recherche_id=r.id, **{"genre_source": "registre", "nb_endroits": 1, "pays": "FR", "faits": {}, "relations": [], "trouve_par": ["registre-associations"], **n})
            s.add(cand)
            s.flush()
            ids[n["nom"]] = cand.id
        return r.id, ids


TROIS = [
    {"nom": "Les Amis du Vercors", "ville": "Grenoble", "numero_officiel": "W382001234", "genre_de_chose": "association", "trouve_par": ["registre-associations"]},
    {"nom": "Amis du Vercors Randonnée", "ville": "Grenoble", "genre_de_chose": "association", "trouve_par": ["wikipedia"]},
    {"nom": "Fondation Example", "ville": "Lyon", "numero_officiel": "412 345 678", "genre_de_chose": "association", "trouve_par": ["wikipedia"]},
    {"nom": "FONDATION EXAMPLE", "ville": "Lyon", "genre_de_chose": "association", "trouve_par": ["tavily"]},
    {"nom": "Coopérative du Grésivaudan", "ville": "Grenoble", "numero_officiel": "501 234 567", "genre_de_chose": "entreprise", "trouve_par": ["recherche-entreprises"]},
    {"nom": "Coopérative du Grésivaudan", "ville": "Grenoble", "numero_officiel": "501234567", "genre_de_chose": "entreprise", "trouve_par": ["registre-associations"]},
    {"nom": "Boulangerie Martin", "ville": "Lyon"},
    {"nom": "Boulangerie Dupont", "ville": "Lyon"},
]


def test_splink_propose_du_moins_certain_au_plus_certain(c, app, cfg):
    rid, ids = creer(app, TROIS)
    r = rapprochements.proposer(cfg, app.state.fabrique, rid)
    assert r["proposes"] == 3 and r["comparees"] == 8  # les deux boulangeries (noms voisins, deux artisans) ne sont pas proposées
    f = c.get("/api/suite/tri").json()
    assert [x["confiance"] for x in f["a_examiner"]] == sorted(x["confiance"] for x in f["a_examiner"])  # du plus incertain au plus certain
    bas, milieu, haut = f["a_examiner"]
    assert 20 <= bas["confiance"] < 60 and 60 <= milieu["confiance"] < 95 and haut["confiance"] >= 95
    assert bas["titre"] == "deux fiches d'association, nom proche"
    assert milieu["titre"] == "deux fiches d'association, nom identique, un identifiant manquant"
    assert haut["titre"] == "deux fiches d'entreprise, identifiant officiel identique"  # « 501 234 567 » et « 501234567 » : le même numéro
    assert set(bas["pourquoi"]) == {"nom", "ville", "numero"} and bas["pourquoi"]["numero"]["niveau"] == "absent d'un côté"  # on voit POURQUOI deux fiches sont rapprochées


def test_la_comparaison_champ_par_champ(c, app, cfg):
    rid, ids = creer(app, TROIS[:2])
    rapprochements.proposer(cfg, app.state.fabrique, rid)
    carte = c.get("/api/suite/tri").json()["a_examiner"][0]
    gauche, droite = carte["fiches"]
    assert [x["champ"] for x in gauche["lignes"]] == ["nom", "ville", "numero", "genre"] == [x["champ"] for x in droite["lignes"]]  # mêmes lignes, même ordre des deux côtés
    etats = {x["champ"]: x["etat"] for x in gauche["lignes"]}
    assert etats == {"nom": "desaccord", "ville": "accord", "numero": "absence", "genre": "accord"}  # une valeur absente n'est JAMAIS une différence
    assert [x["etat"] for x in droite["lignes"]] == [x["etat"] for x in gauche["lignes"]]  # le même style des deux côtés
    assert gauche["source"].startswith("Registre des associations") and gauche["fiabilite"] == "B" and droite["fiabilite"] == "C"  # la source et sa lettre de fiabilité


def test_aucune_fiche_de_personne_physique_n_entre_dans_un_rapprochement(c, app, cfg):
    rid, _ = creer(app, [{"nom": "Jean Martin", "ville": "Lyon", "genre_de_chose": "personne"}, {"nom": "Jean Martin", "ville": "Lyon", "genre_de_chose": "personne"}, {"nom": "Club Alpin", "ville": "Lyon"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid) == {"proposes": 0, "comparees": 1}  # règle 8
    assert c.get("/api/suite/tri").json() == {"a_examiner": [], "tranches": []}


def test_deux_entites_deja_liees_par_une_source_ne_sont_pas_proposees(c, app, cfg):
    rid, _ = creer(app, [{"nom": "Dupont Sports", "ville": "Lyon", "relations": [{"type": "etablissement_de", "vers": "Dupont Sports Lyon", "source": "x"}]}, {"nom": "Dupont Sports Lyon", "ville": "Lyon"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 0  # siège et établissement : deux entités différentes, dites telles par la source


def test_confirmer_lie_les_deux_fiches_et_se_refait(c, app, cfg):
    rid, ids = creer(app, TROIS[2:4])
    rapprochements.proposer(cfg, app.state.fabrique, rid)
    pid = c.get("/api/suite/tri").json()["a_examiner"][0]["id"]
    assert c.post(f"/api/suite/tri/{pid}/confirmer", json={"qui": "sednal"}).json() == {"id": pid, "etat": "confirme"}
    with app.state.fabrique() as s:
        for nom, autre in (("Fondation Example", "FONDATION EXAMPLE"), ("FONDATION EXAMPLE", "Fondation Example")):
            cand = s.get(Candidat, ids[nom])
            assert [x["vers"] for x in cand.relations if x["type"] == "meme_entite"] == [autre]  # les deux côtés, et les fiches elles-mêmes intactes
            assert cand.nom == nom
    f = c.get("/api/suite/tri").json()
    assert f["a_examiner"] == [] and f["tranches"][0]["etat"] == "confirme" and f["tranches"][0]["decide_par"] == "sednal"  # rien ne disparaît : la décision reste lisible
    # changer d'avis : séparer retire le lien, sans rien laisser derrière ; le rapprochement n'est pas reproposé
    assert c.post(f"/api/suite/tri/{pid}/separer", json={}).json()["etat"] == "separe"
    with app.state.fabrique() as s:
        assert all(not s.get(Candidat, i).relations for i in ids.values())
        assert [e.evenement for e in s.scalars(select(Journal).where(Journal.evenement.like("rapprochement_%")))] == ["rapprochements_proposes", "rapprochement_confirme", "rapprochement_separe"]
    assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 0
    assert c.get("/api/suite/tri").json()["tranches"][0]["etat"] == "separe"
    assert c.post("/api/suite/tri/999/confirmer", json={}).status_code == 404


def test_un_moteur_qui_ne_tourne_pas_est_dit_et_ne_fait_rien_croire(c, app, cfg, monkeypatch):
    rid, _ = creer(app, TROIS[:2])

    def casse(fiches, seuil):
        raise rapprochements.Indisponible("Le moteur de rapprochement (Splink) n'a pas pu tourner : Illegal instruction")

    monkeypatch.setattr(rapprochements, "_scorer", casse)
    r = c.post(f"/api/suite/tri/proposer/{rid}")
    assert r.status_code == 503 and "Splink" in r.json()["detail"]
    with app.state.fabrique() as s:
        assert s.scalars(select(Rapprochement)).all() == []
