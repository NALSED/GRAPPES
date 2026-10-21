"""FICHE 09 — preset Presse : test de recette, point par point."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import contexte, flux_rss, mentions
from pilote.app import creer_app
from pilote.base import Candidat
from pilote.config import RACINE
from pilote.config import charger as charger_cfg
from pilote.sources import charger_sources

PHRASE_FICHE = "Presse : trouve des acteurs cités dans les journaux et confirme des noms trouvés ailleurs. Extraction bruyante."
EXEMPLES = RACINE / "config/sources/exemples"
ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Journal Atom</title>
<entry><title>Le Club Imaginaire gagne</title><link href="https://atom.example/a1"/><updated>2026-10-12T10:00:00Z</updated><summary>Résumé.</summary></entry></feed>"""
OPML = """<?xml version="1.0" encoding="UTF-8"?><opml version="2.0"><head><title>Mes abonnements</title></head><body>
<outline text="Sport" title="Sport"><outline type="rss" text="Journal Un" title="Journal Un" xmlUrl="http://127.0.0.1:{port}/un.xml" htmlUrl="https://un.example"/>
<outline type="rss" text="Journal Deux" xmlUrl="http://127.0.0.1:{port}/deux.xml"/></outline>
<outline type="rss" text="Doublon de Un" xmlUrl="http://127.0.0.1:{port}/un.xml"/>
<outline type="rss" text="Adresse cassée" xmlUrl="ftp://exemple.example/flux"/>
<outline text="Un dossier sans flux"/></body></opml>"""


class FauxJournal(BaseHTTPRequestHandler):
    recus: ClassVar[list] = []

    def do_GET(self):
        FauxJournal.recus.append((self.path, time.monotonic(), self.headers.get("User-Agent", "")))
        if self.path == "/robots.txt":
            self.send_response(404)
            self.end_headers()
            return
        if self.path.startswith("/atom"):
            corps, type_ = ATOM.encode(), "application/atom+xml"
        elif self.path.startswith("/page"):
            corps, type_ = b"<html><body>Pas un flux</body></html>", "text/html"
        elif self.path.startswith("/gdelt"):
            corps, type_ = (EXEMPLES / "gdelt.json").read_bytes(), "application/json"
        else:
            corps, type_ = (EXEMPLES / "flux-rss-utilisateur.xml").read_bytes(), "application/rss+xml"
        self.send_response(200)
        self.send_header("Content-Type", type_)
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


@pytest.fixture
def journal():
    s = HTTPServer(("127.0.0.1", 0), FauxJournal)
    FauxJournal.recus = []
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def du_preset(cfg):
    decls, problemes = charger_sources(cfg)
    assert problemes == []
    return {d.id: d for d in decls.values() if "presse" in d.usages}


# --- [ ] Un flux RSS ajouté à la main est lu et rend des articles.
def test_un_flux_ajoute_a_la_main_est_lu_et_rend_des_articles(cfg, journal):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        assert c.get("/api/flux-rss").json() == {"flux": []}  # liste vide au départ : « liste fournie par l'utilisateur »
        r = c.post("/api/flux-rss", json={"url": f"{journal}/rss.xml", "nom": "Journal Exemple", "pays": "fr"})
        assert r.status_code == 201
        res = r.json()
        assert res["articles"] == 3 and res["titres"][0].startswith("Club Imaginaire") and res["format"] == "rss" and res["pays"] == "FR"
        assert [f["nom"] for f in c.get("/api/flux-rss").json()["flux"]] == ["Journal Exemple"]
    y = yaml.safe_load(cfg.fichier_flux_rss.read_text(encoding="utf-8"))  # le fichier de configuration est la référence
    assert y["flux"][0]["url"] == f"{journal}/rss.xml"
    assert any(p == "/rss.xml" for p, _, _ in FauxJournal.recus)  # il a bien été LU


def test_un_flux_atom_est_reconnu(cfg, journal):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        res = c.post("/api/flux-rss", json={"url": f"{journal}/atom.xml"}).json()
    assert res["format"] == "atom" and res["articles"] == 1 and res["titres"] == ["Le Club Imaginaire gagne"]


