"""FICHE 05 — preset Associations : test de recette, point par point."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote.adaptateurs import Client, ErreurSource, charger
from pilote.app import creer_app
from pilote.moteur_sources import choisies
from pilote.sources import charger_sources

PHRASE_FICHE = ("Associations : clubs, associations, fédérations et œuvres caritatives déclarées dans un registre. "
                "Pour les groupes informels, cocher aussi Web, Réseaux sociaux ou Lieux.")


def en_ligne(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pilote-test"}), timeout=15)
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def sources_du_preset(cfg):
    decls, problemes = charger_sources(cfg)
    assert problemes == []
    return {d.id: d for d in decls.values() if "associations" in d.usages}


# --- [ ] Le registre français des associations et Wikidata répondent et rendent des noms.
def test_le_registre_francais_des_associations_rend_des_associations():
    if not en_ligne("https://recherche-entreprises.api.gouv.fr/search?q=a&per_page=1"):
        pytest.skip("pas de réseau")
    noms = charger("recherche_entreprises").chercher({"quoi": "handball", "pays": "FR", "limite": 12}, Client("registre-associations", delai_s=0.3), {"filtre": "association"})
    assert len(noms) >= 5 and all(n["genre"] == "association" and n["pays"] == "FR" and n["numero"] for n in noms)
    assert any(n["numero"].startswith("W") for n in noms)  # numéro d'association (RNA)


def test_le_registre_francais_ne_repond_que_pour_la_france():
    class Mort(Client):
        def get_json(self, *a, **k):
            raise AssertionError("aucun appel hors de France")

    assert charger("recherche_entreprises").chercher({"quoi": "club", "pays": "GB"}, Mort("x"), {"filtre": "association"}) == []


def test_wikidata_est_une_source_du_preset(cfg):
    d = sources_du_preset(cfg)["wikidata"]
    assert d.defaut["chercher"] is True and d.pays == ["monde"] and d.moteur == {"registre_grappes": "wikidata"}


# --- [ ] La Charity Commission fonctionne avec une clé, et la source est bien éteinte sans clé.
class FauxServeur(BaseHTTPRequestHandler):
    recus: ClassVar[list] = []

    def do_GET(self):
        FauxServeur.recus.append((self.path, self.headers.get("Ocp-Apim-Subscription-Key")))
        if self.headers.get("Ocp-Apim-Subscription-Key") != "cle-de-test":
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps([{"organisation_number": 1, "reg_charity_number": 1189012, "group_subsid_suffix": 0, "charity_name": "RIVERSIDE ROWING CLUB"}]).encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_registre():
    s = HTTPServer(("127.0.0.1", 0), FauxServeur)
    FauxServeur.recus = []
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/register/api"
    s.shutdown()


def test_charity_commission_fonctionne_avec_une_cle(faux_registre):
    noms = charger("charity_commission").chercher({"quoi": "rowing clubs", "pays": "GB", "limite": 5}, Client("charity-commission"), {"base": faux_registre, "_cle": "cle-de-test"})
    assert noms[0]["nom"] == "Riverside Rowing Club" and noms[0]["numero"] == "1189012" and noms[0]["genre"] == "association"
    chemin, entete = FauxServeur.recus[0]
    assert chemin == "/register/api/searchCharityName/rowing%20club" and entete == "cle-de-test"  # la clé part dans l'en-tête, jamais dans l'adresse


def test_charity_commission_sans_cle_ou_avec_une_fausse_cle_le_dit_en_clair(faux_registre):
    with pytest.raises(ErreurSource, match="clé d'API de la Charity Commission est absente"):
        charger("charity_commission").chercher({"quoi": "club", "pays": "GB"}, Client("c"), {"base": faux_registre})
    with pytest.raises(ErreurSource, match="401"):
        charger("charity_commission").chercher({"quoi": "club", "pays": "GB"}, Client("c"), {"base": faux_registre, "_cle": "fausse"})
    assert charger("charity_commission").chercher({"quoi": "club", "pays": "FR"}, Client("c"), {"_cle": "x"}) == []  # hors de son pays : rien


def test_charity_commission_est_eteinte_sans_cle(cfg):
    d = sources_du_preset(cfg)["charity-commission"]
    assert d.cle == "CHARITY_COMMISSION_API_KEY" and d.defaut == {"chercher": False, "verifier": False}
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        c.put("/api/reglages/source/charity-commission", json={"chercher": True})  # même cochée par l'utilisateur…
        ligne = next(s for s in c.get("/api/reglages").json()["parties"]["recherche"] if s["id"] == "charity-commission")
        assert ligne["cle"] == "absente" and ligne["bloquee_par_cle"] is True  # …elle est signalée bloquée
    assert "charity-commission" not in [x.id for x in choisies(cfg, {})]  # …et une recherche ne l'utilise pas
    cfg.fichiers_secrets[0].write_text("CHARITY_COMMISSION_API_KEY=une-cle\n", encoding="utf-8")
    assert "charity-commission" in [x.id for x in choisies(cfg, {})]  # avec la clé, elle est utilisée


# --- [ ] Aucune source bruyante (web, réseaux sociaux) n'est présente dans ce preset.
def test_aucune_source_bruyante_dans_le_preset(cfg):
    for sid, d in sources_du_preset(cfg).items():
        assert d.origine == "registre" and d.main == "premiere", sid  # que du fiable
        assert not ({"web", "reseaux_sociaux", "lieux", "presse"} & set(d.usages)), sid
    assert set(sources_du_preset(cfg)) >= {"registre-associations", "wikidata", "charity-commission"}
    # et rien ne vient de IATI ni des registres caritatifs non contrôlés : « n'entrent au catalogue qu'une fois contrôlés »
    assert not {"iati", "charity-commission-us", "registre-caritatif-ca", "registre-caritatif-nz"} & set(charger_sources(cfg)[0])


# --- [ ] La carte affiche bien la phrase qui renvoie vers les autres presets pour l'informel.
def test_la_carte_porte_la_phrase_de_la_fiche(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "associations")
    assert carte["phrase"] == PHRASE_FICHE
    assert yaml.safe_load((cfg.dossier_presets / "associations.yaml").read_text(encoding="utf-8"))["phrase"] == PHRASE_FICHE
    assert "Web" in carte["phrase"] and "Réseaux sociaux" in carte["phrase"] and "Lieux" in carte["phrase"]


# --- [ ] Les noms portent la couleur « registre » et sont marqués première main.
def test_les_sources_du_preset_donnent_la_couleur_registre_et_premiere_main(cfg):
    for d in sources_du_preset(cfg).values():
        assert d.origine == "registre" and d.main == "premiere"


def test_carte_et_pays_une_source_dit_si_elle_couvre_le_pays(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "associations")
    pays = {s["id"]: s["pays"] for s in carte["sources"]}
    assert pays["charity-commission"] == ["GB"] and pays["registre-associations"] == ["FR"] and pays["wikidata"] == ["monde"]
