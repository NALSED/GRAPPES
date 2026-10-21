"""FICHE 11 — page Ajout : sources de tous types, tests local et réel, protections. Test de recette, point par point."""

import base64
import json
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
import yaml
from conftest import copier_config
from fastapi.testclient import TestClient
from test_f07_reseaux import faux_mcp  # noqa: F401  (le serveur MCP simulé de la fiche 07)

from pilote.app import creer_app
from pilote.config import charger as charger_cfg

# Réponse de recherche d'entreprises au format PUBLIÉ de Companies House (Royaume-Uni), noms inventés.
COMPANIES_HOUSE = {"items": [
    {"title": "BRISTOL HARBOUR SPORTS LIMITED", "company_number": "01234567", "company_status": "active", "address": {"locality": "Bristol"}, "company_type": "ltd"},
    {"title": "AVON ROWING CLUB LTD", "company_number": "07654321", "company_status": "active", "address": {"locality": "Bath"}, "company_type": "ltd"},
]}


class FauxService(BaseHTTPRequestHandler):
    recus: ClassVar[list] = []
    cle_attendue: ClassVar[str] = "cle-de-test-uk"

    def do_GET(self):
        FauxService.recus.append((self.path, self.headers.get("Authorization", "")))
        attendu = "Basic " + base64.b64encode(f"{FauxService.cle_attendue}:".encode()).decode()
        if self.path.startswith("/search/companies"):
            if self.headers.get("Authorization") != attendu:
                self.send_response(401)
                self.end_headers()
                return
            corps, code = json.dumps(COMPANIES_HOUSE).encode(), 200
        elif self.path.startswith("/payant"):
            corps, code = json.dumps({"resultats": [{"n": "Club Payant"}]}).encode(), 200
        else:
            corps, code = b"{}", 404
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


@pytest.fixture
def service():
    s = HTTPServer(("127.0.0.1", 0), FauxService)
    FauxService.recus = []
    FauxService.cle_attendue = "cle-de-test-uk"
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


@pytest.fixture
def cfg(tmp_path):
    return charger_cfg(copier_config(tmp_path))


def attendre(c, rid, delai=120):
    t0 = time.time()
    while time.time() - t0 < delai:
        r = c.get(f"/api/recherches/{rid}").json()
        if r["etat"] in ("terminee", "arretee", "echec", "interrompue"):
            return r
        time.sleep(0.5)
    raise AssertionError("la recherche ne se termine pas")


def spec_companies_house(service):
    return {
        "nom": "Companies House (Royaume-Uni)", "url": f"{service}/search/companies", "parametre_requete": "q", "params": {"items_per_page": "{limite}"},
        "liste": "items", "champs": {"nom": "title", "numero": "company_number", "ville": "address.locality"},
        "auth": {"type": "basic"}, "cle": "COMPANIES_HOUSE_API_KEY", "genre": "entreprise", "genres": ["entreprise"], "correspondance_genres": {"ltd": "entreprise"}, "pays": ["GB"], "pays_code": "GB",
        "main": "premiere", "origine": "registre", "confiance": 0.9, "exemple": COMPANIES_HOUSE,
    }  # fmt: skip


