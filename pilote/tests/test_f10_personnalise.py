"""FICHE 10 — preset Personnalisé : test de recette, point par point."""

import sys
import time

import pytest
import yaml
from conftest import copier_config
from fastapi.testclient import TestClient

from pilote import cles
from pilote.app import creer_app
from pilote.config import charger as charger_cfg

PHRASE_FICHE = "Personnalisé : tes propres sources, ou un preset existant que tu modifies."
SCRIPT = """import json, sys
json.load(sys.stdin)
print(json.dumps([{"nom": "Chorale des Quatre Vents", "origine": "mon fichier", "ville": "Ville-Exemple"}, {"nom": "Les Voix du Soir 🎶", "origine": "mon fichier"}], ensure_ascii=False))
"""
BOUCLE = "while True:\n    pass\n"


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


def ajouter_programme(c, tmp_path, code=SCRIPT, nom="Mon programme chorales", **plus):
    f = tmp_path / "prog.py"
    f.write_text(code, encoding="utf-8")
    return c.post("/api/programmes-locaux", json={"nom": nom, "commande": [sys.executable, str(f)], "genres": ["association"], "pays": ["FR"], **plus})


def test_la_carte_porte_la_phrase_de_la_fiche_et_part_vide(cfg):
    with TestClient(creer_app(cfg)) as c:
        cartes = {p["id"]: p for p in c.get("/api/reglages").json()["presets"]}
        assert cartes["personnalise"]["phrase"] == PHRASE_FICHE and cartes["personnalise"]["sources"] == []
        r = c.post("/api/presets", json={"nom": "Mon preset vide"})
        assert r.status_code == 201 and r.json()["sources"] == []
        assert c.post("/api/presets", json={"nom": "Mon preset vide"}).status_code == 422  # nom déjà pris
        assert c.post("/api/presets", json={"nom": "  "}).status_code == 422


# --- [ ] Un preset personnalisé peut contenir une source de registre ET une source web.
def test_un_preset_peut_melanger_registre_et_web(cfg):
    with TestClient(creer_app(cfg)) as c:
        tout = {s["id"]: s for p in c.get("/api/reglages").json()["presets"] for s in p["sources"]}
        assert "ror" in tout and "searxng" in tout
        c.post("/api/presets", json={"nom": "Mélange"})
        assert c.put("/api/presets/melange", json={"sources": ["ror", "searxng", "ror"]}).json()["sources"] == ["ror", "searxng"]  # doublon écarté
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "melange")
        assert {s["id"] for s in carte["sources"]} == {"ror", "searxng"} and carte["perso"] is True
        assert c.put("/api/presets/melange", json={"sources": ["nexiste-pas"]}).status_code == 422
        assert c.put("/api/presets/web", json={"sources": []}).status_code == 422  # un preset livré ne se modifie pas
        assert c.delete("/api/presets/web").status_code == 422
        assert c.delete("/api/presets/melange").status_code == 200
        assert "melange" not in {p["id"] for p in c.get("/api/reglages").json()["presets"]}


# --- [ ] L'export produit un fichier texte lisible SANS aucune clé dedans.
def test_l_export_est_lisible_et_sans_cle(cfg):
    cles.ecrire(cfg, "TAVILY_API_KEY", "tvly-SECRET-ne-doit-jamais-sortir-123456")
    cles.ecrire(cfg, "BRAVE_API_KEY", "brave-AUTRE-SECRET-654321")
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/presets", json={"nom": "À partager"})
        c.put("/api/presets/a-partager", json={"sources": ["tavily", "brave", "ror"]})
        r = c.get("/api/presets/a-partager/export")
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
        texte = r.text
    assert "SECRET" not in texte and "tvly-" not in texte and "brave-AUTRE" not in texte
    y = yaml.safe_load(texte)  # lisible par n'importe quel lecteur YAML
    assert y["preset"]["sources"] == ["tavily", "brave", "ror"] and y["preset"]["nom"] == "À partager"
    tav = next(d for d in y["declarations"] if d["id"] == "tavily")
    assert tav["cle"] == "TAVILY_API_KEY"  # le NOM de la clé, pas sa valeur
    assert all(d["defaut"] == {"chercher": False, "verifier": False} for d in y["declarations"])


