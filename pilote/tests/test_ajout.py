"""Étape 5 : page Ajout (catalogue de l'État, adresse collée, formulaire) — avec un petit serveur local, jamais le réseau."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import catalogue
from pilote.app import creer_app
from pilote.config import charger

CLUBS = [
    {"nom_complet": "FENIX TOULOUSE HANDBALL", "siren": "422893214", "siege": {"libelle_commune": "TOULOUSE"}, "activite": "Activités de clubs de sports"},
    {"nom_complet": "MONTPELLIER HANDBALL", "siren": "300000001", "siege": {"libelle_commune": "MONTPELLIER"}, "activite": "Activités de clubs de sports"},
    {"nom_complet": "HBC NANTES", "siren": "300000002", "siege": {"libelle_commune": "NANTES"}, "activite": "Activités de clubs de sports"},
    {"nom_complet": "BOULANGERIE DU COIN", "siren": "1", "siege": {"libelle_commune": "LYON"}, "activite": "Boulangerie"},
]
CSV = "Nom du club;Commune;Code\nFenix Toulouse;Toulouse;31\nHBC Nantes;Nantes;44\nAutre;Paris;75\n"


class Gestionnaire(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlsplit(self.path)
        if u.path == "/search":
            q = (parse_qs(u.query).get("q") or [""])[0].lower()
            rep = {"total": len(CLUBS), "results": [c for c in CLUBS if q in c["nom_complet"].lower()]}
            corps, typ = json.dumps(rep).encode(), "application/json"
        elif u.path == "/liste.csv":
            corps, typ = CSV.encode(), "text/csv"
        elif u.path == "/flux.xml":
            corps, typ = b"<rss><channel><item><title>x</title></item></channel></rss>", "application/rss+xml"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", typ)
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture(scope="module")
def serveur():
    s = HTTPServer(("127.0.0.1", 0), Gestionnaire)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


@pytest.fixture
def cfg(tmp_path):
    g = tmp_path / "g"
    (g / "config" / "recherche").mkdir(parents=True)
    (g / "src").symlink_to(charger().grappes_racine / "src")
    (g / "config" / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    f = tmp_path / "config" / "pilote.yaml"
    f.parent.mkdir()
    base = charger()
    f.write_text(f"service: {{https: false, hotes_autorises: [testserver]}}\ngrappes: {{racine: {g}}}\ndonnees: {{dossier: {tmp_path / 'd'}}}\n"
                 + yaml.safe_dump({"familles": list(base.familles), "ordre_familles": list(base.ordre_familles)}), encoding="utf-8")
    return charger(f)


SPEC_JSON = {"nom": "Annuaire d'essai", "format": "json", "items": "results", "parametre_requete": "q",
             "champs": {"nom": "nom_complet", "ville": "siege.libelle_commune", "genre": "activite", "id": "siren"}}


def test_appeler_json_montre_les_champs_a_designer(cfg, serveur):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.post("/api/ajout/appeler", json={"url": serveur + "/search?q=handball"}).json()
    assert r["format"] == "json" and r["items"] == "results" and r["nb_items"] == 2
    champs = {x["champ"]: x["valeur"] for x in r["echantillon"]}
    assert champs["nom_complet"] == "FENIX TOULOUSE HANDBALL" and champs["siege.libelle_commune"] == "TOULOUSE"
    assert r["parametre_requete"] == "q" and r["mot_essai"] == "handball"


def test_appeler_csv_detecte_le_separateur(cfg, serveur):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.post("/api/ajout/appeler", json={"url": serveur + "/liste.csv"}).json()
    assert r["format"] == "csv" and r["delimiteur"] == ";" and r["nb_items"] == 3
    assert {x["champ"] for x in r["echantillon"]} == {"Nom du club", "Commune", "Code"}


def test_adresses_refusees_en_clair(cfg, serveur):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        assert c.post("/api/ajout/appeler", json={"url": "file:///etc/passwd"}).status_code == 422
        assert c.post("/api/ajout/appeler", json={"url": serveur + "/nulle-part"}).status_code == 422
        assert "erreur" in c.post("/api/ajout/appeler", json={"url": serveur + "/nulle-part"}).json()["detail"]
        assert c.post("/api/ajout/appeler", json={"url": "http://127.0.0.1:9/x"}).status_code == 422


def test_test_obligatoire_puis_enregistrement_desactive(cfg, serveur):
    spec = {**SPEC_JSON, "url": serveur + "/search?q=handball"}
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        # sans test : refusé
        r = c.post("/api/ajout/enregistrer", json={"spec": spec})
        assert r.status_code == 422 and "Testez la prise d'abord" in r.json()["detail"]
        t = c.post("/api/ajout/tester", json={"spec": spec, "mot": "handball"}).json()
        assert t["ok"] and t["total"] == 2 and sorted(n["nom"] for n in t["noms"]) == ["FENIX TOULOUSE HANDBALL", "MONTPELLIER HANDBALL"]
        fenix = next(n for n in t["noms"] if n["nom"].startswith("FENIX"))
        assert fenix["ville"] == "TOULOUSE" and fenix["genre"] == "Activités de clubs de sports" and fenix["id"] == "422893214"
        r = c.post("/api/ajout/enregistrer", json={"spec": spec}).json()
        assert r == {"id": "annuaire-d-essai", "fichier": "annuaire-d-essai.yaml", "active": False}
        # une autre spécification (non testée) reste refusée
        assert c.post("/api/ajout/enregistrer", json={"spec": {**spec, "nom": "Autre"}}).status_code == 422
        # jamais d'écrasement
        assert c.post("/api/ajout/enregistrer", json={"spec": spec}).status_code == 422
    f = cfg.dossier_grappes_config / "recherche" / "annuaire-d-essai.yaml"
    y = yaml.safe_load(f.read_text(encoding="utf-8"))
    assert y["actif"] is False and y["type"] == "registre" and y["params"] == {"q": "{requete}"} and y["response"] == {"items": "results"}
    assert y["fields"] == {"nom": "nom_complet", "id": "siren", "ville": "siege.libelle_commune", "type": "activite"}
    assert f.read_text(encoding="utf-8").startswith("# Annuaire d'essai\n# Ajoutée avec pilote")


def test_la_prise_enregistree_est_lisible_par_grappes(cfg, serveur):
    # (l'affichage dans Réglages est refait avec la fiche 11 : les sources y sont désormais des déclarations de pilote)
    spec = {**SPEC_JSON, "url": serveur + "/search?q=handball"}
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        c.post("/api/ajout/tester", json={"spec": spec, "mot": "handball"})
        c.post("/api/ajout/enregistrer", json={"spec": spec})
    from grappes.decouverte.sources_yaml import charger_sources

    s = next(x for x in charger_sources(cfg.dossier_grappes_config / "recherche") if x.id == "annuaire-d-essai")
    assert s.actif is False and s.params == {"q": "{requete}"}


def test_test_sans_resultat_dit_pourquoi_et_n_autorise_rien(cfg, serveur):
    spec = {**SPEC_JSON, "url": serveur + "/search?q=handball", "champs": {"nom": "champ_inexistant"}}
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        t = c.post("/api/ajout/tester", json={"spec": spec, "mot": "handball"}).json()
        assert t["ok"] is False and "aucun nom" in t["message"]
        assert c.post("/api/ajout/enregistrer", json={"spec": spec}).status_code == 422
        assert c.post("/api/ajout/tester", json={"spec": SPEC_JSON, "mot": "handball"}).status_code == 422  # pas d'adresse
        assert c.post("/api/ajout/tester", json={"spec": {**SPEC_JSON, "url": serveur + "/search?q=x", "champs": {}}, "mot": "x"}).status_code == 422


def test_csv_a_la_main(cfg, serveur):
    spec = {"nom": "Clubs en CSV", "url": serveur + "/liste.csv", "format": "csv", "delimiteur": ";", "champs": {"nom": "Nom du club", "ville": "Commune"}}
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        t = c.post("/api/ajout/tester", json={"spec": spec, "mot": "toulouse"}).json()
        assert t["ok"] and [n["nom"] for n in t["noms"]] == ["Fenix Toulouse"] and t["noms"][0]["ville"] == "Toulouse"
        assert c.post("/api/ajout/enregistrer", json={"spec": spec}).status_code == 201


def test_flux_xml_refuse_clairement(cfg, serveur):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.post("/api/ajout/tester", json={"spec": {"nom": "x", "url": serveur + "/flux.xml", "format": "xml", "champs": {"nom": "title"}}, "mot": "x"})
        assert r.status_code == 422 and "XML" in r.json()["detail"]


# ---- catalogue de l'État : lecture des réponses du serveur MCP (texte étiqueté) ----
JEUX = """Found 92 dataset(s) for query: 'festivals'
Page 1 of results:

1. Liste des festivals en France
   ID: 62cf95993d99f22480f49334
   Organization: Ministère de la Culture
   Tags: culture, festival
   Resources: 1
   URL: https://www.data.gouv.fr/datasets/liste-des-festivals-en-france

2. Panorama des festivals
   ID: 5b51825fa3a72936dfe1c340
   Organization: Ministère de la Culture
   Resources: 4
   URL: https://www.data.gouv.fr/datasets/panorama-des-festivals
"""
RESSOURCES = """Resources in dataset: Liste des festivals en France
Total resources: 2

1. festivals-global-festivals
   Resource ID: 47ac11c2-8a00-46a7-9fa8-9b802643f975
   Format: csv
   Size: 2.5 MB
   URL: https://static.data.gouv.fr/resources/liste-des-festivals-en-france/festivals.csv

2. documentation
   Resource ID: 11111111-1111-1111-1111-111111111111
   Format: pdf
   URL: https://static.data.gouv.fr/doc.pdf
"""
OPENAPI = """OpenAPI spec for: API Recherche d’Entreprises
Base API URL: https://recherche-entreprises.api.gouv.fr

Servers:
  - https://recherche-entreprises.api.gouv.fr (Serveur de production)

Endpoints (2 paths):
  GET /search
    Recherche textuelle
      - q [query, string]
      - page [query, integer]
      - per_page [query, integer]
  GET /near_point
    Recherche géographique
      - lat [query, number] (required)
      - long [query, number] (required)