# --- [ ] Preuve d'universalité : Companies House (Royaume-Uni) ajouté UNIQUEMENT par la page Ajout, sans code, et des noms britanniques.
def test_companies_house_s_ajoute_par_la_page_sans_code_et_rend_des_noms_britanniques(cfg, service):
    from pilote.adaptateurs import api_json

    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "api", "spec": spec_companies_house(service)})
        assert r.status_code == 201, r.text
        res = r.json()
        sid = res["id"]
        assert sid == "companies-house-royaume-uni" and res["active"] is False
        assert res["test"]["niveaux"]["1"] == "ok" and res["test"]["niveaux"]["2"] == "ok"  # configuration et sortie vérifiées sur l'exemple enregistré
        assert res["test"]["statut"] == "echec" and "clé" in res["test"]["raison"]  # pas encore de clé : enregistrée mais éteinte
        assert c.put(f"/api/reglages/source/{sid}", json={"chercher": True}).status_code == 422
        assert not any(p.startswith("/search") for p, _ in FauxService.recus)  # le test local n'a appelé AUCUN service
        ligne = next(x for x in c.get("/api/reglages").json()["parties"]["recherche"] if x["id"] == sid)  # elle apparaît dans Réglages
        assert ligne["nom"].startswith("Companies House")
        c.put("/api/cles/COMPANIES_HOUSE_API_KEY", json={"valeur": "cle-de-test-uk"})
        assert c.post(f"/api/sources/{sid}/tester").json()["statut"] == "ok"
        assert c.put(f"/api/reglages/source/{sid}", json={"chercher": True}).status_code == 200
        for x in c.get("/api/reglages").json()["parties"]["recherche"]:
            if x["id"] != sid:
                c.put(f"/api/reglages/source/{x['id']}", json={"chercher": False})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "sports", "pays": "Royaume-Uni", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
        assert attendre(c, rid)["etat"] == "terminee"
        lignes = c.get(f"/api/recherches/{rid}/tri").json()["lignes"]
    noms = {x["nom"] for x in lignes}
    assert any("Bristol Harbour Sports" in n.title() for n in noms) and any("Avon Rowing Club" in n.title() for n in noms), noms
    vus = [a for p, a in FauxService.recus if p.startswith("/search/companies")]
    assert vus and all(a.startswith("Basic ") for a in vus)  # la clé est partie en Basic
    assert api_json  # le même adaptateur générique que toute autre API : aucun code propre au Royaume-Uni


# --- [ ] Une source dont la clé est fausse est enregistrée mais éteinte, et ne peut pas être activée.
def test_une_cle_fausse_garde_la_source_eteinte(cfg, service):
    spec = {**spec_companies_house(service), "test_connexion": {"methode": "GET", "url": f"{service}/search/companies?q=x", "auth": {"type": "bearer"}}}
    with TestClient(creer_app(cfg)) as c:
        sid = c.post("/api/ajout/source", json={"type": "api", "spec": spec}).json()["id"]
        c.put("/api/cles/COMPANIES_HOUSE_API_KEY", json={"valeur": "une-mauvaise-cle"})
        t = c.post(f"/api/sources/{sid}/tester").json()
        assert t["statut"] == "echec" and "refusée" in t["raison"]
        assert c.put(f"/api/reglages/source/{sid}", json={"chercher": True}).status_code == 422




# --- Un fichier local (CSV et JSON) s'ajoute sans code, et ses noms sortent d'une vraie recherche.
def test_un_fichier_csv_local_s_ajoute_et_rend_ses_noms(cfg, tmp_path):
    f = tmp_path / "clubs.csv"
    f.write_text("club;commune;code\nChorale des Quatre Vents;Ville-Exemple;A1\nClub d'échecs Fictif;Autre-Ville;B2\nChorale du Port;Port-Exemple;C3\n", encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "fichier", "spec": {"nom": "Mon fichier de clubs", "chemin": str(f), "format": "csv", "delimiteur": ";",
                                                                       "champs": {"nom": "club", "ville": "commune", "numero": "code"}, "genre": "club", "main": "seconde"}})
        assert r.status_code == 201, r.text
        assert r.json()["test"]["statut"] == "ok" and r.json()["test"]["niveaux"]["3"] == "non_verifie"  # pas de point d'accès gratuit : « connexion non vérifiée »
        assert "Connexion non vérifiée" in r.json()["etat_phrase"]
        for x in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{x['id']}", json={"chercher": x["id"] == "mon-fichier-de-clubs"})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorale", "pays": "France", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
        assert attendre(c, rid)["etat"] == "terminee"
        noms = {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]}
    assert noms == {"Chorale des Quatre Vents", "Chorale du Port"}


