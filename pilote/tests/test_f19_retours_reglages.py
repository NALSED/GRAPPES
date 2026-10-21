"""Retours de Sednal du 20/10/2026 sur la page Réglages : sources retirées de l'affichage, voyant, ajout (existante / nouvelle / qui demande un
adaptateur), presets modifiables, blocs repliables, champs séparés. Chaque test nomme le défaut qu'il garde fermé."""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import cles
from pilote.app import creer_app


def lignes(c, partie="recherche"):
    return {x["id"]: x for x in c.get("/api/reglages").json()["parties"][partie]}


def premiere_installation(c):
    assert c.post("/api/assistant/terminer", json={"etape1": {"pays": "FR", "presets_coches": ["web"], "chercher": [], "plafond": 5},
                                                   "etape2": {"active": True, "mode": "memes", "verifier": []}, "etape3": {"actifs": ["csv"], "dossier": ""}}).status_code == 200


# --- [ ] Retirer une source l'enlève de l'AFFICHAGE (et l'éteint), sans toucher à son fichier ; on la remet depuis « Ajouter une source existante ».
def test_retirer_puis_remettre_une_source_ne_touche_pas_aux_fichiers(cfg):
    fichier = cfg.dossier_sources / "wikipedia.yaml"
    avant = fichier.read_bytes()
    with TestClient(creer_app(cfg)) as c:
        assert c.put("/api/reglages/source/wikipedia", json={"chercher": True}).status_code == 200
        assert lignes(c)["wikipedia"]["chercher"] is True and lignes(c)["wikipedia"]["masquee"] == {"recherche": False, "verification": False}
        assert c.post("/api/reglages/source/wikipedia/masquer", json={"partie": "recherche"}).status_code == 200
        w = lignes(c)["wikipedia"]
        assert w["masquee"]["recherche"] is True and w["chercher"] is False  # retirée = éteinte pour ce rôle : pas de source invisible qui continue de servir
        assert fichier.read_bytes() == avant and "wikipedia" in lignes(c)  # la déclaration est intacte, la source existe toujours
        assert c.post("/api/reglages/source/wikipedia/afficher", json={"partie": "recherche"}).status_code == 200
        w = lignes(c)["wikipedia"]
        assert w["masquee"]["recherche"] is False and w["chercher"] is False  # remise à l'affichage, toujours éteinte
        for mauvais in ({"partie": "sortie"}, {"partie": ""}):
            assert c.post("/api/reglages/source/wikipedia/masquer", json=mauvais).status_code == 422
        assert c.post("/api/reglages/source/n-existe-pas/masquer", json={"partie": "recherche"}).status_code == 422


def test_les_deux_parties_se_retirent_separement(cfg):
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/reglages/source/wikidata/masquer", json={"partie": "verification"})
        assert lignes(c, "verification")["wikidata"]["masquee"] == {"recherche": False, "verification": True}


# --- [ ] Une liste d'affichage retouchée à la main et devenue autre chose ne fait jamais tomber la page (invariant des réglages tolérants).
@pytest.mark.parametrize("abime", [{"sources_masquees": 5}, {"sources_masquees": {"a": 1}}, {"verification_masquees": "wikipedia"}, [1, 2]])
def test_un_affichage_abime_ne_fait_pas_tomber_la_page(cfg, abime):
    cfg.fichier_reglages.write_text(yaml.safe_dump({"affichage": abime}), encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        r = c.get("/api/reglages")
        assert r.status_code == 200 and any("affichage" in p["raison"] or "retirées" in p["raison"] for p in r.json()["problemes"])
        assert all(not x["masquee"]["recherche"] for x in r.json()["parties"]["recherche"] if x["id"] == "wikipedia") or isinstance(abime, dict)


# --- [ ] Le voyant : vert si disponible et utilisable, orange s'il manque une clé, rouge si le test a échoué ou si un adaptateur manque.
def test_le_voyant_dit_l_etat_de_la_source(cfg):
    with TestClient(creer_app(cfg)) as c:
        assert lignes(c)["wikipedia"]["voyant"][0] == "ok"  # sans clé, adaptateur présent
        assert lignes(c)["wikipedia"]["gratuite"] is True
        sans_cle = next(x for x in lignes(c).values() if x["cle_requise"] and x["cle"] == "absente")
        assert sans_cle["voyant"] == ["warn", "clé absente"]
        cles.ecrire(cfg, sans_cle["cles_noms"][0], "valeur-de-test-123456")
        assert lignes(c)[sans_cle["id"]]["voyant"][0] == "ok" or len(sans_cle["cles_noms"]) > 1
        assert any(x["gratuite"] is False for x in lignes(c).values())  # au moins une source payante est dite payante


# --- [ ] Une source qui demande un adaptateur est ENREGISTRÉE (jamais un refus muet), le dit en clair, et ne s'allume pas.
def test_une_source_qui_demande_un_adaptateur_est_enregistree_et_le_dit(cfg):
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "adaptateur", "spec": {"nom": "Service à jetons", "url": "https://api.exemple.example/v2", "protocole": "oauth",
                                                                               "trouve": "clubs", "pays": ["monde"], "cle_valeur": "secret-de-test-987654"}})
        assert r.status_code == 201, r.text
        assert r.json()["test"]["statut"] == "echec" and "demande un adaptateur" in r.json()["test"]["raison"]
        s = lignes(c)["service-a-jetons"]
        assert s["adaptateur_manquant"] is True and s["voyant"] == ["err", "demande un adaptateur"] and "demande un adaptateur" in s["etat_phrase"]
        assert "OAuth" in yaml.safe_load((cfg.dossier_sources / "service-a-jetons.yaml").read_text(encoding="utf-8"))["note"]
        rep = c.put("/api/reglages/source/service-a-jetons", json={"chercher": True})
        assert rep.status_code == 422 and "demande un adaptateur" in rep.json()["detail"]
        assert c.post("/api/ajout/source", json={"type": "adaptateur", "spec": {"nom": "Autre", "protocole": "magie"}}).status_code == 422


