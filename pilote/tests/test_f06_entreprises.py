"""FICHE 06 — preset Entreprises : test de recette, point par point."""

import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from pilote import rapprochement as rp
from pilote.adaptateurs import Client, charger
from pilote.app import creer_app
from pilote.base import Candidat, Recherche, creer_fabrique
from pilote.sources import charger_sources


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
    return {d.id: d for d in decls.values() if "entreprises" in d.usages}


# --- [ ] recherche-entreprises, GLEIF et Wikidata répondent et rendent des noms.
@pytest.mark.reseau
def test_recherche_entreprises_rend_des_societes_avec_leur_fonction():
    if not en_ligne("https://recherche-entreprises.api.gouv.fr/search?q=a&per_page=1"):
        pytest.skip("pas de réseau")
    noms = charger("recherche_entreprises").chercher({"quoi": "decathlon", "pays": "FR", "limite": 10}, Client("recherche-entreprises", delai_s=0.4), {"filtre": "entreprise", "etablissements": 2})
    assert noms and {n["fonction"] for n in noms} >= {"siège", "établissement"} and all(n["genre"] == "entreprise" for n in noms)
    siege = next(n for n in noms if n["fonction"] == "siège" and n["relations"])
    assert all(r["type"] == "a_pour_etablissement" for r in siege["relations"])


@pytest.mark.reseau
def test_gleif_rend_des_noms():
    if not en_ligne("https://api.gleif.org/api/v1/lei-records?page%5Bsize%5D=1"):
        pytest.skip("pas de réseau")
    noms = charger("gleif").chercher({"quoi": "Carrefour", "pays": "FR", "limite": 5}, Client("gleif", delai_s=0.4), {"relations_max": 0})
    assert len(noms) == 5 and all("Carrefour" in n["nom"] and n["pays"] == "FR" for n in noms)


def test_wikidata_est_une_source_du_preset(cfg):
    d = sources_du_preset(cfg)["wikidata"]
    assert d.defaut["chercher"] is True and d.defaut["verifier"] is True


# --- [ ] GLEIF rend bien la maison mère et la maison mère ultime d'une entité connue.
@pytest.mark.reseau
def test_gleif_rend_la_maison_mere_et_la_maison_mere_ultime():
    if not en_ligne("https://api.gleif.org/api/v1/lei-records?page%5Bsize%5D=1"):
        pytest.skip("pas de réseau")
    c = Client("gleif", delai_s=0.4)
    noms = charger("gleif").chercher({"quoi": "Carrefour", "pays": "FR", "limite": 12}, c, {"relations_max": 12})
    filiale = next(n for n in noms if n["nom"] == "Carrefour France")
    types = {r["type"]: r["vers"] for r in filiale["relations"]}
    assert types == {"maison_mere": "Carrefour", "maison_mere_ultime": "Carrefour"} and filiale["fonction"] == "filiale"
    assert any(n["fonction"] == "siège" for n in noms)  # une entité sans maison mère est un siège


def test_gleif_sur_un_exemple_lit_les_liens_vers_les_maisons_meres(cfg):
    import json

    from pilote.adaptateurs import gleif

    brut = json.loads((cfg.dossier_sources / "exemples" / "gleif.json").read_text(encoding="utf-8"))
    n = {x["nom"]: x for x in gleif.convertir(brut)}
    assert n["Ateliers Exemple"]["fonction"] == "filiale" and n["Ateliers Exemple"]["_parent"].endswith("/direct-parent")
    assert n["Filiale Imaginaire"]["fonction"] == "siège" and n["Filiale Imaginaire"]["_parent"] == ""


# --- [ ] cleanco est installé et « SAS DUPONT SPORTS » se rapproche de « Dupont Sports ».
def test_cleanco_rapproche_sas_dupont_sports_de_dupont_sports():
    import cleanco  # noqa: F401  (installé)

    assert rp.nom_nu("SAS DUPONT SPORTS") == "dupont sports" == rp.nom_nu("Dupont Sports SARL") == rp.nom_nu("S.A.S. Dupont Sports")
    assert rp.comparer("SAS DUPONT SPORTS", "Dupont Sports") == rp.EXACT
    assert rp.comparer("SAS DUPONT SPORTS", "Dupont Sports Grenoble") == rp.APPROCHANT
    assert rp.comparer("SAS DUPONT SPORTS", "Martin Cycles") is None
    assert rp.comparer("ACME Ltd", "Acme GmbH") == rp.EXACT  # formes juridiques d'autres pays


