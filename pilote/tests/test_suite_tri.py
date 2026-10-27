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
    assert 20 <= bas["confiance"] < 60 and milieu["confiance"] >= 50 and haut["confiance"] >= 95
    assert bas["titre"] == "deux fiches d'association, nom proche"
    assert milieu["titre"] == "deux fiches d'association, nom identique, un identifiant manquant"
    assert haut["titre"] == "deux fiches d'entreprise, identifiant officiel identique"  # « 501 234 567 » et « 501234567 » : le même numéro
    assert set(bas["pourquoi"]) == {"nom", "distinctif", "chiffres", "ville", "numero"} and bas["pourquoi"]["numero"]["niveau"] == "absent d'un côté"  # on voit POURQUOI deux fiches sont rapprochées


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


# --- Partie 1 de test.md : deux entités distinctes ne se rapprochent pas sur la foi du nom seul
def test_deux_entites_de_meme_nom_et_de_numeros_differents_ne_sont_pas_proposees(c, app, cfg):
    rid, _ = creer(app, [{"nom": "Boulangerie Martin", "ville": "Lyon", "numero_officiel": "W111111111"}, {"nom": "Boulangerie Martin", "ville": "Lyon", "numero_officiel": "W222222222"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 0  # deux numéros officiels différents : deux entités, pas un doublon
    rid2, _ = creer(app, [{"nom": "Club Alpin", "ville": "Lyon"}, {"nom": "Club Alpin", "ville": "Paris"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid2)["proposes"] == 0  # homonymes de villes différentes


def test_un_siret_et_son_siren_sont_la_meme_entite(c, app, cfg):
    rid, _ = creer(app, [{"nom": "Dupont Sports SAS", "ville": "Grenoble", "numero_officiel": "123 456 789"}, {"nom": "DUPONT SPORTS", "ville": "Grenoble", "numero_officiel": "123 456 789 00012"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 1
    assert c.get("/api/suite/tri").json()["a_examiner"][0]["confiance"] >= 90  # un siège et son établissement ne se contredisent pas


def test_deux_etablissements_d_une_meme_entreprise_ne_sont_pas_des_doublons(c, app, cfg):
    """Cas réel (Danone) : deux SIRET différents d'un même SIREN sont deux établissements, jamais proposés comme la même fiche."""
    rid, _ = creer(app, [{"nom": "DANONE PRODUITS FRAIS — Ferrières", "ville": "Ferrières", "numero_officiel": "34012345600017"}, {"nom": "DANONE PRODUITS FRAIS — Le Mans", "ville": "Le Mans", "numero_officiel": "34012345600025"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 0


def test_des_fonds_numerotes_ne_sont_pas_des_fautes_de_frappe(c, app, cfg):
    """Cas réel (La Banque Postale Innovation 3 / 5 / 8…) : un chiffre qui diffère fait deux entités, pas un doublon."""
    rid, _ = creer(app, [{"nom": f"Fcpi La Banque Postale Innovation {n}", "ville": "Paris", "genre_de_chose": "entreprise"} for n in (3, 5, 8)] + [{"nom": "La Banque Postale Innovation 3", "ville": "Paris"}])
    r = rapprochements.proposer(cfg, app.state.fabrique, rid)
    cartes = c.get("/api/suite/tri").json()["a_examiner"]
    assert r["proposes"] <= 1 and all("3" in str([f["lignes"][0]["valeur"] for f in x["fiches"]]) for x in cartes)  # seule la paire aux MÊMES chiffres peut rester


def test_des_clubs_aux_noms_generiques_ne_sont_pas_des_doublons(c, app, cfg):
    """Partie 2 de test.md (S3) : « Association sportive de Cannes » et « … de Monaco » ne diffèrent que par leur ville-nom : deux clubs."""
    rid, _ = creer(app, [{"nom": n} for n in ("Association sportive de Cannes", "Association sportive de Monaco", "Association sportive Casino", "ASSOCIATION SPORTIVE", "Association sportive de Cannes (football)")])
    rapprochements.proposer(cfg, app.state.fabrique, rid)
    noms = [{f["lignes"][0]["valeur"] for f in x["fiches"]} for x in c.get("/api/suite/tri").json()["a_examiner"]]
    assert noms == [{"Association sportive de Cannes", "Association sportive de Cannes (football)"}]  # seule la vraie variante d'un même club reste


def test_une_faute_de_frappe_reste_un_rapprochement(c, app, cfg):
    rid, _ = creer(app, [{"nom": "Club Alpin de Grenoble", "ville": "Grenoble"}, {"nom": "Club Alpin de Grenobel", "ville": "Grenoble"}])
    assert rapprochements.proposer(cfg, app.state.fabrique, rid)["proposes"] == 1


# --- Décision du 27/10 (doc 13) : « X sur Y noms vérifiés » visible, jamais une absence de signalement prise pour une vérification
def test_la_recherche_sauvegardee_dit_combien_de_noms_ont_ete_verifies(c, app):
    with app.state.fabrique.begin() as s:
        r = Recherche(qui="test", sujet={"quoi": "x"}, parametres={}, etat="terminee", avancement={"verifications": [{"source": "bodacc", "examines": 4, "a_verifier": 127, "complete": False}]})
        s.add(r)
        s.flush()
        rid = r.id
    assert c.post("/api/suite/recherches", json={"mode": "Simple", "titre": "banques", "recherche_id": rid}).status_code == 201
    v = c.get("/api/suite/etat").json()["recherches"][0]["verification"]
    assert "4 sur 127 noms vérifiés" in v