# --- [ ] La clé collée dans la page est rangée par le programme dans le fichier de clés : jamais dans la déclaration, jamais dans une réponse.
def test_la_cle_collee_est_rangee_par_le_programme(cfg):
    secret = "secret-de-test-abcdef-123456"
    spec = {"nom": "Annuaire des clubs", "url": "http://127.0.0.1:9/chercher", "parametre_requete": "q", "liste": "items", "champs": {"nom": "titre"},
            "auth": {"type": "bearer"}, "cle_valeur": secret, "exemple": {"items": [{"titre": "Club Fictif"}]}}
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "api", "spec": spec})
        assert r.status_code == 201, r.text
        nom = "ANNUAIRE_DES_CLUBS_API_KEY"
        assert cles.valeur(cfg, nom) == secret
        assert secret not in r.text and secret not in c.get("/api/reglages").text
        decl = (cfg.dossier_sources / "annuaire-des-clubs.yaml").read_text(encoding="utf-8")
        assert secret not in decl and nom in decl
        assert lignes(c)["annuaire-des-clubs"]["cle"] == "presente"
        # sans clé collée et sans nom : une API qui demande une clé est refusée avec une phrase qui dit quoi faire
        sans = c.post("/api/ajout/source", json={"type": "api", "spec": {**spec, "nom": "Sans clé", "cle_valeur": ""}})
        assert sans.status_code == 422 and "Collez la clé" in sans.json()["detail"]


# --- [ ] Un preset créé se renomme et se décrit ; un preset livré ne se modifie pas ; son identifiant ne bouge pas.
def test_un_preset_cree_est_editable(cfg):
    with TestClient(creer_app(cfg)) as c:
        ident = c.post("/api/presets", json={"nom": "Mon lot"}).json()["id"]

        def carte():
            return next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == ident)

        assert carte()["perso"] is True
        r = c.put(f"/api/presets/{ident}/infos", json={"nom": "Mon lot de clubs", "phrase": "Les clubs de ma ville."})
        assert r.status_code == 200 and carte()["nom"] == "Mon lot de clubs" and carte()["phrase"] == "Les clubs de ma ville." and carte()["phrase_perso"] == "Les clubs de ma ville."
        c.put(f"/api/presets/{ident}", json={"sources": ["wikipedia"]})
        assert [s["id"] for s in carte()["sources"]] == ["wikipedia"] and carte()["phrase"] == "Les clubs de ma ville."  # modifier les sources garde la description
        assert c.put(f"/api/presets/{ident}/infos", json={"nom": "   ", "phrase": ""}).status_code == 422
        livre = next(p["id"] for p in c.get("/api/reglages").json()["presets"] if not p["perso"])
        assert c.put(f"/api/presets/{livre}/infos", json={"nom": "X", "phrase": ""}).status_code == 422
        c.put("/api/reglages/presets", json={"coches": [ident]})
        c.put(f"/api/presets/{ident}/infos", json={"nom": "Encore un autre nom", "phrase": ""})
        assert c.get("/api/reglages").json()["presets_coches"] == [ident]  # renommer ne décoche pas