def test_ce_qui_n_est_pas_un_flux_est_refuse_en_francais_et_rien_n_est_ecrit(cfg, journal):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.post("/api/flux-rss", json={"url": f"{journal}/page.html"})
        assert r.status_code == 422 and "pas un flux" in r.json()["detail"]  # une page web n'est pas un flux
        r = c.post("/api/flux-rss", json={"url": "ftp://x.example/f"})
        assert r.status_code == 422 and "http://" in r.json()["detail"]
        assert c.post("/api/flux-rss", json={"url": "http://127.0.0.1:9/rien"}).status_code == 422  # ne répond pas
        assert c.post("/api/flux-rss", json={"url": f"{journal}/rss.xml"}).status_code == 201
        assert c.post("/api/flux-rss", json={"url": f"{journal}/rss.xml"}).status_code == 422  # déjà dans la liste
        assert len(c.get("/api/flux-rss").json()["flux"]) == 1


def test_un_xml_qui_declare_des_entites_est_refuse():
    with pytest.raises(Exception, match="entités"):
        flux_rss.lire_articles(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>')


# --- [ ] Un fichier OPML s'importe et crée les flux correspondants.
def test_un_fichier_opml_s_importe_et_cree_les_flux(cfg, journal):
    port = journal.rsplit(":", 1)[1]
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.post("/api/flux-rss/opml", content=OPML.format(port=port).encode(), headers={"content-type": "text/x-opml"})
        assert r.status_code == 201
        res = r.json()
        assert res["ajoutes"] == 2 and res["doublons"] == 1 and res["ignores"] == ["Adresse cassée"]
        flux = c.get("/api/flux-rss").json()["flux"]
        assert [f["nom"] for f in flux] == ["Journal Un", "Journal Deux"] and flux[0]["url"].endswith("/un.xml")
        # un second import du même fichier ne crée rien de plus
        assert c.post("/api/flux-rss/opml", content=OPML.format(port=port).encode()).json()["ajoutes"] == 0
        assert c.post("/api/flux-rss/opml", content=b"pas du xml").status_code == 422
        assert c.post("/api/flux-rss/opml", content=b"<rss></rss>").status_code == 422  # un flux n'est pas un OPML
        assert c.delete(f"/api/flux-rss/{flux[0]['id']}").status_code == 200 and len(c.get("/api/flux-rss").json()["flux"]) == 1


def test_les_flux_de_l_utilisateur_deviennent_des_prises_de_grappes_pour_la_recherche(cfg, journal, tmp_path):
    from pilote.moteur_sources import materialiser

    flux_rss.ajouter(cfg, f"{journal}/rss.xml", "Journal Exemple", verifier=False)
    flux_rss.ajouter(cfg, f"{journal}/atom.xml", "Journal Atom")
    cible = tmp_path / "copie"
    (cible / "recherche").mkdir(parents=True)
    (cible / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    res = materialiser(cfg, cible, {"sources": ["flux-rss-utilisateur"]})
    ids = [f["id"] for f in flux_rss.charger(cfg)]
    assert set(res.jetons) == set(ids) and set(res.jetons.values()) == {"flux-rss-utilisateur"}
    d = yaml.safe_load((cible / "recherche" / f"{ids[1]}.yaml").read_text(encoding="utf-8"))
    assert d["response"]["items"] == "feed.entry" and d["fields"]["url"] == "link.@href" and d["observation"]["ecosysteme"] == "rss"  # Atom
    assert d["respecter_robots"] is True and d["sans_mots_cles"] is True


# --- [ ] GDELT répond ; la mention du GDELT Project avec son lien apparaît dans les sorties et le README.
def test_gdelt_declare_sa_mention_obligatoire_et_le_readme_la_porte(cfg):
    d = du_preset(cfg)["gdelt"]
    assert d.attribution == {"texte": "Données de presse : GDELT Project", "url": "https://www.gdeltproject.org"}
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    assert "GDELT Project" in readme and "https://www.gdeltproject.org" in readme
    assert d.moteur["definition"]["delai_entre_appels_s"] >= 5  # le service limite à un appel toutes les 5 secondes


def test_la_mention_est_ecrite_a_cote_des_sorties_de_toute_recherche_qui_a_utilise_gdelt(cfg, tmp_path):
    rech, sortie = tmp_path / "rech", tmp_path / "export"
    rech.mkdir()
    sortie.mkdir()
    (rech / "lancement.json").write_text(json.dumps({"sources": ["searxng", "gdelt"]}), encoding="utf-8")
    f = mentions.ecrire(cfg, rech, sortie)
    texte = f.read_text(encoding="utf-8")
    assert f.name == "SOURCES.txt" and "GDELT Project" in texte and "https://www.gdeltproject.org" in texte
    (rech / "lancement.json").write_text(json.dumps({"sources": ["searxng"]}), encoding="utf-8")
    (sortie / "SOURCES.txt").unlink()
    assert mentions.ecrire(cfg, rech, sortie) is None and not (sortie / "SOURCES.txt").exists()  # pas de mention pour ce qui n'en exige pas


# --- [ ] Les trois API payantes sont éteintes dans la configuration livrée.
def test_les_api_d_actualite_a_cle_sont_eteintes(cfg):
    d = du_preset(cfg)
    for sid, cle in (("newsdata-io", "NEWSDATA_API_KEY"), ("gnews", "GNEWS_API_KEY"), ("newsapi-ai", "NEWSAPI_AI_KEY")):
        assert d[sid].cle == cle and d[sid].defaut == {"chercher": False, "verifier": False}, sid
    assert d["newsapi-ai"].payant and d["newsapi-ai"].avertissement
    assert "NewsAPI.org".lower() not in " ".join(d).lower() and not [k for k in d if "feedly" in k or "inoreader" in k]  # non retenus
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "presse")
    assert {s["id"] for s in carte["sources"] if s["allumee_par_defaut"]} >= {"flux-rss-utilisateur", "gdelt"}
    assert not {s["id"] for s in carte["sources"] if s["allumee_par_defaut"]} & {"newsdata-io", "gnews", "newsapi-ai"}


def test_la_carte_porte_la_phrase_de_la_fiche(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "presse")
    assert carte["phrase"] == PHRASE_FICHE


# --- [ ] Les noms issus de la presse portent la couleur « presse » et sont marqués seconde main.
def test_les_sources_de_presse_donnent_la_couleur_presse_et_seconde_main(cfg):
    for sid, d in du_preset(cfg).items():
        assert d.origine == "presse" and d.main == "seconde", sid


# --- [ ] L'encadré Contexte affiche les titres déjà collectés, SANS nouvelle collecte.
def faux_dossier_de_recherche(dossier, articles):
    import sqlite3

    (dossier / "donnees").mkdir(parents=True)
    c = sqlite3.connect(dossier / "donnees" / "grappes.db")
    c.executescript("""CREATE TABLE sources (ref_key TEXT PRIMARY KEY, ecosystem TEXT NOT NULL, ident TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1, display_name TEXT);
        CREATE TABLE observations (obs_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, ts TEXT, text TEXT NOT NULL, mentions TEXT NOT NULL DEFAULT '[]', links TEXT NOT NULL DEFAULT '[]',
        hashtags TEXT NOT NULL DEFAULT '[]', engagement INTEGER NOT NULL DEFAULT 0, raw_ref TEXT, run_id TEXT);""")
    for i, (eco, ident, nom, ts, texte, url) in enumerate(articles):
        c.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,1,?)", (f"{eco}:{ident}", eco, ident, nom))
        c.execute("INSERT INTO observations (obs_id, source_key, ts, text, raw_ref) VALUES (?,?,?,?,?)", (f"o{i}", f"{eco}:{ident}", ts, texte, url))
    c.commit()
    c.close()


