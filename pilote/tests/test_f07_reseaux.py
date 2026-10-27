"""FICHE 07 — preset Réseaux sociaux : test de recette, point par point."""

import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import budget as bg
from pilote.adaptateurs import Client, ErreurSource, charger
from pilote.app import creer_app
from pilote.config import RACINE
from pilote.config import charger as charger_config
from pilote.moteur_sources import choisies, materialiser
from pilote.sources import charger_sources

PRESTATAIRES = ("apify-instagram", "apify-facebook", "brightdata-recherche")


def en_ligne(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pilote-test"}), timeout=10)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def du_preset(cfg):
    decls, problemes = charger_sources(cfg)
    assert problemes == []
    return {d.id: d for d in decls.values() if "reseaux_sociaux" in d.usages}


# --- [ ] Telegram fonctionne par annuaires, sans clé payante.
@pytest.mark.reseau
def test_telegram_par_annuaires_sans_cle_rend_des_comptes():
    if not en_ligne("http://127.0.0.1:8888/healthz"):
        pytest.skip("SearXNG local absent")
    noms = charger("telegram_annuaires").chercher({"quoi": "handball", "lieu": "Lyon", "limite": 15}, Client("telegram-annuaires", delai_s=0.5), {})
    assert noms and all(n["site"].startswith("https://t.me/") and n["genre"] == "compte" and n["nom"] for n in noms)


def test_telegram_nettoie_les_titres_ramene_les_apercus_au_canal_et_ignore_les_pages_sans_canal():
    from pilote.adaptateurs import telegram_annuaires as t

    noms = t.convertir(json.loads((RACINE / "config/sources/exemples/telegram-annuaires.json").read_text(encoding="utf-8")))
    assert [(n["nom"], n["site"]) for n in noms] == [
        ("Club Exemple", "https://t.me/club_exemple"), ("@quelquun", "https://t.me/quelquun"), ("@canal_exemple", "https://t.me/canal_exemple"),
    ]  # la page sans canal est ignorée ; l'aperçu « /s/canal_exemple » est le même canal : un seul nom


def test_telegram_ne_demande_aucune_cle_ni_depense(cfg):
    d = du_preset(cfg)["telegram-annuaires"]
    assert d.cle == "" and not d.payant and d.defaut["chercher"] is True and d.moteur["adaptateur"] == "telegram_annuaires"


# --- [ ] Meetup fonctionne sans clé payante (jeton gratuit) ; Reddit fonctionne avec clé et reste éteint sans clé.
class FauxReseaux(BaseHTTPRequestHandler):
    recus: ClassVar[list] = []

    def _rep(self, code, corps):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(corps).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(n).decode()
        FauxReseaux.recus.append((self.path, self.headers.get("Authorization"), corps))
        if self.path == "/api/v1/access_token":
            ok = self.headers.get("Authorization") == "Basic " + __import__("base64").b64encode(b"id-test:secret-test").decode()
            return self._rep(200, {"access_token": "jeton-reddit"}) if ok else self._rep(401, {"error": "invalid"})
        if self.path == "/gql-ext":
            if self.headers.get("Authorization") != "Bearer jeton-meetup":
                return self._rep(401, {"errors": [{"message": "unauthorized"}]})
            return self._rep(200, json.loads((RACINE / "config/sources/exemples/meetup.json").read_text(encoding="utf-8")))
        self._rep(404, {})

    def do_GET(self):
        FauxReseaux.recus.append((self.path, self.headers.get("Authorization"), ""))
        if self.path.startswith("/subreddits/search"):
            if self.headers.get("Authorization") != "Bearer jeton-reddit":
                return self._rep(403, {"message": "Forbidden"})
            return self._rep(200, json.loads((RACINE / "config/sources/exemples/reddit.json").read_text(encoding="utf-8")))
        self._rep(404, {})

    def log_message(self, *a):
        pass


@pytest.fixture
def faux():
    s = HTTPServer(("127.0.0.1", 0), FauxReseaux)
    FauxReseaux.recus = []
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def test_reddit_avec_cle_echange_un_jeton_puis_cherche(faux):
    cles = {"REDDIT_CLIENT_ID": "id-test", "REDDIT_CLIENT_SECRET": "secret-test"}
    noms = charger("reddit").chercher({"quoi": "handball", "lieu": "Lyon", "limite": 5}, Client("reddit"), {"api": faux, "jeton": faux + "/api/v1/access_token", "_cles": cles})
    assert noms == [{"nom": "Communauté Exemple", "origine": "Reddit (communauté)", "site": "https://www.reddit.com/r/exemple/", "genre": "compte"}]
    assert FauxReseaux.recus[-1][1] == "Bearer jeton-reddit" and "handball" in FauxReseaux.recus[-1][0]


def test_reddit_sans_cle_ou_avec_fausses_cles_le_dit_en_clair(faux):
    with pytest.raises(ErreurSource, match="clés de Reddit"):
        charger("reddit").chercher({"quoi": "club"}, Client("reddit"), {"api": faux, "_cles": {}})
    with pytest.raises(ErreurSource, match="401"):
        charger("reddit").chercher({"quoi": "club"}, Client("reddit"), {"api": faux, "jeton": faux + "/api/v1/access_token", "_cles": {"REDDIT_CLIENT_ID": "x", "REDDIT_CLIENT_SECRET": "y"}})


def test_reddit_est_eteint_sans_cle_et_utilise_avec_les_deux_cles(cfg):
    d = du_preset(cfg)["reddit"]
    assert d.cles == ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"] and d.defaut["chercher"] is False
    assert "reddit" not in [x.id for x in choisies(cfg, {"sources": ["reddit"]})]
    cfg.fichiers_secrets[0].write_text("REDDIT_CLIENT_ID=a\n", encoding="utf-8")
    assert "reddit" not in [x.id for x in choisies(cfg, {"sources": ["reddit"]})]  # une seule des deux clés ne suffit pas
    cfg.fichiers_secrets[0].write_text("REDDIT_CLIENT_ID=a\nREDDIT_CLIENT_SECRET=b\n", encoding="utf-8")
    assert "reddit" in [x.id for x in choisies(cfg, {"sources": ["reddit"]})]


def test_meetup_avec_jeton_gratuit_rend_des_groupes_et_sans_jeton_le_dit(faux):
    noms = charger("meetup").chercher({"quoi": "handball", "limite": 5}, Client("meetup"), {"api": faux + "/gql-ext", "_cle": "jeton-meetup"})
    assert noms[0]["nom"] == "Groupe Exemple" and noms[0]["ville"] == "Ville-Exemple" and noms[0]["pays"] == "FR" and noms[0]["genre"] == "club"
    with pytest.raises(ErreurSource, match="jeton de Meetup est absent"):
        charger("meetup").chercher({"quoi": "club"}, Client("meetup"), {"api": faux + "/gql-ext"})
    with pytest.raises(ErreurSource, match="401"):
        charger("meetup").chercher({"quoi": "club"}, Client("meetup"), {"api": faux + "/gql-ext", "_cle": "faux"})


def test_meetup_n_est_pas_payant(cfg):
    d = du_preset(cfg)["meetup"]
    assert not d.payant and d.cle == "MEETUP_ACCESS_TOKEN"


def test_bluesky_et_mastodon_sont_gratuits_sans_cle(cfg):
    for sid in ("bluesky", "mastodon"):
        d = du_preset(cfg)[sid]
        assert d.cle == "" and not d.payant and d.defaut == {"chercher": False, "verifier": False}


@pytest.mark.reseau
def test_bluesky_et_mastodon_publics_repondent():
    if not en_ligne("https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?q=a&limit=1"):
        pytest.skip("pas de réseau")
    b = charger("bluesky").chercher({"quoi": "football club", "limite": 5}, Client("bluesky", delai_s=0.3), {})
    assert b and all(n["site"].startswith("https://bsky.app/profile/") for n in b)
    try:
        m = charger("mastodon").chercher({"quoi": "football", "limite": 5}, Client("mastodon", delai_s=0.3), {})
    except ErreurSource as exc:
        pytest.skip(f"instance Mastodon indisponible : {exc}")
    assert all(n["site"].startswith("https://") for n in m)


# --- [ ] Apify et Bright Data fonctionnent par MCP, sans code spécifique à l'un ou à l'autre.
def test_les_trois_prestataires_utilisent_le_meme_module_generique(cfg):
    d = du_preset(cfg)
    for sid in PRESTATAIRES:
        assert d[sid].moteur["adaptateur"] == "mcp_generique" and d[sid].famille == "mcp" and d[sid].prestataire is True
    assert not any(f.startswith(("apify", "brightdata")) for f in os.listdir(RACINE / "src/pilote/adaptateurs"))  # aucun module propre à un prestataire


@pytest.fixture
def faux_mcp(tmp_path):
    py = charger_config().python_grappes
    assert py.exists(), f"l'interpréteur de grappes est introuvable ({py}) : pilote ne peut pas tourner sans lui, ce test ne se saute pas"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    journal = tmp_path / "mcp.jsonl"
    p = subprocess.Popen([str(py), str(RACINE / "tests/faux_mcp.py"), str(port), str(journal), "Bearer jeton-prestataire"], stderr=subprocess.PIPE)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        p.kill()
        pytest.fail("le faux serveur MCP ne démarre pas")
    yield f"http://127.0.0.1:{port}/mcp", journal
    p.kill()


def lancer_adaptateur(cfg, sid, url, cle, entree):
    """L'adaptateur tourne dans l'interpréteur de grappes (bibliothèque MCP), avec la déclaration réelle de la source."""
    d = du_preset(cfg)[sid]
    params = {**d.moteur["parametres"], "mcp": url, **({"_cle": cle, "_cles": {d.cle: cle}} if cle else {})}
    code = ("import json,sys;from pilote.adaptateurs import Client, charger;a=json.loads(sys.argv[1]);"
            "c=Client(a['sid']);r=charger('mcp_generique').chercher(a['entree'],c,a['params']);print(json.dumps({'r':r,'appels':c.appels}))")  # fmt: skip
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(cfg.grappes_racine / "src"), str(RACINE / "src")])}
    r = subprocess.run([str(cfg.python_grappes), "-c", code, json.dumps({"sid": sid, "entree": entree, "params": params})], capture_output=True, text=True, env=env, check=False, timeout=120)
    return r