# --- [ ] Une même source peut être cochée « vérifier » sans être cochée « chercher ».
def test_une_source_peut_verifier_sans_chercher(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        assert c.put("/api/reglages/source/recherche-entreprises", json={"chercher": False, "verifier": True}).status_code == 200
        ligne = next(s for s in c.get("/api/reglages").json()["parties"]["recherche"] if s["id"] == "recherche-entreprises")
    assert ligne["chercher"] is False and ligne["verifier"] is True
    from pilote.moteur_sources import choisies

    assert "recherche-entreprises" not in [d.id for d in choisies(cfg, {})]  # elle ne cherche pas…
    # …mais elle reste disponible pour vérifier (son interrupteur est enregistré à part)


# --- [ ] Les sources payantes sont éteintes dans la configuration livrée.
def test_les_sources_payantes_sont_eteintes(cfg):
    d = sources_du_preset(cfg)
    for sid in ("opencorporates", "pappers"):
        assert d[sid].payant and d[sid].defaut == {"chercher": False, "verifier": False} and d[sid].cle, sid
    assert "très cher" in d["opencorporates"].note.lower() and "gratuit pour la recherche sur demande" in d["opencorporates"].note.lower()
    assert {s for s, x in d.items() if x.defaut["chercher"]} == {"recherche-entreprises", "gleif", "wikidata"}  # les trois allumées de la fiche


# --- [ ] L'étiquette de fonction apparaît dans Tri, et un siège et ses établissements s'affichent regroupés.
def test_fonction_et_blocs_dans_tri(cfg):
    fab = creer_fabrique(cfg.url_base)
    rel = lambda t, v: {"type": t, "vers": v}
    with fab.begin() as s:
        s.add(Recherche(id="r6", qui="sednal", etat="terminee", sujet={"quoi": "sports"}, parametres={"verification": True}))
        s.flush()
        for nom, num, fonction, relations in (
            ("DUPONT SPORTS", "123456789", "siège", [rel("a_pour_etablissement", "Dupont Sports Grenoble")]),
            ("Dupont Sports Grenoble", "12345678900012", "établissement", [rel("etablissement_de", "DUPONT SPORTS")]),
            ("Groupe Exemple", "", "maison mère", []),
            ("Filiale Exemple", "", "filiale", [rel("maison_mere", "Groupe Exemple")]),
            ("Martin Cycles", "987654321", "siège", []),
        ):
            s.add(Candidat(recherche_id="r6", nom=nom, genre_source="registre", numero_officiel=num, faits={"fonction": fonction}, relations=relations))
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        t = c.get("/api/recherches/r6/tri?classement=groupes").json()
        par_nom = {l["nom"]: l for l in t["lignes"]}
        assert {l["f"] for l in t["lignes"]} == {"siège", "établissement", "maison mère", "filiale"}  # l'étiquette de fonction est transmise
        assert par_nom["DUPONT SPORTS"]["p"] == par_nom["Dupont Sports Grenoble"]["p"]  # siège et établissement : un seul bloc
        assert par_nom["Groupe Exemple"]["p"] == par_nom["Filiale Exemple"]["p"] != par_nom["DUPONT SPORTS"]["p"]  # maison mère et filiale : un autre bloc
        assert par_nom["Martin Cycles"]["p"] == ""  # isolé
        phrases = {p["phrase"] for p in t["paquets"]}
        assert "groupe de DUPONT SPORTS" in phrases and "groupe de Groupe Exemple" in phrases and "isolés (aucun lien avec un autre nom)" in phrases
        f = c.get(f"/api/recherches/r6/noms/{par_nom['Filiale Exemple']['id']}").json()
        assert f["fonction"] == "filiale" and f["bloc"] == "Groupe Exemple" and f["relations"][0]["type"] == "maison_mere"
        assert c.get("/api/recherches/r6/tri?classement=fonction").json()["paquets"][0]["phrase"] == "maison mère"


# --- [ ] Un nom approchant affiche « correspondance probable », pas « confirmé ».
def test_un_nom_approchant_affiche_correspondance_probable_pas_confirme(cfg):
    fab = creer_fabrique(cfg.url_base)
    with fab.begin() as s:
        s.add(Recherche(id="r7", qui="sednal", etat="terminee", sujet={"quoi": "x"}, parametres={"verification": True}))
        s.flush()
        s.add(Candidat(recherche_id="r7", nom="SAS DUPONT SPORTS", genre_source="registre", numero_officiel="123456789"))
        s.add(Candidat(recherche_id="r7", nom="Dupont Sports Grenoble", genre_source="web"))  # approchant
        s.add(Candidat(recherche_id="r7", nom="Dupont Sports", genre_source="presse"))  # exact une fois la forme juridique retirée
        s.add(Candidat(recherche_id="r7", nom="Martin Cycles", genre_source="web"))
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        lignes = {l["nom"]: l for l in c.get("/api/recherches/r7/tri").json()["lignes"]}
    assert lignes["Dupont Sports Grenoble"]["m"] == "correspondance probable"
    assert "confirmé" not in lignes["Dupont Sports Grenoble"]["m"]
    assert lignes["Dupont Sports"]["m"] == "confirmé : même nom"
    assert lignes["Martin Cycles"]["m"] == "" and lignes["SAS DUPONT SPORTS"]["m"] == ""