def test_le_contexte_liste_les_titres_deja_collectes_sans_rien_collecter(cfg, tmp_path):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "handball"}}).json()["id"]
        # (l'exécuteur de ce test ne collecte rien : on pose une base comme en laisserait une vraie recherche)
        faux_dossier_de_recherche(cfg.dossier_recherche(rid), [
            ("rss", "journal.example", "Journal Exemple", "2026-10-12T10:15:00", "Club Imaginaire : victoire au derby. Le club s'impose face à son rival.", "https://journal.example/a"),
            ("presse", "autre.example", "Autre Journal", "2026-10-13T08:00:00", "Nouveau stade pour la Ville-Exemple. Inauguration prévue.", "https://autre.example/b"),
            ("wikipedia", "fr/x", "Une page d'encyclopédie", None, "Handball. Sport collectif.", "https://fr.wikipedia.org/wiki/Handball"),  # pas de la presse
        ])
        avant = [(p, t) for p, t, _ in FauxJournal.recus]
        ctx = c.get(f"/api/recherches/{rid}/contexte").json()
        assert [(a["titre"], a["source"], a["date"]) for a in ctx["articles"]] == [
            ("Nouveau stade pour la Ville-Exemple", "Autre Journal", "2026-10-13"), ("Club Imaginaire : victoire au derby", "Journal Exemple", "2026-10-12"),
        ]  # du plus récent au plus ancien ; l'encyclopédie n'y est pas ; le titre est le début du texte
        assert ctx["nombre"] == 2 and "Aucune nouvelle collecte" in ctx["note"]
        journal_avant = c.get(f"/api/recherches/{rid}/journal").json()
        c.get(f"/api/recherches/{rid}/contexte")
        assert c.get(f"/api/recherches/{rid}/journal").json() == journal_avant  # rien n'est noté : aucune action, aucune collecte
        assert not (cfg.dossier_recherche(rid) / "avancement.jsonl").exists()  # aucun appel de grappes
        assert c.get("/api/recherches/inconnue/contexte").status_code == 404
    assert avant == [(p, t) for p, t, _ in FauxJournal.recus]