# --- [ ] Navigateur : ce que Sednal voit.
@pytest.fixture
def page_reglages(chromium, serveur_vivant, cfg):
    with TestClient(creer_app(cfg)) as c:
        premiere_installation(c)
    url = serveur_vivant(creer_app(cfg))
    page = chromium.new_context(viewport={"width": 1200, "height": 900}).new_page()
    page.erreurs = []
    page.on("pageerror", lambda e: page.erreurs.append(str(e)))
    page.goto(url + "/")
    page.click('.tab[data-p="reglages"]')
    page.wait_for_selector("#list1 .srow", state="attached", timeout=10000)
    return page


def ouvrir_tout(page):
    page.evaluate("document.querySelectorAll('details.bloc').forEach(d => d.open = true)")


def test_chaque_bloc_se_replie_et_garde_intitule_etat_et_rappel(page_reglages):
    p = page_reglages
    blocs = p.locator("#pg-reglages details.bloc")
    assert blocs.count() == 8  # assistant, budget, presets, bases, copies, sources, vérification, sortie
    for i in range(blocs.count()):
        b = blocs.nth(i)
        assert not b.evaluate("d => d.open"), "tout est replié au départ"
        resume = b.locator(":scope > summary").inner_text()
        assert len(resume.strip().splitlines()) >= 2 or "\t" in resume or len(resume) > 12  # intitulé + état + rappel
    assert p.locator("#e1").inner_text().endswith(("active", "actives")) and "prête" in p.locator("#c1").inner_text()
    assert "pays connus" in p.locator("#r-bases").inner_text() and "plafond" in p.locator("#r-budget").inner_text()
    assert not p.locator("#list1").is_visible()
    p.click("details[data-bloc=sources] > summary")
    assert p.locator("#list1").is_visible()
    chev = p.locator("details[data-bloc=sources] > summary .chev").bounding_box()
    box = p.locator("details[data-bloc=sources] > summary").bounding_box()
    assert chev["x"] > box["x"] + box["width"] - 40  # le chevron est à droite
    p.wait_for_function("localStorage.getItem('g_bloc_sources') === '1'")  # l'événement « toggle » est asynchrone : on attend qu'il ait écrit
    p.reload()  # l'état ouvert / fermé est mémorisé
    p.click('.tab[data-p="reglages"]')
    assert p.locator("details[data-bloc=sources]").evaluate("d => d.open") is True
    assert p.erreurs == []


def test_les_champs_d_une_ligne_ne_se_collent_plus(page_reglages):
    p = page_reglages
    ouvrir_tout(p)
    for sel in ("#list1 .sgrow", "#list2 .sgrow", "#presets .sgrow"):
        n = p.locator(sel).count()
        assert n > 0, sel
        for i in range(min(n, 6)):
            enfants = p.locator(sel).nth(i).locator(":scope > .sname, :scope > .smeta, :scope > details")
            boites = [enfants.nth(j).bounding_box() for j in range(enfants.count())]
            ys = [b["y"] for b in boites if b]
            assert ys == sorted(set(ys)), f"{sel} #{i} : des champs sur la même ligne {ys}"
    affichage = p.evaluate("getComputedStyle(document.querySelector('#presets .sgrow > .smeta')).display")
    assert affichage == "block"


def test_la_ligne_ne_montre_que_le_nom_et_gratuite_ou_payante_avec_un_voyant_vert(page_reglages):
    p = page_reglages
    ouvrir_tout(p)
    ligne = p.locator("#list1 .srow:has(input[data-id='wikipedia'])")
    visible = ligne.locator(".sgrow > .sname").inner_text()
    assert "Wikip" in visible
    assert "gratuite" in visible and len(visible) < 40
    assert ligne.locator(".dot.ok").count() == 1
    couleur = ligne.locator(".dot").evaluate("e => getComputedStyle(e).backgroundColor")
    rouge, vert, bleu = [int(x) for x in couleur[couleur.index("(") + 1:-1].split(",")[:3]]
    assert vert > rouge and vert > bleu, couleur  # c'est bien un vert
    assert not ligne.locator("details").evaluate("d => d.open")  # le reste est replié dans les détails
    assert "Pas encore testée" not in ligne.locator(".sgrow").inner_text().split("Détails")[0]


