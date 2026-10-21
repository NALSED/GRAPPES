"""FICHE 01 — page Réglages : test de recette, point par point."""

import json
import os
import shutil
import socket
import urllib.request

import pytest
import yaml
from conftest import copier_config
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.config import RACINE, charger
from pilote.etat_sources import noter

SENTINELLE = "SENTINELLE-clef-secrete-8f3a1c"


def app_de(cfg):
    return creer_app(cfg, lambda ctx: None)


# --- [ ] Les trois parties s'affichent avec leurs trois couleurs.
def test_trois_parties_trois_couleurs(cfg):
    with TestClient(app_de(cfg)) as c:
        d = c.get("/api/reglages").json()
        assert set(d["parties"]) == {"recherche", "verification", "sortie"}
        html = c.get("/").text
    for classe in ("part p1", "part p2", "part p3"):
        assert classe in html
    css = (RACINE / "static" / "pilote.css").read_text(encoding="utf-8")
    # bleu, violet, ambre : les trois couleurs du flux, fixées une fois pour toutes
    assert "--f1:#1f4f8f" in css and "--f2:#5b3a86" in css and "--f3:#8a5a12" in css
    plat = css.replace(" ", "")
    for n in (1, 2, 3):
        assert f".p{n}.part-h{{border-left-color:var(--f{n})" in plat


# --- [ ] Ouvrir la page ne déclenche AUCUN appel vers une API externe ; la date du dernier état connu est affichée.
def test_ouvrir_la_page_n_appelle_rien_et_montre_la_date(cfg, monkeypatch):
    noter(cfg, "tavily", teste_le="2026-10-13T08:00:00+00:00", statut="ok", quota={"restant": 210, "total": 1000, "le": "2026-10-13T08:00:00+00:00"})
    appels = []

    def interdit(*a, **k):
        appels.append(a)
        raise AssertionError("appel réseau interdit à l'ouverture de la page")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(urllib.request, "urlopen", interdit)
    avant = cfg.fichier_etat_sources.read_bytes()
    with TestClient(app_de(cfg)) as c:
        for url in ("/", "/static/reglages.js", "/api/reglages", "/api/reglages"):
            assert c.get(url).status_code == 200
        d = c.get("/api/reglages").json()
    assert appels == []
    assert cfg.fichier_etat_sources.read_bytes() == avant  # rien n'a été rafraîchi
    tav = next(s for s in d["parties"]["recherche"] if s["id"] == "tavily")
    assert "13/10/2026" in tav["etat_phrase"] and "Quota restant" in tav["etat_phrase"] and "210" in tav["etat_phrase"]
    wiki = next(s for s in d["parties"]["recherche"] if s["id"] == "wikipedia")
    assert wiki["etat_phrase"] == "Pas encore testée."


# --- [ ] Une clé d'API n'apparaît JAMAIS dans ce que reçoit le navigateur.
def test_une_cle_n_arrive_jamais_au_navigateur(cfg):
    cfg.fichiers_secrets[0].write_text(f"TAVILY_API_KEY={SENTINELLE}\n", encoding="utf-8")
    with TestClient(app_de(cfg)) as c:
        reponses = [c.get(u) for u in ("/api/reglages", "/api/recherches", "/api/sante", "/", "/static/reglages.js", "/static/index.html")]
        r = c.put("/api/cles/OPENAI_API_KEY", json={"valeur": SENTINELLE + "-2"})
        assert r.json() == {"cle": "presente"}
        reponses.append(r)
        reponses.append(c.get("/api/reglages"))
        d = c.get("/api/reglages").json()
    for rep in reponses:
        assert SENTINELLE not in rep.text and SENTINELLE not in str(rep.headers)
    tav = next(s for s in d["parties"]["recherche"] if s["id"] == "tavily")
    assert tav["cle"] == "presente" and "cle_valeur" not in tav
    assert SENTINELLE not in json.dumps(d)
    # ni dans le journal des actions, ni dans un fichier de configuration (autre que secrets.env)
    assert SENTINELLE not in cfg.journal_actions.read_text(encoding="utf-8")
    for f in list(cfg.dossier_config.rglob("*.yaml")):
        assert SENTINELLE not in f.read_text(encoding="utf-8")
    assert oct(cfg.fichiers_secrets[0].stat().st_mode)[-3:] == "600"


def test_cle_absente_dite_absente(cfg):
    with TestClient(app_de(cfg)) as c:
        tav = next(s for s in c.get("/api/reglages").json()["parties"]["recherche"] if s["id"] == "tavily")
    assert tav["cle"] == "absente" and tav["bloquee_par_cle"] is True


