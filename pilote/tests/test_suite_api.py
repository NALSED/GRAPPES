"""Suite pilote (spécification suite/pilote) : l'état, les règles et les six fonctions de l'Aide. Chaque test nomme la règle de la
spécification qu'il garde fermée."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pilote import cles, suite
from pilote.app import creer_app


@pytest.fixture
def c(cfg):
    with TestClient(creer_app(cfg)) as client:
        yield client


def etat(c):
    return c.get("/api/suite/etat").json()


def src(c, ident):
    return next(s for s in etat(c)["sources"] if s["id"] == ident)


def outil(c, ident):
    return next(o for o in etat(c)["outils"] if o["id"] == ident)


NOUVELLE = {
    "nom": "Ma source",
    "cat": "web",
    "role": "CHERCHER",
    "cout": "gratuit",
    "origine": "seconde main",
    "pays": "FR",
    "langue": "fr",
    "url": "https://exemple.invalid/recherche",
    "parametre_requete": "q",
    "champ_nom": "titre",
    "liste": "resultats",
    "exemple": '{"resultats": [{"titre": "Club Alpin"}]}',
}


# --- l'état de départ est celui de la maquette : 8 catégories, 48 sources, 10 outils dont l'Assistant IA éteint
def test_etat_de_depart(c, cfg):
    e = etat(c)
    assert [x["nom"] for x in e["categories"]][:3] == ["Web", "Organisations officielles", "Associations"]
    from pilote.sources import charger_sources

    reelles = set(charger_sources(cfg)[0])
    assert {s["id"] for s in e["sources"]} == reelles and len(
        reelles
    ) >= 40  # la liste de la suite EST celle des déclarations de pilote
    assert (
        len(e["outils"]) == 10 and outil(c, "ia")["etat"] == "off"
    )  # l'Assistant IA est éteint à la livraison (spécification 10)
    assert all(s["langue"] for s in e["sources"])  # le champ Langue existe sur toute source (spécification 05)
    assert e["recherches"] == [] and e["plan"]["nodes"] == []  # aucune recherche inventée
    assert (
        src(c, "tavily")["cout"] == "payant"
        and src(c, "tavily")["cle_requise"] is True
        and src(c, "searxng")["cout"] == "gratuit"
    )
    assert src(c, "charity-commission")["pays"] == "UK"  # GB dans la déclaration, UK à l'écran


# --- règle « une source nouvelle démarre à vérifier » (05) : jamais opérationnelle sans test réussi
def test_une_source_ajoutee_ecrit_sa_declaration_et_demarre_a_verifier(c, cfg):
    # exemple de réponse qui ne contient pas le champ du nom : le test local échoue, la source reste « à vérifier »
    r = c.post("/api/suite/sources", json={**NOUVELLE, "exemple": '{"resultats": [{"autre": 1}]}'})
    assert r.status_code == 201, r.json()
    ident = r.json()["id"]
    assert (cfg.dossier_sources / f"{ident}.yaml").exists()  # la même déclaration que l'ancienne page Ajout
    s = src(c, ident)
    assert (
        s["etat"] == "warn" and s["langue"] == "fr" and s["declaree"] is True and s["chercher"] is False and s["tests"]
    )
    assert (
        c.post(f"/api/suite/sources/{ident}/allumer").status_code == 422
    )  # un test échoué interdit d'allumer, comme dans l'ancienne page
    # un exemple conforme : le test passe, la source est enregistrée ÉTEINTE (comme dans l'ancienne page) et ne s'allume que sur demande
    ok = c.post("/api/suite/sources", json={**NOUVELLE, "nom": "Autre source"}).json()["id"]
    assert src(c, ok)["test_reussi"] is True and src(c, ok)["etat"] == "off"
    assert c.post(f"/api/suite/sources/{ok}/allumer").status_code == 200 and src(c, ok)["etat"] == "ok"


def test_champs_de_source_refuses_avec_la_raison(c):
    avant = len(etat(c)["sources"])
    for mauvais, mot in (
        ({"cat": "x"}, "catégorie"),
        ({"role": "LIEN"}, "rôle"),
        ({"url": ""}, "adresse"),
        ({"champ_nom": ""}, "NOM"),
        ({"parametre_requete": ""}, "reçoit"),
        ({"cout": "payant"}, "prix"),
        ({"langue": "français"}, "code"),
        ({"nom": ""}, "nom"),
    ):
        r = c.post("/api/suite/sources", json={**NOUVELLE, **mauvais})
        assert r.status_code == 422 and mot in r.json()["detail"], (mauvais, r.json())
    assert len(etat(c)["sources"]) == avant  # rien n'a été écrit
    assert c.post("/api/suite/sources", json=NOUVELLE).status_code == 201
    assert c.post("/api/suite/sources", json=NOUVELLE).status_code == 422  # même nom : refusé


def test_une_source_declaree_ne_change_que_par_la_surcouche(c, cfg):
    fichier = cfg.dossier_sources / "tavily.yaml"
    avant = fichier.read_bytes()
    c.put(
        "/api/suite/sources/tavily",
        json={"langue": "de", "role": "ENRICHIR", "nom": "Autre nom", "cout": "gratuit", "pays": "XX"},
    )
    s = src(c, "tavily")
    assert s["langue"] == "de" and s["role"] == "ENRICHIR"  # ce que la suite ajoute
    assert (
        s["nom"] == "Tavily" and s["cout"] == "payant" and s["pays"] == "Mondial"
    )  # ce que la déclaration dit n'est pas modifiable d'ici
    assert fichier.read_bytes() == avant  # la déclaration n'est jamais touchée par l'usage
    assert c.put("/api/suite/sources/tavily", json={"langue": "français"}).status_code == 422
    assert c.put("/api/suite/sources/inconnue", json={"langue": "fr"}).status_code == 422


# --- allumer et éteindre passent par les cases de Réglages (même fonction que l'ancienne page), avec ses refus et ses avertissements
def test_allumer_et_eteindre_ecrivent_dans_reglages(c, cfg):
    import yaml

    c.post("/api/suite/sources/searxng/eteindre")
    reg = yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8"))
    assert reg["sources"]["searxng"]["chercher"] is False and src(c, "searxng")["etat"] == "off"
    assert c.post("/api/suite/sources/searxng/allumer").status_code == 200
    assert yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8"))["sources"]["searxng"]["chercher"] is True
    assert (
        src(c, "searxng")["etat"] == "warn"
    )  # allumée mais jamais testée : « à vérifier », jamais « opérationnelle » sans test


def test_un_avertissement_de_source_se_lit_avant_d_allumer(c):
    r = c.post("/api/suite/sources/apify-facebook/allumer", json={})
    assert (
        r.status_code == 409
        and r.json()["detail"]["avertissements"][0]["texte"]
        and src(c, "apify-facebook")["etat"] == "off"
    )
    assert c.post("/api/suite/sources/apify-facebook/allumer", json={"confirme": True}).status_code == 200
    assert src(c, "apify-facebook")["chercher"] is True
    assert c.post("/api/suite/sources/apify-facebook/eteindre").status_code == 200  # éteindre ne redemande rien


def test_le_test_local_d_une_source_est_celui_de_l_ancienne_page(c, cfg):
    from pilote.etat_sources import lire

    t = c.post("/api/suite/sources/registre-associations/test").json()
    assert (
        t["ok"] is True and lire(cfg)["registre-associations"]["statut"] == "ok"
    )  # écrit dans le même état que l'ancienne page
    assert (
        src(c, "registre-associations")["etat"] == "ok"
        and "test local réussi" in src(c, "registre-associations")["tests"][0]
    )
    c.post("/api/suite/sources/registre-associations/eteindre")
    assert src(c, "registre-associations")["etat"] == "off"


# --- règle 4 : RETIRER est réversible et ne touche à rien d'autre ; la source revient telle quelle
def test_retirer_est_reversible_et_ne_change_rien_d_autre(c, cfg):
    avant = src(c, "tavily")
    reglages_avant = cfg.fichier_reglages.read_bytes() if cfg.fichier_reglages.exists() else b""
    assert c.post("/api/suite/sources/tavily/retirer").json() == {"retiree": True}
    retiree = src(c, "tavily")
    assert retiree["retiree"] is True and {k: v for k, v in retiree.items() if k != "retiree"} == {
        k: v for k, v in avant.items() if k != "retiree"
    }
    assert "tavily" not in [s["id"] for s in suite.lister_sources(suite.charger(c.app.state.cfg))]
    assert (
        cfg.fichier_reglages.read_bytes() if cfg.fichier_reglages.exists() else b""
    ) == reglages_avant  # ni Réglages ni les cases ne bougent
    c.post("/api/suite/sources/tavily/rajouter")
    assert src(c, "tavily") == avant


# --- règle 4 : SUPPRIMER est définitif et le serveur exige la confirmation, quoi qu'ait fait la page
def test_supprimer_une_recherche_exige_la_confirmation(c):
    rid = c.post(
        "/api/suite/recherches",
        json={
            "titre": "Test",
            "mode": "Simple",
            "cats": ["assos"],
            "simple": {"preset": "assos", "pays": "FR", "saisie": "club"},
        },
    ).json()["id"]
    r = c.delete(f"/api/suite/recherches/{rid}")
    assert r.status_code == 409 and len(etat(c)["recherches"]) == 1
    assert c.delete(f"/api/suite/recherches/{rid}?confirme=true").status_code == 200
    assert etat(c)["recherches"] == []
    assert c.delete(f"/api/suite/recherches/{rid}?confirme=true").status_code == 404
    assert c.post("/api/suite/recherches", json={"titre": "x", "mode": "Autre"}).status_code == 422


# --- 12 : une recherche avancée garde ses tuiles à leurs coordonnées et TOUS ses liens
def test_recherche_avancee_garde_son_plan(c):
    plan = {
        "nodes": [
            {"id": "saisie", "nom": "Ta saisie", "role": "ENTREE", "x": 40, "y": 50},
            {"id": "a", "nom": "DILA — JOAFE", "role": "CHERCHER", "x": 210, "y": 130, "ref": "dila-joafe"},
            {"id": "grappes", "nom": "Grappes", "role": "GRAPPES", "x": 380, "y": 90},
        ],
        "edges": [{"from": "saisie", "to": "a"}, {"from": "a", "to": "grappes"}],
    }
    rid = c.post(
        "/api/suite/recherches", json={"titre": "Plan", "mode": "Avancée", "cats": ["assos"], "plan": plan}
    ).json()["id"]
    rch = next(r for r in etat(c)["recherches"] if r["id"] == rid)
    assert [(n["id"], n["x"], n["y"]) for n in rch["plan"]["nodes"]] == [
        ("saisie", 40, 50),
        ("a", 210, 130),
        ("grappes", 380, 90),
    ]
    assert [e["id"] for e in rch["plan"]["edges"]] == ["saisie>a", "a>grappes"]


def test_plan_refuse_les_liens_impossibles(c):
    base = [
        {"id": "saisie", "role": "ENTREE", "nom": "s", "x": 0, "y": 0},
        {"id": "g", "role": "GRAPPES", "nom": "g", "x": 9, "y": 9},
        {"id": "a", "role": "CHERCHER", "nom": "a", "x": 5, "y": 5},
    ]
    for liens in (
        [{"from": "a", "to": "saisie"}],
        [{"from": "g", "to": "a"}],
        [{"from": "a", "to": "a"}],
        [{"from": "a", "to": "fantome"}],
    ):
        assert c.put("/api/suite/plan", json={"nodes": base, "edges": liens}).status_code == 422, liens
    assert (
        c.put("/api/suite/plan", json={"nodes": base + [dict(base[2])], "edges": []}).status_code == 422
    )  # tuile posée deux fois
    ok = c.put("/api/suite/plan", json={"nodes": base, "edges": [{"from": "a", "to": "g"}, {"from": "a", "to": "g"}]})
    assert ok.status_code == 200 and len(etat(c)["plan"]["edges"]) == 1  # un lien en double n'existe pas
    assert not any(
        n["removable"] for n in etat(c)["plan"]["nodes"] if n["role"] in ("ENTREE", "GRAPPES")
    )  # Ta saisie et Grappes ne se retirent pas


# --- 10 : l'Assistant IA ne s'allume pas sans avoir lu l'avertissement ; l'éteindre ne redemande rien
def test_assistant_ia_demande_l_avertissement(c):
    r = c.post("/api/suite/outils/ia/allumer", json={})
    assert r.status_code == 422 and "avertissement" in r.json()["detail"] and outil(c, "ia")["etat"] == "off"
    assert c.post("/api/suite/outils/ia/allumer", json={"avertissement_lu": True}).status_code == 200
    assert outil(c, "ia")["etat"] == "ok"
    assert c.post("/api/suite/outils/ia/eteindre").status_code == 200 and outil(c, "ia")["etat"] == "off"
    assert (
        c.post("/api/suite/outils/budget/allumer", json={}).status_code == 200
    )  # les autres outils n'ont pas d'avertissement


# --- 06 : un outil créé démarre à vérifier ; un script est testé pour de vrai, sans réseau ; changer le script demande un nouveau test
def test_outil_script_teste_pour_de_vrai(c):
    code = 'def run(resultats):\n    return [r for r in resultats if r.get("pays") == "FR"]'
    r = c.post(
        "/api/suite/outils",
        json={
            "nom": "Garder la France",
            "nature": "script",
            "code": code,
            "test_entree": '[{"pays":"FR"},{"pays":"UK"}]',
            "test_sortie": '[{"pays":"FR"}]',
        },
    )
    assert r.status_code == 201
    ident = r.json()["id"]
    assert outil(c, ident)["etat"] == "warn"
    t = c.post(f"/api/suite/outils/{ident}/test").json()
    assert (
        t["ok"] is True
        and t["execute"] is True
        and json.loads(t["sortie"]) == [{"pays": "FR"}]
        and outil(c, ident)["etat"] == "ok"
    )
    c.put(f"/api/suite/outils/{ident}", json={"code": code.replace('"FR"', '"UK"')})
    assert outil(c, ident)["etat"] == "warn"  # on a changé ce qui avait été testé
    assert c.post(f"/api/suite/outils/{ident}/test").json()["ok"] is False  # la sortie n'est plus celle attendue
    assert (
        c.post("/api/suite/outils", json={"nom": "Cassé", "nature": "script", "code": "x = 1"}).status_code == 422
    )  # pas de run()
    assert (
        c.post(
            "/api/suite/outils",
            json={"nom": "Autre signature", "nature": "script", "code": "def run(x):\n    return x"},
        ).status_code
        == 422
    )  # signature imposée


def test_script_sans_reseau_et_borne_en_temps(c):
    mauvais = 'import socket\ndef run(resultats):\n    socket.create_connection(("93.184.216.34", 80), 2)\n    return resultats'
    ident = c.post(
        "/api/suite/outils",
        json={"nom": "Réseau", "nature": "script", "code": mauvais, "test_entree": "[]", "test_sortie": "[]"},
    ).json()["id"]
    t = c.post(f"/api/suite/outils/{ident}/test").json()
    assert t["ok"] is False and outil(c, ident)["etat"] == "warn"
    boucle = c.post(
        "/api/suite/outils",
        json={
            "nom": "Boucle sans fin",
            "nature": "script",
            "code": "def run(resultats):\n    while True:\n        pass",
            "test_entree": "[]",
        },
    ).json()["id"]
    assert c.post(f"/api/suite/outils/{boucle}/test").json()["ok"] is False


# --- 05 : une clé d'API ne ressort JAMAIS de l'API, seulement « enregistrée »
def test_la_cle_ne_sort_jamais(c, cfg):
    secret = "sk-ultra-secret-12345"
    c.post("/api/suite/sources/exa/retirer")  # une écriture, pour que le fichier d'état existe
    assert c.put("/api/suite/sources/tavily/cle", json={"valeur": secret}).json() == {"cle": True}
    assert src(c, "tavily")["cle"] is True and src(c, "linkup")["cle"] is False
    assert secret not in c.get("/api/suite/etat").text
    assert secret not in (cfg.donnees / "suite" / "etat.json").read_text(encoding="utf-8")
    assert secret not in cfg.journal_actions.read_text(encoding="utf-8")
    assert (
        cles.valeur(cfg, "TAVILY_API_KEY") == secret
    )  # sous le nom de variable de la déclaration : celui que le moteur lit
    assert c.put("/api/suite/sources/tavily/cle", json={"valeur": "a\nb"}).status_code == 422
    assert c.put("/api/suite/sources/inconnue/cle", json={"valeur": "x"}).status_code == 422
    assert (
        c.put("/api/suite/sources/searxng/cle", json={"valeur": "x"}).status_code == 422
    )  # une source sans clé n'en reçoit pas


# --- un fichier d'état abîmé ne bloque pas la page (même tolérance que Réglages)
def test_etat_abime_est_mis_de_cote(c, cfg):
    c.post("/api/suite/sources/tavily/retirer")
    f = cfg.donnees / "suite" / "etat.json"
    f.write_text("{pas du json", encoding="utf-8")
    assert src(c, "tavily")["retiree"] is False and f.with_name("etat.json.abime").exists()


# --- 11 : les six fonctions de l'Aide
def poser(c, nodes, edges, cats=()):
    ok = c.put("/api/suite/plan", json={"nodes": nodes, "edges": edges, "cats": list(cats)})
    assert ok.status_code == 200, ok.json()


def tuile(i, nom, role, ref=None, x=0, y=0):
    return {"id": i, "nom": nom, "role": role, "ref": ref, "x": x, "y": y}


def regles(c, **corps):
    return [
        (k["regle"], k["niveau"], k["nom"])
        for k in c.post("/api/suite/aide/verifier_plan", json=corps).json()["constats"]
    ]


def nom(c, ident):
    return src(c, ident)["nom"]


def test_verifier_plan_les_huit_controles(c):
    s, g = tuile("saisie", "Ta saisie", "ENTREE"), tuile("grappes", "Grappes", "GRAPPES")
    reg, ent = src(c, "registre-associations"), src(c, "recherche-entreprises")
    # 1 et 2 : une tuile isolée n'est jamais interrogée et son résultat se perd
    poser(c, [s, g, tuile("r", reg["nom"], "CHERCHER", reg["id"])], [{"from": "saisie", "to": "grappes"}])
    assert regles(c) == [(1, "bloquant", reg["nom"]), (2, "bloquant", reg["nom"])]
    # 3 : source posée mais éteinte dans Réglages (Bluesky est éteint à la livraison)
    bs = src(c, "bluesky")
    poser(
        c,
        [s, g, tuile("b", bs["nom"], "CHERCHER", "bluesky")],
        [{"from": "saisie", "to": "b"}, {"from": "b", "to": "grappes"}],
    )
    assert (3, "bloquant", bs["nom"]) in regles(c)
    # 4 : deux sources du même rôle sans RAPPROCHER derrière ; avec Fusion derrière, plus de remarque
    deux = [s, g, tuile("a", reg["nom"], "CHERCHER", reg["id"]), tuile("b", ent["nom"], "CHERCHER", ent["id"])]
    liens = [
        {"from": "saisie", "to": "a"},
        {"from": "saisie", "to": "b"},
        {"from": "a", "to": "grappes"},
        {"from": "b", "to": "grappes"},
    ]
    poser(c, deux, liens)
    assert [r for r in regles(c, langue="fr") if r[0] == 4] == [
        (4, "remarque", reg["nom"]),
        (4, "remarque", ent["nom"]),
    ]
    f = tuile("f", "Fusion / doublons", "RAPPROCHER", "fusion")
    poser(
        c,
        [*deux, f],
        [
            {"from": "saisie", "to": "a"},
            {"from": "saisie", "to": "b"},
            {"from": "a", "to": "f"},
            {"from": "b", "to": "f"},
            {"from": "f", "to": "grappes"},
        ],
    )
    assert regles(c, langue="fr") == []  # un plan juste ne donne aucun constat


def test_verifier_plan_quota_langue_ia_et_determinisme(c, cfg):
    from pilote.etat_sources import noter

    s, g = tuile("saisie", "Ta saisie", "ENTREE"), tuile("grappes", "Grappes", "GRAPPES")
    # 5 : le quota que le fournisseur a rendu (Tavily : 190 restants sur 1000 = 81 %) est LU dans l'état de la source, jamais inventé
    assert src(c, "tavily")["quota"] == {
        "utilise": 0,
        "plafond": 1000,
        "unite": "mois",
    }  # le quota gratuit déclaré, 0 consommé
    noter(cfg, "tavily", quota={"restant": 190, "total": 1000, "le": "2026-10-26T10:00:00+00:00"})
    assert (
        src(c, "tavily")["quota"] == {"utilise": 810, "plafond": 1000, "unite": "mois"}
        and src(c, "tavily")["pct"] == 81
    )
    poser(
        c,
        [s, g, tuile("t", nom(c, "tavily"), "CHERCHER", "tavily")],
        [{"from": "saisie", "to": "t"}, {"from": "t", "to": "grappes"}],
    )
    assert regles(c, langue="en") == [(5, "remarque", nom(c, "tavily"))]
    # 6 : le registre des associations cherche en français ; saisie anglaise => remarque, sauf si une Traduction est en amont
    reg = src(c, "registre-associations")
    base = [s, g, tuile("d", reg["nom"], "CHERCHER", reg["id"])]
    poser(c, base, [{"from": "saisie", "to": "d"}, {"from": "d", "to": "grappes"}])
    assert regles(c, langue="en") == [(6, "remarque", reg["nom"])] and regles(c, langue="fr") == []
    assert regles(c) == []  # langue inconnue : le contrôle ne dit rien plutôt que de deviner
    t = tuile("t", "Traduction", "OUTIL", "traduction")
    poser(c, [*base, t], [{"from": "saisie", "to": "t"}, {"from": "t", "to": "d"}, {"from": "d", "to": "grappes"}])
    assert regles(c, langue="en") == []
    # 8 : l'Assistant IA posé laisse un rappel ; éteint, il est aussi bloquant (3)
    ia = tuile("i", "Assistant IA", "OUTIL", "ia")
    poser(c, [*base, ia], [{"from": "saisie", "to": "d"}, {"from": "d", "to": "i"}, {"from": "i", "to": "grappes"}])
    assert regles(c) == [(3, "bloquant", "Assistant IA"), (8, "remarque", "Assistant IA")]
    assert regles(c) == regles(c)  # les mêmes tuiles donnent toujours les mêmes constats
    # la langue d'une saisie vient d'une bibliothèque de détection
    assert c.post("/api/suite/langue", json={"texte": "je cherche une association à Grenoble"}).json() == {
        "langue": "fr"
    }
    assert c.post("/api/suite/langue", json={"texte": "looking for a charity in London please"}).json() == {
        "langue": "en"
    }
    assert c.post("/api/suite/langue", json={"texte": "ok"}).json() == {"langue": None}


def test_verifier_plan_lien_inadmissible_deja_en_base(cfg):
    e = suite.charger(cfg)
    e["plan"] = {
        "nodes": [tuile("saisie", "Ta saisie", "ENTREE"), tuile("a", "A", "CHERCHER")],
        "edges": [{"id": "a>saisie", "from": "a", "to": "saisie"}],
        "cats": [],
        "saisies": {},
    }
    assert (7, "bloquant", "Ta saisie") in [(k["regle"], k["niveau"], k["nom"]) for k in suite.verifier_plan(e)]


def test_proposer_plan_ne_pose_rien_et_n_invente_aucun_nom(c):
    e = etat(c)
    noms_connus = {s["nom"] for s in e["sources"]} | {o["nom"] for o in e["outils"]} | {"Ta saisie", "Grappes"}
    for objectif in ("assos", "entreprises", "lieux", "presse", "web"):
        p = c.post("/api/suite/aide/proposer_plan", json={"objectif": objectif, "pays": "FR"}).json()
        assert {t["nom"] for t in p["tuiles"]} <= noms_connus  # chaque nom vient d'une déclaration réelle
        assert p["tuiles"][0]["role"] == "ENTREE" and p["tuiles"][-1]["role"] == "GRAPPES"
        ids = {n["id"] for n in p["nodes"]}
        assert all(ed["from"] in ids and ed["to"] in ids for ed in p["edges"])
    assert etat(c)["plan"]["nodes"] == []  # proposer ne pose jamais
    noms = [
        t["nom"]
        for t in c.post("/api/suite/aide/proposer_plan", json={"objectif": "assos", "pays": "FR"}).json()["tuiles"]
    ]
    assert nom(c, "registre-associations") in noms  # allumée, française
    assert (
        nom(c, "charity-commission") not in noms and nom(c, "bnf_organisations") not in noms
    )  # éteintes à la livraison, ou pays UK
    c.post("/api/suite/sources/registre-associations/eteindre")
    noms = [
        t["nom"]
        for t in c.post("/api/suite/aide/proposer_plan", json={"objectif": "assos", "pays": "FR"}).json()["tuiles"]
    ]
    assert nom(c, "registre-associations") not in noms  # une source éteinte n'est pas proposée
    assert c.post("/api/suite/aide/proposer_plan", json={"objectif": "nimporte"}).status_code == 422
    # vérifier est exclu par défaut, comme la case décochée des préréglages
    p = c.post("/api/suite/aide/proposer_plan", json={"objectif": "entreprises"}).json()
    assert nom(c, "opensanctions") not in [t["nom"] for t in p["tuiles"]]


def test_lister_sources_definir_ouvrir(c):
    ls = c.post("/api/suite/aide/lister_sources", json={"role": "VERIFIER", "etat": "off"}).json()["sources"]
    assert {s["id"] for s in ls} == {"bodacc", "courtlistener", "opensanctions", "wayback"}
    c.post("/api/suite/sources/wayback/retirer")
    assert {
        s["id"]
        for s in c.post("/api/suite/aide/lister_sources", json={"role": "VERIFIER", "etat": "off"}).json()["sources"]
    } == {"bodacc", "courtlistener", "opensanctions"}
    d = c.post("/api/suite/aide/definir", json={"mot": "Retirer"}).json()
    assert d["mot"] == "Retirer" and "sans rien effacer" in d["definition"] and "réversible" in d["definition"]
    assert "RAPPROCHER" in c.post("/api/suite/aide/definir", json={"mot": "rapprocher"}).json()["mot"]
    assert c.post("/api/suite/aide/definir", json={"mot": "à vérifier"}).json()["mot"] == "à vérifier"
    assert c.post("/api/suite/aide/definir", json={"mot": "cluster"}).status_code == 422  # pas dans la liste close
    assert "grappe" in c.get("/api/suite/aide/mots").json()["mots"]
    assert c.post("/api/suite/aide/ouvrir", json={"ecran": "reglages/outils"}).json() == {"ecran": "reglages/outils"}
    for inactif in ("tri", "tableau-de-bord", "nimporte"):
        assert c.post("/api/suite/aide/ouvrir", json={"ecran": inactif}).status_code == 422
    assert c.post("/api/suite/aide/lire_plan").json() == {"tuiles": [], "liens": []}


# --- 11 : sans modèle, la phrase libre ne fait rien et le reste marche
def test_sans_modele_la_phrase_libre_est_desactivee(c):
    assert etat(c)["modele"] is False
    assert c.post("/api/suite/aide/phrase", json={"phrase": "comment je cherche une asso ?"}).json() == {
        "modele": False
    }
    assert c.post("/api/suite/aide/verifier_plan").status_code == 200  # les puces marchent sans modèle


def test_avec_modele_il_choisit_la_fonction_mais_n_ecrit_rien(c, monkeypatch):
    monkeypatch.setattr(c.app.state.cfg.__class__, "suite_modele_url", "http://modele.test", raising=False)
    from pilote import suite_modele

    monkeypatch.setattr(suite_modele, "disponible", lambda url: True)
    monkeypatch.setattr(
        suite_modele, "choisir_fonction", lambda url, phrase: {"fonction": "definir", "args": {"mot": "Retirer"}}
    )
    r = c.post("/api/suite/aide/phrase", json={"phrase": "retirer ça veut dire quoi ?"}).json()
    assert (
        r["fonction"] == "definir" and "sans rien effacer" in r["resultat"]["definition"]
    )  # le texte vient de la liste close, pas du modèle
    monkeypatch.setattr(
        suite_modele, "choisir_fonction", lambda url, phrase: {"fonction": "ouvrir", "args": {"ecran": "tri"}}
    )
    assert "pas encore conçu" in c.post("/api/suite/aide/phrase", json={"phrase": "ouvre le tri"}).json()["refus"]


def test_le_modele_ne_peut_choisir_qu_une_des_six_fonctions(monkeypatch):
    from pilote import suite_modele

    monkeypatch.setattr(
        suite_modele,
        "_appel",
        lambda url, corps=None, delai=0: (
            {"models": [{"name": "m"}]}
            if corps is None
            else {"message": {"content": '{"fonction": "poser_tuile", "args": {}}'}}
        ),
    )
    assert suite_modele.choisir_fonction("http://x", "pose une tuile") is None
    monkeypatch.setattr(
        suite_modele,
        "_appel",
        lambda url, corps=None, delai=0: (
            {"models": [{"name": "m"}]} if corps is None else {"message": {"content": "pas du json"}}
        ),
    )
    assert suite_modele.choisir_fonction("http://x", "n'importe quoi") is None


# --- le lancement part sur le moteur actuel et reste honnête sur ce qu'il fait
def test_lancer_une_recherche_sur_les_sources_choisies(cfg):
    class Faux:
        def lancer(self, rid):
            self.rid = rid

    app = creer_app(cfg)
    faux = Faux()
    with TestClient(app) as c:
        app.state.gestionnaire.lancer = faux.lancer  # aucun appel réseau, aucun crédit
        assert c.post("/api/suite/lancer", json={"saisie": "", "sources": ["searxng"]}).status_code == 422
        assert c.post("/api/suite/lancer", json={"saisie": "club de judo", "sources": []}).status_code == 422
        assert c.post("/api/suite/lancer", json={"saisie": "club de judo", "sources": ["inconnue"]}).status_code == 422
        # Tavily : clé absente, éteinte… ; Bluesky : éteinte ; OpenSanctions : ne fait que vérifier ; searxng et registre des associations : partent
        choix = ["searxng", "registre-associations", "tavily", "bluesky", "opensanctions"]
        r = c.post(
            "/api/suite/lancer",
            json={
                "saisie": "club de judo",
                "sources": choix,
                "cats": ["assos"],
                "pays": "FR",
                "mode": "Simple",
                "simple": {"preset": "assos", "pays": "FR", "saisie": "club de judo"},
            },
        )
        assert r.status_code == 202, r.json()
        corps = r.json()
        assert faux.rid == corps["recherche_id"]
        assert {x["id"]: x["raison"] for x in corps["ecartees"]} == {
            "tavily": "sa clé d'API est absente",
            "bluesky": "elle est éteinte dans Réglages",
            "opensanctions": "elle est éteinte dans Réglages",
        }
        assert len(corps["lancees"]) == 2
        rch = c.get(f"/api/recherches/{faux.rid}").json()
        assert rch["sujet"] == {"quoi": "club de judo", "pays": "France"} and rch["parametres"]["sources"] == [
            "searxng",
            "registre-associations",
        ]
        assert etat(c)["recherches"][0]["resultat"] == "en cours"
        r2 = c.post("/api/suite/lancer", json={"saisie": "x", "sources": ["bluesky", "opensanctions"]})
        assert r2.status_code == 422 and "Aucune des sources choisies" in r2.json()["detail"]


# --- 05 : la fiabilité A–F remplace « première / seconde main » ; défaut B (officiel), C (encyclopédie), D (web, presse), ajustable
def test_fiabilite_de_la_source_par_defaut_et_choisie(c):
    assert (src(c, "companies-house")["fiabilite"], src(c, "wikipedia")["fiabilite"], src(c, "tavily")["fiabilite"]) == ("B", "C", "D")
    assert src(c, "tavily")["fiabilite_choisie"] is False
    assert "origine" not in src(c, "tavily")  # l'ancien champ n'existe plus
    assert c.put("/api/suite/sources/tavily", json={"fiabilite": "A"}).status_code == 200
    assert src(c, "tavily")["fiabilite"] == "A" and src(c, "tavily")["fiabilite_choisie"] is True
    assert c.put("/api/suite/sources/tavily", json={"fiabilite": "G"}).status_code == 422
    assert src(c, "tavily")["fiabilite"] == "A"  # un refus ne change rien


# --- règle non négociable n° 8 : grappes vise les personnes morales, jamais une recherche par nom de personne physique
def test_regle_8_aucune_recherche_de_personne_physique(c, cfg):
    from pilote.sources import charger_sources

    assert "personne" not in cfg.genres
    assert not [d.id for d in charger_sources(cfg)[0].values() if "personne" in d.genres]
    textes = json.dumps(c.get("/api/suite/aide/objectifs").json(), ensure_ascii=False).lower()
    assert "dirigeant" not in textes and "personne" not in textes
    from pathlib import Path

    for f in (Path(__file__).resolve().parents[1] / "static" / "suite" / "js").glob("*.js"):
        assert "dirigeant" not in f.read_text(encoding="utf-8").lower(), f.name  # ni libellé ni aide ne propose de chercher un dirigeant
