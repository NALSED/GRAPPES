"""FICHE 02 — assistant de première installation : test de recette, point par point."""

import json
import shutil
import subprocess

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.config import RACINE

E1 = {"pays": "FR", "presets_coches": ["web", "organisations_officielles"], "chercher": ["tavily", "wikipedia", "esr_etablissements"], "plafond": 12}
E2 = {"active": True, "mode": "memes", "verifier": ["wikipedia", "esr_etablissements"]}
E3 = {"actifs": ["csv", "json"], "dossier": "mes-resultats"}


def app_de(cfg):
    return creer_app(cfg, lambda ctx: None)


# --- [ ] Première installation : les trois étapes s'enchaînent dans l'ordre et le menu principal est inaccessible avant la fin.
def test_premiere_installation_detectee_et_menu_cache_cote_page(cfg):
    with TestClient(app_de(cfg)) as c:
        assert c.get("/api/reglages").json()["assistant"] == {"termine": False, "premiere_installation": True}
        html = c.get("/").text
    # les trois phrases de la fiche et l'ordre des étapes sont dans la page
    debut = html.index('id="assistant"')
    positions = [html.index(t, debut) for t in ("① SOURCES", "② VÉRIFICATION", "③ SORTIE", "Récapitulatif")]
    assert positions == sorted(positions)
    css = (RACINE / "static" / "pilote.css").read_text(encoding="utf-8")
    assert "body.sans-menu.tab{display:none}" in css.replace(" ", "")  # le menu est caché tant que l'assistant n'est pas terminé


