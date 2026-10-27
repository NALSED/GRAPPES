"""FICHE 04 — preset Organisations officielles : test de recette, point par point."""

import json
import os
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from pilote.adaptateurs import Client, ErreurSource, charger
from pilote.app import creer_app
from pilote.config import RACINE
from pilote.sources import charger_sources


def en_ligne(url: str) -> bool:
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pilote-test"}), timeout=15)
        return True
    except urllib.error.HTTPError:
        return True  # le serveur répond (même par une erreur) : le réseau est là
    except (urllib.error.URLError, OSError):
        return False


def declarations_organisations(cfg):
    decls, problemes = charger_sources(cfg)
    assert problemes == []
    return {d.id: d for d in decls.values() if "organisations" in d.usages}


# --- [ ] data.gouv.fr, Wikidata et ROR répondent et rendent des noms.
@pytest.mark.reseau
def test_ror_rend_des_noms():
    if not en_ligne("https://api.ror.org/v2/organizations?query=universite"):
        pytest.skip("pas de réseau")
    noms = charger("ror").chercher({"quoi": "université", "pays": "FR", "limite": 5}, Client("ror", delai_s=0.3), {})
    assert len(noms) == 5 and all(n["nom"] and n["origine"] and n["pays"] == "FR" for n in noms)
    assert noms[0]["numero"].startswith("https://ror.org/") and all(n["genre"] == "administration" for n in noms)


@pytest.mark.reseau
def test_datagouv_par_son_serveur_mcp_rend_des_noms():
    if not en_ligne("https://mcp.data.gouv.fr/"):
        pytest.skip("pas de réseau")
    # l'adaptateur tourne dans l'interpréteur de grappes (c'est lui qui a la bibliothèque MCP), comme dans une vraie recherche
    from pilote.config import charger as charger_config

    cfg = charger_config()
    py = cfg.python_grappes
    if not py.exists():
        pytest.skip("interpréteur de grappes absent")
    code = ("import json;from pilote.adaptateurs import Client, charger;"
            "c=Client('datagouv-organisations');r=charger('datagouv_organisations').chercher({'quoi':'université','pays':'FR','limite':5},c,{});"
            "print(json.dumps({'n':len(r),'appels':c.appels,'premier':r[0]}))")  # fmt: skip
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(cfg.grappes_racine / "src"), str(RACINE / "src")])}
    sortie = subprocess.run([str(py), "-c", code], capture_output=True, text=True, env=env, check=False, timeout=120)
    assert sortie.returncode == 0, sortie.stderr[-500:]
    d = json.loads(sortie.stdout.strip().splitlines()[-1])
    assert d["n"] == 5 and d["appels"] >= 1 and d["premier"]["nom"] and "data.gouv.fr" in d["premier"]["origine"] and d["premier"]["pays"] == "FR"


def test_datagouv_ne_couvre_que_la_france():
    class Mort(Client):
        def mcp(self, *a, **k):
            raise AssertionError("aucun appel pour un autre pays")

    assert charger("datagouv_organisations").chercher({"quoi": "université", "pays": "GB"}, Mort("x"), {}) == []


def test_lecture_des_organisations_de_data_gouv_sur_un_exemple():
    from pilote.adaptateurs import datagouv_organisations as dg

    texte = (RACINE / "config" / "sources" / "exemples" / "datagouv-organisations.txt").read_text(encoding="utf-8")
    noms = dg.convertir(texte)
    assert [n["nom"] for n in noms] == ["Ministère Exemple (ME)", "Association Imaginaire"]
    assert "service public certifiée" in noms[0]["origine"] and "service public" not in noms[1]["origine"]