def test_l_export_est_refuse_si_une_valeur_de_cle_s_y_glissait(cfg):
    cles.ecrire(cfg, "MA_CLE_API", "valeur-secrete-xyz789")
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/presets", json={"nom": "Piégé"})
        c.put("/api/presets/piege", json={"sources": ["ror"]})
        f = cfg.dossier_sources / "ror.yaml"
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        d["note"] = "ma clé est valeur-secrete-xyz789"  # une déclaration qui porterait une clé par erreur
        f.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
        r = c.get("/api/presets/piege/export")
    assert r.status_code == 422 and "valeur de clé" in r.json()["detail"]


# --- [ ] Réimporté ailleurs, il recrée le preset, avec les sources en attente de clé.
def test_l_import_recree_le_preset_sur_une_autre_installation(cfg, tmp_path_factory):
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/presets", json={"nom": "À partager"})
        c.put("/api/presets/a-partager", json={"sources": ["tavily", "ror"]})
        texte = c.get("/api/presets/a-partager/export").text
    autre = charger_cfg(copier_config(tmp_path_factory.mktemp("autre")))
    for nom in ("tavily", "ror"):
        (autre.dossier_sources / f"{nom}.yaml").unlink()  # l'autre installation ne connaît pas ces sources
    with TestClient(creer_app(autre)) as c:
        r = c.post("/api/presets/importer", json={"texte": texte})
        assert r.status_code == 201, r.text
        res = r.json()
        assert res["id"] == "a-partager" and set(res["ajoutees"]) == {"tavily", "ror"} and res["en_attente_de_cle"] == ["tavily"]
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "a-partager")
        assert [s["id"] for s in carte["sources"]] == ["ror", "tavily"] or {s["id"] for s in carte["sources"]} == {"tavily", "ror"}
        tav = next(s for s in carte["sources"] if s["id"] == "tavily")
        assert tav["cle_requise"] is True and tav["cle_presente"] is False and tav["allumee_par_defaut"] is False  # en attente de clé, éteinte
        assert c.post("/api/presets/importer", json={"texte": texte}).status_code == 422  # déjà là : jamais d'écrasement
        assert c.post("/api/presets/importer", json={"texte": "pas: un preset"}).status_code == 422
        assert c.post("/api/presets/importer", json={"texte": "::: pas du yaml ["}).status_code == 422


