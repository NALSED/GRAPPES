"""Étape 4 : classements (fichiers), paquets, décisions annulables, ressemblances, fiches, export."""

import csv
import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import classements as cl
from pilote.app import creer_app
from pilote.base import Candidat, Recherche, creer_fabrique
from pilote.config import charger

NOMS = [
    # nom, origine, endroits, trouve_par, genre, ville, site, numéro
    ("Fenix Toulouse Handball", "registre", 3, ["sirene_naf", "web"], "Activités de clubs de sports", "Toulouse", "fenix.fr", "422893214"),
    ("Fenix Toulouse", "web", 1, ["web"], "", "Toulouse", "", ""),
    ("Montpellier Handball", "registre", 2, ["sirene_nom", "wikidata"], "Activités de clubs de sports", "Montpellier", "mhb.fr", "300000001"),
    ("Handball Shop Nantes", "web", 1, ["web"], "", "Nantes", "", ""),
    ("Ligue Nationale de Handball", "presse", 2, ["rss", "web"], "", "", "lnh.fr", ""),
    ("Championnat de France masculin 2024", "encyclo", 1, ["wikipedia"], "", "", "", ""),
    ("Collectif Handball Lille", "texte", 1, ["texte"], "", "Lille", "", ""),
    ("Amicale Handball Brest", "texte", 1, ["texte"], "", "Brest", "", ""),
]