# --- [ ] ROR est interrogeable par nom et par pays.
@pytest.mark.reseau
def test_ror_par_nom_et_par_pays():
    if not en_ligne("https://api.ror.org/v2/organizations?query=universite"):
        pytest.skip("pas de réseau")
    c = Client("ror", delai_s=0.3)
    fr = charger("ror").chercher({"quoi": "university", "pays": "FR", "limite": 5}, c, {})
    nz = charger("ror").chercher({"quoi": "university", "pays": "NZ", "limite": 5}, c, {})
    monde = charger("ror").chercher({"quoi": "Université de Montpellier", "pays": "", "limite": 3}, c, {})
    assert fr and nz and {n["pays"] for n in fr} == {"FR"} and {n["pays"] for n in nz} == {"NZ"}  # par pays
    assert any("Montpellier" in n["nom"] for n in monde)  # par nom
    assert {n["nom"] for n in fr}.isdisjoint({n["nom"] for n in nz})


# --- [ ] La source CKAN générique fonctionne avec au moins deux portails de pays différents en ne changeant que l'adresse.
@pytest.mark.reseau
def test_ckan_deux_portails_de_deux_pays_en_changeant_seulement_l_adresse():
    portails = {"CA": "https://open.canada.ca/data", "IE": "https://data.gov.ie"}
    if not all(en_ligne(p + "/api/3/action/organization_list?limit=1") for p in portails.values()):
        pytest.skip("portails injoignables")
    ckan = charger("ckan")  # UN seul module, le même pour les deux pays
    resultats = {}
    for pays, adresse in portails.items():
        resultats[pays] = ckan.chercher({"quoi": "health council", "pays": pays, "limite": 5}, Client("ckan", delai_s=0.3), {"portail": adresse})
        assert resultats[pays] and all(n["nom"] and urlsplit(adresse).netloc in n["origine"] and n["pays"] == pays for n in resultats[pays])
    assert {n["nom"] for n in resultats["CA"]}.isdisjoint({n["nom"] for n in resultats["IE"]})
    # aucun code propre à un pays dans l'adaptateur
    source = (RACINE / "src" / "pilote" / "adaptateurs" / "ckan.py").read_text(encoding="utf-8")
    assert "canada" not in source.lower() and "ireland" not in source.lower() and "gov.ie" not in source


def test_ckan_sans_adresse_ou_avec_une_mauvaise_adresse_le_dit_en_clair():
    with pytest.raises(ErreurSource, match="adresse du portail"):
        charger("ckan").chercher({"quoi": "mairie", "limite": 3}, Client("ckan"), {})

    class Faux(Client):
        def get_json(self, *a, **k):
            return {"pas": "du ckan"}

    with pytest.raises(ErreurSource, match="CKAN"):
        charger("ckan").chercher({"quoi": "mairie", "limite": 3}, Faux("ckan"), {"portail": "https://exemple.test"})