def test_l_import_ne_remplace_pas_une_source_existante_et_refuse_les_programmes(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        assert ajouter_programme(c, tmp_path).status_code == 201
        c.post("/api/presets", json={"nom": "Avec programme"})
        c.put("/api/presets/avec-programme", json={"sources": ["mon-programme-chorales", "ror"]})
        texte = c.get("/api/presets/avec-programme/export").text
        c.delete("/api/presets/avec-programme")
    autre = charger_cfg(copier_config(tmp_path / "autre"))
    avant = (autre.dossier_sources / "ror.yaml").read_text(encoding="utf-8")
    with TestClient(creer_app(autre)) as c:
        res = c.post("/api/presets/importer", json={"texte": texte}).json()
        assert res["existantes"] == ["ror"] and res["ajoutees"] == []
        assert res["ignorees"][0]["source"] == "mon-programme-chorales" and "jamais importé" in res["ignorees"][0]["raison"]
        assert not (autre.dossier_sources / "mon-programme-chorales.yaml").exists()
    assert (autre.dossier_sources / "ror.yaml").read_text(encoding="utf-8") == avant


# ===================== F17-4 / F17-5 (revue du 19/10, faites le 20/10) =====================


# --- [ ] F17-4a : le domaine d'une source « api »/« mcp » déclarée est dit dans Réglages — « » pour une source du catalogue.
def test_le_domaine_d_une_source_ajoutee_est_affiche(cfg):
    with TestClient(creer_app(cfg)) as c:
        lignes = {x["id"]: x for x in c.get("/api/reglages").json()["parties"]["recherche"]}
        assert lignes["tavily"]["domaine"] == ""  # source du catalogue : l'adresse est dans du code revu, pas dans la déclaration
        r = c.post("/api/ajout/source", json={"type": "api", "spec": {
            "nom": "Annuaire pièges", "url": "https://sous.domaine.exemple.example/chercher?x=1", "parametre_requete": "q",
            "liste": "items", "champs": {"nom": "t"}, "exemple": {"items": [{"t": "A"}]}}})
        assert r.status_code == 201, r.text
        lignes = {x["id"]: x for x in c.get("/api/reglages").json()["parties"]["recherche"]}
        assert lignes["annuaire-pieges"]["domaine"] == "sous.domaine.exemple.example"
        r2 = c.post("/api/ajout/source", json={"type": "mcp", "spec": {
            "nom": "Serveur pièges", "mcp": "https://mcp.exemple.example:9000/rpc", "outil": "search",
            "exemple": {"items": []}}})
        assert r2.status_code == 201, r2.text
        assert {x["id"]: x for x in c.get("/api/reglages").json()["parties"]["recherche"]}["serveur-pieges"]["domaine"] == "mcp.exemple.example"


# --- [ ] F17-4b : importer un preset qui réclame une clé DÉJÀ présente l'ajoute quand même (éteinte), mais le SIGNALE en gros ; jamais en silence.
def test_l_import_signale_une_source_qui_reclame_une_cle_deja_presente(cfg, tmp_path_factory):
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/presets", json={"nom": "Piégeur de clé"})
        c.put("/api/presets/piegeur-de-cle", json={"sources": ["tavily", "ror"]})
        texte = c.get("/api/presets/piegeur-de-cle/export").text
    autre = charger_cfg(copier_config(tmp_path_factory.mktemp("autre_cle")))
    (autre.dossier_sources / "tavily.yaml").unlink()  # l'autre installation ne connaît pas encore tavily
    cles.ecrire(autre, "TAVILY_API_KEY", "ma-vraie-cle-tavily-123456")  # mais A DÉJÀ une clé de ce nom
    with TestClient(creer_app(autre)) as c:
        res = c.post("/api/presets/importer", json={"texte": texte}).json()
        assert "tavily" in res["ajoutees"]  # ajoutée quand même, jamais un refus muet
        assert res["cles_deja_presentes"] == [{"source": "tavily", "cle": "TAVILY_API_KEY"}]  # mais signalé, nommément
        assert cles.valeur(autre, "TAVILY_API_KEY") == "ma-vraie-cle-tavily-123456"  # jamais touchée par l'import
        assert c.put("/api/reglages/source/tavily", json={"chercher": True}).status_code == 200  # reste activable : signalé, pas bloqué
    autre2 = charger_cfg(copier_config(tmp_path_factory.mktemp("autre_sans_cle")))
    (autre2.dossier_sources / "tavily.yaml").unlink()
    with TestClient(creer_app(autre2)) as c:
        res = c.post("/api/presets/importer", json={"texte": texte}).json()
        assert res["cles_deja_presentes"] == []  # pas de clé déjà là : rien à signaler


# --- [ ] F17-5 : l'exemple d'une source « fichier » ou « base » (lit un fichier DE LA MACHINE) n'est jamais embarqué dans un export.
def test_l_exemple_d_une_source_locale_n_est_jamais_exporte(cfg, tmp_path):
    f = tmp_path / "clubs.csv"
    f.write_text("club;ville\nChorale Imaginaire;Ville-Exemple\n", encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "fichier", "spec": {"nom": "Mes clubs", "chemin": str(f), "format": "csv",
                                                                           "delimiteur": ";", "champs": {"nom": "club", "ville": "ville"}}})
        assert r.status_code == 201, r.text
        c.post("/api/presets", json={"nom": "Avec local"})
        c.put("/api/presets/avec-local", json={"sources": ["mes-clubs", "ror"]})
        texte = c.get("/api/presets/avec-local/export").text
    y = yaml.safe_load(texte)
    assert "Chorale Imaginaire" not in texte and "Ville-Exemple" not in texte  # rien du contenu du fichier local
    mc = next(d for d in y["declarations"] if d["id"] == "mes-clubs")
    assert mc["exemple_reponse"] not in y["exemples"]  # son exemple n'est pas embarqué
    ror = next(d for d in y["declarations"] if d["id"] == "ror")
    assert ror["exemple_reponse"] in y["exemples"]  # une source normale, elle, garde le sien


def test_un_import_a_moitie_casse_n_ecrit_rien(cfg):
    y = {"format": "pilote-preset/1", "preset": {"nom": "Cassé", "sources": ["bonne", "mauvaise"]},
         "declarations": [{"id": "bonne", "nom": "Bonne"}, {"id": "mauvaise", "nom": "Mauvaise"}]}
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/presets/importer", json={"texte": yaml.safe_dump(y)})
    assert r.status_code == 422
    assert not (cfg.dossier_sources / "bonne.yaml").exists() and not (cfg.dossier_presets_perso / "casse.yaml").exists()


