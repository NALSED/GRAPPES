"""FICHE 03 — preset Web : test de recette, point par point."""

import urllib.error
import urllib.request

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.sources import charger_sources

SOURCES_WEB = {"searxng", "tavily", "brave", "linkup", "exa", "marginalia", "mojeek", "wayback", "serper", "firecrawl"}  # serper et firecrawl : spécification 17, 26/10/2026


def declarations_web(cfg):
    decls, problemes = charger_sources(cfg)
    assert problemes == []
    return {d.id: d for d in decls.values() if "web" in d.usages and d.roles != ["enrichir"]}  # sans RDAP (ENRICHIR, registre du domaine), rangé aussi dans Web : voir plus bas


# --- [ ] SearXNG est installé sur la VM et répond en local.
@pytest.mark.reseau
def test_searxng_repond_en_local():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8888/search?q=handball&format=json", timeout=30) as r:
            import json

            d = json.load(r)
    except (urllib.error.URLError, OSError):
        pytest.skip("SearXNG ne tourne pas sur cette machine")
    assert isinstance(d.get("results"), list) and d["results"] and {"title", "url"} <= set(d["results"][0])
    with urllib.request.urlopen("http://127.0.0.1:8888/healthz", timeout=10) as r:
        assert r.status == 200  # le point de santé de SearXNG répond aussi


# --- [ ] Le preset Web, livré tel quel, fonctionne sans aucune clé payante (SearXNG n'en demande aucune).
def test_le_preset_web_livre_marche_sans_cle_payante(cfg):
    web = declarations_web(cfg)
    assert set(web) == SOURCES_WEB
    allumees = {sid for sid, d in web.items() if d.defaut["chercher"]}
    assert allumees == {"searxng", "tavily"}  # exactement celles de la fiche
    assert web["searxng"].cle == "" and not web["searxng"].payant
    # la seule allumée qui demande une clé est Tavily, et son offre gratuite couvre 1 000 requêtes par mois
    assert [sid for sid in allumees if web[sid].cle] == ["tavily"] and web["tavily"].cout["gratuit_par_mois"] == 1000
    # sans aucune clé : seule SearXNG est utilisée par une recherche
    from pilote.moteur_sources import choisies

    assert [d.id for d in choisies(cfg, {"sources": sorted(web)})] == ["searxng"]  # sans aucune clé : SearXNG seule cherche (Wayback ne fait que vérifier des adresses)
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        lignes = {s["id"]: s for s in c.get("/api/reglages").json()["parties"]["recherche"]}
    assert lignes["searxng"]["chercher"] is True and lignes["searxng"]["bloquee_par_cle"] is False


# --- [ ] Les trois sources payantes sont bien éteintes dans la configuration livrée.
def test_les_trois_sources_payantes_sont_eteintes(cfg):
    web = declarations_web(cfg)
    for sid in ("brave", "linkup", "exa"):
        assert web[sid].defaut == {"chercher": False, "verifier": False} and web[sid].payant and web[sid].cle
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        lignes = {s["id"]: s for s in c.get("/api/reglages").json()["parties"]["recherche"]}
    assert not any(lignes[s]["chercher"] or lignes[s]["verifier"] for s in ("brave", "linkup", "exa"))


# --- [ ] Chaque source déclare : seconde main, son coût, ses pays (monde), son usage.
def test_chaque_source_web_declare_main_cout_pays_et_usage(cfg):
    for sid, d in declarations_web(cfg).items():
        assert d.main == "seconde", sid
        assert d.pays == ["monde"], sid
        assert "web" in d.usages and d.genres == ["page"], sid
        assert {"unite", "vers_dollar", "par_appel", "gratuit_par_mois"} <= set(d.cout), sid
        assert d.famille == "api"
    brut = yaml.safe_load((cfg.dossier_sources / "searxng.yaml").read_text(encoding="utf-8"))
    assert brut["main"] == "seconde" and brut["pays"] == ["monde"] and brut["usages"] == ["web"]


def test_les_autres_sources_citees_dans_la_fiche_ne_sont_pas_la(cfg):
    ids = set(charger_sources(cfg)[0])
    for exclu in ("scrapingbee", "scraperapi", "zenrows", "bing", "google_custom_search"):
        assert exclu not in ids  # fiche 03, « non retenu » (Serper en est sorti le 26/10/2026 : spécification 17, F23-3)


def test_les_prises_payantes_se_lisent_hors_ligne(cfg):
    from pilote.tests_source import tester

    for sid in ("searxng", "brave", "linkup", "exa"):
        r = tester(cfg, charger_sources(cfg)[0][sid])
        assert r["niveaux"]["1"] == "ok" and r["niveaux"]["2"] == "ok", (sid, r)  # configuration et convention de sortie, sans appeler le service
        assert next(n["nom"] for n in r["noms_exemple"]) == "Club Exemple de Handball"


# --- [ ] Wayback (vérification d'une adresse) et Mojeek (diversification du Web) : simulés tant que les clés ou le réseau manquent.
def test_wayback_rend_un_nom_seulement_si_une_capture_existe():
    import json
    from pathlib import Path

    from pilote.adaptateurs import wayback

    rep = json.loads((Path(__file__).parent.parent / "config/sources/exemples/wayback.json").read_text(encoding="utf-8"))
    noms = wayback.convertir(rep, "club-exemple.example", "Club Exemple")
    assert noms == [{"nom": "Club Exemple", "site": "club-exemple.example", "numero": rep["archived_snapshots"]["closest"]["url"], "origine": "Wayback Machine (capture du 12/04/2019)"}]
    assert wayback.convertir({"archived_snapshots": {}}, "mort.example", "Mort") == []


def test_wayback_ne_cherche_pas_par_nom():
    from pilote.adaptateurs import wayback

    class SansReseau:
        def get_json(self, *a, **k):
            raise AssertionError("aucun appel sans adresse")

    assert wayback.chercher({"quoi": "Club Exemple"}, SansReseau(), {}) == []


def test_mojeek_est_eteinte_sans_cle_et_dans_le_preset_web(cfg):
    d = declarations_web(cfg)["mojeek"]
    assert d.cle == "MOJEEK_API_KEY" and d.defaut["chercher"] is False


# --- [ ] RDAP (spécification 26) : la catégorie Web gagne une autre nature d'information, ce que l'infrastructure d'une organisation dit d'elle.
def test_rdap_est_rangee_dans_web_comme_un_enrichissement_de_premiere_main(cfg):
    decls, _ = charger_sources(cfg)
    r = decls["rdap"]
    assert "web" in r.usages and r.roles == ["enrichir"] and r.main == "premiere" and r.fiabilite == "B" and r.cles == []
