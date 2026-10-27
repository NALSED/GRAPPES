"""Étape 3 : sujet en champs séparés, profondeur, limites, programmation, avancement exact."""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.base import Programme, Recherche, creer_fabrique
from pilote.config import charger
from pilote.executeur_grappes import Suivi, preparer
from pilote.lancement import LancementInvalide, libelle_quand, limites, phrase_du_sujet, prochaine_occurrence
from pilote.programmation import creer_programme, echeances
from pilote.taches import ContexteRecherche


@pytest.fixture
def cfg(tmp_path):
    base = charger()
    import yaml

    f = tmp_path / "config" / "pilote.yaml"
    f.parent.mkdir()
    f.write_text("service: {https: false, hotes_autorises: [testserver]}\n" + f"donnees: {{dossier: {tmp_path / 'd'}}}\n" + yaml.safe_dump(
        {"profondeurs": list(base.profondeurs), "profondeur_par_defaut": "normal", "limites_par_defaut": {"temps_minutes": 30, "appels": None}}), encoding="utf-8")
    return charger(f)


def test_phrase_du_sujet_a_partir_des_champs_separes():
    assert phrase_du_sujet({"quoi": "clubs de handball professionnels", "pays": "France"}) == "clubs de handball professionnels en France"
    assert phrase_du_sujet({"quoi": "librairies indépendantes", "pays": "France", "lieu": "Toulouse"}) == "librairies indépendantes de Toulouse"
    assert phrase_du_sujet({"quoi": "chorales"}) == "chorales"
    with pytest.raises(LancementInvalide):
        phrase_du_sujet({"quoi": "  "})


def test_limites_le_cran_borne_les_appels(cfg):
    assert limites(cfg, {"profondeur": "strict"})["appels"] == 5
    assert limites(cfg, {"profondeur": "normal", "limites": {"appels": 10}})["appels"] == 10
    assert limites(cfg, {"profondeur": "normal", "limites": {"appels": 999}})["appels"] == 18  # jamais au-delà du cran
    assert limites(cfg, {"profondeur": "normal", "limites": {"temps_minutes": 2}})["temps_s"] == 120
    with pytest.raises(LancementInvalide):
        limites(cfg, {"profondeur": "enorme"})


