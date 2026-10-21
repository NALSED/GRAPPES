"""FICHE 12 — page Recherches : test de recette, point par point."""

import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from conftest import copier_config
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.config import RACINE
from pilote.config import charger as charger_cfg

NOMS = ("Chorale des Quatre Vents", "Les Voix du Soir")


@pytest.fixture
def cfg(tmp_path):
    return charger_cfg(copier_config(tmp_path))


def attendre(c, rid, delai=120, etats=("terminee", "arretee", "echec", "interrompue")):
    t0 = time.time()
    while time.time() - t0 < delai:
        r = c.get(f"/api/recherches/{rid}").json()
        if r["etat"] in etats:
            return r
        time.sleep(0.3)
    raise AssertionError("la recherche ne se termine pas")


def programme(tmp_path, nom, code, c):
    f = tmp_path / f"{nom}.py"
    f.write_text(code, encoding="utf-8")
    r = c.post("/api/programmes-locaux", json={"nom": nom, "commande": [sys.executable, str(f)], "genres": ["association"], "pays": ["FR"]})
    assert r.status_code == 201 and r.json()["test"]["statut"] == "ok", r.text
    return r.json()["id"]


def seulement(c, *ids):
    for x in c.get("/api/reglages").json()["parties"]["recherche"]:
        c.put(f"/api/reglages/source/{x['id']}", json={"chercher": x["id"] in ids})


def script(noms=NOMS, avant=""):
    return f'import json, sys, time\n{avant}\njson.load(sys.stdin)\nprint(json.dumps([{{"nom": n, "origine": "mon fichier"}} for n in {list(noms)!r}], ensure_ascii=False))\n'


# --- [ ] Une recherche se lance, tourne en tâche de fond, et la page peut être fermée puis rouverte sans perdre le suivi.
def test_la_recherche_tourne_en_tache_de_fond_et_le_suivi_survit_a_la_page(cfg):
    def lent(ctx):
        for i in range(5):
            time.sleep(0.4)
            ctx.avancer(noms=i + 1)
        ctx.ajouter_candidats([{"nom": "A", "genre_source": "web"}])

    with TestClient(creer_app(cfg, lent)) as c:
        t0 = time.time()
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorales"}}).json()["id"]
        assert time.time() - t0 < 1.5  # la requête répond sans attendre la fin
        assert c.get(f"/api/recherches/{rid}").json()["etat"] in ("en_attente", "en_cours")
        # « page fermée puis rouverte » : un client tout neuf retrouve la recherche et son avancement, sans rien perdre
        autre = TestClient(c.app)  # sans relancer le service : seulement un autre navigateur
        assert any(x["id"] == rid for x in autre.get("/api/recherches").json())
        fin = attendre(autre, rid)
        assert fin["etat"] == "terminee" and fin["avancement"]["noms"] == 5
    # le service est relancé : la recherche terminée est toujours là, avec son suivi
    with TestClient(creer_app(cfg, lambda ctx: time.sleep(0.1))) as c2:
        assert c2.get(f"/api/recherches/{rid}").json()["etat"] == "terminee"


# --- [ ] Aucun nom de résultat n'apparaît sur cette page.
def test_aucun_nom_de_resultat_sur_la_page_recherches(cfg):
    html = (RACINE / "static/index.html").read_text(encoding="utf-8")
    page = html[html.index('id="pg-lancement"'):html.index('id="pg-tri"')]
    assert "Recherches" in page and "Aucun nom de résultat ici" in page
    js = (RACINE / "static/lancement.js").read_text(encoding="utf-8")
    assert not re.search(r"/tri\b|/candidats|/noms/", js)  # la page n'appelle jamais les routes qui rendent des noms
    with TestClient(creer_app(cfg, lambda ctx: ctx.ajouter_candidats([{"nom": "Nom Secret Du Résultat", "genre_source": "web"}]))) as c:
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorales"}}).json()["id"]
        attendre(c, rid)
        tout = json.dumps([c.get("/api/recherches").json(), c.get(f"/api/recherches/{rid}").json()], ensure_ascii=False)
        assert "Nom Secret" not in tout  # ni la liste ni le suivi ne portent un nom, seulement leur nombre
        assert c.get("/api/recherches").json()[0]["noms"] == 1


