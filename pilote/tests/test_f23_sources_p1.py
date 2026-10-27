"""Sources P1 de la spécification 17 branchées le 26/10 : chacune se charge, son test local passe sur l'exemple enregistré, elle est éteinte à la livraison."""

import pytest

from pilote import reglages as rg
from pilote.sources import charger_sources
from pilote import tests_source

IDS = ["propublica-nonprofit", "photon", "radio-browser", "lemmy", "sepiasearch"]


@pytest.mark.parametrize("ident", IDS)
def test_source_p1_charge_teste_et_eteinte(cfg, ident):
    decls, problemes = charger_sources(cfg)
    assert not problemes and ident in decls
    d = decls[ident]
    assert rg.choix_source(rg.charger_tolerant(cfg)[0], d)["chercher"] is False  # éteinte à la livraison
    assert "personne" not in d.genres  # règle 8 : jamais une recherche par nom de personne physique
    res = tests_source.tester(cfg, d)
    assert res["statut"] == "ok" and res["noms_exemple"], res


NOUVELLES = ["serper", "firecrawl", "guardian", "nyt", "bodacc", "prh-finlande", "amf-info-financiere", "nz-charities", "acnc", "mobilizon", "universites", "mediacloud"]


@pytest.mark.parametrize("ident", NOUVELLES)
def test_source_p1_deuxieme_lot(cfg, ident, monkeypatch):
    decls, problemes = charger_sources(cfg)
    assert not problemes and ident in decls
    d = decls[ident]
    for cle in d.cles:
        monkeypatch.setenv(cle, "cle-de-test")  # le test local ne l'envoie jamais ; il exige seulement qu'elle soit présente
    assert rg.choix_source(rg.charger_tolerant(cfg)[0], d)["chercher"] is False and rg.choix_source(rg.charger_tolerant(cfg)[0], d)["verifier"] is False
    assert "personne" not in d.genres
    res = tests_source.tester(cfg, d)
    assert res["statut"] == "ok", res
    if d.moteur.get("adaptateur"):  # les sources de type « adaptateur » rendent des noms ; les autres passent par le moteur de collecte
        assert res["noms_exemple"]


def test_une_verification_exacte_ne_confirme_que_le_meme_nom(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "cleanco", None)  # le pont tourne dans l'interpréteur de grappes, qui n'a pas cleanco : l'import échouerait ici aussi
    from pilote.adaptateurs.api_json import _exactes

    noms = [{"nom": "DUPONT & DUPONT"}, {"nom": "Dupont Sports SAS"}, {"nom": "Dupont et Dupont"}]
    assert [n["nom"] for n in _exactes(noms, {"correspondance_exacte": True}, {"nom": "Dupont & Dupont"})] == ["DUPONT & DUPONT"]  # casse, accents, ponctuation : oui ; un autre mot : non
    assert _exactes(noms, {}, {"nom": "x"}) == noms  # sans l'option, rien n'est filtré
    assert _exactes(noms, {"correspondance_exacte": True}, {"nom": ""}) == []  # sans nom à vérifier, rien n'est confirmé


def test_un_chemin_peut_viser_le_premier_element_d_une_liste():
    from pilote.adaptateurs.mcp_generique import _lire

    assert _lire({"names": [{"name": "A"}, {"name": "B"}]}, "names.0.name") == "A" and _lire({"names": []}, "names.0.name") is None


# --- [ ] Une source choisie n'est jamais mangée en silence par la collecte web : elle garde un appel, et si elle n'est pas appelée, c'est dit.
def test_une_reserve_d_appels_est_gardee_pour_les_sources_par_adaptateur(cfg, tmp_path):
    import json

    from pilote.executeur_grappes import preparer

    class FauxContexte:
        recherche_id, qui = "r23", "test"
        sujet = {"quoi": "red cross"}
        parametres = {"sources": ["nz-charities", "acnc", "wikipedia"], "profondeur": "normal"}
        dossier = tmp_path / "travail"
        _fabrique = None

        def __init__(self):
            self.dossier.mkdir(parents=True, exist_ok=True)

    spec = preparer(cfg, FauxContexte())
    assert spec["reserve_sources"] == 2 == len(spec["adaptateurs"])  # un appel gardé par source interrogée par adaptateur
    auto = json.loads(json.dumps(spec))  # la spécification écrite est bien celle qui part au pont
    assert auto["limites"]["appels"] >= spec["reserve_sources"]