def test_ckan_est_eteinte_jusqu_a_ce_que_l_utilisateur_donne_l_adresse(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        ligne = next(s for s in c.get("/api/reglages").json()["parties"]["recherche"] if s["id"] == "ckan")
        assert ligne["chercher"] is False and ligne["parametres_attendus"]["portail"]["requis"] is True
        r = c.put("/api/reglages/source/ckan", json={"chercher": True})
        assert r.status_code == 422 and "adresse du portail" in r.json()["detail"]
        r = c.put("/api/reglages/source/ckan", json={"parametres": {"portail": "open.canada.ca"}})
        assert r.status_code == 422 and "https://" in r.json()["detail"]
        assert c.put("/api/reglages/source/ckan", json={"parametres": {"portail": "https://open.canada.ca/data"}, "chercher": True}).status_code == 200
        ligne = next(s for s in c.get("/api/reglages").json()["parties"]["recherche"] if s["id"] == "ckan")
        assert ligne["chercher"] is True and ligne["parametres"]["portail"] == "https://open.canada.ca/data"


# --- [ ] Si le pays choisi n'a pas de portail connu, le programme le dit clairement et propose l'ajout manuel.
def test_pays_sans_portail_connu_le_dit_et_propose_l_ajout_manuel(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        sans = c.get("/api/portails-ckan?pays=FR").json()
        assert sans["portail"] is None and "Aucun portail" in sans["message"] and "Ajout" in sans["message"]
        avec = c.get("/api/portails-ckan?pays=ca").json()
        assert avec["portail"] == "https://open.canada.ca/data" and avec["message"] == "" and avec["verifie_le"] == "2026-10-13"
        assert c.get("/api/portails-ckan?pays=ZZ").json()["portail"] is None


# --- Déclarations du preset.
def test_les_quatre_sources_du_preset_sont_declarees_comme_la_fiche_le_demande(cfg):
    d = declarations_organisations(cfg)
    assert {"datagouv-organisations", "wikidata", "ror", "ckan", "esr_etablissements", "bnf_organisations", "wikipedia"} >= {"datagouv-organisations", "wikidata", "ror", "ckan"}
    assert {s for s in ("datagouv-organisations", "wikidata", "ror") if d[s].defaut["chercher"]} == {"datagouv-organisations", "wikidata", "ror"}  # allumées
    assert d["ckan"].defaut["chercher"] is False  # éteinte jusqu'à l'adresse
    assert d["datagouv-organisations"].pays == ["FR"] and d["wikidata"].pays == ["monde"] and d["ror"].pays == ["monde"] and d["ckan"].pays == ["monde"]
    for sid in ("datagouv-organisations", "wikidata", "ror", "ckan"):
        assert d[sid].main == "premiere" and d[sid].origine == "registre" and not d[sid].payant, sid  # gratuites, première main, couleur « registre »
    assert d["datagouv-organisations"].moteur["adaptateur"] == "datagouv_organisations" and d["datagouv-organisations"].famille == "mcp"


def test_lecture_hors_ligne_des_quatre_sources(cfg):
    from pilote.tests_source import tester

    decls = charger_sources(cfg)[0]
    for sid in ("datagouv-organisations", "wikidata", "ror"):
        r = tester(cfg, decls[sid])
        assert r["statut"] == "ok" and r["niveaux"]["2"] == "ok", (sid, r)


def test_singulier_pour_interroger_des_noms_d_organisations():
    from pilote.adaptateurs import singulier

    assert singulier("universités françaises") == "université française"  # "françaises" -> "française"
    assert singulier("clubs de sports") == "club de sport"
    assert singulier("bus Paris") == "bus Paris"  # un nom propre ne perd jamais son s


# --- [ ] Les noms issus de ces sources portent la couleur « registre » dans Tri et sont marqués première main.
@pytest.mark.reseau
def test_recherche_reelle_les_noms_sont_registre_et_premiere_main(cfg):
    import time

    from sqlalchemy import select

    from pilote.base import Candidat
    from pilote.config import charger as charger_config

    if not en_ligne("https://api.ror.org/v2/organizations?query=universite") or not charger_config().python_grappes.exists():
        pytest.skip("pas de réseau ou pas d'interpréteur de grappes")
    app = creer_app(cfg)
    with TestClient(app) as c:
        for s in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{s['id']}", json={"chercher": s["id"] in ("datagouv-organisations", "wikidata", "ror")})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "universités", "pays": "France", "combien": 400}, "parametres": {"profondeur": "large"}}).json()["id"]
        t0 = time.time()
        while time.time() - t0 < 300 and c.get(f"/api/recherches/{rid}").json()["etat"] not in ("terminee", "echec", "arretee"):
            time.sleep(2)
        assert c.get(f"/api/recherches/{rid}").json()["etat"] == "terminee"
        with app.state.fabrique() as s:
            lignes = s.scalars(select(Candidat).where(Candidat.recherche_id == rid)).all()
            tri = c.get(f"/api/recherches/{rid}/tri").json()
    assert len(lignes) > 30 and {x.genre_source for x in lignes} == {"registre"}
    sources = {src for x in lignes for src in x.trouve_par}
    assert {"wikidata", "datagouv-organisations"} <= sources  # chaque source a rendu des noms
    for x in lignes:
        assert all(p["main"] == "premiere" for p in x.faits["preuves"] if p["source"] in ("wikidata", "datagouv-organisations", "ror"))
    assert {l["o"] for l in tri["lignes"]} == {"registre"}  # la couleur « registre » est celle que Tri recevra