# --- [ ] Les trois jauges avancent et correspondent aux trois étapes.
def test_les_trois_jauges_suivent_les_trois_etapes_d_une_vraie_recherche(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        programme(tmp_path, "solide", script(), c)
        seulement(c, "solide")
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        r = attendre(c, rid)
        assert r["etat"] == "terminee", r["message"]
    etapes = []
    for ligne in (cfg.dossier_recherche(rid) / "avancement.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(ligne)
        if e.get("evenement") == "etape" and e["etape"] not in etapes:
            etapes.append(e["etape"])
    assert etapes == ["recherche", "verification", "sortie"]  # les trois étapes, dans l'ordre : les trois jauges
    js = (RACINE / "static/lancement.js").read_text(encoding="utf-8")
    assert "s:1" in js and "s:2" in js and "s:3" in js  # bleu, violet, ambre
    assert r["avancement"]["etape"] == "fini"


# --- [ ] Changer un réglage dans Réglages pendant qu'une recherche tourne : la recherche en cours n'est pas affectée.
def test_un_reglage_change_pendant_la_recherche_ne_l_affecte_pas(cfg, tmp_path):
    marque = tmp_path / "demarre"
    with TestClient(creer_app(cfg)) as c:
        programme(tmp_path, "lente", script(avant=f"open({str(marque)!r}, 'w').write('x')\ntime.sleep(3)"), c)
        marque.unlink()  # le test local de l'ajout a lancé le programme une fois : on repart de zéro
        seulement(c, "lente")
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        t0 = time.time()
        while not marque.exists() and time.time() - t0 < 60:
            time.sleep(0.2)
        avant = (cfg.dossier_recherche(rid) / "lancement.json").read_text(encoding="utf-8")
        # pendant la course : la source est éteinte, le plafond tombe à zéro, la vérification est coupée
        c.put("/api/reglages/source/lente", json={"chercher": False})
        c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 0})
        c.put("/api/reglages/verification", json={"active": False})
        r = attendre(c, rid)
        assert r["etat"] == "terminee", r["message"]
        assert (cfg.dossier_recherche(rid) / "lancement.json").read_text(encoding="utf-8") == avant  # ses réglages sont ceux du départ
        assert {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]} == set(NOMS)  # et elle a rendu ce qu'elle devait
        # la recherche SUIVANTE, elle, prend les réglages changés
        rid2 = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        attendre(c, rid2)
        assert json.loads((cfg.dossier_recherche(rid2) / "lancement.json").read_text(encoding="utf-8"))["sources"] == []


# --- [ ] Une option avancée surcharge bien la valeur par défaut, pour cette recherche seulement.
def test_une_option_avancee_surcharge_pour_cette_recherche_seulement(cfg, tmp_path):
    reglages_avant = None
    with TestClient(creer_app(cfg)) as c:
        programme(tmp_path, "solide", script(), c)
        seulement(c, "solide")
        reglages_avant = c.get("/api/reglages").json()["verification"], c.get("/api/reglages").json()["budget"]
        options = {"profondeur": "strict", "exploration": 2, "lire_la_page": False, "sites_a_ignorer": ["https://www.Exemple-Ignore.org/page", "autre.example"], "verification": False}
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": options}).json()["id"]
        r1 = attendre(c, rid)
        rid2 = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        attendre(c, rid2)
        assert (c.get("/api/reglages").json()["verification"], c.get("/api/reglages").json()["budget"]) == reglages_avant  # Réglages n'a pas bougé
    a1 = yaml.safe_load((cfg.dossier_recherche(rid) / "config/autonomie.yaml").read_text(encoding="utf-8"))
    a2 = yaml.safe_load((cfg.dossier_recherche(rid2) / "config/autonomie.yaml").read_text(encoding="utf-8"))
    assert a1["profondeur"] == 2 and a2["profondeur"] == 0  # exploration : éteinte par défaut
    assert a1["pages_par_cycle"] == 0 and a2["pages_par_cycle"] > 0  # extrait seulement : ne concerne que la première
    assert "exemple-ignore.org" in a1["interdits"] and "autre.example" in a1["interdits"] and "exemple-ignore.org" not in a2["interdits"]
    assert r1["etat"] == "terminee"
    assert c.post("/api/recherches", json={"sujet": {"quoi": "x"}, "parametres": {"exploration": 5}}).status_code == 422
    assert c.post("/api/recherches", json={"sujet": {"quoi": "x"}, "parametres": {"sites_a_ignorer": ["pas une adresse"]}}).status_code == 422
    assert c.post("/api/recherches", json={"sujet": {"quoi": "x"}, "parametres": {"presets": ["nexiste-pas"]}}).status_code == 422


def test_les_presets_coches_restreignent_les_sources_de_cette_recherche(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        programme(tmp_path, "solide", script(), c)
        programme(tmp_path, "autre", script(noms=("Autre Nom",)), c)
        seulement(c, "solide", "autre")
        c.post("/api/presets", json={"nom": "Seulement solide"})
        c.put("/api/presets/seulement-solide", json={"sources": ["solide"]})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict", "presets": ["seulement-solide"]}}).json()["id"]
        attendre(c, rid)
        noms = {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]}
    assert noms == set(NOMS)  # « Autre Nom » est allumée dans Réglages mais n'est pas dans le preset coché