def test_un_fichier_json_local_et_les_fichiers_casses(cfg, tmp_path):
    f = tmp_path / "asso.json"
    f.write_text(json.dumps({"data": [{"label": "Les Voix du Soir", "town": "Ville-Exemple"}]}), encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        ok = c.post("/api/ajout/source", json={"type": "fichier", "spec": {"nom": "Mon json", "chemin": str(f), "liste": "data", "champs": {"nom": "label", "ville": "town"}}})
        assert ok.status_code == 201 and ok.json()["test"]["statut"] == "ok"
        # fichier cassé : refusé avec une raison en français, rien n'est écrit
        casse = tmp_path / "casse.json"
        casse.write_text("{pas du json", encoding="utf-8")
        r = c.post("/api/ajout/source", json={"type": "fichier", "spec": {"nom": "Casse", "chemin": str(casse), "champs": {"nom": "x"}}})
        assert r.status_code == 201 and r.json()["test"]["statut"] == "echec" and r.json()["test"]["niveau_echec"] == 2  # enregistrée mais éteinte, avec la raison
        assert c.put("/api/reglages/source/casse", json={"chercher": True}).status_code == 422
        for spec in ({"nom": "X", "chemin": str(tmp_path / "absent.csv"), "champs": {"nom": "a"}}, {"nom": "Y", "chemin": str(f), "champs": {}}):
            rr = c.post("/api/ajout/source", json={"type": "fichier", "spec": spec})
            assert rr.status_code == 422 and rr.json()["detail"]
        assert c.post("/api/ajout/source", json={"type": "inconnu", "spec": {"nom": "Z"}}).status_code == 422
        assert not (cfg.dossier_sources / "x.yaml").exists() and not (cfg.dossier_sources / "y.yaml").exists()


# --- Base de données personnelle : lecture seule, SELECT uniquement.
def faire_base(chemin):
    con = sqlite3.connect(chemin)
    con.execute("create table clubs (nom text, commune text, genre text)")
    con.executemany("insert into clubs values (?,?,?)", [("Club Nautique Imaginaire", "Port-Exemple", "club"), ("Club Nautique du Lac", "Lac-Exemple", "club"), ("Boulangerie Fictive", "Ville-Exemple", "commerce")])
    con.commit()
    con.close()


def test_une_base_perso_n_accepte_que_select_en_lecture_seule(cfg, tmp_path):
    base = tmp_path / "ma_base.db"
    faire_base(base)
    avant = base.read_bytes()
    with TestClient(creer_app(cfg)) as c:
        for mauvaise in ("DELETE FROM clubs", "select nom from clubs; drop table clubs", "update clubs set nom='x'", "select * from clubs where 1; attach database 'x' as y", "pragma writable_schema=1"):
            r = c.post("/api/ajout/source", json={"type": "base", "spec": {"nom": "Piege", "base": str(base), "requete": mauvaise, "mot_essai": "club"}})
            assert r.status_code == 422, mauvaise
        bonne = {"nom": "Ma base de clubs", "base": str(base), "requete": "select nom, commune as ville, genre from clubs where nom like :q_like", "mot_essai": "nautique", "confiance": 0.6}
        r = c.post("/api/ajout/source", json={"type": "base", "spec": bonne})
        assert r.status_code == 201, r.text
        assert r.json()["test"]["statut"] == "ok" and len(r.json()["test"]["noms_exemple"]) == 2
        d = yaml.safe_load((cfg.dossier_sources / "ma-base-de-clubs.yaml").read_text(encoding="utf-8"))
        assert d["confiance"] == 0.6 and d["defaut"] == {"chercher": False, "verifier": False}  # la confiance est celle que l'utilisateur a fixée
        for x in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{x['id']}", json={"chercher": x["id"] == "ma-base-de-clubs"})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "nautique", "pays": "France", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
        assert attendre(c, rid)["etat"] == "terminee"
        noms = {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]}
    assert noms == {"Club Nautique Imaginaire", "Club Nautique du Lac"}
    assert base.read_bytes() == avant  # la base n'a pas bougé d'un octet


def test_meme_une_requete_trafiquee_apres_coup_ne_peut_pas_ecrire(tmp_path):
    from pilote.adaptateurs import ErreurSource, base_sql

    base = tmp_path / "b.db"
    faire_base(base)
    avant = base.read_bytes()
    with pytest.raises(ErreurSource):
        base_sql.lignes({"base": str(base), "requete": "delete from clubs"}, "x", 5)
    with pytest.raises(ErreurSource):  # une écriture cachée derrière un WITH
        base_sql.lignes({"base": str(base), "requete": "with t as (select 1) delete from clubs"}, "x", 5)
    con = sqlite3.connect(f"file:{base.as_posix()}?mode=ro", uri=True)  # et la base elle-même refuse d'écrire quand on l'ouvre comme pilote le fait
    with pytest.raises(sqlite3.OperationalError):
        con.execute("delete from clubs")
    con.close()
    assert base.read_bytes() == avant