# --- Partie 1 de test.md : une source qui demande d'attendre (429) est attendue, pas comptée en échec tout de suite
def test_un_429_est_attendu_puis_la_requete_reussit(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    from pilote import adaptateurs

    appels = []

    class Rep:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b'{"ok": true}'

    def ouvrir(req, timeout=0):
        appels.append(1)
        if len(appels) < 3:
            raise urllib.error.HTTPError(req.full_url, 429, "trop", {"Retry-After": "0"}, io.BytesIO(b""))
        return Rep()

    monkeypatch.setattr(urllib.request, "urlopen", ouvrir)
    monkeypatch.setattr(adaptateurs.time, "sleep", lambda s: None)
    assert adaptateurs.Client("x").get_json("https://exemple.example/a") == {"ok": True} and len(appels) == 3
    appels.clear()
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: (_ for _ in ()).throw(urllib.error.HTTPError(req.full_url, 429, "trop", {"Retry-After": "0"}, io.BytesIO(b""))))
    with pytest.raises(adaptateurs.ErreurSource, match="elle demande d'attendre"):
        adaptateurs.Client("x").get_json("https://exemple.example/a")  # trois refus de suite : un échec, dit en français


def test_les_mots_courts_ne_disparaissent_plus_de_la_requete():
    from pilote.adaptateurs import mots_significatifs

    assert mots_significatifs("Air France") == ["Air", "France"] and mots_significatifs("WWF France") == ["WWF", "France"]
    assert mots_significatifs("CEA") == ["CEA"] and mots_significatifs("AS Lyon") == ["AS", "Lyon"]
    assert mots_significatifs("les amis de the Vercors") == ["amis", "Vercors"]  # les petits mots restent écartés


# --- Partie 1 de test.md : une liste de risque n'est pas une sanction (cas réel : Danone, registre de risque d'exportation)
def test_opensanctions_distingue_une_sanction_d_un_registre_de_risque():
    from pilote.adaptateurs import opensanctions

    rep = {"results": [
        {"id": "NK-a", "schema": "Company", "caption": "Danone", "datasets": ["ir_uani_business_registry"], "properties": {"name": ["Danone"], "topics": ["export.risk"]}},
        {"id": "NK-b", "schema": "Company", "caption": "Rosneft", "datasets": ["us_ofac_sdn"], "properties": {"name": ["Rosneft"], "topics": ["sanction"]}},
    ]}  # fmt: skip
    danone = opensanctions.convertir(rep, "Danone")[0]
    assert danone["signal"] == "information" and "qui n'est pas une sanction" in danone["origine"] and "export.risk" in danone["origine"]
    rosneft = opensanctions.convertir(rep, "Rosneft")[0]
    assert rosneft["signal"] == "alerte" and "sanctions ou de criminalité" in rosneft["origine"]


# --- Partie 2 de test.md (F3) : une clé refusée est un échec DIT en français, jamais un succès silencieux
def test_une_cle_refusee_est_un_echec_lisible(tmp_path):
    import json

    from pilote import disjoncteur

    f = tmp_path / "avancement.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in [
        {"evenement": "prise_fin", "prise": "guardian", "statut": "erreur : guardian : HTTP 401"},
        {"evenement": "prise_fin", "prise": "serper", "statut": "arrêté : serper : HTTP 403, arrêt pour ce cycle"},
        {"evenement": "prise_fin", "prise": "exa", "statut": "erreur : exa : HTTP 402"},
        {"evenement": "prise_fin", "prise": "wikipedia", "statut": "ok"},
    ]) + "\n", encoding="utf-8")  # fmt: skip
    r = disjoncteur.issues(f, {"guardian": "guardian", "serper": "serper", "exa": "exa", "wikipedia": "wikipedia"})
    assert r["guardian"]["issue"] == "echec" and "clé d'API est refusée" in r["guardian"]["raison"] and "401" in r["guardian"]["raison"]
    assert r["serper"]["issue"] == "echec" and "clé d'API est refusée" in r["serper"]["raison"]  # avant : « arrêté », donc compté comme ayant répondu
    assert "crédits de la source sont épuisés" in r["exa"]["raison"] and r["wikipedia"]["issue"] == "ok"