def test_apify_par_mcp_envoie_la_cle_et_les_mots_et_rend_des_comptes(cfg, faux_mcp):
    url, journal = faux_mcp
    r = lancer_adaptateur(cfg, "apify-instagram", url, "Bearer jeton-prestataire", {"quoi": "handball", "lieu": "Lyon", "limite": 10})
    assert r.returncode == 0, r.stderr[-600:]
    sortie = json.loads(r.stdout.strip().splitlines()[-1])
    assert [n["nom"] for n in sortie["r"]] == ["Club Imaginaire", "Section Fictive"] and sortie["appels"] == 1
    assert sortie["r"][0]["ville"] == "Ville-Exemple" and "Instagram" in sortie["r"][0]["origine"]
    recu = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
    assert recu["arguments"]["actor"] == "apify/instagram-scraper" and recu["arguments"]["input"]["search"] == "handball Lyon"  # mot-clé ET lieu
    assert recu["arguments"]["input"]["searchLimit"] == 10


def test_brightdata_par_mcp_lit_des_liens(cfg, faux_mcp):
    url, journal = faux_mcp
    r = lancer_adaptateur(cfg, "brightdata-recherche", url, "Bearer jeton-prestataire", {"quoi": "handball", "lieu": "Lyon", "limite": 10})
    assert r.returncode == 0, r.stderr[-600:]
    sortie = json.loads(r.stdout.strip().splitlines()[-1])["r"]
    assert [n["site"] for n in sortie] == ["https://www.instagram.com/asso_imaginaire/", "https://www.facebook.com/page.fictive"]
    assert "site:instagram.com" in json.loads(journal.read_text(encoding="utf-8").splitlines()[0])["arguments"]["query"]