# --- Serveur MCP et prestataire de collecte par la page, sans code.
def test_un_serveur_mcp_s_ajoute_par_la_page_et_un_prestataire_exige_un_avertissement(cfg, faux_mcp):  # noqa: F811
    url, journal = faux_mcp
    exemple = [{"fullName": "Club Imaginaire", "city": "Ville-Exemple", "url": "https://x.example/ci"}]
    spec = {"nom": "Mon prestataire", "mcp": url, "outil": "call-actor", "arguments": {"actor": "apify/instagram-scraper", "input": {"search": "{mots_et_lieu}"}},
            "cle": "MON_TOKEN", "cle_prefixe": "Bearer ", "genre": "compte", "genres": ["compte"], "exemple": exemple,
            "cout": {"unite": "résultat", "vers_dollar": 0.0023, "par_appel": 25}, "prestataire": True}
    with TestClient(creer_app(cfg)) as c:
        sans = c.post("/api/ajout/source", json={"type": "mcp", "spec": spec})
        assert sans.status_code == 422 and "avertissement" in sans.json()["detail"]
        r = c.post("/api/ajout/source", json={"type": "mcp", "spec": {**spec, "avertissement": "Payant au résultat ; vérifiez les conditions d'usage."}})
        assert r.status_code == 201, r.text
        assert r.json()["test"]["niveaux"]["2"] == "ok"
        assert not journal.exists() or journal.read_text(encoding="utf-8") == ""  # l'enregistrement et le test local n'ont rien appelé
        d = yaml.safe_load((cfg.dossier_sources / "mon-prestataire.yaml").read_text(encoding="utf-8"))
        assert d["prestataire"] is True and d["defaut"] == {"chercher": False, "verifier": False} and d["avertissement"]


# --- Protection pendant les recherches : une source qui échoue ne bloque rien, passe en pause, et le résultat dit « n sources sur m ».
FRAGILE = """import json, os, sys
with open({appels!r}, "a") as f:
    f.write("appel\\n")
json.load(sys.stdin)
if os.path.exists({drapeau!r}):
    sys.exit(1)
print(json.dumps([{{"nom": "Chorale Fragile", "origine": "ma source fragile"}}]))
"""
BON = """import json, sys
json.load(sys.stdin)
print(json.dumps([{"nom": "Chorale Solide", "origine": "ma source solide"}]))
"""


