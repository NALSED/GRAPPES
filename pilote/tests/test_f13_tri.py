"""FICHE 13 — page Tri : test de recette, point par point. Les points visuels sont vérifiés dans un VRAI navigateur sans tête
(outils/installer_navigateur_test.sh) : tailles, couleurs, niveaux de gris, clavier."""

import re

import pytest
from conftest import copier_config
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.base import Candidat, Recherche
from pilote.config import RACINE
from pilote.config import charger as charger_cfg

VILLES = ["Lyon", "Grenoble", "Toulouse", "Nantes", "Lille", "Bordeaux", "Rennes", "Dijon"]
ORIGINES = ["registre", "presse", "web", "web", "texte", "encyclo"]
SOURCES = [["recherche-entreprises"], ["rss_liberation"], ["searxng"], ["searxng", "wikipedia"], ["(texte)"], ["wikidata"]]
GENRES = ["club", "association", "club", "entreprise"]


def peupler(cfg, n=400, quoi="clubs de handball", rid="r13", verification=True):
    """Une recherche terminée avec `n` noms variés (origines, villes, genres, sources) : de quoi fabriquer des facettes."""
    from pilote.base import creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        s.add(Recherche(id=rid, qui="sednal", sujet={"quoi": quoi, "inclure": ["pro"]}, parametres={"verification": verification}, etat="terminee"))
        s.flush()
        for i in range(n):
            o = ORIGINES[i % len(ORIGINES)]
            s.add(Candidat(recherche_id=rid, nom=f"{'Club' if i % 3 else 'Union'} Handball {VILLES[i % len(VILLES)]} {i:03d}", genre_source=o, trouve_par=SOURCES[i % len(SOURCES)],
                           nb_endroits=1 + (i % 3), genre_de_chose=GENRES[i % len(GENRES)], ville=VILLES[i % len(VILLES)], pays="FR" if i % 5 else "GB",
                           site="" if i % 4 else f"club{i}.example", faits={}))
    return fabrique


def terminer_assistant(cfg):
    """La première installation est faite (sinon l'assistant cache le menu)."""
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/assistant/terminer", json={"etape1": {"pays": "FR", "presets_coches": ["web"], "chercher": [], "plafond": 5},
                                                     "etape2": {"active": True, "mode": "memes", "verifier": []}, "etape3": {"actifs": ["csv"], "dossier": ""}})
        assert r.status_code == 200, r.text


@pytest.fixture
def cfg(tmp_path):
    return charger_cfg(copier_config(tmp_path))


# --- [ ] Tabulator est en place SANS npm ni chaîne de compilation.
def test_tabulator_est_en_place_sans_npm(cfg):
    d = RACINE / "static/vendor/tabulator"
    assert (d / "tabulator.min.js").stat().st_size > 100_000 and (d / "tabulator.min.css").exists()
    assert "MIT License" in (d / "LICENSE").read_text(encoding="utf-8")
    assert not (RACINE / "package.json").exists() and not (RACINE / "node_modules").exists()  # ni npm ni chaîne de compilation
    with TestClient(creer_app(cfg)) as c:
        assert c.get("/static/vendor/tabulator/tabulator.min.js").status_code == 200  # servi par pilote lui-même
        html = c.get("/").text
    assert "/static/vendor/tabulator/tabulator.min.js" in html and "cdn" not in html.split("<!-- ============ TRI")[1].split("</script>")[0].lower()


def test_les_pages_n_ont_besoin_d_aucun_reseau_pour_le_tableau():
    html = (RACINE / "static/index.html").read_text(encoding="utf-8")
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    assert scripts and all(s.startswith("/static/") for s in scripts)


@pytest.fixture
def navigateur(chromium, serveur_vivant, cfg):
    """Une page Tri ouverte dans un vrai navigateur, sur 400 noms. Rend (page, url, cfg)."""
    peupler(cfg, 400)
    terminer_assistant(cfg)
    url = serveur_vivant(creer_app(cfg))
    ctx = chromium.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.goto(url + "/")
    page.evaluate("localStorage.setItem('g_tri_recherche','r13')")
    page.reload()
    page.click('.tab[data-p="tri"]')
    page.wait_for_selector(".grp", timeout=15000)
    yield page, url, cfg
    ctx.close()
    assert erreurs == [], erreurs  # aucune erreur de script pendant tout le test