def test_retirer_et_ajouter_une_source_existante_depuis_la_page(page_reglages):
    p = page_reglages
    ouvrir_tout(p)
    avant = p.locator("#list1 .srow").count()
    ligne = p.locator("#list1 .srow:has(input[data-id='wikipedia'])")
    ligne.locator("button.retirer").click()
    p.wait_for_function(f"document.querySelectorAll('#list1 .srow').length === {avant - 1}")
    assert p.locator("#list1 input[data-id='wikipedia']").count() == 0
    p.click("button[data-existante='1']")
    p.wait_for_selector("#ajouts1 .tableau .srow")
    assert "Wikip" in p.locator("#ajouts1 .tableau").inner_text()
    assert p.locator("#ajouts1 .tableau .dot.ok").count() >= 1
    p.click("#ajouts1 button[data-remettre='wikipedia']")
    p.wait_for_function(f"document.querySelectorAll('#list1 .srow').length === {avant}")
    assert p.erreurs == []


def test_le_bouton_nouvelle_source_ouvre_la_page_ajout_avec_le_role(page_reglages):
    p = page_reglages
    ouvrir_tout(p)
    p.click("button[data-nouvelle='2']")
    assert p.locator("#pg-ajout.on").count() == 1 and p.locator("#t-verifier").is_checked()
    p.select_option("#t-type", "rss")
    assert p.locator("#flux-rss").is_visible() and p.locator("#t-generique").is_hidden()  # le bloc RSS est dans Ajout
    p.select_option("#t-type", "adaptateur")
    assert p.locator("#t-autre").is_visible() and p.locator("#t-cle-val").is_visible()
    assert p.locator("#t-cle-val").get_attribute("type") == "password"
    p.select_option("#t-type", "fichier")
    assert p.locator("#t-cle-zone").is_hidden()


def test_rss_n_est_plus_dans_reglages_et_nommage_sources(page_reglages):
    p = page_reglages
    html = p.content()
    assert p.locator("#pg-reglages #flux-rss").count() == 0 and p.locator("#pg-ajout #flux-rss").count() == 1
    assert "① SOURCES" in p.locator("#pg-reglages").inner_text() and "RECHERCHE" not in p.locator("#pg-reglages").inner_text()
    assert "Destination : sources" in p.locator("#pg-ajout").inner_text() or "sources · vérification · sortie" in p.locator("#pg-ajout").inner_text()
    assert html.count("① Sources") >= 1  # l'assistant dit « Sources » aussi


def test_le_texte_du_mode_plus_est_a_jour_et_le_defaut_reste_eteint(page_reglages, cfg):
    p = page_reglages
    ouvrir_tout(p)
    assert p.locator("#verif-mode").is_checked() is False  # le défaut reste « memes » (décision de Sednal, F17-2)
    texte = p.locator("#verif-mode-txt").inner_text()
    assert "points de confirmation" not in texte and "nombre d'endroits" in texte
    for nom in ("CourtListener", "OpenSanctions", "Wayback Machine"):
        assert nom in texte
    p.evaluate("document.querySelector('#verif-sw').click()")  # coupée (la case est sous son habillage)
    p.wait_for_function("document.querySelector('#verif-txt').innerText.includes('coupée')")
    assert "points de confirmation" not in p.locator("#verif-txt").inner_text()
    assert json.loads(json.dumps(p.locator("#e2").inner_text())) == "Coupée"


def test_un_preset_cree_propose_de_modifier_son_nom_et_sa_description(page_reglages):
    p = page_reglages
    ouvrir_tout(p)
    p.once("dialog", lambda d: d.accept("Lot de test"))
    p.click("#preset-vide")
    p.wait_for_selector("#presets button[data-infos]")
    p.wait_for_load_state("networkidle")  # la page se redessine après la création : on attend qu'elle ait fini
    p.click("#presets button[data-infos]")
    p.fill("input[id^=pn-]", "Lot renommé")
    p.fill("input[id^=pd-]", "Une description à moi")
    p.click("button[data-enreg-infos]")
    p.wait_for_function("document.querySelector('#presets').innerText.includes('Lot renommé')")
    assert "Une description à moi" in p.locator("#presets").inner_text()
    assert p.erreurs == []


def test_bases_officielles_et_copies_locales_sont_deux_blocs_separes(page_reglages):
    p = page_reglages
    bases, copies = p.locator("details[data-bloc=bases]"), p.locator("details[data-bloc=copies]")
    assert bases.count() == 1 and copies.count() == 1 and bases.locator("#cop-liste").count() == 0 and copies.locator("#cat-liste").count() == 0
    assert "bases officielles" in bases.locator(":scope > summary").inner_text().lower() and "copies locales" in copies.locator(":scope > summary").inner_text().lower()


