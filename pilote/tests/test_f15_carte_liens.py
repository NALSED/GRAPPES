"""Fiche 15, chapitre 4 — Vue « carte de liens » : jamais tout d'un coup, taille = endroits, couleur = origine, un style par type de lien."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_f13_tri import terminer_assistant

from pilote.app import creer_app
from pilote.base import Candidat, Recherche, creer_fabrique


def peupler_liens(cfg, n_isoles=0, rid="r15"):
    fab = creer_fabrique(cfg.url_base)
    with fab.begin() as s:
        s.add(Recherche(id=rid, qui="t", sujet={"quoi": "clubs"}, parametres={}, etat="terminee"))
        s.flush()
        a = Candidat(recherche_id=rid, nom="Alpha Sport SAS", genre_source="registre", nb_endroits=3, trouve_par=["recherche-entreprises"], faits={},
                     relations=[{"type": "maison_mere", "vers": "Holding Zeta", "source": "gleif"}, {"type": "a_pour_etablissement", "vers": "Alpha Sport Lyon", "source": "recherche-entreprises"}])
        b = Candidat(recherche_id=rid, nom="Alpha Sport Lyon", genre_source="web", nb_endroits=1, trouve_par=["searxng"], faits={"adresse": "1 rue du Port, Lyon"},
                     relations=[{"type": "etablissement_de", "vers": "Alpha Sport SAS", "source": "recherche-entreprises"}])
        c = Candidat(recherche_id=rid, nom="Club Beta", genre_source="presse", nb_endroits=2, trouve_par=["rss"], faits={"adresse": "1 rue du port lyon"}, relations=[{"type": "trouve_via", "vers": "Alpha Sport Lyon"}])
        s.add_all([a, b, c])
        for i in range(n_isoles):
            s.add(Candidat(recherche_id=rid, nom=f"Isolé {i:03d}", genre_source="web", faits={}, relations=[{"type": "maison_mere", "vers": "Holding Zeta"}] if i else []))
    return fab


def ids(cfg, rid="r15"):
    fab = creer_fabrique(cfg.url_base)
    with fab() as s:
        return {c.nom: c.id for c in s.query(Candidat).filter_by(recherche_id=rid)}


def test_sans_nom_garde_la_carte_ne_montre_rien_au_lieu_de_tout(cfg):
    peupler_liens(cfg, n_isoles=200)
    with TestClient(creer_app(cfg)) as c:
        r = c.get("/api/recherches/r15/carte").json()
    assert r["noeuds"] == [] and "gardés" in r["message"] and r["mode"] == "gardes"


def test_les_noms_gardes_sont_montres_avec_leurs_liens_entre_eux(cfg):
    peupler_liens(cfg)
    i = ids(cfg)
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/recherches/r15/decisions", json={"valeur": "garder", "ids": [i["Alpha Sport SAS"], i["Alpha Sport Lyon"]]})
        r = c.get("/api/recherches/r15/carte").json()
    assert {n["nom"] for n in r["noeuds"]} == {"Alpha Sport SAS", "Alpha Sport Lyon"}  # les non gardés et le « hors résultats » ne sont pas dessinés
    assert [(a["famille"]) for a in r["aretes"]] == ["siege"]  # le lien est donné par les DEUX noms : un seul trait
    alpha = next(n for n in r["noeuds"] if n["nom"] == "Alpha Sport SAS")
    assert alpha["e"] == 3 and alpha["o"] == "registre" and alpha["d"] == "garder"  # taille = endroits, couleur = origine


def test_le_voisinage_d_un_nom_montre_ses_voisins_et_les_points_hors_resultats(cfg):
    peupler_liens(cfg)
    i = ids(cfg)
    with TestClient(creer_app(cfg)) as c:
        r = c.get("/api/recherches/r15/carte", params={"centre": i["Alpha Sport SAS"]}).json()
        lyon = c.get("/api/recherches/r15/carte", params={"centre": i["Alpha Sport Lyon"]}).json()
    noms = {n["nom"]: n for n in r["noeuds"]}
    assert set(noms) == {"Alpha Sport SAS", "Alpha Sport Lyon", "Holding Zeta"} and noms["Holding Zeta"]["externe"] and noms["Alpha Sport SAS"]["centre"]
    assert {a["famille"] for a in r["aretes"]} == {"siege", "maison_mere"}
    assert {a["famille"] for a in lyon["aretes"]} == {"siege", "trouve_via", "meme_adresse"}  # trouvé via + même adresse (calculée) + siège


def test_le_plafond_est_dur_meme_quand_tout_est_lie(cfg):
    peupler_liens(cfg, n_isoles=200)
    i = ids(cfg)
    fab = creer_fabrique(cfg.url_base)
    with fab.begin() as s:  # un nom lié à 150 autres
        c0 = s.get(Candidat, i["Alpha Sport SAS"])
        c0.relations = [{"type": "siege", "vers": f"Isolé {k:03d}"} for k in range(150)]
    with TestClient(creer_app(cfg)) as c:
        r = c.get("/api/recherches/r15/carte", params={"centre": i["Alpha Sport SAS"]}).json()
    assert len(r["noeuds"]) == 60 and r["tronque"] is True and r["plafond"] == 60


def test_sans_relation_enregistree_la_carte_le_dit(cfg):
    fab = creer_fabrique(cfg.url_base)
    with fab.begin() as s:
        s.add(Recherche(id="r0", qui="t", sujet={"quoi": "x"}, parametres={}, etat="terminee"))
        s.flush()
        s.add(Candidat(recherche_id="r0", nom="Seul", faits={}))
    i = ids(cfg, "r0")
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/recherches/r0/decisions", json={"valeur": "garder", "ids": [i["Seul"]]})
        r = c.get("/api/recherches/r0/carte").json()
        inconnu = c.get("/api/recherches/r0/carte", params={"centre": 99999}).json()
        absent = c.get("/api/recherches/nexistepas/carte")
    assert r["relations_enregistrees"] == 0 and "Aucune relation" in r["message"]
    assert "n'existe pas" in inconnu["message"] and absent.status_code == 404


@pytest.fixture
def page(chromium, serveur_vivant, cfg):
    peupler_liens(cfg)
    terminer_assistant(cfg)
    url = serveur_vivant(creer_app(cfg))
    p = chromium.new_context(viewport={"width": 1300, "height": 900}).new_page()
    erreurs = []
    p.on("pageerror", lambda e: erreurs.append(str(e)))
    p.goto(url + "/")
    p.evaluate("localStorage.setItem('g_tri_recherche','r15')")
    p.reload()
    p.click('.tab[data-p="tri"]')
    p.wait_for_selector(".grp", timeout=15000)
    yield p
    assert erreurs == [], erreurs


def test_dans_le_navigateur_la_carte_se_dessine_et_decide_depuis_un_point(page, cfg):
    page.click('.views button[data-v="carte"]')
    page.wait_for_selector("#carte-zone")
    page.wait_for_function("document.querySelector('#carte-zone').innerText.includes('gardés')", timeout=10000)  # rien de gardé : la phrase, pas un nuage de points
    i = ids(cfg)
    with TestClient(creer_app(cfg)) as c:  # on garde deux noms (l'API du même fichier de base)
        c.post("/api/recherches/r15/decisions", json={"valeur": "garder", "ids": [i["Alpha Sport SAS"], i["Alpha Sport Lyon"]]})
    page.click('.views button[data-v="liste"]')
    page.click('.views button[data-v="carte"]')
    page.wait_for_function("document.querySelector('#carte-zone').dataset.noeuds === '2'", timeout=10000)
    assert page.locator("#carte-zone").get_attribute("data-aretes") == "1"
    legende = page.inner_text("#carte-legende")
    # la légende explique la taille, la couleur, et NE nomme que les familles de liens réellement dessinées, avec leur style
    assert "Taille = nombre d’endroits" in legende and "siège / établissement (trait plein)" in legende
    assert "même adresse" not in legende  # aucune source ne fournit d'adresse : ne pas promettre un lien impossible
    assert page.evaluate("typeof window.cytoscape") == "function"


def test_dans_le_navigateur_on_garde_depuis_la_carte_et_on_peut_etendre_la_recherche(page, cfg):
    page.keyboard.press("ArrowDown")
    page.wait_for_selector(".row.sel")
    choisi = int(page.locator(".row.sel").first.get_attribute("data-id"))
    page.click('.views button[data-v="carte"]')
    page.click("#carte-voisins")
    page.wait_for_selector('#carte-info button[data-cd="garder"]', timeout=10000)
    assert page.locator("#carte-info").inner_text().strip()  # le panneau dit en texte ce que la carte dessine
    page.click('#carte-info button[data-cd="garder"]')
    fab = creer_fabrique(cfg.url_base)
    for _ in range(100):
        with fab() as s:
            from pilote.tri import decisions_courantes

            if decisions_courantes(s, "r15").get(choisi) == "garder":
                break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("la décision prise depuis la carte n'a pas été enregistrée")
    page.wait_for_selector('#carte-info button[data-cd="etendre"]')
    page.click('#carte-info button[data-cd="etendre"]')
    page.wait_for_function("document.getElementById('f-quoi').value.length > 0")  # Recherches s'ouvre avec le nom : rien n'est lancé tout seul
    assert page.locator("#pg-lancement.on").count() == 1