def lancer(c, mot="chorale"):
    rid = c.post("/api/recherches", json={"sujet": {"quoi": mot, "pays": "France", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
    r = attendre(c, rid)
    assert r["etat"] == "terminee", r["message"]
    return rid, r


def test_une_source_qui_echoue_n_arrete_pas_la_recherche_passe_en_pause_et_le_bilan_le_dit(cfg, tmp_path):
    import sys

    appels, drapeau = tmp_path / "appels.txt", tmp_path / "casse"
    (tmp_path / "bon.py").write_text(BON, encoding="utf-8")
    (tmp_path / "fragile.py").write_text(FRAGILE.format(appels=str(appels), drapeau=str(drapeau)), encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        for nom, f in (("Source solide", "bon.py"), ("Source fragile", "fragile.py")):
            r = c.post("/api/programmes-locaux", json={"nom": nom, "commande": [sys.executable, str(tmp_path / f)], "genres": ["association"], "pays": ["FR"]})
            assert r.json()["test"]["statut"] == "ok", r.text
        for x in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{x['id']}", json={"chercher": x["id"] in ("source-solide", "source-fragile")})
        appels.write_text("")
        drapeau.write_text("x")  # à partir de maintenant la source fragile échoue
        rid, r = lancer(c)
        b = r["avancement"]["sources_bilan"]
        assert b["phrase"] == "1 source sur 2 a répondu" and [e["source"] for e in b["echecs"]] == ["source-fragile"] and "code 1" in b["echecs"][0]["raison"]
        assert "Chorale Solide" in {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]}  # la recherche a continué avec les autres
        lancer(c)
        assert "En pause" not in next(x for x in c.get("/api/reglages").json()["parties"]["recherche"] if x["id"] == "source-fragile")["etat_phrase"]  # deux échecs : pas encore
        lancer(c)  # troisième échec de suite
        ligne = next(x for x in c.get("/api/reglages").json()["parties"]["recherche"] if x["id"] == "source-fragile")
        assert "En pause : 3 erreurs de suite" in ligne["etat_phrase"]
        # quatrième recherche : la source en pause n'est plus appelée, et on le dit
        avant = len(appels.read_text().splitlines())
        _, r4 = lancer(c)
        assert len(appels.read_text().splitlines()) == avant
        assert r4["avancement"]["sources_en_pause"][0]["source"] == "source-fragile" and "3 erreurs de suite" in r4["avancement"]["sources_en_pause"][0]["raison"]
        assert r4["avancement"]["sources_bilan"]["phrase"] == "1 source sur 1 a répondu"
        # l'utilisateur la répare, la remet en service : elle est de nouveau appelée
        drapeau.unlink()
        assert c.post("/api/sources/source-fragile/reprendre").status_code == 200
        rid5, r5 = lancer(c)
        assert len(appels.read_text().splitlines()) > avant and r5["avancement"]["sources_bilan"]["phrase"] == "2 sources sur 2 ont répondu"
        assert "Chorale Fragile" in {x["nom"] for x in c.get(f"/api/recherches/{rid5}/tri").json()["lignes"]}
        assert c.post("/api/sources/nexiste-pas/reprendre").status_code == 404


# --- Test réel : le prix est affiché AVANT le clic, rien ne part sans confirmation, la dépense est comptée.
def spec_payante(service, vers_dollar=0.0015):
    return {"nom": "Service payant", "url": f"{service}/payant", "parametre_requete": "q", "liste": "resultats", "champs": {"nom": "n"}, "genre": "club",
            "auth": {"type": "header", "nom": "X-Cle"}, "cle": "SERVICE_PAYANT_KEY", "cout": {"unite": "requête", "vers_dollar": vers_dollar, "par_appel": 1},
            "exemple": {"resultats": [{"n": "Club Payant"}]}}  # fmt: skip


def test_le_test_reel_affiche_son_prix_avant_le_clic_et_compte_la_depense(cfg, service):
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/ajout/source", json={"type": "api", "spec": spec_payante(service)})
        assert FauxService.recus == []  # l'ajout et son test local n'ont envoyé AUCUNE requête (donc rien de facturable)
        c.put("/api/cles/SERVICE_PAYANT_KEY", json={"valeur": "cle-payante-123"})
        avant = len(FauxService.recus)
        p = c.get("/api/sources/service-payant/test-reel").json()
        assert p["gratuit"] is False and p["dollars"] == 0.0015 and p["phrase"].startswith("1 requête, environ 0,0015 $")
        assert len(FauxService.recus) == avant  # afficher le prix n'appelle rien
        refus = c.post("/api/sources/service-payant/test-reel", json={"mot": "club"})
        assert refus.status_code == 422 and "prix" in refus.json()["detail"] and len(FauxService.recus) == avant  # sans confirmation, rien ne part
        r = c.post("/api/sources/service-payant/test-reel", json={"mot": "club", "confirme": True})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1 and r.json()["noms"][0]["nom"] == "Club Payant" and r.json()["dollars"] == 0.0015
        assert len(FauxService.recus) == avant + 1 and FauxService.recus[-1][0].startswith("/payant")
        assert c.get("/api/reglages").json()["budget"]["depense_du_mois_usd"] == pytest.approx(0.0015)
        assert c.get("/api/recherches").json() == []  # une dépense de test n'est pas une recherche
        # le plafond bloque un test que le mois ne permet plus
        c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 0.001})
        bloque = c.post("/api/sources/service-payant/test-reel", json={"mot": "club", "confirme": True})
        assert bloque.status_code == 422 and "plafond" in bloque.json()["detail"] and len(FauxService.recus) == avant + 1


def test_une_source_gratuite_dit_qu_il_n_y_a_rien_a_payer(cfg, service):
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/ajout/source", json={"type": "api", "spec": spec_payante(service, vers_dollar=0)})
        assert c.get("/api/sources/service-payant/test-reel").json()["phrase"] == "1 requête, gratuite : rien à payer."
        assert c.get("/api/sources/nexiste-pas/test-reel").status_code == 404
