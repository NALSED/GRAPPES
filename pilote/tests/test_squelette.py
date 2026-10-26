"""Étape 1 : service, configuration, base, objet recherche, tâche de fond, HTTPS."""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pilote.app import creer_app
from pilote.base import Candidat, Decision, Journal, Recherche, creer_fabrique
from pilote.config import charger
from pilote.taches import Arret, ContexteRecherche


@pytest.fixture
def cfg(tmp_path):
    f = tmp_path / "config" / "pilote.yaml"
    f.parent.mkdir()
    f.write_text(
        f"service: {{port: 9999, https: false, hotes_autorises: [testserver]}}\ngrappes: {{racine: {tmp_path / 'g'}, config: config}}\n"
        f"donnees: {{dossier: {tmp_path / 'd'}}}\ntravail: {{fils: 2}}\nqui_par_defaut: sednal\n", encoding="utf-8")
    return charger(f)


def attendre(client, rid, finaux=("terminee", "arretee", "echec", "interrompue"), delai=10):
    t0 = time.time()
    while time.time() - t0 < delai:
        r = client.get(f"/api/recherches/{rid}").json()
        if r["etat"] in finaux:
            return r
        time.sleep(0.05)
    raise AssertionError(f"pas fini : {r}")


def test_configuration_aucun_chemin_en_dur(cfg, tmp_path):
    assert cfg.service.port == 9999 and not cfg.service.https
    assert cfg.grappes_racine == tmp_path / "g"  # vient de la configuration
    assert cfg.dossier_grappes_config == tmp_path / "g" / "config"
    assert cfg.dossier_recherche("abc") == tmp_path / "d" / "recherches" / "abc"  # nommé d'après l'identifiant


def test_configuration_livree_est_lisible():
    c = charger()
    assert c.service.port == 8443 and c.service.https and c.service.hote == "127.0.0.1"
    assert str(c.grappes_racine) == "/opt/grappes" and c.fils >= 1


def test_la_requete_repond_sans_attendre_la_fin(cfg):
    porte = threading.Event()

    def lent(ctx: ContexteRecherche):
        porte.wait(10)

    with TestClient(creer_app(cfg, lent)) as c:
        t0 = time.time()
        r = c.post("/api/recherches", json={"sujet": {"quoi": "clubs de handball"}, "parametres": {"profondeur": 1}})
        assert r.status_code == 202 and time.time() - t0 < 2
        rid = r.json()["id"]
        assert c.get(f"/api/recherches/{rid}").json()["etat"] in ("en_attente", "en_cours")
        porte.set()
        fin = attendre(c, rid)
        assert fin["etat"] == "terminee" and fin["qui"] == "sednal" and fin["sujet"]["quoi"] == "clubs de handball"


def test_candidats_et_avancement_s_attachent_a_la_recherche(cfg):
    def travail(ctx: ContexteRecherche):
        ctx.avancer(source="SIRENE", appels_faits=1, appels_prevus=5, noms=2)
        ctx.ajouter_candidats([
            {"nom": "Club A", "genre_source": "registre", "trouve_par": ["sirene"], "ville": "Lille"},
            {"nom": "Club B", "genre_source": "presse", "trouve_par": ["franceinfo"]},
        ])
        assert ctx.dossier.name == ctx.recherche_id  # dossier de travail = identifiant

    app = creer_app(cfg, travail)
    with TestClient(app) as c:
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "x"}}).json()["id"]
        fin = attendre(c, rid)
        assert fin["avancement"]["source"] == "SIRENE" and fin["avancement"]["appels_prevus"] == 5
        with app.state.fabrique() as s:
            noms = [x.nom for x in s.scalars(select(Candidat).where(Candidat.recherche_id == rid))]
        assert noms == ["Club A", "Club B"]
        assert (cfg.donnees / "recherches" / rid).is_dir()