@pytest.fixture
def monde(tmp_path):
    g = tmp_path / "g"
    (g / "config" / "recherche").mkdir(parents=True)
    (g / "donnees").mkdir()
    (g / "src").symlink_to(charger().grappes_racine / "src")
    (g / "config" / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    (g / "config" / "registres.yaml").write_text("registres: {}\n", encoding="utf-8")
    (g / "config" / "sortie.yaml").write_text(
        "profils:\n  resultat:\n    actif: true\n    fichier: resultat.csv\n    colonnes: [nom]\n    entete: [NOM]\n    delimiteur: \",\"\n"
        "  tsites:\n    actif: true\n    fichier: tsites.csv\n    colonnes: [nom, ville, pays]\n    entete: [nom, ville, pays]\n    delimiteur: \";\"\n"
        "  brut:\n    actif: false\n    fichier: brut.csv\n    colonnes: [nom]\n    entete: [nom]\n    delimiteur: \";\"\n", encoding="utf-8")
    base = charger()
    f = tmp_path / "config" / "pilote.yaml"
    f.parent.mkdir()
    f.write_text(
        f"service: {{https: false, hotes_autorises: [testserver]}}\ngrappes: {{racine: {g}}}\ndonnees: {{dossier: {tmp_path / 'd'}}}\n"
        f"classements: {{livres: {tmp_path / 'livres'}, perso: '{{donnees}}/perso'}}\n"
        + yaml.safe_dump({"familles": list(base.familles), "ordre_familles": list(base.ordre_familles)}), encoding="utf-8")
    shutil.copytree(base.dossier_classements_livres, tmp_path / "livres")
    cfg = charger(f)
    fab = creer_fabrique(cfg.url_base)
    with fab.begin() as s:
        s.add(Recherche(id="r1", qui="sednal", etat="terminee", sujet={"quoi": "clubs de handball"}, parametres={"verification": True}))
        s.flush()
        for nom, o, e, tp, genre, ville, site, num in NOMS:
            s.add(Candidat(recherche_id="r1", nom=nom, genre_source=o, nb_endroits=e, trouve_par=tp, genre_de_chose=genre, ville=ville, pays="FR", site=site,
                           numero_officiel=num, faits={"sources": ["web:" + site] if site else []}))
    return cfg


def test_les_classements_livres_sont_des_fichiers_ordinaires_et_valides(monde):
    ids = {c.id for c in cl.lister(monde)}
    assert ids >= {"solides", "fragiles", "source", "genre", "endroit", "ressemble", "alpha", "decisions"}
    assert all(c.livre for c in cl.lister(monde))
    assert (monde.dossier_classements_livres / "solides.yaml").read_text(encoding="utf-8").startswith("# Classement livré")


def test_ouvre_sur_une_dizaine_de_paquets_jamais_sur_des_milliers_de_lignes(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri").json()
    assert t["classement"]["id"] == "solides" and t["total"] == 8 and t["a_decider"] == 8
    phrases = [p["phrase"] for p in t["paquets"]]
    assert phrases[0] == "dans un registre officiel, à plusieurs endroits"  # le plus solide d'abord
    assert phrases[-1].startswith("lu dans un texte")
    assert sum(p["n"] for p in t["paquets"]) == 8 and len(t["paquets"]) <= 12
    assert {o["id"] for o in t["origines"]} == {"registre", "presse", "encyclo", "web", "texte"}


def test_changer_de_classement_c_est_changer_de_paquets(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        a = c.get("/api/recherches/r1/tri?classement=ressemble").json()
        b = c.get("/api/recherches/r1/tri?classement=source").json()
        d = c.get("/api/recherches/r1/tri?classement=alpha").json()
    assert [p["phrase"] for p in a["paquets"]] == ["sans doute le même, écrit différemment", "noms distincts"]
    proches = {l["nom"] for l in a["lignes"] if l["p"] == "proche"}
    assert proches == {"Fenix Toulouse Handball", "Fenix Toulouse"}
    assert "Annuaire des entreprises" in [p["phrase"] for p in b["paquets"]]  # nom lisible, pas « sirene_naf »
    assert all(len(p["phrase"]) == 1 for p in d["paquets"])


def test_decision_groupee_sur_un_paquet_entier_et_annulable(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri").json()
        reg = next(p for p in t["paquets"] if p["phrase"].startswith("dans un registre officiel, à plusieurs"))
        r = c.post("/api/recherches/r1/decisions", json={"valeur": "garder", "classement": "solides", "cle": reg["cle"]}).json()
        assert len(r["touches"]) == reg["n"]
        t2 = c.get("/api/recherches/r1/tri").json()
        assert t2["a_decider"] == 8 - reg["n"] and t2["peut_annuler"]
        assert {l["d"] for l in t2["lignes"] if l["p"] == reg["cle"]} == {"garder"}
        # annuler : tout le lot revient d'un coup
        u = c.post("/api/recherches/r1/annuler").json()
        assert sorted(u["touches"]) == sorted(r["touches"])
        t3 = c.get("/api/recherches/r1/tri").json()
        assert t3["a_decider"] == 8 and not t3["peut_annuler"]


def test_annuler_fait_reapparaitre_la_decision_precedente(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri").json()
        nid = t["lignes"][0]["id"]
        c.post("/api/recherches/r1/decisions", json={"valeur": "garder", "ids": [nid]})
        c.post("/api/recherches/r1/decisions", json={"valeur": "rejeter", "ids": [nid]})
        d = {l["id"]: l["d"] for l in c.get("/api/recherches/r1/tri").json()["lignes"]}
        assert d[nid] == "rejeter"
        c.post("/api/recherches/r1/annuler")
        d = {l["id"]: l["d"] for l in c.get("/api/recherches/r1/tri").json()["lignes"]}
        assert d[nid] == "garder"
        c.post("/api/recherches/r1/annuler")
        assert {l["id"]: l["d"] for l in c.get("/api/recherches/r1/tri").json()["lignes"]}[nid] is None


def test_action_groupee_ne_touche_pas_ce_qui_est_deja_decide(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri").json()
        web = next(p for p in t["paquets"] if p["phrase"].startswith("trouvé sur le web"))
        un = next(l["id"] for l in t["lignes"] if l["p"] == web["cle"])
        c.post("/api/recherches/r1/decisions", json={"valeur": "garder", "ids": [un]})
        r = c.post("/api/recherches/r1/decisions", json={"valeur": "rejeter", "classement": "solides", "cle": web["cle"]}).json()
        assert un not in r["touches"]
        d = {l["id"]: l["d"] for l in c.get("/api/recherches/r1/tri").json()["lignes"]}
        assert d[un] == "garder"


def test_valeur_de_decision_inconnue_refusee_et_qui_journalise(monde):
    app = creer_app(monde, lambda c: None)
    with TestClient(app) as c:
        assert c.post("/api/recherches/r1/decisions", json={"valeur": "super", "ids": [1]}).status_code == 422
        assert c.post("/api/recherches/r1/decisions", json={"valeur": "garder"}).status_code == 422
        c.post("/api/recherches/r1/decisions", json={"valeur": "garder", "ids": [1], "qui": "sednal"})
        j = c.get("/api/recherches/r1/journal").json()
        assert any(x["evenement"] == "decision" and x["qui"] == "sednal" for x in j)
    from sqlalchemy import select

    from pilote.base import Decision

    with app.state.fabrique() as s:
        assert [d.qui for d in s.scalars(select(Decision))] == ["sednal"]


def test_separer_retire_la_ressemblance(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri?classement=ressemble").json()
        nid = next(l["id"] for l in t["lignes"] if l["nom"] == "Fenix Toulouse")
        c.post(f"/api/recherches/r1/noms/{nid}/separer")
        t = c.get("/api/recherches/r1/tri?classement=ressemble").json()
        assert [p["phrase"] for p in t["paquets"]] == ["noms distincts"]


def test_fiche_en_francais_courant(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri").json()
        nid = next(l["id"] for l in t["lignes"] if l["nom"] == "Fenix Toulouse Handball")
        f = c.get(f"/api/recherches/r1/noms/{nid}").json()
    assert f["origine_phrase"] == "dans un registre officiel" and f["endroits"] == 3 and f["numero_officiel"] == "422893214"
    assert {"Annuaire des entreprises", "Recherche web"} <= {s["nom"] for s in f["sources"]}
    assert not any("_" in s["nom"] for s in f["sources"])  # aucun identifiant technique


def test_creer_dupliquer_exporter_un_classement(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        r = c.post("/api/classements", json={"nom": "Avec un site web", "grouper_par": ["site"], "ordre_paquets": "solidite"})
        assert r.status_code == 201 and r.json()["id"] == "avec-un-site-web" and not r.json()["livre"]
        assert (monde.dossier_classements_perso / "avec-un-site-web.yaml").exists()
        t = c.get("/api/recherches/r1/tri?classement=avec-un-site-web").json()
        assert [p["phrase"] for p in t["paquets"]] == ["ont un site web", "pas de site trouvé"]
        d = c.post("/api/classements/solides/dupliquer").json()
        assert d["nom"] == "Les plus solides d'abord (copie)" and not d["livre"]
        f = c.get("/api/classements/avec-un-site-web/fichier")
        assert "grouper_par" in f.text and "attachment" in f.headers["content-disposition"]
        # un classement ne travaille que sur des faits, et il faut un nom
        assert c.post("/api/classements", json={"nom": "X", "grouper_par": ["score"]}).status_code == 422
        assert c.post("/api/classements", json={"nom": " ", "grouper_par": ["site"]}).status_code == 422
        # jamais d'écrasement
        assert c.post("/api/classements", json={"nom": "Avec un site web", "grouper_par": ["site"]}).json()["id"] == "avec-un-site-web-2"


def test_export_gardes_vers_les_sorties_activees_et_decisions_a_part(monde):
    with TestClient(creer_app(monde, lambda c: None)) as c:
        t = c.get("/api/recherches/r1/tri").json()
        ids = {l["nom"]: l["id"] for l in t["lignes"]}
        c.post("/api/recherches/r1/decisions", json={"valeur": "garder", "ids": [ids["Fenix Toulouse Handball"], ids["Montpellier Handball"]]})
        c.post("/api/recherches/r1/decisions", json={"valeur": "rejeter", "ids": [ids["Handball Shop Nantes"]]})
        c.post("/api/recherches/r1/decisions", json={"valeur": "plus_tard", "ids": [ids["Collectif Handball Lille"]]})
        r = c.post("/api/recherches/r1/export").json()
    assert r["gardes"] == 2 and r["decisions"] == 4
    assert set(r["fichiers"]) == {"resultat.csv", "resultat.csv.trace.json", "resultat_tsites.csv", "resultat_tsites.csv.trace.json", "decisions.csv"}  # le CSV par défaut : les noms, et nom;ville;pays pour trouver-sites
    d = Path(r["dossier"])
    assert (d / "resultat.csv").read_text(encoding="utf-8").splitlines() == ["NOM", "Fenix Toulouse Handball", "Montpellier Handball"]
    lignes = list(csv.reader((d / "decisions.csv").read_text(encoding="utf-8").splitlines(), delimiter=";"))
    assert lignes[0][:2] == ["nom", "ville"] and len(lignes) == 5
    assert {x[6] for x in lignes[1:]} == {"gardé", "rejeté", "mis de côté"} and {x[7] for x in lignes[1:]} == {"sednal"}
    assert not (monde.grappes_racine / "sorties").exists()  # la sortie de grappes n'est jamais touchée


def test_ressemblances_prudentes():
    r = cl.ressemblances({1: "Fenix Toulouse Handball", 2: "Fenix Toulouse", 3: "Handball Club Nantes", 4: "Paris Saint-Germain Handball", 5: "Paris Handball"})
    assert set(r) == {1, 2}  # « Paris Handball » n'est pas le début ni la fin de « Paris Saint-Germain Handball »


@pytest.mark.reseau
def test_rendu_de_la_page_tri_sous_node():
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node absent")
    r = subprocess.run(["node", "tests/js/rendu_tri.mjs"], capture_output=True, text=True, check=False, cwd=Path(__file__).resolve().parents[1])
    assert r.returncode == 0, r.stdout + r.stderr