# --- [ ] Un fichier de configuration volontairement cassé est refusé, raison en français, ancien réglage intact.
def test_reglage_casse_refuse_avec_raison_et_ancien_intact(cfg):
    with TestClient(app_de(cfg)) as c:
        assert c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 25}).status_code == 200
        avant = cfg.fichier_reglages.read_bytes()
        cas = [
            ("PUT", "/api/reglages/budget", {"plafond_mensuel_usd": -5}, "plafond"),
            ("PUT", "/api/reglages/source/tavily", {"confiance": 7}, "confiance"),
            ("PUT", "/api/reglages/source/nexiste-pas", {"chercher": True}, "n'existe pas"),
            ("PUT", "/api/reglages/pays", {"pays": "France"}, "deux lettres"),
            ("PUT", "/api/reglages/presets", {"coches": ["inconnu"]}, "n'existe pas"),
            ("PUT", "/api/reglages/source/tavily", {"cout": {"vers_dollar": -1}}, "au moins"),
        ]
        for methode, url, corps, mot in cas:
            r = c.request(methode, url, json=corps)
            assert r.status_code == 422, (url, corps, r.text)
            assert mot in r.json()["detail"], r.json()["detail"]
            assert cfg.fichier_reglages.read_bytes() == avant  # l'ancien réglage est intact
        assert yaml.safe_load(avant)["budget"]["plafond_mensuel_usd"] == 25


def test_fichier_de_source_casse_est_signale_sans_arreter_les_autres(cfg):
    (cfg.dossier_sources / "cassee.yaml").write_text("id: cassee\nnom: [oups\n", encoding="utf-8")
    (cfg.dossier_sources / "mauvais-genre.yaml").write_text(
        yaml.safe_dump({"id": "mauvais-genre", "nom": "X", "genres": ["fromage"], "pays": ["FR"], "usages": ["web"], "main": "seconde", "famille": "api", "moteur": {"prise": "x"}}), encoding="utf-8")
    (cfg.dossier_sources / "sans-main.yaml").write_text(
        yaml.safe_dump({"id": "sans-main", "nom": "X", "genres": ["page"], "pays": ["FR"], "usages": ["web"], "famille": "api", "moteur": {"prise": "x"}}), encoding="utf-8")
    with TestClient(app_de(cfg)) as c:
        d = c.get("/api/reglages").json()
    raisons = {p["fichier"]: p["raison"] for p in d["problemes"]}
    assert "illisible" in raisons["cassee.yaml"] and "YAML" in raisons["cassee.yaml"]
    assert "fromage" in raisons["mauvais-genre.yaml"] and "n'existe pas" in raisons["mauvais-genre.yaml"]
    assert "première" in raisons["sans-main.yaml"]
    assert any(s["id"] == "tavily" for s in d["parties"]["recherche"])  # les autres sources sont là


def test_reglages_yaml_casse_ne_fait_pas_tomber_la_page(cfg):
    cfg.fichier_reglages.write_text("budget: [ceci n'est pas\n", encoding="utf-8")
    with TestClient(app_de(cfg)) as c:
        r = c.get("/api/reglages")
        assert r.status_code == 200
        assert any(p["fichier"] == "reglages.yaml" and "illisible" in p["raison"] for p in r.json()["problemes"])
        # et toute écriture est refusée tant que le fichier est cassé (on ne l'écrase pas sans le dire)
        assert c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 5}).status_code == 422
    assert "oups" not in cfg.fichier_reglages.read_text(encoding="utf-8") and "ceci n'est pas" in cfg.fichier_reglages.read_text(encoding="utf-8")


# --- [ ] Une source peut être cochée « chercher » sans « vérifier », et l'inverse.
def test_chercher_et_verifier_sont_independants(cfg):
    def ligne(c, sid):
        d = c.get("/api/reglages").json()
        return next(s for s in d["parties"]["recherche"] if s["id"] == sid)

    with TestClient(app_de(cfg)) as c:
        c.put("/api/reglages/source/wikipedia", json={"chercher": True, "verifier": False})
        s = ligne(c, "wikipedia")
        assert s["chercher"] is True and s["verifier"] is False
        c.put("/api/reglages/source/wikipedia", json={"chercher": False, "verifier": True})
        s = ligne(c, "wikipedia")
        assert s["chercher"] is False and s["verifier"] is True
        # une source qui ne sait que chercher ne peut pas être cochée « vérifier »
    (cfg.dossier_sources / "seule.yaml").write_text(
        yaml.safe_dump({"id": "seule", "nom": "Seule", "genres": ["page"], "pays": ["monde"], "usages": ["web"], "main": "seconde", "famille": "api", "roles": ["chercher"], "moteur": {"prise": "x"}}), encoding="utf-8")
    with TestClient(app_de(cfg)) as c:
        r = c.put("/api/reglages/source/seule", json={"verifier": True})
        assert r.status_code == 422 and "ne peut pas servir à vérifier" in r.json()["detail"]
        # dans le fichier de réglages, les deux choix sont bien deux champs distincts
    reg = yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8"))
    assert reg["sources"]["wikipedia"] == {"chercher": False, "verifier": True}