# ===================== Revue du 20/10 (soir) : défauts trouvés à la relecture, gardés fermés =====================


# --- [ ] Ajouter une source ne remplace JAMAIS une clé déjà rangée (elle peut appartenir à une autre source, ou être la vraie clé de Sednal).
def test_une_cle_deja_rangee_n_est_jamais_remplacee(cfg):
    spec = {"url": "http://127.0.0.1:9/x", "parametre_requete": "q", "liste": "items", "champs": {"nom": "t"}, "auth": {"type": "bearer"}, "exemple": {"items": [{"t": "A"}]}}
    cles.ecrire(cfg, "ANNUAIRE_API_KEY", "ancienne-valeur-123")
    cles.ecrire(cfg, "TAVILY_API_KEY", "vraie-cle-tavily-123")
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "api", "spec": {**spec, "nom": "Annuaire", "cle_valeur": "nouvelle-valeur-456"}})
        assert r.status_code == 201 and cles.valeur(cfg, "ANNUAIRE_API_KEY") == "ancienne-valeur-123"  # nom déjà pris : un autre est choisi
        assert cles.valeur(cfg, "ANNUAIRE_API_KEY_2") == "nouvelle-valeur-456" and "ANNUAIRE_API_KEY_2" in (cfg.dossier_sources / "annuaire.yaml").read_text(encoding="utf-8")
        r = c.post("/api/ajout/source", json={"type": "api", "spec": {**spec, "nom": "Piege", "cle": "TAVILY_API_KEY", "cle_valeur": "autre-valeur-789"}})
        assert r.status_code == 422 and "n'est pas remplacée" in r.json()["detail"] and cles.valeur(cfg, "TAVILY_API_KEY") == "vraie-cle-tavily-123"
        assert not (cfg.dossier_sources / "piege.yaml").exists()  # refus AVANT toute écriture
        r = c.post("/api/ajout/source", json={"type": "api", "spec": {**spec, "nom": "Meme valeur", "cle": "TAVILY_API_KEY", "cle_valeur": "vraie-cle-tavily-123"}})
        assert r.status_code == 201  # la même valeur peut resservir à une seconde source


# --- [ ] Une source « Autre » ne s'accroche jamais à un adaptateur existant parce qu'elle en porte le nom.
@pytest.mark.parametrize("nom", ["Api json", "Base sql", "Mcp generique", "Wayback 2"])
def test_une_source_autre_ne_s_accroche_pas_a_un_adaptateur_existant(cfg, nom):
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/ajout/source", json={"type": "adaptateur", "spec": {"nom": nom, "protocole": "graphql"}})
        assert r.status_code == 201, r.text
        s = lignes(c)[r.json()["id"]]
        assert s["adaptateur_manquant"] is True and s["voyant"] == ["err", "demande un adaptateur"]


# --- [ ] Rallumer une source retirée (assistant, appel direct) la remet à l'affichage : jamais une source active invisible.
def test_rallumer_une_source_retiree_la_remet_a_l_affichage(cfg):
    with TestClient(creer_app(cfg)) as c:
        c.post("/api/reglages/source/wikipedia/masquer", json={"partie": "recherche"})
        assert c.post("/api/assistant/etape/1", json={"donnees": {"pays": "FR", "presets_coches": ["web"], "chercher": ["wikipedia"], "plafond": 5}}).status_code == 200
        w = lignes(c)["wikipedia"]
        assert w["chercher"] is True and w["masquee"]["recherche"] is False
        c.post("/api/reglages/source/wikidata/masquer", json={"partie": "verification"})
        c.put("/api/reglages/source/wikidata", json={"verifier": True})
        assert lignes(c, "verification")["wikidata"]["masquee"]["verification"] is False
        c.put("/api/reglages/source/wikidata", json={"chercher": False})  # éteindre un AUTRE rôle ne touche pas à l'affichage
        c.post("/api/reglages/source/wikidata/masquer", json={"partie": "recherche"})
        assert lignes(c)["wikidata"]["masquee"] == {"recherche": True, "verification": False}


