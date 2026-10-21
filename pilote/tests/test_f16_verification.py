"""FICHE 16 — sources « vérifier » : choisies à part des sources qui cherchent, puis appelées sur chaque candidat qui a un site."""

import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from pilote import adaptateurs
from pilote.app import creer_app
from pilote.moteur_sources import choisies, materialiser, verificatrices
from pilote.pont.verification import verifier_candidats


def en_ligne(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pilote-test"}), timeout=15)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def cible(tmp_path):
    c = tmp_path / "copie"
    (c / "recherche").mkdir(parents=True)
    (c / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    return c


# --- [ ] Une source « vérifier » n'est jamais appelée comme source qui cherche, et n'est préparée que si sa case est cochée.
def test_wayback_est_une_verificatrice_pas_une_source_de_recherche(cfg, tmp_path):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        assert [d.id for d in verificatrices(cfg, {})] == []  # case décochée : rien
        assert c.put("/api/reglages/source/wayback", json={"verifier": True}).status_code == 200
        c.put("/api/reglages/verification", json={"active": True, "mode": "memes"})
        assert [d.id for d in verificatrices(cfg, {})] == []  # cochée, mais « memes » : une source de vérification SEULE attend le mode « plus »
        c.put("/api/reglages/verification", json={"active": True, "mode": "plus"})
        assert [d.id for d in verificatrices(cfg, {})] == ["wayback"]
        assert "wayback" not in [d.id for d in choisies(cfg, {"sources": ["wayback", "searxng"]})]
        res = materialiser(cfg, cible(tmp_path), {"sources": ["searxng"]})
        assert [v["source"] for v in res.verificateurs] == ["wayback"] and res.verificateurs[0]["module"] == "wayback"
        assert "wayback" not in res.ids and all(a["source"] != "wayback" for a in res.adaptateurs)
        assert verificatrices(cfg, {"verification": False}) == []  # l'interrupteur de Réglages éteint tout
        assert {d.id for d in verificatrices(cfg, {})} == {"wayback"}  # ROR, data.gouv... ont le rôle « vérifier » mais cherchent par nom : jamais appelées sur un candidat  # l'interrupteur de Réglages éteint tout


# --- [ ] Chaque candidat qui a un site reçoit sa vérification ; les autres sont laissés tels quels ; un défaut n'arrête rien.
def test_verifier_candidats_ajoute_la_preuve_sans_toucher_aux_endroits(monkeypatch):
    class Faux:
        @staticmethod
        def chercher(entree, client, parametres):
            if entree["site"] == "plante.example":
                raise RuntimeError("panne")
            return [{"nom": entree["nom"], "numero": f"https://archive.example/{entree['site']}", "origine": "Wayback Machine (capture du 12/04/2019)"}] if entree["site"] != "mort.example" else []

    monkeypatch.setattr(adaptateurs, "charger", lambda nom: Faux)
    lignes = [{"nom": "A", "site": "a.example", "nb_endroits": 2, "faits": {"preuves": []}}, {"nom": "B", "site": ""}, {"nom": "C", "site": "mort.example"}]
    evenements = []
    verifier_candidats(lignes, {"verificateurs": [{"source": "wayback", "module": "wayback"}]}, {}, lambda: False, 60.0, lambda ev, **d: evenements.append((ev, d)))
    assert lignes[0]["faits"]["verifications"] == [{"source": "wayback", "origine": "Wayback Machine (capture du 12/04/2019)", "preuve": "https://archive.example/a.example", "signal": "confirmation"}]
    assert lignes[0]["nb_endroits"] == 2 and "verifications" not in lignes[0]["faits"]["preuves"]
    assert "faits" not in lignes[1] and "verifications" not in lignes[2].get("faits", {})
    fin = next(d for ev, d in evenements if ev == "prise_fin")
    assert fin == {"prise": "wayback", "trouves": 1, "noms": 0, "examines": 2, "a_verifier": 2, "statut": "ok"}  # 2 candidats avec adresse examinés, 1 vérifié
    lignes = [{"nom": "P", "site": "plante.example"}, {"nom": "A", "site": "a.example"}]
    evenements.clear()
    verifier_candidats(lignes, {"verificateurs": [{"source": "wayback", "module": "wayback"}]}, {}, lambda: False, 60.0, lambda ev, **d: evenements.append((ev, d)))
    assert "faits" not in lignes[1] and any(ev == "source_echec" for ev, _ in evenements)  # la source est laissée de côté, pas la recherche


def test_un_arret_demande_coupe_la_verification_sans_perdre_les_candidats(monkeypatch):
    appels = []
    monkeypatch.setattr(adaptateurs, "charger", lambda nom: type("M", (), {"chercher": staticmethod(lambda e, c, p: appels.append(e) or [])}))
    lignes = [{"nom": "A", "site": "a.example"}, {"nom": "B", "site": "b.example"}]
    verifier_candidats(lignes, {"verificateurs": [{"source": "wayback", "module": "wayback"}]}, {}, lambda: True, 60.0, lambda *a, **k: None)
    assert appels == [] and [x["nom"] for x in lignes] == ["A", "B"]


# --- [ ] Contre le vrai service : un site connu reçoit une capture, un site inventé n'en reçoit pas.
def test_wayback_reel_sur_des_candidats():
    if not en_ligne("https://archive.org/wayback/available?url=archive.org"):
        pytest.skip("pas de réseau")
    lignes = [{"nom": "Internet Archive", "site": "archive.org"}, {"nom": "Inventé", "site": "zzz-inexistant-club-8431.example"}]
    verifier_candidats(lignes, {"verificateurs": [{"source": "wayback", "module": "wayback", "delai_s": 0.4}]}, {}, lambda: False, 120.0, lambda *a, **k: None)
    v = lignes[0]["faits"]["verifications"][0]
    assert v["source"] == "wayback" and v["preuve"].startswith("http") and "Wayback Machine" in v["origine"]
    assert "faits" not in lignes[1]


# --- [ ] De bout en bout : une vraie recherche (programme local + pont de grappes) ajoute la capture Wayback au candidat qui a un site.
def test_recherche_complete_avec_wayback_en_verification(cfg, tmp_path):
    import json
    import sys
    import time

    if not en_ligne("https://archive.org/wayback/available?url=archive.org"):
        pytest.skip("pas de réseau")
    code = 'import json, sys\njson.load(sys.stdin)\nprint(json.dumps([{"nom": "Internet Archive", "site": "archive.org", "origine": "mon fichier"}], ensure_ascii=False))\n'
    f = tmp_path / "prog.py"
    f.write_text(code, encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/programmes-locaux", json={"nom": "prog", "commande": [sys.executable, str(f)], "genres": ["association"], "pays": ["FR"]})
        assert r.status_code == 201, r.text
        for x in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{x['id']}", json={"chercher": x["id"] == r.json()["id"]})
        c.put("/api/reglages/source/wayback", json={"verifier": True})
        c.put("/api/reglages/verification", json={"active": True, "mode": "plus"})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "archives", "pays": "France"}, "parametres": {"profondeur": "strict"}}).json()["id"]
        t0 = time.time()
        while time.time() - t0 < 180 and c.get(f"/api/recherches/{rid}").json()["etat"] not in ("terminee", "echec", "arretee", "interrompue"):
            time.sleep(0.5)
        assert c.get(f"/api/recherches/{rid}").json()["etat"] == "terminee"
    lignes = json.loads(next(cfg.dossier_recherche(rid).rglob("candidats.json")).read_text(encoding="utf-8"))
    ia = next(x for x in lignes if x["nom"] == "Internet Archive")
    assert ia["site"] == "archive.org" and ia["faits"]["verifications"][0]["source"] == "wayback" and ia["faits"]["verifications"][0]["preuve"].startswith("http")