def test_un_prestataire_sans_cle_ou_avec_une_mauvaise_cle_le_dit(cfg, faux_mcp):
    url, _ = faux_mcp
    sans = lancer_adaptateur(cfg, "apify-instagram", url, "", {"quoi": "handball"})
    assert sans.returncode != 0 and "clé du prestataire est absente" in sans.stderr
    mauvaise = lancer_adaptateur(cfg, "apify-instagram", url, "Bearer faux", {"quoi": "handball"})
    assert mauvaise.returncode != 0 and "ne répond pas" in mauvaise.stderr


def test_lecture_des_exemples_enregistres_des_prestataires(cfg):
    from pilote.adaptateurs import mcp_generique as m

    for sid in PRESTATAIRES:
        d = du_preset(cfg)[sid]
        texte = (cfg.dossier_sources / d.exemple_reponse).read_text(encoding="utf-8")
        noms = m.convertir(texte if d.exemple_reponse.endswith(".txt") else json.loads(texte), d.moteur["parametres"])
        assert noms and all(n["nom"] and n["origine"] for n in noms), sid


# --- [ ] Instagram et Facebook via Apify : par mot-clé et lieu.
def test_instagram_et_facebook_par_apify_prennent_mot_cle_et_lieu(cfg):
    d = du_preset(cfg)
    for sid in ("apify-instagram", "apify-facebook"):
        arguments = json.dumps(d[sid].moteur["parametres"]["arguments"])
        assert "{mots_et_lieu}" in arguments and d[sid].cle == "APIFY_TOKEN" and d[sid].cle_prefixe == "Bearer "
    assert d["apify-instagram"].moteur["parametres"]["arguments"]["actor"] == "apify/instagram-scraper"