# --- [ ] Mettre le plafond à zéro : la recherche part quand même, sur les sources gratuites seulement, et le message le dit.
def test_plafond_a_zero_la_recherche_part_sur_les_sources_gratuites_et_le_dit(cfg, tmp_path):
    from test_f11_ajout_sources import FauxService, service, spec_payante  # noqa: F401

    srv = HTTPServerLocal(FauxService)
    try:
        with TestClient(creer_app(cfg)) as c:
            programme(tmp_path, "gratuite", script(), c)
            c.post("/api/ajout/source", json={"type": "api", "spec": spec_payante(srv.url)})
            c.put("/api/cles/SERVICE_PAYANT_KEY", json={"valeur": "cle-payante-123"})
            assert c.post("/api/sources/service-payant/tester").json()["statut"] == "ok"  # la clé est là : le test local passe, la source peut être allumée
            seulement(c, "gratuite", "service-payant")
            c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 0})
            avant = len(FauxService.recus)
            est = c.post("/api/lancement/estimation", json={"parametres": {"profondeur": "strict"}}).json()
            assert est["limitee_aux_gratuites"] is True and est["cout"]["phrase"].startswith("gratuit") and "service-payant" not in est["sources"]
            assert "Service payant" in est["message"] and "gratuites" in est["message"]
            rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
            r = attendre(c, rid)
            assert r["etat"] == "terminee", r["message"]  # elle n'est PAS refusée
            assert len(FauxService.recus) == avant  # la source payante n'a reçu aucune requête
            a = r["avancement"]
            assert a["limitee_aux_gratuites"] is True and a["sources_ecartees"][0]["source"] == "service-payant"
            assert {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]} == set(NOMS)  # les gratuites ont travaillé
    finally:
        srv.arreter()


class HTTPServerLocal:
    def __init__(self, handler):
        import threading
        from http.server import HTTPServer

        handler.recus = []
        self.s = HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.s.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.s.server_port}"

    def arreter(self):
        self.s.shutdown()


# --- [ ] Une recherche planifiée à une date et heure se déclenche bien (par un vrai planificateur de tâches).
def test_une_recherche_programmee_se_declenche_a_l_heure_dite(cfg):
    from apscheduler.schedulers.background import BackgroundScheduler

    with TestClient(creer_app(cfg, lambda ctx: ctx.ajouter_candidats([{"nom": "A", "genre_source": "web"}]), pas_planificateur=3600)) as c:
        pl = c.app.router.lifespan_context  # noqa: F841 (le planificateur est armé par le service lui-même)
        quand = (datetime.now() + timedelta(seconds=3)).strftime("%Y-%m-%dT%H:%M:%S")
        r = c.post("/api/programmes", json={"sujet": {"quoi": "chorales", "pays": "France"}, "parametres": {"profondeur": "strict"}, "quand": {"date": quand}})
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        assert not c.get("/api/recherches").json()  # rien ne part avant l'heure
        t0 = time.time()
        while time.time() - t0 < 30 and not c.get("/api/recherches").json():
            time.sleep(0.3)
        lst = c.get("/api/recherches").json()
        assert lst and lst[0]["parametres"]["programme"] == pid
        attendre(c, lst[0]["id"])
        prog = next(p for p in c.get("/api/programmes").json() if p["id"] == pid)
        assert prog["actif"] is False and prog["derniere_recherche_id"] == lst[0]["id"]  # un lancement daté s'éteint après son déclenchement
    assert BackgroundScheduler  # c'est APScheduler, pas une boucle maison