# --- [ ] Une source qui exige un réglage (adresse d'un portail) n'est pas verte tant qu'il manque : son activation serait refusée.
def test_une_source_a_reglage_obligatoire_n_est_pas_verte_sans_lui(cfg):
    with TestClient(creer_app(cfg)) as c:
        assert lignes(c)["ckan"]["voyant"] == ["warn", "réglage à donner"]
        assert c.put("/api/reglages/source/ckan", json={"parametres": {"portail": "https://data.exemple.example"}}).status_code == 200
        assert lignes(c)["ckan"]["voyant"][0] == "ok"


# --- [ ] Une entrée de source retouchée à la main ne fait tomber ni la page, ni le test d'une source (cinq lectures fragiles corrigées).
def test_une_entree_de_source_abimee_ne_fait_rien_tomber(cfg):
    cfg.fichier_reglages.write_text(yaml.safe_dump({"sources": {"wikipedia": 5, "ckan": {"parametres": "pas un dictionnaire"}, "gdelt": []}}), encoding="utf-8")
    with TestClient(creer_app(cfg), raise_server_exceptions=False) as c:
        r = c.get("/api/reglages")
        assert r.status_code == 200 and any("Wikipédia" in p["raison"] for p in r.json()["problemes"])
        for sid in ("wikipedia", "ckan", "gdelt"):
            assert c.post(f"/api/sources/{sid}/tester").status_code == 200, sid


# --- [ ] Des retraits envoyés en même temps ne se perdent pas (lire, modifier, écrire sous verrou).
def test_des_retraits_simultanes_ne_se_perdent_pas(cfg):
    from concurrent.futures import ThreadPoolExecutor

    with TestClient(creer_app(cfg)) as c:
        ids = [x for x in lignes(c) if x != "wikipedia"][:12]
        with ThreadPoolExecutor(6) as ex:
            codes = list(ex.map(lambda s: c.post(f"/api/reglages/source/{s}/masquer", json={"partie": "recherche"}).status_code, ids))
        assert codes == [200] * len(ids)
        assert {s for s, x in lignes(c).items() if x["masquee"]["recherche"]} == set(ids)


# --- [ ] Navigateur, en profondeur : téléphone, clavier, mode sombre, tous les onglets sans erreur.
def test_sur_telephone_aucun_defilement_horizontal(chromium, serveur_vivant, cfg):
    with TestClient(creer_app(cfg)) as c:
        premiere_installation(c)
    url = serveur_vivant(creer_app(cfg))
    page = chromium.new_context(viewport={"width": 375, "height": 800}).new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(url + "/")
    page.click('.tab[data-p="reglages"]')
    page.wait_for_selector("#list1 .srow", state="attached")
    for ouvert in (False, True):
        if ouvert:
            ouvrir_tout(page)
        largeur = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert largeur[0] <= largeur[1] + 1, (ouvert, largeur)
    chev = page.locator("details[data-bloc=sources] > summary .chev").bounding_box()
    assert chev["x"] + chev["width"] <= 375  # le chevron reste dans l'écran
    page.click('.tab[data-p="ajout"]')
    page.select_option("#t-type", "adaptateur")
    largeur = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    assert largeur[0] <= largeur[1] + 1, largeur
    assert erreurs == []


def test_les_blocs_s_ouvrent_au_clavier(page_reglages):
    p = page_reglages
    p.focus("details[data-bloc=budget] > summary")
    p.keyboard.press("Enter")
    assert p.locator("#budget-plafond").is_visible()
    p.keyboard.press(" ")
    assert not p.locator("#budget-plafond").is_visible()


def test_mode_sombre_voyant_lisible_et_aucune_erreur_dans_les_onglets(chromium, serveur_vivant, cfg):
    with TestClient(creer_app(cfg)) as c:
        premiere_installation(c)
    url = serveur_vivant(creer_app(cfg))
    page = chromium.new_context(viewport={"width": 1200, "height": 900}, color_scheme="dark").new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" and "fonts.g" not in m.text else None)
    page.goto(url + "/")
    for onglet in ("reglages", "ajout", "lancement", "tri", "reglages"):
        page.click(f'.tab[data-p="{onglet}"]')
        page.wait_for_timeout(300)
    ouvrir_tout(page)
    fond = page.evaluate("getComputedStyle(document.body).backgroundColor")
    vert = page.locator("#list1 .dot.ok").first.evaluate("e => getComputedStyle(e).backgroundColor")
    assert vert != fond and vert != "rgba(0, 0, 0, 0)"
    r, g, b = [int(x) for x in vert[vert.index("(") + 1:-1].split(",")[:3]]
    assert g > r and g > b and g > 120  # un vert clair, lisible sur fond sombre
    assert erreurs == [], erreurs