def test_panne_de_l_executeur_finit_en_echec_lisible_et_garde_l_acquis(cfg):
    def casse(ctx):
        ctx.ajouter_candidats([{"nom": "Gardé", "genre_source": "web"}])
        raise RuntimeError("la source ne répond pas")

    app = creer_app(cfg, casse)
    with TestClient(app) as c:
        rid = c.post("/api/recherches", json={}).json()["id"]
        fin = attendre(c, rid)
        assert fin["etat"] == "echec" and "la source ne répond pas" in fin["message"]
        with app.state.fabrique() as s:
            assert s.scalars(select(Candidat).where(Candidat.recherche_id == rid)).all()


def test_executeur_par_defaut_dit_en_clair_quand_grappes_est_introuvable(cfg):
    with TestClient(creer_app(cfg)) as c:
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "x"}}).json()["id"]
        fin = attendre(c, rid)
        assert fin["etat"] == "echec" and "configuration de grappes est introuvable" in fin["message"]


def test_arret_garde_l_acquis(cfg):
    def boucle(ctx: ContexteRecherche):
        ctx.ajouter_candidats([{"nom": "Déjà trouvé", "genre_source": "registre"}])
        while not ctx.doit_s_arreter():
            time.sleep(0.02)
        raise Arret()

    app = creer_app(cfg, boucle)
    with TestClient(app) as c:
        rid = c.post("/api/recherches", json={}).json()["id"]
        t0 = time.time()
        while c.get(f"/api/recherches/{rid}").json()["etat"] != "en_cours" and time.time() - t0 < 5:
            time.sleep(0.02)
        assert c.post(f"/api/recherches/{rid}/arret").json()["arret_demande"] is True
        fin = attendre(c, rid)
        assert fin["etat"] == "arretee" and "gardé" in fin["message"]
        with app.state.fabrique() as s:
            assert len(s.scalars(select(Candidat).where(Candidat.recherche_id == rid)).all()) == 1


def test_chaque_action_porte_un_qui(cfg):
    app = creer_app(cfg, lambda ctx: None)
    with TestClient(app) as c:
        rid = c.post("/api/recherches", json={"qui": "sednal"}).json()["id"]
        attendre(c, rid)
        c.post(f"/api/recherches/{rid}/arret")
        j = c.get(f"/api/recherches/{rid}/journal").json()
        assert {x["evenement"] for x in j} >= {"creation", "debut", "fin", "arret_demande"}
        assert all(x["qui"] for x in j)


def test_recherche_inconnue_404(cfg):
    with TestClient(creer_app(cfg)) as c:
        assert c.get("/api/recherches/nope").status_code == 404
        assert c.get("/api/sante").json()["ok"] is True


def test_recherche_restee_en_cours_est_marquee_interrompue_au_redemarrage(cfg):
    url = cfg.url_base
    f = creer_fabrique(url)
    with f.begin() as s:
        s.add(Recherche(id="vieille", qui="sednal", etat="en_cours"))
    with TestClient(creer_app(cfg)) as c:
        r = c.get("/api/recherches/vieille").json()
        assert r["etat"] == "interrompue" and "gardé" in r["message"]


def test_decisions_reservees_a_l_utilisateur_avec_qui_et_lot(cfg):
    f = creer_fabrique(cfg.url_base)
    with f.begin() as s:
        s.add(Recherche(id="r1", qui="sednal"))
        s.flush()
        s.add(Candidat(recherche_id="r1", nom="X"))
        s.flush()
        s.add(Decision(recherche_id="r1", candidat_id=1, valeur="garder", qui="sednal", lot="lot1"))
    with f() as s:
        d = s.scalars(select(Decision)).one()
        assert (d.valeur, d.qui, d.lot, d.annulee) == ("garder", "sednal", "lot1", False)
        assert s.scalars(select(Journal)).all() == []


def test_https_certificat_auto_signe(cfg, tmp_path):
    from dataclasses import replace

    from pilote.tls import certificat

    cfg2 = replace(cfg, donnees=tmp_path / "d2")
    cert, cle = certificat(cfg2)
    assert cert.exists() and cle.exists() and oct(cle.stat().st_mode)[-3:] == "600"
    assert certificat(cfg2) == (cert, cle)  # créé une fois, réutilisé