# --- [ ] Le plafond de dépense se règle et se relit après redémarrage du service.
def test_plafond_survit_au_redemarrage(cfg):
    with TestClient(app_de(cfg)) as c:
        assert c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 42.5}).json()["plafond_mensuel_usd"] == 42.5
    with TestClient(app_de(cfg)) as c2:  # « redémarrage » : une toute nouvelle application sur les mêmes fichiers
        assert c2.get("/api/reglages").json()["budget"]["plafond_mensuel_usd"] == 42.5


# --- [ ] Aucun chemin codé en dur : déplacer le dossier de configuration et le retrouver par sa variable.
def test_dossier_de_configuration_deplace_retrouve_par_sa_variable(tmp_path, monkeypatch):
    ancien = tmp_path / "ancien"
    f = copier_config(ancien)
    with TestClient(app_de(charger(f))) as c:
        c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 7})
        avant = c.get("/api/reglages").json()
    nouveau = tmp_path / "ailleurs" / "plus" / "loin"
    nouveau.parent.mkdir(parents=True)
    shutil.move(str(ancien / "config"), str(nouveau))
    shutil.move(str(ancien / "donnees"), str(nouveau.parent / "donnees")) if (ancien / "donnees").exists() else None
    assert not (ancien / "config").exists()
    monkeypatch.setenv("PILOTE_CONFIG", str(nouveau / "pilote.yaml"))
    cfg2 = charger()
    assert cfg2.dossier_config == nouveau and cfg2.dossier_sources == nouveau / "sources"
    with TestClient(app_de(cfg2)) as c:
        apres = c.get("/api/reglages").json()
    assert apres["budget"]["plafond_mensuel_usd"] == 7
    assert [s["id"] for s in apres["parties"]["recherche"]] == [s["id"] for s in avant["parties"]["recherche"]]


def test_aucun_chemin_en_dur_dans_le_code():
    import re

    interdit = re.compile(r"""["'](/opt/|/home/)""")
    for f in (RACINE / "src").rglob("*.py"):
        assert not interdit.search(f.read_text(encoding="utf-8")), f
    assert "PILOTE_CONFIG" in (RACINE / "src" / "pilote" / "config.py").read_text(encoding="utf-8")


def test_presets_calcules_depuis_les_usages_declares(cfg):
    with TestClient(app_de(cfg)) as c:
        d = c.get("/api/reglages").json()
    web = next(p for p in d["presets"] if p["id"] == "web")
    attendues = {y["id"] for f in cfg.dossier_sources.glob("*.yaml") for y in [yaml.safe_load(f.read_text(encoding="utf-8"))] if "web" in y["usages"]}
    assert attendues and {s["id"] for s in web["sources"]} == attendues  # exactement les sources qui déclarent l'usage « web »
    assert "tavily" in attendues
    # aucune liste de sources dans la carte du preset : seulement nom, phrase, usage
    carte = yaml.safe_load((cfg.dossier_presets / "web.yaml").read_text(encoding="utf-8"))
    assert set(carte) == {"id", "nom", "ordre", "phrase", "usage"}
    assert len(d["presets"]) == 8 and [p["id"] for p in d["presets"]][-1] == "personnalise"
    assert os.path.exists(cfg.dossier_presets / "personnalise.yaml")


def test_rendu_de_la_page_sous_node(cfg, tmp_path):
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node absent")
    with TestClient(app_de(cfg)) as c:
        (tmp_path / "api.json").write_text(json.dumps(c.get("/api/reglages").json()), encoding="utf-8")
    r = subprocess.run(["node", "tests/js/rendu_reglages.mjs", str(tmp_path / "api.json")], capture_output=True, text=True, check=False, cwd=RACINE)
    assert r.returncode == 0, r.stdout + r.stderr