"""


def test_lecture_des_reponses_du_catalogue():
    j = catalogue.lire_jeux(JEUX)
    assert [x["id"] for x in j] == ["62cf95993d99f22480f49334", "5b51825fa3a72936dfe1c340"] and j[0]["organisation"] == "Ministère de la Culture"
    r = catalogue.lire_ressources(RESSOURCES)
    assert [x["format"] for x in r] == ["csv", "pdf"] and r[0]["url"].endswith("festivals.csv")
    o = catalogue.lire_openapi(OPENAPI)
    assert o["base"] == "https://recherche-entreprises.api.gouv.fr"
    assert [p["chemin"] for p in o["points"]] == ["/search", "/near_point"]
    assert o["points"][0]["parametre_requete"] == "q" and o["points"][1]["parametre_requete"] == ""
    assert [p["nom"] for p in o["points"][1]["parametres"]] == ["lat", "long"] and o["points"][1]["parametres"][0]["requis"]


def test_catalogue_injoignable_dit_pourquoi(cfg, monkeypatch):
    def casse(*a, **k):
        raise catalogue.CatalogueIndisponible("le catalogue de l'État est injoignable (réseau)")

    monkeypatch.setattr(catalogue, "appeler", casse)
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.get("/api/ajout/catalogue?q=festivals")
        assert r.status_code == 502 and "injoignable" in r.json()["detail"]
        assert c.get("/api/ajout/catalogue?q=%20").status_code == 422


def test_catalogue_chercher_assemble_apis_et_jeux(cfg, monkeypatch):
    def faux(cfg_, outil, args):
        return JEUX if outil == "search_datasets" else "Found 1 third-party API(s)\n\n1. API Recherche d’Entreprises\n   ID: 672cf684c3488a0c533f7094\n   Organization: DINUM\n   Base API URL: https://recherche-entreprises.api.gouv.fr\n   URL: https://www.data.gouv.fr/dataservices/672cf684c3488a0c533f7094\n"

    monkeypatch.setattr(catalogue, "appeler", faux)
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.get("/api/ajout/catalogue?q=entreprises").json()
    assert r["apis"][0]["base"] == "https://recherche-entreprises.api.gouv.fr" and len(r["jeux"]) == 2


@pytest.mark.reseau
def test_rendu_de_la_page_ajout_sous_node():
    import shutil
    import subprocess
    from pathlib import Path

    if shutil.which("node") is None:
        pytest.skip("node absent")
    r = subprocess.run(["node", "tests/js/rendu_ajout.mjs"], capture_output=True, text=True, check=False, cwd=Path(__file__).resolve().parents[1])
    assert r.returncode == 0, r.stdout + r.stderr