# --- [ ] Un avertissement s'affiche UNE fois à l'activation d'un prestataire.
def test_avertissement_une_seule_fois_a_l_activation(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        for sid in PRESTATAIRES:
            assert c.get("/api/reglages").json()  # la page se charge
        r = c.put("/api/reglages/source/apify-instagram", json={"chercher": True})
        assert r.status_code == 409
        av = r.json()["detail"]["avertissements"]
        assert av[0]["source"] == "apify-instagram" and "plafond mensuel" in av[0]["texte"] and "facturés" in av[0]["texte"]
        assert not (cfg.fichier_reglages.exists() and "apify-instagram" in yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8")).get("sources", {}))  # rien n'a été écrit
        assert c.put("/api/reglages/source/apify-instagram", json={"chercher": True, "confirme": True}).status_code == 200
        c.put("/api/reglages/source/apify-instagram", json={"chercher": False})
        assert c.put("/api/reglages/source/apify-instagram", json={"chercher": True}).status_code == 200  # déjà accepté : plus de question
        assert c.put("/api/reglages/source/apify-facebook", json={"chercher": True}).status_code == 409  # un autre prestataire a le sien


def test_l_assistant_aussi_montre_l_avertissement(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        corps = {"donnees": {"chercher": ["brightdata-recherche"], "pays": "FR"}}
        assert c.post("/api/assistant/etape/1", json=corps).status_code == 409
        assert c.post("/api/assistant/etape/1", json={**corps, "confirme": True}).status_code == 200


def test_l_avertissement_est_affiche_par_la_page_avant_l_activation():
    js = (RACINE / "static/commun.js").read_text(encoding="utf-8") if (RACINE / "static/commun.js").exists() else (RACINE / "src/pilote/static/commun.js").read_text(encoding="utf-8")
    assert "window.confirm" in js and "avertissements" in js


# --- [ ] Le coût d'un prestataire est compté dans le plafond, et le plafond le bloque.
def test_le_plafond_ecarte_un_prestataire_trop_cher_et_garde_les_gratuites(cfg):
    decls, _ = charger_sources(cfg)
    d = decls["apify-instagram"]
    cout = d.cout
    # 25 résultats par appel à 0,0023 $ : 1 appel = 0,0575 $ ; 20 appels = 1,15 $
    assert bg.dollars_pour(cout, 20) == pytest.approx(1.15)
    sources = [(d, cout), (decls["telegram-annuaires"], decls["telegram-annuaires"].cout)]
    ok, refusees = bg.autoriser(sources, 20, plafond=1.0, depense=0.0, unites={})
    assert [x.id for x in ok] == ["telegram-annuaires"] and "1,15 $" in refusees[0]["raison"] and "il ne reste que 1,00 $" in refusees[0]["raison"]
    ok, refusees = bg.autoriser(sources, 20, plafond=5.0, depense=0.0, unites={})
    assert {x.id for x in ok} == {"apify-instagram", "telegram-annuaires"} and refusees == []
    ok, refusees = bg.autoriser(sources, 20, plafond=5.0, depense=4.5, unites={})  # 0,50 $ restent : le prestataire pourrait dépasser
    assert [x.id for x in ok] == ["telegram-annuaires"]
    ok, refusees = bg.autoriser(sources, 1, plafond=5.0, depense=5.0, unites={})  # plafond atteint : seules les gratuites
    assert [x.id for x in ok] == ["telegram-annuaires"] and "plafond de 5 $" in refusees[0]["raison"] and "seules les sources gratuites" in refusees[0]["raison"]


def test_le_cout_reel_est_compte_par_appel_et_entre_dans_la_depense_du_mois(cfg):
    decls, _ = charger_sources(cfg)
    sources = {s: (decls[s], decls[s].cout) for s in ("apify-instagram", "telegram-annuaires")}
    couts = bg.couts_de_la_recherche(sources, {"apify-instagram": 3, "telegram-annuaires": 7}, {})
    assert set(couts) == {"apify-instagram"}  # une source gratuite ne coûte rien
    assert couts["apify-instagram"]["dollars"] == pytest.approx(3 * 25 * 0.0023) and couts["apify-instagram"]["unites"] == 75


def test_une_recherche_ecarte_le_prestataire_quand_le_plafond_est_trop_bas(cfg, tmp_path):
    cfg.fichiers_secrets[0].write_text("APIFY_TOKEN=abc\n", encoding="utf-8")
    cible = tmp_path / "copie"
    cible.mkdir()
    for nom in ("recherche",):
        (cible / nom).mkdir()
    (cible / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    b = {"appels_max": 40, "plafond": 0.5, "depense": 0.0, "unites": {}}
    res = materialiser(cfg, cible, {"sources": ["apify-instagram", "telegram-annuaires"], "_budget": b})
    assert res.ids == ["telegram-annuaires"] and res.exclues_budget[0]["source"] == "apify-instagram"
    assert "Bearer" not in (cible / "secrets.env").read_text(encoding="utf-8")  # le prestataire écarté n'a même pas sa clé dans la copie
    res = materialiser(cfg, cible, {"sources": ["apify-instagram", "telegram-annuaires"], "_budget": {**b, "plafond": 10.0}})
    assert set(res.ids) == {"apify-instagram", "telegram-annuaires"} and res.exclues_budget == []
    assert (cible / "secrets.env").read_text(encoding="utf-8").strip() == "APIFY_TOKEN=Bearer abc"


# --- [ ] La configuration livrée n'a aucun prestataire activé.
def test_aucun_prestataire_n_est_active_dans_la_configuration_livree(cfg):
    decls, _ = charger_sources(cfg)
    prestataires = [d for d in decls.values() if d.prestataire]
    assert {d.id for d in prestataires} >= set(PRESTATAIRES)
    for d in prestataires:
        assert d.defaut == {"chercher": False, "verifier": False} and d.avertissement, d.id
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        parties = c.get("/api/reglages").json()["parties"]
        for ligne in parties["recherche"] + parties["verification"]:
            if ligne["id"] in {d.id for d in prestataires}:
                assert not ligne["chercher"] and not ligne["verifier"], ligne["id"]
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "reseaux_sociaux")
        assert not any(s["allumee_par_defaut"] for s in carte["sources"] if s["id"] in PRESTATAIRES)


def test_les_appels_de_chaque_source_sont_comptes_depuis_le_suivi(tmp_path):
    from pilote.executeur_grappes import appels_par_source

    f = tmp_path / "avancement.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in [
        {"evenement": "appel", "prise": "apify-instagram"}, {"evenement": "appel", "prise": "apify-instagram"},
        {"evenement": "appel", "prise": "découverte"}, {"evenement": "etape", "etape": "x"}, {"evenement": "appel", "prise": "tavily"},
    ]) + "\nligne cassée\n", encoding="utf-8")
    assert appels_par_source(f, {"apify-instagram": "apify-instagram", "tavily": "tavily"}) == {"apify-instagram": 2, "tavily": 1}