def test_options_et_profondeur_inconnue(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        o = c.get("/api/lancement/options").json()
        assert [p["id"] for p in o["profondeurs"]] == ["strict", "normal", "large", "maximum"] and o["profondeurs"][0]["appels"] == 5
        assert c.post("/api/recherches", json={"sujet": {"quoi": "x"}, "parametres": {"profondeur": "enorme"}}).status_code == 422


def test_preparer_copie_la_config_et_ne_touche_pas_la_vraie(tmp_path):
    from conftest import copier_config

    cfg = charger(copier_config(tmp_path / "pilote"))
    g = tmp_path / "g"
    (g / "config" / "recherche").mkdir(parents=True)
    (g / "config" / "autonomie.yaml").write_text("autonome: true\nquotas: {requetes_par_cycle: 20}\ninterdits: [reddit.com]\n", encoding="utf-8")
    (g / "config" / "classement.yaml").write_text("actif: true\n", encoding="utf-8")
    (g / "config" / "recherche.yaml").write_text("actifs: [tavily, wikipedia]\n", encoding="utf-8")
    (g / "config" / "recherche" / "wikipedia.yaml").write_text("id: wikipedia\ntype: http\n", encoding="utf-8")
    (g / "config" / "sujets.yaml").write_text("sujets: [{nom: autre, phrase: autre}]\n", encoding="utf-8")
    from dataclasses import replace

    c2 = replace(cfg, grappes_racine=g)
    import threading

    d = tmp_path / "travail" / "abc"
    d.mkdir(parents=True)
    ctx = ContexteRecherche("abc", {"quoi": "clubs", "pays": "France", "inclure": ["handball"], "exclure": ["boutique"], "combien": 30},
                            {"profondeur": "strict", "sources": ["wikipedia", "searxng"], "limites": {"temps_minutes": 5}}, d, "sednal", threading.Event(), None)
    spec = preparer(c2, ctx)
    assert spec["phrase"] == "clubs en France" and spec["limites"] == {"appels": 5, "temps_s": 300} and spec["mots_a_exclure"] == ["boutique"]
    assert "autre" not in (d / "config" / "sujets.yaml").read_text() and "clubs en France" in (d / "config" / "sujets.yaml").read_text()
    import yaml

    a = yaml.safe_load((d / "config" / "autonomie.yaml").read_text())
    assert a["requetes_par_cycle"] == 5 and a["autonome"] is True and a["interdits"] == ["reddit.com"]
    assert "actifs: [wikipedia, searxng]" in (d / "config" / "recherche.yaml").read_text()  # les sources choisies, dans l'ordre
    assert yaml.safe_load((d / "config" / "recherche" / "searxng.yaml").read_text())["url"].startswith("http://127.0.0.1")  # définition écrite dans la copie
    assert (d / "config" / "secrets.env").read_text() == ""  # aucune clé pour ces deux sources
    assert yaml.safe_load((d / "config" / "classement.yaml").read_text())["actif"] is False
    assert "actifs: [tavily, wikipedia]" in (g / "config" / "recherche.yaml").read_text()  # la vraie config est intacte
    assert "autre" in (g / "config" / "sujets.yaml").read_text()


def test_suivi_compte_exactement_les_appels(tmp_path):
    f = tmp_path / "av.jsonl"
    lignes = [
        {"evenement": "budget", "requetes": 18}, {"evenement": "etape", "etape": "recherche"},
        {"evenement": "plan", "prises": {"tavily": 2, "wikipedia": 2}}, {"evenement": "prise_debut", "prise": "tavily"},
        {"evenement": "appel", "prise": "tavily", "statut": "200"}, {"evenement": "appel", "prise": "tavily", "statut": "200"},
        {"evenement": "prise_fin", "prise": "tavily", "trouves": 12, "noms": 12}, {"evenement": "appel", "prise": "découverte"},
        {"evenement": "etape", "etape": "verification"},
    ]
    f.write_text("\n".join(json.dumps(x) for x in lignes) + "\n{\"evenement\": \"app", encoding="utf-8")  # dernière ligne coupée : ignorée
    s = Suivi(f, 18)
    e = s.lire()
    assert e["appels_faits"] == 3 and e["appels_prevus"] == 18 and e["noms"] == 12 and e["etape"] == "verification"
    assert e["prises"]["tavily"] == {"prevus": 2, "faits": 2, "trouves": 12, "fini": True}
    with f.open("a") as fh:
        fh.write('el", "prise": "x"}\n')
    assert s.lire()["appels_faits"] == 4  # la ligne finie est lue au passage suivant, une seule fois
    assert s.lire()["appels_faits"] == 4


def test_prochaine_occurrence_quotidienne_hebdomadaire_et_datee():
    ref = datetime(2026, 10, 13, 8, 0).astimezone()  # mardi 13 octobre 2026
    p = prochaine_occurrence({"jours": [], "heure": "10:00"}, ref)
    assert p.astimezone().hour == 10 and p.astimezone().day == 13
    p = prochaine_occurrence({"jours": [], "heure": "07:00"}, ref)
    assert p.astimezone().day == 14  # 7 h est passé : demain
    p = prochaine_occurrence({"jours": [0], "heure": "08:00"}, ref)  # lundi
    assert p.astimezone().weekday() == 0 and p.astimezone().day == 19
    assert prochaine_occurrence({"date": (ref + timedelta(hours=3)).replace(tzinfo=None).isoformat()}, ref) is not None
    assert prochaine_occurrence({"date": (ref - timedelta(hours=3)).replace(tzinfo=None).isoformat()}, ref) is None
    assert libelle_quand({"jours": [], "heure": "10:00"}) == "tous les jours 10 h 00"
    assert libelle_quand({"jours": [0], "heure": "08:00"}) == "lundi 08 h 00"


def test_echeance_cree_une_nouvelle_recherche_puis_reprogramme(cfg):
    f = creer_fabrique(cfg.url_base)
    lancees = []
    pid = creer_programme(f, {"quoi": "clubs", "pays": "France"}, {"profondeur": "strict"}, {"jours": [], "heure": "10:00"}, "sednal")
    assert echeances(f, lancees.append, maint=datetime.now(UTC)) == []  # pas encore l'heure
    with f.begin() as s:
        s.get(Programme, pid).prochaine = datetime.now(UTC) - timedelta(minutes=1)
    crees = echeances(f, lancees.append)
    assert len(crees) == 1 and lancees == crees
    with f() as s:
        r = s.get(Recherche, crees[0])
        p = s.get(Programme, pid)
        assert r.qui == "sednal" and r.parametres["programme"] == pid
        assert p.actif and p.prochaine.replace(tzinfo=UTC) > datetime.now(UTC) - timedelta(minutes=1)
        assert p.derniere_recherche_id == crees[0]


def test_lancement_date_s_eteint_apres_declenchement(cfg):
    f = creer_fabrique(cfg.url_base)
    date = (datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes")
    pid = creer_programme(f, {"quoi": "x"}, {}, {"date": date}, "sednal")
    with f.begin() as s:
        s.get(Programme, pid).prochaine = datetime.now(UTC) - timedelta(seconds=1)
        s.get(Programme, pid).quand = {"date": (datetime.now() - timedelta(minutes=5)).isoformat(timespec="minutes")}
    assert len(echeances(f, lambda r: None)) == 1
    with f() as s:
        assert s.get(Programme, pid).actif is False


def test_api_programmes_et_comptes_des_recherches(cfg):
    with TestClient(creer_app(cfg, lambda c: c.ajouter_candidats([{"nom": "A", "genre_source": "web"}, {"nom": "B", "genre_source": "web"}]), pas_planificateur=3600)) as c:
        r = c.post("/api/programmes", json={"sujet": {"quoi": "chorales", "pays": "France"}, "parametres": {"profondeur": "normal"}, "quand": {"jours": [0], "heure": "08:00"}})
        assert r.status_code == 201
        lst = c.get("/api/programmes").json()
        assert lst[0]["libelle"] == "chorales en France — lundi 08 h 00" and lst[0]["actif"] and lst[0]["prochaine"].endswith("Z")
        assert c.put(f"/api/programmes/{lst[0]['id']}", json={"actif": False}).json() == {"actif": False}
        assert c.post("/api/programmes", json={"sujet": {"quoi": "x"}, "quand": {"date": "2000-01-01T10:00"}}).status_code == 422
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorales"}}).json()["id"]
        t0 = time.time()
        while time.time() - t0 < 5 and c.get(f"/api/recherches/{rid}").json()["etat"] != "terminee":
            time.sleep(0.05)
        une = next(x for x in c.get("/api/recherches").json() if x["id"] == rid)
        assert une["noms"] == 2 and une["tries"] == 0


@pytest.mark.reseau
@pytest.mark.parametrize("page", ["rendu_lancement.mjs"])
def test_rendu_de_la_page_lancement_sous_node(page):
    import shutil
    import subprocess
    from pathlib import Path

    if shutil.which("node") is None:
        pytest.skip("node absent")
    r = subprocess.run(["node", f"tests/js/{page}"], capture_output=True, text=True, check=False, cwd=Path(__file__).resolve().parents[1])
    assert r.returncode == 0, r.stdout + r.stderr


# --- [ ] Heure d'été : un lancement programmé garde son heure locale de part et d'autre du changement d'heure. Le serveur de Sednal est en
#         Asia/Yerevan (sans heure d'été) ; le défaut ne se voyait que dans un fuseau qui change d'heure : on simule Paris.
@pytest.mark.parametrize(("apres", "attendu"), [
    (datetime(2026, 10, 24, 10, 0, tzinfo=UTC), "2026-10-26 10:00:00+01:00"),  # passage à l'heure d'hiver le dimanche 25/10
    (datetime(2026, 3, 28, 10, 0, tzinfo=UTC), "2026-03-30 10:00:00+02:00"),   # passage à l'heure d'été le dimanche 29/03
])  # fmt: skip
def test_un_lancement_programme_garde_son_heure_locale_au_changement_d_heure(monkeypatch, apres, attendu):
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    try:
        assert str(prochaine_occurrence({"jours": [0], "heure": "10:00"}, apres).astimezone()) == attendu  # chaque lundi 10:00
        assert str(prochaine_occurrence({"date": attendu[:16]}, apres).astimezone()) == attendu  # date fixe, sans fuseau
    finally:
        monkeypatch.undo()
        time.tzset()
