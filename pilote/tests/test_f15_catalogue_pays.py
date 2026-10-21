"""Fiche 15, chapitre 3 — Catalogue des bases officielles par pays (une donnée, pas du code)."""

from __future__ import annotations

import dataclasses

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import catalogue_pays
from pilote.app import creer_app
from pilote.refus import ConfigRefusee

PAYS_VERIFIES = {"FR", "GB", "NZ", "NO", "EE", "CZ", "PL", "US", "CA"}


def test_les_neuf_pays_verifies_sont_au_catalogue_et_valides(cfg):
    cat, problemes = catalogue_pays.charger(cfg)
    assert problemes == [] and set(cat) == PAYS_VERIFIES
    for d in cat.values():
        assert d["bases"], d["pays"]
        assert all(b["verifie_le"] and b["licence"] and b["url"].startswith("https://") for b in d["bases"])


def test_le_catalogue_ne_contient_aucun_poids_ecrit(cfg):
    texte = "".join(f.read_text(encoding="utf-8") for f in catalogue_pays.dossier(cfg).glob("*.yaml"))
    assert "taille" not in texte and "octets" not in texte  # le poids est demandé au serveur


def test_pays_inconnu_le_dit_et_propose_ckan_ou_ajout(cfg):
    r = catalogue_pays.pour_pays(cfg, "zz", [])
    assert r["trouve"] is False and r["bases"] == [] and "Pas de catalogue pour ce pays" in r["message"] and "CKAN" in r["message"] and "Ajout" in r["message"]


def test_les_bases_sont_cochees_selon_les_presets(cfg):
    r = catalogue_pays.pour_pays(cfg, "FR", ["associations"])
    coche = {b["id"]: b["coche"] for b in r["bases"]}
    assert coche["rna"] is True and coche["sirene"] is False and coche["osm-geofabrik"] is False
    assert [b["id"] for b in r["bases"] if b["telechargeable"]] == ["osm-geofabrik"]


@pytest.mark.parametrize(("contenu", "dit"), [
    ({"pays": "FR", "bases": [{"id": "a", "nom": "A", "contenu": "x", "acces": "api", "licence": "x", "url": "ftp://x", "verifie_le": "2026-01-01"}]}, "http"),
    ({"pays": "FR", "bases": [{"id": "a", "nom": "A", "contenu": "x", "acces": "magie", "licence": "x", "url": "https://x", "verifie_le": "2026-01-01"}]}, "magie"),
    ({"pays": "FR", "bases": [{"id": "a", "nom": "A", "contenu": "x", "acces": "api", "licence": "x", "url": "https://x"}]}, "verifie_le"),
    ({"pays": "FR", "bases": [{"id": "a", "nom": "A", "contenu": "x", "acces": "api", "licence": "x", "url": "https://x", "verifie_le": "2026-01-01", "poids": 3}]}, "inconnu"),
    ({"pays": "France", "bases": []}, "deux lettres"),
])
def test_une_entree_fausse_est_refusee_avec_la_phrase_qui_dit_ou(contenu, dit):
    with pytest.raises(ConfigRefusee, match=dit):
        catalogue_pays.valider(contenu, "FR.yaml")


def test_un_fichier_casse_n_arrete_pas_les_autres(tmp_path, cfg):
    d = tmp_path / "catalogue_pays"
    d.mkdir()
    (d / "FR.yaml").write_text(yaml.safe_dump({"pays": "FR", "nom": "France", "bases": [{"id": "a", "nom": "A", "contenu": "x", "acces": "api", "licence": "x", "url": "https://x", "verifie_le": "2026-01-01"}]}), encoding="utf-8")
    (d / "GB.yaml").write_text("pays: [", encoding="utf-8")
    cfg2 = dataclasses.replace(cfg, dossier_config=tmp_path, chemins={})
    cat, problemes = catalogue_pays.charger(cfg2)
    assert set(cat) == {"FR"} and len(problemes) == 1


def test_l_api_repond_et_refuse_une_adresse_hors_catalogue(cfg):
    c = TestClient(creer_app(cfg))
    r = c.get("/api/catalogue-pays", params={"pays": "no"}).json()
    assert r["trouve"] and r["nom"] == "Norvège" and r["bases"]
    assert c.get("/api/catalogue-pays", params={"pays": "ZZ"}).json()["trouve"] is False
    assert c.get("/api/catalogue-pays/taille", params={"url": "https://exemple.invalide/x.pbf"}).status_code == 404


def test_phrase_de_taille():
    assert catalogue_pays.phrase_taille(5_100_000_000) == "5.1 Go" and catalogue_pays.phrase_taille(123_000_000) == "123 Mo" and "inconnu" in catalogue_pays.phrase_taille(None)


def test_taille_reelle_demandee_au_serveur_sans_rien_telecharger(cfg):
    url = next(b["telechargement"] for b in catalogue_pays.charger(cfg)[0]["EE"]["bases"] if "telechargement" in b)
    n = catalogue_pays.taille(url)
    if n is None:
        pytest.skip("Geofabrik ne répond pas")
    assert 50e6 < n < 1e9  # l'Estonie : une centaine de Mo


def test_une_adresse_morte_est_signalee_et_une_vivante_non(cfg):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/vivante" else 404)
            self.end_headers()

        do_HEAD = do_GET

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    d = catalogue_pays.dossier(cfg)
    for f in d.glob("*.yaml"):
        f.unlink()
    b = {"nom": "A", "contenu": "x", "acces": "api", "licence": "x", "verifie_le": "2026-01-01"}
    (d / "FR.yaml").write_text(yaml.safe_dump({"pays": "FR", "nom": "France", "bases": [{"id": "ok", "url": base + "/vivante", **b}, {"id": "mort", "url": base + "/disparue", **b}]}), encoding="utf-8")
    morts = catalogue_pays.verifier_adresses(cfg, delai=3)
    s.shutdown()
    assert [(m["base"], m["erreur"]) for m in morts] == [("mort", "404")] or [m["base"] for m in morts] == ["mort"]


def test_la_page_reglages_montre_les_bases_du_pays_et_le_poids(chromium, serveur_vivant, cfg):
    with TestClient(creer_app(cfg)) as c:  # la première installation est faite (sinon l'assistant cache la page)
        assert c.post("/api/assistant/terminer", json={"etape1": {"pays": "FR", "presets_coches": ["web"], "chercher": [], "plafond": 5},
                                                       "etape2": {"active": True, "mode": "memes", "verifier": []}, "etape3": {"actifs": ["csv"], "dossier": ""}}).status_code == 200
    url = serveur_vivant(creer_app(cfg))
    page = chromium.new_context(viewport={"width": 1200, "height": 900}).new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(url + "/")
    page.click('.tab[data-p="reglages"]')
    page.evaluate("document.querySelectorAll('details.bloc').forEach(d => d.open = true)")  # les blocs de Réglages sont repliés au départ
    page.fill("#cat-pays", "ee")
    page.click("#cat-voir")
    page.wait_for_selector("#cat-liste .srow", timeout=10000)
    assert "licence" in page.inner_text("#cat-liste") and "OpenStreetMap" in page.inner_text("#cat-liste")
    page.fill("#cat-pays", "fr")
    page.click("#cat-voir")
    page.wait_for_selector("select[data-zone]", timeout=10000)
    assert page.locator("select[data-zone] option").count() == 28  # France entière + 27 zones
    page.fill("#cat-pays", "zz")
    page.click("#cat-voir")
    page.wait_for_function("document.querySelector('#cat-liste').innerText.includes('Pas de catalogue')")
    assert erreurs == [], erreurs