# --- bout en bout : une vraie recherche (pont, MCP réel) avec un prestataire simulé : le coût réel est compté, puis le plafond le bloque.
def attendre(c, rid, delai=120):
    t0 = time.time()
    while time.time() - t0 < delai:
        r = c.get(f"/api/recherches/{rid}").json()
        if r["etat"] in ("terminee", "arretee", "echec", "interrompue"):
            return r
        time.sleep(0.5)
    raise AssertionError("la recherche ne se termine pas")


def test_bout_en_bout_le_cout_est_compte_puis_le_plafond_bloque_le_prestataire(tmp_path, faux_mcp):
    from conftest import copier_config

    from pilote.base import Recherche
    from pilote.config import charger as charger_cfg

    url, journal = faux_mcp
    cfg = charger_cfg(copier_config(tmp_path))
    f = cfg.dossier_sources / "apify-instagram.yaml"
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    d["moteur"]["parametres"]["mcp"] = url  # le prestataire simulé remplace le vrai serveur dans cette copie de la configuration
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cfg.fichiers_secrets[0].write_text("APIFY_TOKEN=jeton-prestataire\n", encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        for ligne in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{ligne['id']}", json={"chercher": False})
        assert c.put("/api/reglages/source/apify-instagram", json={"chercher": True}).status_code == 409
        assert c.put("/api/reglages/source/apify-instagram", json={"chercher": True, "confirme": True}).status_code == 200
        c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 5})
        sujet = {"quoi": "handball", "lieu": "Lyon", "pays": "France", "combien": 50}
        rid = c.post("/api/recherches", json={"sujet": sujet, "parametres": {"profondeur": "large"}}).json()["id"]
        r = attendre(c, rid)
        assert r["etat"] == "terminee", r["message"]
        noms = [x["nom"] for x in c.get(f"/api/recherches/{rid}/candidats").json()] if c.get(f"/api/recherches/{rid}/candidats").status_code == 200 else []
        with c.app.state.fabrique() as s:
            couts = s.get(Recherche, rid).couts
        assert set(couts) == {"apify-instagram"} and couts["apify-instagram"]["dollars"] > 0
        assert couts["apify-instagram"]["unites"] == 25 * len(journal.read_text(encoding="utf-8").splitlines())  # autant d'appels que le serveur en a vus
        assert c.get("/api/reglages").json()["budget"]["depense_du_mois_usd"] == pytest.approx(couts["apify-instagram"]["dollars"])
        assert noms == [] or "Club Imaginaire" in noms
        # le plafond tombe sous ce que la source peut coûter : la recherche suivante se fait SANS elle et sans appel au prestataire
        appels_avant = len(journal.read_text(encoding="utf-8").splitlines())
        c.put("/api/reglages/budget", json={"plafond_mensuel_usd": 0.01})
        rid2 = c.post("/api/recherches", json={"sujet": sujet, "parametres": {"profondeur": "large"}}).json()["id"]
        r2 = attendre(c, rid2)
        assert r2["etat"] == "terminee", r2["message"]
        assert len(journal.read_text(encoding="utf-8").splitlines()) == appels_avant
        spec = json.loads((cfg.dossier_recherche(rid2) / "lancement.json").read_text(encoding="utf-8"))
        assert spec["sources"] == [] and spec["exclues_budget"][0]["source"] == "apify-instagram"
        assert "plafond" in c.get(f"/api/recherches/{rid2}").json()["avancement"]["sources_ecartees"][0]["raison"]  # et on le dit à l'utilisateur


