"""La suite pilote dans un vrai navigateur (sauté s'il est absent) : les règles de la spécification qui vivent dans l'interface,
et le balayage des valeurs de style écrites en dur (règle 3)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import copier_config

from pilote.app import creer_app
from pilote.config import charger

STATIC = Path(__file__).resolve().parents[1] / "static" / "suite"


# --- règle 3 : aucune couleur, taille de texte, rayon ni ombre écrits en dur hors des jetons (jetons.css et typo.css sont les sources)
def test_aucune_valeur_de_style_en_dur():
    fautes = []
    for f in [STATIC / "suite.css", *sorted((STATIC / "js").glob("*.js")), STATIC / "index.html"]:
        for n, ligne in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if (
                re.search(r"#[0-9a-fA-F]{3,8}\b(?![\w-])", ligne)
                and "href" not in ligne
                and "&#" not in ligne
                and "aria" not in ligne
            ):
                fautes.append(f"{f.name}:{n} couleur {ligne.strip()[:70]}")
            if re.search(r"\b(rgba?|hsla?)\(", ligne):
                fautes.append(f"{f.name}:{n} rgb/hsl {ligne.strip()[:70]}")
            if f.suffix == ".css" and re.search(
                r"(font-size|border-radius|box-shadow|letter-spacing)\s*:[^;]*\d+(\.\d+)?(px|em|rem)", ligne
            ):
                fautes.append(f"{f.name}:{n} taille/rayon/ombre {ligne.strip()[:70]}")
            if f.suffix == ".css" and re.search(r"(?<!-)\b(padding|margin|gap)[a-z-]*\s*:[^;]*[1-9]\d*px", ligne):
                fautes.append(f"{f.name}:{n} espacement {ligne.strip()[:70]}")
            if f.suffix == ".js" and re.search(
                r"style:\s*\{[^}]*(color|background|fontSize|borderRadius|boxShadow|padding|margin|gap)", ligne
            ):
                fautes.append(f"{f.name}:{n} style en ligne {ligne.strip()[:70]}")
    assert not fautes, "\n".join(fautes)


def test_les_31_pictogrammes_et_le_vocabulaire_ferme():
    assert (
        len(re.findall(r'^  "[a-z-]+":', (STATIC / "js" / "pictogrammes.js").read_text(encoding="utf-8"), re.MULTILINE))
        == 31
    )
    for f in (STATIC / "js").glob("*.js"):
        texte = f.read_text(encoding="utf-8")
        for interdit in (
            "Délier",
            "Réduire",
            "Réinitialiser",
            ">Terminé",
            "Régler",
            "Allumé",
            "inactif",
            "cluster",
            "connecteur",
            "fournisseur",
        ):
            assert interdit not in texte, f"{f.name} emploie « {interdit} » (liste close des mots)"


@pytest.fixture
def page(tmp_path, chromium, serveur_vivant):
    cfg = charger(copier_config(tmp_path))
    app = creer_app(cfg)
    url = serveur_vivant(app)
    p = chromium.new_page(viewport={"width": 1360, "height": 1000})
    erreurs = []
    p.on("pageerror", lambda e: erreurs.append(str(e)))
    p.goto(f"{url}/suite#/recherche")
    p.wait_for_selector(".carte")
    p.url_base = url
    p.erreurs = erreurs
    yield p
    assert not erreurs, erreurs
    p.close()


def aller(page, hash_):
    page.goto(f"{page.url_base}/suite{hash_}")
    page.reload()
    page.wait_for_selector(".carte")


def test_coquille_quatre_onglets_dont_deux_inactifs(page):
    onglets = page.locator(".onglet")
    assert onglets.all_inner_texts() == ["Tableau de bord\nplus tard", "Recherche", "Réglages", "Tri"]
    assert page.locator(".onglet[aria-disabled=true]").count() == 1  # le Tableau de bord reste visible, grisé, inactif
    page.click(".onglet:has-text('Tableau de bord')", force=True)  # Playwright refuse un clic normal sur un bouton aria-disabled
    assert page.locator(".onglet[aria-current=page]").inner_text() == "Recherche"  # rien ne se passe : onglet non conçu
    assert page.locator("h1").count() == 1


def test_retirer_une_source_se_defait_sans_fenetre(page):
    aller(page, "#/reglages")
    page.click(".carte-tete:has-text('Web')")
    page.click("[data-source=tavily] button:has-text('Retirer')")
    assert page.locator(".fenetre, .panneau").count() == 0  # retirer ne demande rien
    page.wait_for_selector("[data-source=tavily]", state="detached")
    page.click("button:has-text('Ajouter Tavily')")
    page.wait_for_selector("[data-source=tavily]")


def test_assistant_ia_passe_par_l_avertissement(page):
    aller(page, "#/reglages")
    page.click(".sous button:has-text('Outils')")
    page.click("[data-outil=ia] button:has-text('Allumer')")
    assert page.locator(".avert-points li").count() == 4
    page.click(".fenetre button:has-text('Annuler')")
    assert "éteint" in page.locator("[data-outil=ia] .etat").inner_text()
    page.click("[data-outil=ia] button:has-text('Allumer')")
    page.click(".fenetre button:has-text('Allumer')")
    page.wait_for_function("document.querySelector('[data-outil=ia] .etat').innerText.includes('opérationnel')")
    page.click("[data-outil=ia] button:has-text('Éteindre')")  # éteindre ne redemande rien
    page.wait_for_function("document.querySelector('[data-outil=ia] .etat').innerText.includes('éteint')")
    assert page.locator(".fenetre").count() == 0
    assert (
        page.locator("[data-outil=traduction] .etat").inner_text().strip() == "opérationnel"
    )  # masculin pour un outil


def test_la_cle_est_masquee_et_jamais_relue(page):
    aller(page, "#/reglages")
    page.click(".carte-tete:has-text('Web')")
    page.click("[data-source=tavily] button:has-text('Modifier')")
    champ = page.locator(".panneau input[type=password]")
    assert champ.count() == 1
    champ.fill("sk-secret-visible-jamais")
    page.click(".panneau button:has-text('Enregistrer')")
    page.wait_for_selector(".panneau", state="detached")
    page.click("[data-source=tavily] button:has-text('Modifier')")
    assert "clé enregistrée" in page.locator(".panneau").inner_text()
    assert (
        "sk-secret-visible-jamais" not in page.content()
        and page.locator(".panneau input[type=password]").input_value() == ""
    )


def test_supprimer_une_recherche_demande_une_fenetre(page):
    page.fill("#app .carte-corps input[type=text] >> nth=0", "club de judo")
    page.click("button:has-text('Lancer la recherche') >> nth=0")
    page.wait_for_selector(".sauvee")
    page.click(".sauvee button:has-text('Supprimer')")
    assert page.locator(".avert-points li").count() >= 2
    page.click(".fenetre button:has-text('Annuler')")
    assert page.locator(".sauvee").count() == 1
    page.click(".sauvee button:has-text('Supprimer')")
    page.click(".fenetre button:has-text('Supprimer')")
    page.wait_for_selector(".sauvee", state="detached")


def test_plan_pose_sans_lien_puis_relie_a_la_main(page):
    page.click("button[aria-label=Replier]")  # l'Aide est posée par-dessus le coin du plan
    page.click(".palette-groupe-tete:has-text('Associations')")
    page.click(".palette-entree:has-text('Registre des associations (France)')")
    assert page.locator(".lien-trait").count() == 0  # poser ne relie à rien, jamais
    assert page.locator("[data-tuile]").count() == 3  # Ta saisie, Grappes, la tuile posée
    assert "posée" in page.locator(".palette-entree:has-text('Registre des associations (France)')").inner_text()
    # déplacer : un glissement n'ouvre pas la fenêtre de tuile
    tuile = page.locator("[data-tuile='associations:dila-joafe'], [data-tuile='assos:registre-associations']").first
    avant = tuile.bounding_box()
    page.mouse.move(avant["x"] + 65, avant["y"] + 32)
    page.mouse.down()
    page.mouse.move(avant["x"] + 165, avant["y"] + 92, steps=6)
    page.mouse.up()
    apres = tuile.bounding_box()
    assert apres["x"] > avant["x"] + 50 and page.locator(".fenetre").count() == 0
    # relier : port de sortie de « Ta saisie », puis clic sur la tuile
    page.click("[data-tuile=saisie] .port.sortie")
    page.click("[data-tuile='assos:registre-associations'] .tuile")
    assert page.locator(".lien-trait").count() == 1 and page.locator(".fenetre").count() == 0
    # la fenêtre de tuile : un clic simple l'ouvre, trois colonnes
    page.click("[data-tuile='assos:registre-associations'] .tuile")
    page.wait_for_selector(".fenetre.w1040")
    assert page.locator(".fenetre .etiquette-col").all_inner_texts() == ["ENTRÉE", "LA TUILE", "SORTIE"]
    page.click(".fenetre button:has-text('Fermer')")
    # retirer la tuile : elle sort du plan avec ses liens, la source reste
    page.click("[data-tuile='assos:registre-associations'] .tuile")
    page.click(".fenetre button:has-text('Retirer la tuile')")
    assert page.locator("[data-tuile]").count() == 2 and page.locator(".lien-trait").count() == 0
    assert (
        page.locator("[data-tuile=saisie] .tuile-retrait").count() == 0
        and page.locator("[data-tuile=saisie]").count() == 1
    )


def test_aide_sans_modele_les_puces_marchent_et_elle_ne_pose_rien(page):
    assert page.locator(".aide-saisie input").is_disabled()
    assert (
        page.locator("button[aria-label=Replier]").count() == 1
        and page.locator(".aide button[aria-label=Fermer]").count() == 0
    )
    page.click(".aide-puce:has-text('Ça veut dire quoi')")
    page.click(".aide-choix .aide-puce:text-is('Retirer')")
    page.wait_for_selector(".bulle-r:has-text('sans rien effacer')")
    page.click(".aide-pied .aide-puce:has-text('Comment je fais')")
    page.click(".aide-choix .aide-puce:has-text('association')")
    page.wait_for_selector(".aide-carte")
    assert page.locator("[data-tuile]").count() == 2  # proposé, pas posé
    page.click(".aide-carte button:has-text('Poser ces tuiles')")
    assert page.locator("[data-tuile]").count() > 2
    page.click(".aide-pied .aide-puce:has-text('Pourquoi ça')")
    page.wait_for_selector(".bulle-r:has-text('rien à signaler')")  # le plan proposé est complet : aucun constat
    page.click("button[aria-label=Replier]")
    page.click(".palette-groupe-tete:has-text('Web')")
    page.click(".palette-entree:has-text('Tavily')")  # une tuile posée seule : isolée
    page.click(".aide-replie")
    page.click(".aide-pied .aide-puce:has-text('Pourquoi ça')")
    page.wait_for_selector(".constat.bloquant")
    assert "Tavily" in page.locator(".constat.bloquant").first.inner_text()
    # replier : une barre de 44 px, jamais fermée
    page.click("button[aria-label=Replier]")
    assert page.locator(".aide-replie").bounding_box()["height"] == 44


def test_focus_visible_et_tout_au_clavier(page):
    aller(page, "#/reglages")
    page.keyboard.press("Tab")
    sorti = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
    assert sorti == "solid"


def test_les_sorties_d_une_condition_se_nomment_oui_ou_non(page):
    page.click("button[aria-label=Replier]")
    page.click(".palette-entree:has-text('Condition')")
    page.click(".palette-entree:has-text('Fusion')")
    cond = page.locator("[data-tuile^='si:']").first
    fus = page.locator("[data-tuile^='fusion:']").first
    page.click("[data-tuile^='si:'] .port.sortie")
    page.click("[data-tuile^='fusion:'] .tuile")
    page.click(
        "[data-tuile^='fusion:'] .tuile"
    )  # ouvre la fenêtre de la fusion : on y vérifie qu'elle n'a pas de puces oui/non
    page.wait_for_selector(".fenetre.w1040")
    assert page.locator(".fenetre .puce:text-is('oui')").count() == 0
    page.click(".fenetre button:has-text('Fermer')")
    page.click("[data-tuile^='si:'] .tuile")
    page.wait_for_selector(".fenetre.w1040")
    page.click(".fenetre .puce:text-is('oui')")
    assert page.locator(".fenetre .puce[aria-pressed=true]").inner_text() == "oui"
    page.click(".fenetre button:has-text('Fermer')")
    assert "oui" in page.locator(".lien-etiquette").text_content()
    assert cond.count() == 1 and fus.count() == 1


def test_onglet_tri_confirmer_et_separer(tmp_path, chromium, serveur_vivant):
    from test_suite_tri import TROIS, creer

    cfg = charger(copier_config(tmp_path))
    app = creer_app(cfg)
    url = serveur_vivant(app)
    p = chromium.new_page(viewport={"width": 1360, "height": 1000})
    erreurs = []
    p.on("pageerror", lambda e: erreurs.append(str(e)))
    p.goto(f"{url}/suite#/tri")
    p.wait_for_selector(".note")
    assert "Aucun rapprochement à examiner" in p.locator(".note").inner_text()  # file vide : un état normal, sans ton badin
    rid, _ = creer(app, TROIS)
    from pilote import rapprochements

    rapprochements.proposer(cfg, app.state.fabrique, rid)
    p.reload()
    p.wait_for_selector(".rapp-carte")
    assert "3 rapprochements à examiner, du plus incertain au plus certain." in p.inner_text(".page-titre")
    pourcentages = [int(x.split()[0]) for x in p.locator(".rapp-confiance .chiffres").all_inner_texts()]
    assert pourcentages == sorted(pourcentages)  # le plus incertain d'abord
    premiere = p.locator(".rapp-carte").first
    assert premiere.locator(".rapp-valeur.accord").count() >= 1 and premiere.locator(".rapp-valeur.desaccord").count() >= 1 and premiere.locator(".rapp-valeur.absence").count() >= 1
    assert premiere.locator(".fiab").all_inner_texts() == ["B", "C"]
    assert premiere.locator("button.principal").inner_text() == "Confirmer" and premiere.locator("button.danger").count() == 0  # ni l'un ni l'autre n'est un bouton danger
    assert not p.locator(".carte.ouverte:has-text('Déjà tranchés')").count()  # fermée par défaut
    premiere.locator("button:has-text('Confirmer')").click()
    p.wait_for_function("document.querySelectorAll('.rapp-carte').length === 2")
    p.click(".carte-tete:has-text('Déjà tranchés')")
    assert "1 décision" in p.inner_text(".carte-tete:has-text('Déjà tranchés')")
    assert "Confirmé" in p.inner_text(".sauvee")
    p.click(".sauvee button:has-text('Séparer')")  # les deux gestes se refont
    p.wait_for_function("document.querySelector('.sauvee .mode').innerText === 'Séparé'")
    assert not erreurs, erreurs
    p.close()