def test_le_comportement_de_la_page_sous_node(cfg, tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node absent")
    with TestClient(app_de(cfg)) as c:
        (tmp_path / "premiere.json").write_text(json.dumps(c.get("/api/reglages").json()), encoding="utf-8")
        assert c.post("/api/assistant/terminer", json={"etape1": E1, "etape2": E2, "etape3": E3}).status_code == 200
        (tmp_path / "existante.json").write_text(json.dumps(c.get("/api/reglages").json()), encoding="utf-8")
    r = subprocess.run(["node", "tests/js/rendu_assistant.mjs", str(tmp_path / "premiere.json"), str(tmp_path / "existante.json")], capture_output=True, text=True, check=False, cwd=RACINE)
    assert r.returncode == 0, r.stdout + r.stderr


# --- [ ] Après l'étape 3, les fichiers de configuration sont écrits et lisibles à la main.
def test_apres_l_etape_3_la_configuration_est_ecrite_et_lisible(cfg):
    assert not cfg.fichier_reglages.exists()
    with TestClient(app_de(cfg)) as c:
        r = c.post("/api/assistant/terminer", json={"etape1": E1, "etape2": E2, "etape3": E3})
        assert r.status_code == 200
    texte = cfg.fichier_reglages.read_text(encoding="utf-8")
    assert texte.startswith("# Choix de l'utilisateur")  # un commentaire en français en tête : lisible à la main
    y = yaml.safe_load(texte)
    assert y["pays"] == "FR" and y["presets_coches"] == ["web", "organisations_officielles"] and y["budget"]["plafond_mensuel_usd"] == 12
    assert y["sources"]["tavily"]["chercher"] is True and y["sources"]["tavily"]["verifier"] is False
    assert y["sources"]["wikipedia"] == {"chercher": True, "verifier": True}
    assert y["sources"]["bnf_organisations"]["chercher"] is False  # pas cochée : éteinte
    assert y["verification"] == {"active": True, "mode": "memes"} and y["sortie"]["actifs"] == ["csv", "json"] and y["sortie"]["dossier"] == "mes-resultats"
    assert y["assistant"]["termine"] is True


def test_etape_invalide_refusee_et_rien_n_est_ecrit(cfg):
    with TestClient(app_de(cfg)) as c:
        r = c.post("/api/assistant/terminer", json={"etape1": {**E1, "pays": "France"}, "etape2": E2, "etape3": E3})
        assert r.status_code == 422 and "deux lettres" in r.json()["detail"]
        r = c.post("/api/assistant/terminer", json={"etape1": {**E1, "chercher": ["nexiste-pas"]}, "etape2": E2, "etape3": E3})
        assert r.status_code == 422 and "n'existe pas" in r.json()["detail"]
    assert not cfg.fichier_reglages.exists()


# --- [ ] Supprimer la configuration et relancer : l'assistant réapparaît.
def test_supprimer_la_configuration_fait_reapparaitre_l_assistant(cfg):
    with TestClient(app_de(cfg)) as c:
        c.post("/api/assistant/terminer", json={"etape1": E1, "etape2": E2, "etape3": E3})
        assert c.get("/api/reglages").json()["assistant"]["premiere_installation"] is False
    cfg.fichier_reglages.unlink()
    with TestClient(app_de(cfg)) as c2:
        assert c2.get("/api/reglages").json()["assistant"]["premiere_installation"] is True


# --- [ ] Avec une configuration déjà présente : l'assistant est sauté.
def test_configuration_deja_presente_saute_l_assistant(cfg):
    cfg.fichier_reglages.write_text("budget:\n  plafond_mensuel_usd: 3\nverification:\n  active: false\n", encoding="utf-8")  # écrite à la main
    with TestClient(app_de(cfg)) as c:
        d = c.get("/api/reglages").json()
    assert d["assistant"]["premiere_installation"] is False and d["budget"]["plafond_mensuel_usd"] == 3


# --- [ ] Depuis Réglages, l'assistant se rouvre à l'étape 2 sans toucher aux étapes 1 et 3.
def test_rejouer_l_etape_2_ne_touche_pas_les_etapes_1_et_3(cfg):
    with TestClient(app_de(cfg)) as c:
        c.post("/api/assistant/terminer", json={"etape1": E1, "etape2": E2, "etape3": E3})
        avant = yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8"))
        r = c.post("/api/assistant/etape/2", json={"donnees": {"active": False, "mode": "plus", "verifier": []}})
        assert r.status_code == 200
        assert c.post("/api/assistant/etape/9", json={"donnees": {}}).status_code == 422
    apres = yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8"))
    assert apres["verification"] == {"active": False, "mode": "plus"}  # l'étape 2 a changé
    for cle in ("pays", "presets_coches", "budget", "sortie"):
        assert apres[cle] == avant[cle], cle  # étapes 1 et 3 intactes
    assert {k: v.get("chercher") for k, v in apres["sources"].items()} == {k: v.get("chercher") for k, v in avant["sources"].items()}
    assert not any(v.get("verifier") for v in apres["sources"].values())  # (une source qui ne sait que chercher n'a pas de case « vérifier »)


# --- [ ] « Personnaliser à partir de ce preset » crée une copie nommée ; le preset d'origine est inchangé.
def test_personnaliser_cree_une_copie_nommee_sans_toucher_l_original(cfg):
    original = (cfg.dossier_presets / "web.yaml").read_bytes()
    with TestClient(app_de(cfg)) as c:
        sources_web = [s["id"] for p in c.get("/api/reglages").json()["presets"] if p["id"] == "web" for s in p["sources"]]
        r = c.post("/api/presets/personnaliser", json={"depuis": "web", "nom": "Mon Web à moi"})
        assert r.status_code == 201 and r.json()["id"] == "mon-web-a-moi"
        d = c.get("/api/reglages").json()
        copie = next(p for p in d["presets"] if p["id"] == "mon-web-a-moi")
        assert copie["perso"] is True and copie["nom"] == "Mon Web à moi" and copie["copie_de"] == "web"
        assert [s["id"] for s in copie["sources"]] == sources_web
        assert c.post("/api/presets/personnaliser", json={"depuis": "web", "nom": "Mon Web à moi"}).status_code == 422  # nom déjà pris
        assert c.post("/api/presets/personnaliser", json={"depuis": "web", "nom": "  "}).status_code == 422
        assert c.post("/api/presets/personnaliser", json={"depuis": "nexiste-pas", "nom": "X"}).status_code == 422
    assert (cfg.dossier_presets / "web.yaml").read_bytes() == original  # l'original est intact
    fichier = yaml.safe_load((cfg.dossier_presets_perso / "mon-web-a-moi.yaml").read_text(encoding="utf-8"))
    assert fichier["nom"] == "Mon Web à moi" and fichier["sources"] == sources_web


# --- [ ] Le récapitulatif final affiche l'état de chaque source (avec un bouton Tester par source).
def test_recapitulatif_etat_de_chaque_source_et_tester(cfg):
    with TestClient(app_de(cfg)) as c:
        avant = {s["id"]: s["etat_phrase"] for s in c.get("/api/reglages").json()["parties"]["recherche"]}
        assert set(avant.values()) == {"Pas encore testée."}
        r = c.post("/api/sources/wikipedia/tester").json()
        assert r["statut"] == "ok" and "Vérifiée hors ligne" in r["etat_phrase"] and r["niveaux"]["2"] == "ok"
        t = c.post("/api/sources/tavily/tester").json()  # pas de clé dans cette copie de configuration
        assert t["statut"] == "echec" and t["niveau_echec"] == 3 and "absente" in t["raison"]
        apres = {s["id"]: s["etat_phrase"] for s in c.get("/api/reglages").json()["parties"]["recherche"]}
        assert "Vérifiée hors ligne" in apres["wikipedia"] and "Test échoué" in apres["tavily"] and apres["bnf_organisations"] == "Pas encore testée."
        assert c.post("/api/sources/nexiste-pas/tester").status_code == 404
        # une source dont le test a échoué ne peut pas être activée tant que le test ne passe pas
        r = c.put("/api/reglages/source/tavily", json={"chercher": True})
        assert r.status_code == 422 and "ne peut pas être activée" in r.json()["detail"]