# --- [ ] Décision du 17/10/2026 : les emoji passent tels quels dans les termes et dans les résultats.
class FauxBluesky(BaseHTTPRequestHandler):
    recus: ClassVar[list] = []

    def do_GET(self):
        import urllib.parse as up

        FauxBluesky.recus.append(up.parse_qs(up.urlsplit(self.path).query).get("q", [""])[0])
        corps = json.dumps({"actors": [{"handle": "hand.bsky.social", "displayName": "🤾 Handball Club Imaginaire 🔥"}, {"handle": "sans.bsky.social", "displayName": "Les Lions du Rhône 🦁"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


def test_emoji_dans_le_terme_et_dans_les_resultats_de_bout_en_bout(tmp_path):
    import csv

    from conftest import copier_config
    from sqlalchemy import select

    from pilote.base import Candidat
    from pilote.config import charger as charger_cfg

    s = HTTPServer(("127.0.0.1", 0), FauxBluesky)
    FauxBluesky.recus = []
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        cfg = charger_cfg(copier_config(tmp_path))
        f = cfg.dossier_sources / "bluesky.yaml"
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        d["moteur"]["parametres"] = {"api": f"http://127.0.0.1:{s.server_port}/xrpc"}
        f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        with TestClient(creer_app(cfg)) as c:
            for ligne in c.get("/api/reglages").json()["parties"]["recherche"]:
                c.put(f"/api/reglages/source/{ligne['id']}", json={"chercher": ligne["id"] == "bluesky"})
            rid = c.post("/api/recherches", json={"sujet": {"quoi": "handball 🤾", "lieu": "Lyon", "pays": "France", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
            r = attendre(c, rid)
            assert r["etat"] == "terminee", r["message"]
            assert any("🤾" in q for q in FauxBluesky.recus), FauxBluesky.recus  # le terme arrive intact à la source
            with c.app.state.fabrique() as sess:
                noms = [x.nom for x in sess.scalars(select(Candidat).where(Candidat.recherche_id == rid)).all()]
            assert "🤾 Handball Club Imaginaire 🔥" in noms and "Les Lions du Rhône 🦁" in noms, noms
            t = c.get(f"/api/recherches/{rid}/tri").json()
            ids = {x["nom"]: x["id"] for x in t["lignes"]}
            assert "🤾 Handball Club Imaginaire 🔥" in ids
            c.post(f"/api/recherches/{rid}/decisions", json={"valeur": "garder", "ids": list(ids.values())})
            exp = c.post(f"/api/recherches/{rid}/export").json()
            lu = (tmp_path / exp["dossier"] if not exp["dossier"].startswith("/") else __import__("pathlib").Path(exp["dossier"]))
            texte = " ".join((lu / fich).read_text(encoding="utf-8") for fich in exp["fichiers"])
            assert "🤾 Handball Club Imaginaire 🔥" in texte and "🦁" in texte
            lignes = list(csv.reader((lu / "decisions.csv").read_text(encoding="utf-8").splitlines(), delimiter=";"))
            assert any("🤾" in x[0] for x in lignes)
    finally:
        s.shutdown()


# --- [ ] Arctic Shift (alternative sans clé à Reddit) : forme de réponse simulée, communautés pour adultes écartées.
def test_arctic_shift_ecarte_les_communautes_pour_adultes():
    import json
    from pathlib import Path

    from pilote.adaptateurs import arctic_shift

    rep = json.loads((Path(__file__).parent.parent / "config/sources/exemples/arctic-shift.json").read_text(encoding="utf-8"))
    noms = arctic_shift.convertir(rep)
    assert len(noms) == sum(1 for d in rep["data"] if not d["over18"]) == 2
    assert all(n["site"].startswith("https://www.reddit.com/r/") and n["genre"] == "compte" for n in noms)