def test_le_contexte_sans_base_est_vide(cfg, tmp_path):
    assert contexte.lire(tmp_path / "rien") == {"articles": [], "nombre": 0, "note": contexte.NOTE}


def test_le_contexte_ne_peut_pas_ecrire_dans_la_base(tmp_path):
    faux_dossier_de_recherche(tmp_path, [("rss", "j", "J", None, "Titre. Texte.", "")])
    import sqlite3

    c = sqlite3.connect(f"file:{tmp_path / 'donnees' / 'grappes.db'}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("DELETE FROM observations")
    c.close()
    assert contexte.lire(tmp_path)["nombre"] == 1


# --- bout en bout : une vraie recherche (pont de grappes) lit un flux de l'utilisateur et GDELT (simulé), puis le Contexte relit la base.
def test_bout_en_bout_flux_utilisateur_et_gdelt_donnent_des_articles_de_presse(tmp_path, journal):
    from conftest import copier_config

    cfg = charger_cfg(copier_config(tmp_path))
    f = cfg.dossier_sources / "gdelt.yaml"
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    d["moteur"]["definition"]["url"] = f"{journal}/gdelt"  # GDELT simulé par le serveur de test (la vraie adresse est limitée à un appel par 5 s)
    d["moteur"]["definition"]["delai_entre_appels_s"] = 0.5
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        for ligne in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{ligne['id']}", json={"chercher": ligne["id"] in ("flux-rss-utilisateur", "gdelt")})
        assert c.post("/api/flux-rss", json={"url": f"{journal}/rss.xml", "nom": "Journal Exemple"}).status_code == 201
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "club imaginaire", "pays": "France", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
        t0 = time.time()
        while time.time() - t0 < 120:
            r = c.get(f"/api/recherches/{rid}").json()
            if r["etat"] in ("terminee", "arretee", "echec", "interrompue"):
                break
            time.sleep(0.5)
        assert r["etat"] == "terminee", r["message"]
        ctx = c.get(f"/api/recherches/{rid}/contexte").json()
        titres = " | ".join(a["titre"] for a in ctx["articles"])
        assert ctx["nombre"] >= 4 and "Club Imaginaire" in titres  # 3 articles du flux + les articles de GDELT
        assert {a["source"] for a in ctx["articles"]} >= {"Journal Exemple"}
        gd = [p for p, _, _ in FauxJournal.recus if p.startswith("/gdelt")]
        assert gd and any(p == "/rss.xml" for p, _, _ in FauxJournal.recus)
        avant = len(FauxJournal.recus)
        c.get(f"/api/recherches/{rid}/contexte")
        assert len(FauxJournal.recus) == avant  # l'encadré n'a rien collecté
        with c.app.state.fabrique() as s:
            from sqlalchemy import select

            cands = s.scalars(select(Candidat).where(Candidat.recherche_id == rid)).all()
        for x in cands:
            assert x.genre_source == "presse" and all(p["main"] == "seconde" for p in x.faits["preuves"]), x.nom


def test_rendu_des_flux_et_du_contexte_sous_node():
    import subprocess

    r = subprocess.run(["node", "tests/js/rendu_presse.mjs"], capture_output=True, text=True, check=False, cwd=RACINE)
    assert r.returncode == 0, r.stdout + r.stderr


# --- [ ] F09-2 : un flux Atom importé par OPML n'est plus lu comme du RSS. Importé « inconnu » (pas de lecture réseau à l'import),
#         son format est détecté à la première recherche, une fois, et enregistré ; un flux injoignable reste « inconnu » et sera retenté.
def test_un_flux_atom_importe_par_opml_est_detecte_a_la_premiere_recherche(cfg, journal, tmp_path):
    from pilote.moteur_sources import materialiser

    opml = f"""<?xml version="1.0"?><opml version="2.0"><body>
<outline type="rss" text="Journal Atom" xmlUrl="{journal}/atom.xml"/>
<outline type="rss" text="Journal RSS" xmlUrl="{journal}/rss.xml"/>
<outline type="rss" text="Injoignable" xmlUrl="http://127.0.0.1:9/mort.xml"/></body></opml>"""
    res = flux_rss.importer_opml(cfg, opml.encode())
    assert res["ajoutes"] == 3 and {f["format"] for f in flux_rss.charger(cfg)} == {"inconnu"}  # rien n'est lu à l'import
    cible = tmp_path / "copie"
    (cible / "recherche").mkdir(parents=True)
    (cible / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    materialiser(cfg, cible, {"sources": ["flux-rss-utilisateur"]})
    par_nom = {f["nom"]: f for f in flux_rss.charger(cfg)}
    assert par_nom["Journal Atom"]["format"] == "atom" and par_nom["Journal RSS"]["format"] == "rss"
    assert par_nom["Injoignable"]["format"] == "inconnu"  # retenté à la prochaine recherche
    atom = yaml.safe_load((cible / "recherche" / f"{par_nom['Journal Atom']['id']}.yaml").read_text(encoding="utf-8"))
    assert atom["response"]["items"] == "feed.entry"  # avant : « rss.channel.item », donc zéro article, sans erreur
    mort = yaml.safe_load((cible / "recherche" / f"{par_nom['Injoignable']['id']}.yaml").read_text(encoding="utf-8"))
    assert mort["response"]["items"] == "rss.channel.item"  # inconnu : traité comme RSS, comme avant


# --- [ ] Deux ajouts de flux en même temps : aucun n'est perdu (lire, modifier, écrire sous verrou).
def test_des_ajouts_de_flux_simultanes_ne_se_perdent_pas(cfg):
    from concurrent.futures import ThreadPoolExecutor

    adresses = [f"https://journal{i}.example/rss.xml" for i in range(12)]
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda u: flux_rss.ajouter(cfg, u, verifier=False), adresses))
    assert sorted(f["url"] for f in flux_rss.charger(cfg)) == sorted(adresses)