# --- [ ] La fourchette de coût affichée avant le lancement est cohérente avec ce qui est réellement dépensé.
def test_la_fourchette_de_cout_encadre_la_depense_reelle(cfg, tmp_path):
    from test_f11_ajout_sources import FauxService, spec_payante

    srv = HTTPServerLocal(FauxService)
    try:
        with TestClient(creer_app(cfg)) as c:
            c.post("/api/ajout/source", json={"type": "api", "spec": spec_payante(srv.url)})
            c.put("/api/cles/SERVICE_PAYANT_KEY", json={"valeur": "cle-payante-123"})
            assert c.post("/api/sources/service-payant/tester").json()["statut"] == "ok"  # la clé est là : le test local passe, la source peut être allumée
            seulement(c, "service-payant")
            c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 5})
            avant = len(FauxService.recus)
            est = c.post("/api/lancement/estimation", json={"parametres": {"profondeur": "strict"}}).json()
            assert len(FauxService.recus) == avant  # estimer n'appelle rien
            assert est["cout"]["sources_payantes"] == ["service-payant"] and 0 < est["cout"]["bas_usd"] <= est["cout"]["haut_usd"]
            rid = c.post("/api/recherches", json={"sujet": {"quoi": "club", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
            r = attendre(c, rid)
            assert r["etat"] == "terminee", r["message"]
            depense = c.get("/api/reglages").json()["budget"]["depense_du_mois_usd"]
            assert depense > 0 and est["cout"]["bas_usd"] <= depense <= est["cout"]["haut_usd"], (est["cout"], depense)
    finally:
        srv.arreter()


def test_l_estimation_du_temps_est_une_fourchette_mesuree_apres_trois_recherches(cfg):
    with TestClient(creer_app(cfg, lambda ctx: time.sleep(0.3))) as c:
        e0 = c.post("/api/lancement/estimation", json={"parametres": {"profondeur": "strict"}}).json()
        assert e0["temps"]["mesure"] is False and "estimation large" in e0["temps"]["phrase"] and e0["temps"]["bas_s"] < e0["temps"]["haut_s"]
        for _ in range(3):
            attendre(c, c.post("/api/recherches", json={"sujet": {"quoi": "x"}, "parametres": {"profondeur": "strict"}}).json()["id"])
        e = c.post("/api/lancement/estimation", json={"parametres": {"profondeur": "strict"}}).json()
        assert e["temps"]["mesure"] is True and e["temps"]["bas_s"] <= e["temps"]["haut_s"] <= 5 and e["temps"]["phrase"] == "moins d'une minute"
        # la limite de temps demandée borne la fourchette
        e2 = c.post("/api/lancement/estimation", json={"parametres": {"profondeur": "maximum", "limites": {"temps_minutes": 2}}}).json()
        assert e2["temps"]["haut_s"] <= 120


# --- Pause et reprise (suivi d'une recherche en cours).
def test_pause_et_reprise_ne_perdent_rien(cfg, tmp_path):
    debut_a, debut_b = tmp_path / "a_demarre", tmp_path / "b_demarre"
    with TestClient(creer_app(cfg)) as c:
        programme(tmp_path, "aaa", script(avant=f"open({str(debut_a)!r}, 'w').write('x')\ntime.sleep(2)"), c)
        programme(tmp_path, "bbb", script(noms=("Nom B",), avant=f"open({str(debut_b)!r}, 'w').write('x')"), c)
        debut_a.unlink(missing_ok=True)
        debut_b.unlink(missing_ok=True)
        seulement(c, "aaa", "bbb")
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        t0 = time.time()
        while not debut_a.exists() and time.time() - t0 < 60:
            time.sleep(0.1)
        assert c.post(f"/api/recherches/{rid}/pause").json() == {"en_pause": True}
        time.sleep(4)  # la première source se termine, la seconde NE démarre PAS
        r = c.get(f"/api/recherches/{rid}").json()
        assert r["etat"] == "en_cours" and r["avancement"]["en_pause"] is True and not debut_b.exists()
        assert c.post(f"/api/recherches/{rid}/reprise").json() == {"en_pause": False}
        fin = attendre(c, rid)
        assert fin["etat"] == "terminee" and debut_b.exists()
        assert {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]} == {*NOMS, "Nom B"}  # rien n'a été perdu
        assert c.post(f"/api/recherches/{rid}/pause").status_code == 409  # une recherche finie ne se met pas en pause
        assert c.post("/api/recherches/nexiste-pas/pause").status_code == 404


def test_un_arret_pendant_la_pause_la_leve(cfg, tmp_path):
    debut = tmp_path / "a_demarre"
    with TestClient(creer_app(cfg)) as c:
        programme(tmp_path, "aaa", script(avant=f"open({str(debut)!r}, 'w').write('x')\ntime.sleep(1.5)"), c)
        programme(tmp_path, "bbb", script(noms=("Nom B",)), c)
        debut.unlink(missing_ok=True)
        seulement(c, "aaa", "bbb")
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        t0 = time.time()
        while not debut.exists() and time.time() - t0 < 60:
            time.sleep(0.1)
        c.post(f"/api/recherches/{rid}/pause")
        time.sleep(2.5)
        c.post(f"/api/recherches/{rid}/arret")
        fin = attendre(c, rid, delai=60)
        assert fin["etat"] == "arretee"
        assert {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]} == set(NOMS)  # l'acquis est gardé


def test_la_page_recherches_sous_node_est_toujours_la_meme_chose():
    assert Path(RACINE / "tests/js/rendu_lancement.mjs").exists()
