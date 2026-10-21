"""Chasse aux injections HTML (20/10) : une donnée venue d'une source (nom, ville, site, source, relation, preuve de vérification) ou d'une
déclaration (nom de source, de preset) ne doit JAMAIS s'exécuter dans la page. Chaque vue de Tri et Réglages est rendue avec des valeurs
piégées ; le test échoue si un script piégé s'est exécuté ou si une balise piégée existe dans la page."""

import pytest
from conftest import copier_config
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.base import Candidat, Recherche
from pilote.config import charger as charger_cfg

PIEGES = [
    '<img src=x data-pirate onerror="window.__pirate=1">',
    '"><svg data-pirate onload="window.__pirate=2">',
    "'><img src=x data-pirate onerror='window.__pirate=3'>",
    "</script><script>window.__pirate=4</script>",
    "javascript:window.__pirate=5",
]


@pytest.fixture
def cfg(tmp_path):
    return charger_cfg(copier_config(tmp_path))


def peupler_pieges(cfg):
    from pilote.base import creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        s.add(Recherche(id="rp", qui="sednal", sujet={"quoi": PIEGES[0], "inclure": [PIEGES[1]]}, parametres={"verification": True}, etat="terminee"))
        s.flush()
        for i, p in enumerate(PIEGES * 4):
            s.add(Candidat(recherche_id="rp", nom=f"{p} {i}", genre_source=["registre", "presse", "web", "texte"][i % 4], trouve_par=[p, "wikipedia"],
                           nb_endroits=1 + i % 3, genre_de_chose=p, ville=p, pays="FR", site=p if i % 2 else f"https://x.example/{p}",
                           faits={"verifications": [{"source": p, "origine": p, "preuve": p, "signal": "alerte"}],
                                  "relations": [{"type": p, "vers": p}], "numero_officiel": p}))  # fmt: skip


def test_aucune_donnee_piegee_ne_s_execute_dans_tri_ni_reglages(chromium, serveur_vivant, cfg):
    with TestClient(creer_app(cfg)) as c:
        assert c.post("/api/assistant/terminer", json={"etape1": {"pays": "FR", "presets_coches": ["web"], "chercher": [], "plafond": 5},
                                                       "etape2": {"active": True, "mode": "memes", "verifier": []}, "etape3": {"actifs": ["csv"], "dossier": ""}}).status_code == 200
        c.post("/api/presets", json={"nom": "Preset piégé"})
        c.put("/api/presets/preset-piege/infos", json={"nom": PIEGES[0], "phrase": PIEGES[1]})
    peupler_pieges(cfg)
    url = serveur_vivant(creer_app(cfg))
    page = chromium.new_context(viewport={"width": 1400, "height": 900}).new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: (erreurs.append("dialogue : " + d.message), d.dismiss()))
    page.goto(url + "/")
    page.evaluate("localStorage.setItem('g_tri_recherche','rp')")
    page.reload()

    def propre(ou):
        assert page.evaluate("window.__pirate") is None, f"script piégé exécuté : {ou}"
        assert page.locator("[data-pirate]").count() == 0, f"balise piégée dans la page : {ou}"

    page.click('.tab[data-p="tri"]')
    page.wait_for_timeout(600)
    assert "<img src=x" in page.inner_text("#pg-tri")  # les valeurs piégées sont bien là, affichées comme du TEXTE (sinon le test ne prouve rien)
    propre("Tri, liste")
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(300)
    propre("Tri, fiche d'un nom")
    for v in ("colonnes", "tableau", "fiches", "carte", "liste"):
        page.click(f'.views button[data-v="{v}"]')
        page.wait_for_timeout(500)
        propre(f"Tri, vue {v}")
    page.click('.tab[data-p="reglages"]')
    page.evaluate("document.querySelectorAll('details.bloc').forEach(d => d.open = true)")
    page.wait_for_timeout(400)
    assert "<img src=x" in page.inner_text("#presets")  # le preset piégé est affiché, en texte
    propre("Réglages")
    page.click('.tab[data-p="lancement"]')
    page.wait_for_timeout(400)
    propre("Recherches")
    assert [e for e in erreurs if "pirate" in e or "dialogue" in e] == [], erreurs