def ouvrir_premier_nom(page):
    page.keyboard.press("ArrowDown")  # ouvre le paquet du nom actif et le sélectionne
    page.wait_for_selector(".row.sel")


# --- [ ] Les trois niveaux de typographie sont distincts : le nom nettement plus gros et plus gras que la deuxième ligne.
def test_trois_tailles_deux_graisses(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    t = page.evaluate("""() => { const l = document.querySelector('.row.sel'); const f = e => { const s = getComputedStyle(l.querySelector(e)); return [s.fontSize, s.fontWeight]; };
        return {r1: f('.r1'), r2: f('.r2'), r3: f('.r3')}; }""")
    assert t["r1"] == ["16px", "600"] and t["r2"] == ["13px", "400"] and t["r3"] == ["11px", "400"], t
    # sur tout le texte des lignes : exactement trois tailles et deux graisses
    tout = page.evaluate("""() => { const tailles = new Set(), graisses = new Set();
        document.querySelectorAll('.row .r1, .row .r2, .row .r3, .row .r2 *').forEach(e => { const s = getComputedStyle(e); tailles.add(s.fontSize); graisses.add(s.fontWeight); });
        return [[...tailles].sort(), [...graisses].sort()]; }""")
    assert tout[0] == ["11px", "13px", "16px"] and set(tout[1]) <= {"400", "600"}, tout


# --- [ ] Le niveau 3 n'apparaît QUE sur la ligne sélectionnée.
def test_le_niveau_3_n_apparait_que_sur_la_ligne_selectionnee(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    for _ in range(3):
        page.keyboard.press("ArrowDown")
    n = page.evaluate("""() => [...document.querySelectorAll('.row')].map(r => [r.classList.contains('sel'), r.querySelector('.r3').textContent.trim().length > 0])""")
    assert sum(1 for sel, plein in n if sel) == 1
    assert [plein for sel, plein in n if sel] == [True] and not any(plein for sel, plein in n if not sel)
    # et toutes les lignes ont la même hauteur : les gestes ne bougent jamais
    hauteurs = page.evaluate("[...new Set([...document.querySelectorAll('.row')].map(r => r.getBoundingClientRect().height))]")
    assert hauteurs == [64]


# --- [ ] Bord gauche = origine, fond de ligne = décision. Les deux se lisent ensemble sur une même ligne.
def test_bord_gauche_origine_et_fond_decision(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    avant = page.evaluate("""() => { const r = document.querySelector('.row.sel'); const s = getComputedStyle(r); return [s.borderLeftColor, s.backgroundColor]; }""")
    page.keyboard.press("g")
    page.wait_for_selector(".row.d-garder")
    apres = page.evaluate("""() => { const r = document.querySelector('.row.d-garder'); const s = getComputedStyle(r);
        return [s.borderLeftColor, s.backgroundColor, getComputedStyle(document.documentElement).getPropertyValue('--ouibg').trim(), getComputedStyle(document.documentElement).getPropertyValue('--o1').trim()]; }""")
    assert apres[0] == avant[0]  # le bord (origine) ne change pas avec la décision
    assert apres[1] != avant[1]  # le fond (décision) change
    page.keyboard.press("r")
    page.wait_for_selector(".row.d-rejeter")
    rejete = page.evaluate("""() => { const r = document.querySelector('.row.d-rejeter'); const s = getComputedStyle(r); return [s.borderLeftColor, s.backgroundColor]; }""")
    assert rejete[1] not in (avant[1], apres[1])  # gardé et rejeté n'ont pas le même fond
    for i in range(page.locator(".grp-h").count()):  # la page se redessine à chaque ouverture : on retrouve chaque en-tête à son tour
        h = page.locator(".grp-h").nth(i)
        if h.locator(".car").inner_text().strip() == "▸":
            h.click()
    couleurs = page.evaluate("""() => { const o = {}; document.querySelectorAll('.row').forEach(r => { const m = r.querySelector('.mot').textContent; o[m] = getComputedStyle(r).borderLeftColor; }); return o; }""")
    assert len(set(couleurs.values())) == len(couleurs) and {"REGISTRE", "PRESSE", "WEB"} <= set(couleurs)  # une teinte par origine, mot compris


# --- [ ] En noir et blanc, l'information reste lisible (mots courts + points).
def test_en_niveaux_de_gris_l_information_reste_lisible(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    page.keyboard.press("g")
    page.keyboard.press("r")
    page.keyboard.press("p")
    page.add_style_tag(content="html{filter:grayscale(1)!important}")
    lignes = page.evaluate("""() => [...document.querySelectorAll('.row')].map(r => ({ mot: r.querySelector('.mot').textContent, points: r.querySelector('.pts') ? r.querySelector('.pts').textContent : '',
        decision: [...r.classList].find(c => c.startsWith('d-')) || '', marque: r.querySelector('.rd').textContent.trim() }))""")
    assert lignes and all(re.fullmatch(r"REGISTRE|PRESSE|WEB|TEXTE|ENCYCLO", l["mot"]) for l in lignes)  # l'origine a un mot, pas seulement une teinte
    assert all(re.fullmatch(r"\d+ endroits?", l["points"]) for l in lignes)  # un NOMBRE d'endroits, séparé de la qualité de la source (le mot)
    attendu = {"d-garder": "✓", "d-rejeter": "✕", "d-plus_tard": "·"}
    assert all(l["marque"] == attendu[l["decision"]] for l in lignes if l["decision"])  # une décision a un signe, pas seulement une teinte


# --- [ ] Dans Tri, le vert et le rouge n'apparaissent NULLE PART ailleurs que sur les décisions. (Depuis le 20/10, Sednal a aussi donné le vert,
# l'orange et le rouge au VOYANT d'état d'une source dans Réglages : QUESTIONS P1 ; ces règles-là sont les seules admises hors décisions.)
def test_vert_et_rouge_reserves_aux_decisions(navigateur):
    page, _, _ = navigateur
    css = (RACINE / "static/pilote.css").read_text(encoding="utf-8")
    autorises = {".chip.ex", ".bulk.k", ".bulk.r", ".row.d-garder", ".row.d-rejeter", ".dec .k.on", ".dec .r.on", ".motifs .mo.on", ".tabulator-row.d-garder", ".tabulator-row.d-rejeter",
                 ".tabulator-row.tabulator-selected.d-garder", ".tabulator-row.tabulator-selected.d-rejeter", ".row.d-garder.sel", ".row.d-rejeter.sel",
                 ".dot.ok", ".dot.err", ".dot.err::after", ".srow .retirer:hover"}  # les trois dernières : le voyant des sources (Réglages), pas la page Tri
    for regle in re.finditer(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)):
        sel, corps = regle.group(1).strip(), regle.group(2)
        if re.search(r"var\(--(oui|non)(bg)?\)", corps) and not sel.startswith(("--", ":root", "@")):
            assert all(s.strip() in autorises for s in sel.split(",")), f"vert/rouge hors décision : {sel}"
    js = (RACINE / "static/tri.js").read_text(encoding="utf-8")
    assert js.count("var(--oui)") + js.count("var(--non)") <= 2  # seulement les signes ✓ / ✕ des décisions, jamais ailleurs
    ouvrir_premier_nom(page)
    page.keyboard.press("g")
    # dans le DOM réel : hors lignes décidées et boutons de décision, aucun élément de la page Tri n'a la teinte du vert ni du rouge
    tokens = page.evaluate("""() => { const r = getComputedStyle(document.documentElement); const c = v => { const e = document.createElement('i'); e.style.color = r.getPropertyValue(v); document.body.appendChild(e); const x = getComputedStyle(e).color; e.remove(); return x; };
        return [c('--oui'), c('--non'), c('--ouibg') ? (() => { const e = document.createElement('i'); e.style.background = r.getPropertyValue('--ouibg'); document.body.appendChild(e); const x = getComputedStyle(e).backgroundColor; e.remove(); return x; })() : '', (() => { const e = document.createElement('i'); e.style.background = r.getPropertyValue('--nonbg'); document.body.appendChild(e); const x = getComputedStyle(e).backgroundColor; e.remove(); return x; })()]; }""")
    intrus = page.evaluate("""(tokens) => { const bad = []; const ok = e => e.closest('.d-garder,.d-rejeter,.dec,.bulk,.motifs,.rd');
        document.querySelectorAll('#pg-tri *').forEach(e => { if (ok(e)) return; const s = getComputedStyle(e);
          for (const p of ['color','backgroundColor','borderTopColor','borderLeftColor']) if (tokens.includes(s[p])) bad.push(e.tagName + '.' + e.className + ' ' + p); });
        return bad; }""", tokens)
    assert intrus == [], intrus


# --- [ ] Les mots cherchés sont surlignés dans les noms.
def test_les_mots_cherches_sont_surlignes(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    marques = page.evaluate("[...document.querySelectorAll('.row .r1 mark')].map(m => m.textContent.toLowerCase())")
    assert marques and set(marques) == {"handball"}  # le mot de la recherche, et seulement lui
    # la recherche de texte ajoute ses propres mots, sans tenir compte des accents ni des majuscules
    page.fill("#tri-q", "GRENOBLE")
    page.wait_for_function("document.querySelectorAll('.row').length === 0 || [...document.querySelectorAll('.row .r1 mark')].some(m => m.textContent.toLowerCase() === 'grenoble')", timeout=10000)
    page.evaluate("document.activeElement.blur()")  # le clavier quitte la zone de texte et revient à la liste
    page.keyboard.press("ArrowDown")
    page.wait_for_selector(".row .r1 mark")
    noms = page.evaluate("[...document.querySelectorAll('.row .r1')].map(r => r.textContent)")
    assert noms and all("grenoble" in n.lower() for n in noms)


# --- [ ] Les filtres apparaissent tout seuls selon le contenu des résultats, avec leur nombre, sans avoir été écrits à la main.
def test_les_facettes_se_construisent_depuis_les_resultats(cfg):
    peupler(cfg, 400)
    with TestClient(creer_app(cfg)) as c:
        t = c.get("/api/recherches/r13/tri").json()
        facettes = {f["id"]: f for f in t["facettes"]}
        # les colonnes à peu de valeurs deviennent des filtres, avec le nombre de noms à côté
        assert {"origine", "pays", "ville", "genre", "confirmations", "source"} <= set(facettes)
        assert "fonction" not in facettes and "decision" not in facettes  # aucune fonction, aucune décision encore : une seule valeur, pas de filtre vide
        assert {v["valeur"]: v["n"] for v in facettes["ville"]["valeurs"]} == {v: 50 for v in VILLES}
        assert sum(v["n"] for v in facettes["origine"]["valeurs"]) == 400
        assert {v["valeur"]: v["n"] for v in facettes["pays"]["valeurs"]} == {"FR": 320, "GB": 80}
        # un clic filtre : les lignes, les paquets et les comptes des AUTRES facettes suivent
        f = c.get("/api/recherches/r13/tri", params={"filtre": ["ville:Lyon", "pays:FR"]}).json()
        assert f["total"] == 40 and all(x["v"] == "Lyon" for x in f["lignes"]) and f["total_tout"] == 400
        assert {v["valeur"]: v["n"] for v in {x["id"]: x for x in f["facettes"]}["ville"]["valeurs"]}["Grenoble"] == 40  # le compte d'une facette ignore son propre filtre
        # deux valeurs d'une même facette s'additionnent
        deux = c.get("/api/recherches/r13/tri", params={"filtre": ["ville:Lyon", "ville:Lille"]}).json()
        assert deux["total"] == 100
        # une seule valeur dans les résultats : plus de filtre
        un_seul = c.get("/api/recherches/r13/tri", params={"filtre": ["ville:Lyon", "pays:FR", "genre:club"]}).json()
        assert {x["id"]: x for x in un_seul["facettes"]}.get("ville")  # les facettes restent proposées pour pouvoir défaire un filtre
    # d'autres résultats, d'autres filtres : rien n'est écrit en dur pour un jeu de résultats
    peupler(cfg, 6, quoi="chorales", rid="r6")
    with TestClient(creer_app(cfg)) as c:
        autre = {f["id"] for f in c.get("/api/recherches/r6/tri").json()["facettes"]}
        assert "ville" in autre and "confirmations" in autre


def test_la_recherche_de_texte_filtre_les_noms_sans_tenir_compte_des_accents(cfg):
    from pilote.base import creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        s.add(Recherche(id="rt", qui="sednal", sujet={"quoi": "clubs"}, parametres={}, etat="terminee"))
        s.flush()
        for nom in ("Club Hélios Nîmes", "Club Soleil Lyon", "Étoile Sportive Nîmes"):
            s.add(Candidat(recherche_id="rt", nom=nom, genre_source="web", trouve_par=["searxng"], nb_endroits=1, faits={}))
    with TestClient(creer_app(cfg)) as c:
        noms = lambda q: sorted(x["nom"] for x in c.get("/api/recherches/rt/tri", params={"q": q}).json()["lignes"])
        assert noms("nimes") == ["Club Hélios Nîmes", "Étoile Sportive Nîmes"] and noms("helios nimes") == ["Club Hélios Nîmes"] and noms("ETOILE") == ["Étoile Sportive Nîmes"]
        assert "etoile" in c.get("/api/recherches/rt/tri", params={"q": "ÉTOILE"}).json()["recherche"]["mots"]


# --- [ ] « Nouveaux noms » : comparés à ce qui a été GARDÉ ; un nom rejeté peut réapparaître comme nouveau.
def test_nouveaux_noms_compares_a_ce_qui_a_ete_garde(cfg):
    from pilote.base import creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        for rid in ("ancienne", "recente"):
            s.add(Recherche(id=rid, qui="sednal", sujet={"quoi": "chorales"}, parametres={}, etat="terminee"))
        s.flush()
        for nom in ("Chorale A", "Chorale B", "Chorale C"):
            s.add(Candidat(recherche_id="ancienne", nom=nom, genre_source="web", trouve_par=["searxng"], nb_endroits=1, faits={}))
        for nom in ("Chorale A", "Chorale B", "Chorale D"):
            s.add(Candidat(recherche_id="recente", nom=nom, genre_source="web", trouve_par=["searxng"], nb_endroits=1, faits={}))
    with TestClient(creer_app(cfg)) as c:
        ids = {x["nom"]: x["id"] for x in c.get("/api/recherches/ancienne/tri").json()["lignes"]}
        c.post("/api/recherches/ancienne/decisions", json={"valeur": "garder", "ids": [ids["Chorale A"]]})
        c.post("/api/recherches/ancienne/decisions", json={"valeur": "rejeter", "ids": [ids["Chorale B"]]})
        n = c.get("/api/recherches/recente/tri", params={"nouveaux": True}).json()
        assert sorted(x["nom"] for x in n["lignes"]) == ["Chorale B", "Chorale D"]  # A était gardé ; B, rejeté, réapparaît comme nouveau
        assert c.get("/api/recherches/recente/tri").json()["total"] == 3


# --- Les actions groupées ne touchent que ce que les filtres montrent.
def test_une_action_groupee_ne_touche_que_les_noms_filtres(cfg):
    peupler(cfg, 100)
    with TestClient(creer_app(cfg)) as c:
        t = c.get("/api/recherches/r13/tri", params={"filtre": ["ville:Lyon"]}).json()
        paquet = t["paquets"][0]
        r = c.post("/api/recherches/r13/decisions", json={"valeur": "garder", "classement": t["classement"]["id"], "cle": paquet["cle"], "filtres": ["ville:Lyon"]}).json()
        tout = c.get("/api/recherches/r13/tri").json()
        gardes = [x for x in tout["lignes"] if x["d"] == "garder"]
        assert len(gardes) == len(r["touches"]) == paquet["n"] and all(x["v"] == "Lyon" for x in gardes)  # pas un seul nom d'une autre ville
        assert c.post("/api/recherches/r13/annuler").status_code == 200
        assert not [x for x in c.get("/api/recherches/r13/tri").json()["lignes"] if x["d"]]


# --- [ ] Trier 400 noms au clavier sans toucher la souris, sans que la position des boutons change.
def test_trier_400_noms_au_clavier_sans_souris_et_sans_que_les_boutons_bougent(navigateur):
    page, _, cfg = navigateur  # le premier nom à décider est déjà actif : on n'a besoin que du clavier, dès la première touche

    def boutons():
        return page.evaluate("[...document.querySelectorAll('#detail .dec button, #detail .motifs button')].map(b => { const r = b.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width)]; })")

    positions = boutons()
    assert len(positions) >= 6
    touches = ["g", "r", "p", "g", "1", "g", "2", "g", "3", "g"]
    decides = 0
    pas_de_bouge = True
    while decides < 400:
        page.keyboard.press(touches[decides % len(touches)])
        decides += 1
        if decides % 25 == 0:
            pas_de_bouge &= boutons() == positions  # les boutons sont toujours au même endroit : le geste devient automatique
        if decides % 100 == 0:
            try:
                page.wait_for_function(f"document.querySelector('#ov-rest').textContent.includes('reste {400 - decides} ')", timeout=15000)
            except Exception:  # noqa: BLE001
                raise AssertionError(f"après {decides} touches : {page.inner_text('#ov-rest')!r}, message {page.inner_text('#tri-msg')!r}") from None
    assert pas_de_bouge
    page.wait_for_function("document.querySelector('#ov-rest').textContent.includes('reste 0 ')", timeout=15000)
    # tout est enregistré côté serveur (les décisions partent une à une, dans l'ordre)
    import time

    with TestClient(creer_app(cfg)) as c:
        t0 = time.time()
        while time.time() - t0 < 30:
            t = c.get("/api/recherches/r13/tri").json()
            if t["a_decider"] == 0:
                break
            time.sleep(0.3)
        assert t["a_decider"] == 0 and sum(1 for x in t["lignes"] if x["d"]) == 400
        rej = {x["motifs"].get("hors_zone", 0) for x in c.get("/api/recherches/r13/rejets").json()["sources"]}
        assert max(rej) > 0  # la touche 2 a bien rejeté pour « hors zone »


# --- [ ] Un motif de rejet s'attribue à une touche, et on peut ensuite voir quelle source produit le plus de rejets.
def test_les_motifs_de_rejet_ont_une_touche_et_disent_d_ou_vient_le_bruit(cfg):
    peupler(cfg, 60)
    with TestClient(creer_app(cfg)) as c:
        motifs = c.get("/api/motifs-rejet").json()
        assert {m["id"] for m in motifs} >= {"mauvais_type", "hors_zone", "doublon"} and all(len(m["touche"]) == 1 for m in motifs)
        lignes = c.get("/api/recherches/r13/tri").json()["lignes"]
        web = [x["id"] for x in lignes if x["t"] == ["searxng"]][:6]
        reg = [x["id"] for x in lignes if x["t"] == ["recherche-entreprises"]][:2]
        c.post("/api/recherches/r13/decisions", json={"valeur": "rejeter", "ids": web[:4], "motif": "hors_zone"})
        c.post("/api/recherches/r13/decisions", json={"valeur": "rejeter", "ids": web[4:], "motif": "doublon"})
        c.post("/api/recherches/r13/decisions", json={"valeur": "rejeter", "ids": reg[:1], "motif": "hors_zone"})
        c.post("/api/recherches/r13/decisions", json={"valeur": "rejeter", "ids": reg[1:]})  # un rejet sans motif reste possible
        r = c.get("/api/recherches/r13/rejets").json()
        assert r["total_rejetes"] == 8
        premier = r["sources"][0]  # la source qui produit le plus de rejets vient en tête
        assert premier["source"] == "searxng" and premier["rejetes"] == 6 and premier["motifs"] == {"hors_zone": 4, "doublon": 2}
        assert premier["part"] == round(6 / premier["total"], 3)
        sirene = next(x for x in r["sources"] if x["source"] == "recherche-entreprises")
        assert sirene["motifs"] == {"hors_zone": 1, "sans_motif": 1}
        # le motif est gardé avec le nom (affiché dans Tri) et un motif inconnu ou sur autre chose qu'un rejet est refusé
        assert next(x for x in c.get("/api/recherches/r13/tri").json()["lignes"] if x["id"] == web[0])["mo"] == "hors_zone"
        assert c.post("/api/recherches/r13/decisions", json={"valeur": "rejeter", "ids": web[:1], "motif": "inconnu"}).status_code == 422
        assert c.post("/api/recherches/r13/decisions", json={"valeur": "garder", "ids": web[:1], "motif": "doublon"}).status_code == 422
        # annuler un rejet le retire des comptes
        c.post("/api/recherches/r13/annuler")
        assert c.get("/api/recherches/r13/rejets").json()["total_rejetes"] == 7
        # les touches se changent ; une touche déjà prise (G, R, P, Z) ou en double est refusée avec la raison
        ok = c.put("/api/motifs-rejet", json={"motifs": [{"id": "pas_un_club", "libelle": "Pas un club", "touche": "x"}, {"id": "hors_zone", "libelle": "Hors zone", "touche": "h"}]})
        assert ok.status_code == 200 and [m["touche"] for m in ok.json()] == ["x", "h"]
        assert c.put("/api/motifs-rejet", json={"motifs": [{"id": "a", "libelle": "A", "touche": "g"}]}).status_code == 422
        assert c.put("/api/motifs-rejet", json={"motifs": [{"id": "ab", "libelle": "A", "touche": "x"}, {"id": "cd", "libelle": "B", "touche": "X"}]}).status_code == 422
        assert c.get("/api/motifs-rejet").json()[0]["id"] == "pas_un_club"  # le refus n'a rien écrit


def test_une_touche_de_motif_rejette_avec_son_motif_dans_le_navigateur(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    nom = page.inner_text(".row.sel .r1")
    page.keyboard.press("2")  # « hors zone »
    page.wait_for_selector(".row.d-rejeter")
    assert "rejeté : Hors zone" in page.inner_text(".row.d-rejeter .r2")
    assert page.inner_text(".row.d-rejeter .rd") == "✕"
    # une touche réglée par l'utilisateur
    page.evaluate("window.prompt = () => '7 = Pas un club\\n8 = Hors zone'")
    page.click("#motifs-regler")
    page.wait_for_selector("button[data-motif] kbd:text('7')")
    page.keyboard.press("7")
    page.wait_for_function("[...document.querySelectorAll('.row.d-rejeter .r2')].some(e => e.textContent.includes('Pas un club'))")
    assert nom


# --- [ ] Le niveau de confiance d'une source se règle depuis Tri.
def test_la_confiance_d_une_source_se_regle_depuis_la_fiche_d_un_nom(cfg):
    peupler(cfg, 12)
    with TestClient(creer_app(cfg)) as c:
        nid = next(x["id"] for x in c.get("/api/recherches/r13/tri").json()["lignes"] if x["t"] == ["searxng"])
        fiche = c.get(f"/api/recherches/r13/noms/{nid}").json()
        src = next(s for s in fiche["sources"] if s["id"] == "searxng")
        assert 0 <= src["confiance"] <= 1
        assert c.put("/api/reglages/source/searxng", json={"confiance": 0.77}).status_code == 200  # le geste de la fiche : même réglage que dans Réglages
        assert next(s for s in c.get(f"/api/recherches/r13/noms/{nid}").json()["sources"] if s["id"] == "searxng")["confiance"] == 0.77
        assert next(x for x in c.get("/api/reglages").json()["parties"]["recherche"] if x["id"] == "searxng")["confiance"] == 0.77


def test_le_champ_de_confiance_est_dans_le_panneau_de_detail(navigateur):
    page, _, _ = navigateur
    ouvrir_premier_nom(page)
    page.wait_for_selector("#dtail .dsrc")
    assert page.locator("#dtail input[data-src]").count() >= 1 and page.locator("#dtail button[data-conf]").count() >= 1


# --- [ ] Une confirmation de seconde main qui recopie une source déjà comptée n'ajoute pas de point.
def test_une_confirmation_de_seconde_main_ne_compte_pas_deux_fois():
    from pilote.pont.faits import endroits_comptes

    reg = {"source": "recherche-entreprises", "classe": "registre", "main": "premiere", "lieu": "registre:recherche-entreprises"}
    page1 = {"source": "searxng", "classe": "web", "main": "seconde", "lieu": "page:exemple.org"}
    page2 = {"source": "searxng", "classe": "web", "main": "seconde", "lieu": "page:autre.org"}
    ror = {"source": "ror", "classe": "registre", "main": "premiere", "lieu": "registre:ror"}
    assert endroits_comptes([reg]) == 1
    assert endroits_comptes([reg, page1, page2]) == 1  # deux pages qui répètent le registre : toujours UN point
    assert endroits_comptes([reg, ror, page1]) == 2  # deux sources de première main distinctes : deux points
    assert endroits_comptes([page1, page2]) == 2  # sans première main, deux pages indépendantes comptent chacune
    assert endroits_comptes([page1, {**page1, "source": "autre-source"}]) == 1  # la même page vue par deux sources reste une page


# --- Les 4 vues et les classements de la maquette restent ; la vue Tableau est faite par Tabulator.
def test_les_classements_de_la_maquette_sont_tous_la(cfg):
    peupler(cfg, 30)
    with TestClient(creer_app(cfg)) as c:
        ids = {x["id"] for x in c.get("/api/recherches/r13/tri").json()["classements"]}
    assert {"solides", "fragiles", "source", "genre", "endroit", "ressemble", "alpha", "site"} <= ids  # les huit de la maquette


def test_la_vue_tableau_est_un_tabulator_au_clavier(navigateur):
    page, _, _ = navigateur
    page.click('.views button[data-v="tableau"]')
    page.wait_for_selector("#tbl.tabulator .tabulator-row", timeout=15000)
    assert page.evaluate("typeof Tabulator") == "function"
    assert page.locator("#tbl .tabulator-group").count() >= 1  # des groupes (les paquets du classement), repliables
    avant = page.locator("#tbl .tabulator-row:not(.tabulator-group)").count()
    page.locator("#tbl .tabulator-group").first.click()
    page.wait_for_function(f"document.querySelectorAll('#tbl .tabulator-row:not(.tabulator-group)').length < {avant}")
    page.locator("#tbl .tabulator-group").first.click()  # on le rouvre
    nom = page.inner_text("#tbl .tabulator-row:not(.tabulator-group) .r1")
    assert nom
    # le tableau est trié par colonne, par un clic sur l'en-tête
    page.click('#tbl .tabulator-col[tabulator-field="v"]')
    villes = page.evaluate("[...document.querySelector('#tbl .tabulator-group').querySelectorAll('.tabulator-row [tabulator-field=v]')].map(c => c.textContent).filter(Boolean)")  # dans le premier groupe
    assert villes == sorted(villes) or villes == sorted(villes, reverse=True)
    # on décide au clavier depuis le tableau, et la ligne prend le fond de la décision
    page.keyboard.press("g")
    page.wait_for_selector("#tbl .tabulator-row.d-garder")
    assert "✓ gardé" in page.inner_text("#tbl .tabulator-row.d-garder")
    # le tableau n'ajoute ni vert ni rouge ailleurs que sur les décisions, et n'a pas de lignes alternées
    fonds = page.evaluate("[...new Set([...document.querySelectorAll('#tbl .tabulator-row:not(.d-garder):not(.d-rejeter):not(.tabulator-group)')].map(r => getComputedStyle(r).backgroundColor))]")
    assert len(fonds) <= 2, fonds  # le fond normal, plus au plus la ligne survolée ou sélectionnée : jamais un zèbre


def test_captures_pour_l_oeil(navigateur):
    """Garde une trace visuelle (couleur et niveaux de gris) dans donnees/captures/ ; échoue seulement si la page n'a pas pu être photographiée."""
    page, _, cfg = navigateur
    dossier = cfg.donnees / "captures"
    dossier.mkdir(parents=True, exist_ok=True)
    ouvrir_premier_nom(page)
    for touche in ("g", "r", "2", "p"):
        page.keyboard.press(touche)
    page.screenshot(path=str(dossier / "tri_liste.png"))
    page.add_style_tag(content="html{filter:grayscale(1)!important}")
    page.screenshot(path=str(dossier / "tri_liste_gris.png"))
    assert (dossier / "tri_liste_gris.png").stat().st_size > 5000


# --- [ ] La fiche d'un nom montre ce que les sources « vérifier » ont rendu (ex. capture Wayback), avec un lien seulement si c'est une adresse web.
def test_la_fiche_montre_les_verifications(cfg):
    from sqlalchemy import select

    fabrique = peupler(cfg, 3)
    with fabrique.begin() as s:
        cand = s.scalars(select(Candidat).where(Candidat.recherche_id == "r13")).first()
        cand.faits = {"verifications": [{"source": "wayback", "origine": "Wayback Machine (capture du 12/04/2019)", "preuve": "http://web.archive.org/web/2019/x"}, {"source": "wayback", "origine": "", "preuve": "javascript:alert(1)"}]}
        cid = cand.id
    with TestClient(creer_app(cfg)) as c:
        fiche = c.get(f"/api/recherches/r13/noms/{cid}").json()
        assert fiche["verifications"][0] == {"nom": "Wayback Machine", "origine": "Wayback Machine (capture du 12/04/2019)", "preuve": "http://web.archive.org/web/2019/x", "signal": "confirmation"}
        assert fiche["verifications"][1]["preuve"] == "javascript:alert(1)"  # rendue telle quelle : c'est la page qui ne fait un lien que pour http(s)
    js = (RACINE / "static/tri.js").read_text(encoding="utf-8")
    assert "/^https?:" in js and "noopener" in js and "Alerte" in js and "Information" in js  # une alerte ne se présente pas comme une confirmation