# --- [ ] OpenSanctions : vérification PAR NOM, correspondance exacte seulement, résultat = alerte (jamais une confirmation).
def exemple_opensanctions():
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent.parent / "config/sources/exemples/opensanctions.json").read_text(encoding="utf-8"))


def test_opensanctions_ne_signale_que_les_noms_exacts():
    from pilote.adaptateurs import opensanctions

    rep = exemple_opensanctions()
    r = opensanctions.convertir(rep, "societe francaise d'import export")  # casse, accents, ponctuation : sans importance
    assert len(r) == 1 and r[0]["signal"] == "alerte" and "figure sur une liste de sanctions" in r[0]["origine"] and r[0]["numero"].startswith("https://www.opensanctions.org/entities/")
    assert opensanctions.convertir(rep, "SFIE SA")[0]["signal"] == "alerte"  # un autre nom connu de la même entité
    assert opensanctions.convertir(rep, "Société Française d'Import") == []  # nom proche mais différent : aucune accusation
    assert opensanctions.convertir(rep, "Club de handball") == [] and opensanctions.convertir(rep, "  ") == []
    rep["results"][0]["schema"] = "Person"
    assert opensanctions.convertir(rep, "SFIE SA") == []  # une personne n'est jamais signalée


def test_opensanctions_reste_eteinte_sans_cle_et_ne_fait_aucun_appel():
    from pilote.adaptateurs import ErreurSource, opensanctions

    class SansReseau:
        def get_json(self, *a, **k):
            raise AssertionError("aucun appel sans clé")

    with pytest.raises(ErreurSource):
        opensanctions.chercher({"nom": "Club"}, SansReseau(), {"_cle": ""})
    assert opensanctions.chercher({"nom": ""}, SansReseau(), {"_cle": ""}) == []


def test_une_verification_par_nom_est_faite_meme_sans_site_et_porte_son_signal(monkeypatch):
    class Faux:
        @staticmethod
        def chercher(entree, client, parametres):
            assert parametres["_cle"] == "secret"
            return [{"nom": entree["nom"], "numero": "https://www.opensanctions.org/entities/NK-1", "signal": "alerte", "origine": "OpenSanctions : ..."}] if entree["nom"] == "Listé" else []

    monkeypatch.setattr(adaptateurs, "charger", lambda nom: Faux)
    lignes = [{"nom": "Listé", "site": ""}, {"nom": "Propre", "site": ""}]
    spec = {"verificateurs": [{"source": "opensanctions", "module": "opensanctions", "verifie_sur": "nom", "cles_noms": ["OPENSANCTIONS_API_KEY"]}]}
    verifier_candidats(lignes, spec, {"OPENSANCTIONS_API_KEY": "secret"}, lambda: False, 60.0, lambda *a, **k: None)
    assert lignes[0]["faits"]["verifications"][0]["signal"] == "alerte" and "faits" not in lignes[1]


def test_opensanctions_est_une_verificatrice_par_nom_et_la_cle_manquante_l_ecarte(cfg):
    with TestClient(creer_app(cfg)) as c:
        c.put("/api/reglages/verification", json={"active": True, "mode": "plus"})
        c.put("/api/reglages/source/opensanctions", json={"verifier": True})
        assert "opensanctions" not in [d.id for d in verificatrices(cfg, {})]  # pas de clé : éteinte
        assert "opensanctions" not in [d.id for d in choisies(cfg, {"sources": ["opensanctions"]})]