# --- [ ] Un programme local très simple s'ajoute, passe le test local, et ses noms apparaissent dans Tri.
def test_un_programme_local_s_ajoute_passe_son_test_et_ses_noms_arrivent_dans_tri(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        r = ajouter_programme(c, tmp_path)
        assert r.status_code == 201, r.text
        res = r.json()
        assert res["id"] == "mon-programme-chorales" and res["active"] is False and res["test"]["statut"] == "ok"
        assert [n["nom"] for n in res["test"]["noms_exemple"]] == ["Chorale des Quatre Vents", "Les Voix du Soir 🎶"]
        assert res["test"]["niveaux"]["4"] == "ok"
        c.post("/api/presets", json={"nom": "Mes chorales"})
        c.put("/api/presets/mes-chorales", json={"sources": ["mon-programme-chorales"]})
        for ligne in c.get("/api/reglages").json()["parties"]["recherche"]:
            c.put(f"/api/reglages/source/{ligne['id']}", json={"chercher": ligne["id"] == "mon-programme-chorales"})
        rid = c.post("/api/recherches", json={"sujet": {"quoi": "chorales", "pays": "France", "combien": 50}, "parametres": {"profondeur": "large"}}).json()["id"]
        r = attendre(c, rid)
        assert r["etat"] == "terminee", r["message"]
        noms = {x["nom"] for x in c.get(f"/api/recherches/{rid}/tri").json()["lignes"]}
    assert {"Chorale des Quatre Vents", "Les Voix du Soir 🎶"} <= noms


def test_un_programme_qui_tourne_en_boucle_est_arrete_et_reste_eteint(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        t0 = time.time()
        r = ajouter_programme(c, tmp_path, code=BOUCLE, nom="Boucle sans fin", delai_s=1, exemple=[{"nom": "X", "origine": "essai"}])
        assert time.time() - t0 < 20
        assert r.status_code == 201 and r.json()["test"]["statut"] == "echec" and "limite de temps" in r.json()["test"]["raison"]
        a = c.put("/api/reglages/source/boucle-sans-fin", json={"chercher": True})
        assert a.status_code == 422 and "ne peut pas être activée" in a.json()["detail"]


def test_un_programme_mal_decrit_est_refuse_en_francais(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        assert c.post("/api/programmes-locaux", json={"nom": "Sans commande", "commande": []}).status_code == 422
        assert ajouter_programme(c, tmp_path, nom="  ").status_code == 422
        assert ajouter_programme(c, tmp_path, exemple="pas du json").status_code == 422
        assert ajouter_programme(c, tmp_path, genres=["inconnu"]).status_code == 422
        assert not list(cfg.dossier_sources.glob("sans-commande*"))
        assert ajouter_programme(c, tmp_path).status_code == 201
        assert ajouter_programme(c, tmp_path).status_code == 422  # jamais par-dessus une source existante


def test_un_programme_qui_ne_respecte_pas_la_sortie_echoue_au_test(cfg, tmp_path):
    with TestClient(creer_app(cfg)) as c:
        r = ajouter_programme(c, tmp_path, code='print("bonjour")', nom="Sortie libre")
        assert r.status_code == 201 and r.json()["test"]["statut"] == "echec" and "JSON" in r.json()["test"]["raison"]


# --- [ ] Un identifiant de preset inconnu, même très long ou exotique, est refusé proprement (422) sans rien créer sur le disque.
#         (Régression du 20/10 : le verrou portait le nom reçu, créait un fichier par identifiant demandé et plantait sur un nom trop long.)
@pytest.mark.parametrize("ident", ["inexistant", "a" * 300, "é😀", "web"])
def test_un_identifiant_de_preset_inconnu_ne_cree_rien_et_ne_plante_pas(cfg, ident):
    avant = sorted(p.name for p in cfg.dossier_presets_perso.glob("*")) if cfg.dossier_presets_perso.exists() else []
    with TestClient(creer_app(cfg)) as c:
        assert c.put(f"/api/presets/{ident}", json={"sources": ["ror"]}).status_code == 422
        assert c.put(f"/api/presets/{ident}/infos", json={"nom": "z"}).status_code == 422
        assert c.delete(f"/api/presets/{ident}").status_code == 422
    apres = sorted(p.name for p in cfg.dossier_presets_perso.glob("*")) if cfg.dossier_presets_perso.exists() else []
    assert apres == avant
