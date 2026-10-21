"""REVUE du 19/10 : un test par défaut trouvé, pour qu'aucun ne revienne.

Chaque test nomme le défaut qu'il garde fermé. Les quatre premiers avaient été constatés par mesure avant correction.
"""

import json
import threading

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import disjoncteur, etat_sources
from pilote.app import creer_app
from pilote.moteur_sources import materialiser, verificatrices
from pilote.pont.verification import verifier_candidats


class FauxContexte:
    """Ce que `ExecuteurGrappes` attend d'un contexte de recherche : deux gestes, qu'on garde pour les regarder."""

    def __init__(self):
        self.avances, self.notes = {}, []

    def avancer(self, **champs):
        self.avances.update(champs)

    def noter(self, evenement, **detail):
        self.notes.append((evenement, detail))


def copie_de_config(tmp_path):
    cible = tmp_path / "copie"
    (cible / "recherche").mkdir(parents=True, exist_ok=True)
    (cible / "recherche.yaml").write_text("actifs: []\n", encoding="utf-8")
    return cible


def verif_active(c, mode="plus"):
    assert c.put("/api/reglages/verification", json={"active": True, "mode": mode}).status_code == 200


# --- [ ] Plusieurs changements de réglages envoyés en même temps : aucun n'est perdu (lecture-modification-écriture sous verrou).
def test_des_reglages_simultanes_ne_s_ecrasent_pas(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        ids = [x["id"] for x in c.get("/api/reglages").json()["parties"]["recherche"]][:12]
        assert len(ids) == 12
        codes: list[int] = []
        fils = [threading.Thread(target=lambda i=i: codes.append(c.put(f"/api/reglages/source/{i}", json={"confiance": 0.42}).status_code)) for i in ids]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        assert codes == [200] * 12
        reg = yaml.safe_load(cfg.fichier_reglages.read_text(encoding="utf-8"))
        perdues = [i for i in ids if (reg.get("sources") or {}).get(i, {}).get("confiance") != 0.42]
        assert perdues == [], f"réglages perdus : {perdues}"


# --- [ ] Un reglages.yaml retouché à la main avec des valeurs impossibles : la page s'affiche, le dit, et garde les défauts.
def test_une_valeur_impossible_n_empeche_pas_d_ouvrir_les_reglages(cfg):
    cfg.fichier_reglages.write_text(yaml.safe_dump({
        "version": 1, "budget": "gratuit", "verification": [],
        "sources": {"searxng": {"confiance": "beaucoup", "cout": {"vers_dollar": "cher"}}},
    }), encoding="utf-8")  # fmt: skip
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.get("/api/reglages")
        assert r.status_code == 200  # avant : 500, et la page qui aurait permis de corriger était justement celle-là
        d = r.json()
        raisons = " ".join(p["raison"] for p in d["problemes"])
        assert "le budget" in raisons and "niveau de confiance" in raisons and "vers_dollar" in raisons
        s = next(x for x in d["parties"]["recherche"] if x["id"] == "searxng")
        assert s["confiance"] == 0.3 and s["cout_effectif"]["vers_dollar"] == 0.0  # valeurs de la déclaration
        assert d["budget"]["plafond_mensuel_usd"] == 10.0 and d["verification"]["active"] is True


# --- [ ] Une source de VÉRIFICATION payante est écartée par le plafond de dépense, comme une source de recherche.
def test_une_verificatrice_payante_est_ecartee_par_le_plafond(cfg, tmp_path):
    f = cfg.dossier_config / "sources" / "wayback.yaml"
    d = yaml.safe_load(f.read_text(encoding="utf-8"))
    d["cout"] = {"unite": "appel", "vers_dollar": 1.0, "par_appel": 1, "gratuit_par_mois": 0}
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        verif_active(c)
        assert c.put("/api/reglages/source/wayback", json={"verifier": True, "confirme": True}).status_code == 200
    assert [x.id for x in verificatrices(cfg, {})] == ["wayback"]
    mat = materialiser(cfg, copie_de_config(tmp_path), {"sources": [], "_budget": {"appels_max": 200, "plafond": 0.0, "depense": 0.0, "unites": {}}})
    assert mat.verificateurs == [] and [e["source"] for e in mat.exclues_budget] == ["wayback"]
    mat = materialiser(cfg, copie_de_config(tmp_path), {"sources": [], "_budget": {"appels_max": 200, "plafond": 500.0, "depense": 0.0, "unites": {}}})
    assert [v["source"] for v in mat.verificateurs] == ["wayback"]  # de la place sous le plafond : elle est utilisée


# --- [ ] Une source de vérification qui échoue est comptée : disjoncteur, bilan, et phrase du bilan.
def test_une_verificatrice_en_echec_est_comptee_comme_les_autres(cfg, tmp_path):
    from pilote.executeur_grappes import ExecuteurGrappes

    with TestClient(creer_app(cfg, lambda c: None)) as c:
        verif_active(c)
        c.put("/api/reglages/source/wayback", json={"verifier": True})
    mat = materialiser(cfg, copie_de_config(tmp_path), {"sources": ["searxng"]})
    assert [v["source"] for v in mat.verificateurs] == ["wayback"]
    av = tmp_path / "avancement.jsonl"
    av.write_text("\n".join(json.dumps(x) for x in [
        {"evenement": "source_ok", "prise": "searxng"},
        {"evenement": "source_echec", "prise": "wayback", "raison": "la source ne répond pas"},
    ]), encoding="utf-8")  # fmt: skip
    spec = {"sources": mat.ids, "verificateurs": mat.verificateurs, "jetons": mat.jetons}
    ctx = FauxContexte()
    for _ in range(disjoncteur.SEUIL):
        ExecuteurGrappes(cfg).faire_le_bilan(ctx, spec, av)
    e = etat_sources.lire(cfg)["wayback"]
    assert e["erreurs_de_suite"] == disjoncteur.SEUIL and e["disjoncteur"]  # avant : jamais comptée, jamais mise en pause
    assert ctx.avances["sources_bilan"]["total"] == 2 and ctx.avances["sources_bilan"]["repondu"] == 1
    assert "1 source sur 2 a répondu" in ctx.avances["sources_bilan"]["phrase"]
    assert [x["source"] for x in ctx.avances["sources_bilan"]["echecs"]] == ["wayback"]
    # mise en pause : la recherche suivante ne l'appelle plus, et le dit
    mat2 = materialiser(cfg, copie_de_config(tmp_path / "deux"), {"sources": ["searxng"]})
    assert mat2.verificateurs == [] and [p["source"] for p in mat2.en_pause] == ["wayback"]


# --- Reprise automatique du disjoncteur après un délai (décision de Sednal, 20/10).


def _mettre_en_pause_depuis(cfg, sid: str, il_y_a_s: float) -> None:
    """Pose un disjoncteur dont la date « depuis » est dans le passé, sans passer par une vraie recherche."""
    from datetime import UTC, datetime, timedelta

    depuis = (datetime.now(UTC) - timedelta(seconds=il_y_a_s)).isoformat(timespec="seconds")
    etat_sources.noter(cfg, sid, teste_le=depuis, statut="ok", erreurs_de_suite=disjoncteur.SEUIL,
                       disjoncteur={"depuis": depuis, "raison": f"{disjoncteur.SEUIL} erreurs de suite"})  # fmt: skip


# --- [ ] `en_pause` est une lecture PURE (n'écrit jamais) : une source dont le délai est passé n'y figure plus, mais le fichier n'est pas touché.
def test_en_pause_n_ecrit_jamais_et_oublie_une_pause_perimee(cfg):
    _mettre_en_pause_depuis(cfg, "wayback", disjoncteur.DELAI_REPRISE_S + 60)  # délai largement dépassé
    avant = cfg.fichier_etat_sources.read_bytes()
    assert disjoncteur.en_pause(cfg, ["wayback"]) == {}  # plus écartée : elle sera retentée
    assert cfg.fichier_etat_sources.read_bytes() == avant  # mais rien n'a été écrit par la seule lecture
    _mettre_en_pause_depuis(cfg, "wayback", 60)  # mise en pause il y a 1 minute : largement dans le délai
    assert "wayback" in disjoncteur.en_pause(cfg, ["wayback"])  # toujours écartée


# --- [ ] Reprise automatique : la source est retentée ; si elle répond, le disjoncteur se lève ; si elle échoue encore, il se réarme (date fraîche).
def test_une_source_en_pause_perimee_est_retentee_puis_levee_si_elle_repond(cfg, tmp_path):
    from pilote.executeur_grappes import ExecuteurGrappes

    _mettre_en_pause_depuis(cfg, "wayback", disjoncteur.DELAI_REPRISE_S + 60)
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        verif_active(c)
        c.put("/api/reglages/source/wayback", json={"verifier": True})
    mat = materialiser(cfg, copie_de_config(tmp_path), {"sources": ["searxng"]})
    assert [v["source"] for v in mat.verificateurs] == ["wayback"] and mat.en_pause == []  # réessayée, pas écartée
    av = tmp_path / "avancement.jsonl"
    av.write_text(json.dumps({"evenement": "source_ok", "prise": "wayback"}) + "\n" + json.dumps({"evenement": "source_ok", "prise": "searxng"}),
                  encoding="utf-8")  # fmt: skip
    spec = {"sources": mat.ids, "verificateurs": mat.verificateurs, "jetons": mat.jetons}
    ExecuteurGrappes(cfg).faire_le_bilan(FauxContexte(), spec, av)
    e = etat_sources.lire(cfg)["wayback"]
    assert e["disjoncteur"] is None and e["erreurs_de_suite"] == 0  # a répondu : la pause est levée pour de bon


def test_une_source_en_pause_perimee_retentee_qui_echoue_encore_se_rearme(cfg, tmp_path):
    from pilote.executeur_grappes import ExecuteurGrappes

    ancien = (disjoncteur.DELAI_REPRISE_S + 60)
    _mettre_en_pause_depuis(cfg, "wayback", ancien)
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        verif_active(c)
        c.put("/api/reglages/source/wayback", json={"verifier": True})
    mat = materialiser(cfg, copie_de_config(tmp_path), {"sources": ["searxng"]})
    assert mat.en_pause == []  # réessayée
    av = tmp_path / "avancement.jsonl"
    av.write_text(json.dumps({"evenement": "source_echec", "prise": "wayback", "raison": "la source ne répond pas"})
                  + "\n" + json.dumps({"evenement": "source_ok", "prise": "searxng"}), encoding="utf-8")  # fmt: skip
    spec = {"sources": mat.ids, "verificateurs": mat.verificateurs, "jetons": mat.jetons}
    ExecuteurGrappes(cfg).faire_le_bilan(FauxContexte(), spec, av)
    e = etat_sources.lire(cfg)["wayback"]
    assert e["disjoncteur"] is not None  # retombée en panne : réarmée
    assert disjoncteur.reprise_dans_s(e["disjoncteur"]) > disjoncteur.DELAI_REPRISE_S - 5  # avec une date FRAÎCHE, pas l'ancienne
    assert "wayback" in disjoncteur.en_pause(cfg, ["wayback"])  # de nouveau écartée, pour un nouveau délai complet


# --- [ ] Réglages : la phrase dit le délai restant, sans jamais rien écrire.
def test_la_phrase_de_reprise_compte_le_delai_sans_rien_ecrire(cfg):
    _mettre_en_pause_depuis(cfg, "wayback", 60)  # il y a 1 minute
    avant = cfg.fichier_etat_sources.read_bytes()
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        ligne = next(x for x in c.get("/api/reglages").json()["parties"]["verification"] if x["id"] == "wayback")
    assert "En pause" in ligne["etat_phrase"] and "Reprise automatique dans environ 19 minute" in ligne["etat_phrase"]
    assert ligne["voyant"] == ["warn", "en pause"]  # toujours orange : rien ne garantit encore qu'elle répondra
    assert cfg.fichier_etat_sources.read_bytes() == avant  # ouvrir Réglages n'écrit jamais (règle du fichier 01)
    _mettre_en_pause_depuis(cfg, "wayback", disjoncteur.DELAI_REPRISE_S + 1)  # délai dépassé
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        ligne = next(x for x in c.get("/api/reglages").json()["parties"]["verification"] if x["id"] == "wayback")
    assert "Reprise automatique à la prochaine recherche." in ligne["etat_phrase"]


# --- [ ] La reprise manuelle reste immédiate, sans attendre le délai (geste de l'utilisateur toujours disponible).
def test_la_reprise_manuelle_reste_immediate(cfg):
    _mettre_en_pause_depuis(cfg, "wayback", 60)  # tout juste mise en pause : loin du délai automatique
    assert "wayback" in disjoncteur.en_pause(cfg, ["wayback"])
    disjoncteur.reprendre(cfg, "wayback")
    assert disjoncteur.en_pause(cfg, ["wayback"]) == {}
    assert etat_sources.lire(cfg)["wayback"]["disjoncteur"] is None


# --- [ ] Une vérification coupée au milieu est DITE : elle ne ressemble pas à une vérification sans trouvaille.
def test_une_verification_coupee_est_dite(cfg, monkeypatch):
    from pilote import adaptateurs
    from pilote.executeur_grappes import ExecuteurGrappes

    appels = {"n": 0}

    class Faux:
        @staticmethod
        def chercher(entree, client, parametres):
            appels["n"] += 1
            return []

    monkeypatch.setattr(adaptateurs, "charger", lambda nom: Faux)
    lignes = [{"nom": f"N{i}", "site": f"n{i}.example"} for i in range(5)]
    spec = {"verificateurs": [{"source": "wayback", "module": "wayback", "verifie_sur": "site"}]}
    bilans = verifier_candidats(lignes, spec, {}, lambda: appels["n"] >= 2, 60.0, lambda *a, **k: None)
    assert bilans == [{"source": "wayback", "examines": 2, "a_verifier": 5, "trouves": 0, "complete": False, "raison": "arrêt ou limite d'appels atteinte"}]
    ctx = FauxContexte()
    ExecuteurGrappes(cfg).dire_la_verification(ctx, bilans)
    assert ctx.avances["verifications"] == bilans
    assert ctx.notes == [("verification_incomplete", {"source": "wayback", "examines": 2, "a_verifier": 5, "raison": "arrêt ou limite d'appels atteinte"})]
    # une vérification complète ne se plaint pas
    ctx2 = FauxContexte()
    ExecuteurGrappes(cfg).dire_la_verification(ctx2, [{"source": "wayback", "examines": 5, "a_verifier": 5, "trouves": 1, "complete": True, "raison": ""}])
    assert ctx2.notes == []


# --- [ ] Le bilan de vérification arrive jusqu'à la page Tri.
def test_la_page_tri_dit_la_verification_incomplete(cfg):
    from sqlalchemy import select

    from pilote.base import Candidat, Recherche, creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        s.add(Recherche(id="r17", qui="sednal", sujet={"quoi": "clubs"}, parametres={"verification": True}, etat="terminee",
                        avancement={"verifications": [{"source": "wayback", "examines": 2, "a_verifier": 5, "trouves": 1, "complete": False, "raison": "limite de temps"}]}))  # fmt: skip
        s.flush()
        s.add(Candidat(recherche_id="r17", nom="Club Exemple", genre_source="web", trouve_par=["searxng"], nb_endroits=1, faits={}))
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        v = c.get("/api/recherches/r17/tri").json()["recherche"]["verifications"]
        assert v[0]["nom"] == "Wayback Machine" and v[0]["examines"] == 2 and v[0]["complete"] is False
    with fabrique() as s:
        assert s.scalar(select(Candidat.nom).where(Candidat.recherche_id == "r17")) == "Club Exemple"


# --- [ ] Un nom qui n'existe pas rend 404, jamais une panne.
def test_un_nom_inexistant_rend_404(cfg):
    from pilote.base import Recherche, creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        s.add(Recherche(id="r17b", qui="sednal", sujet={"quoi": "x"}, parametres={}, etat="terminee"))
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        assert c.get("/api/recherches/r17b/noms/999999").status_code == 404


# --- [ ] Un nom d'hôte qui n'est pas la boucle locale est refusé (un domaine extérieur pointant sur 127.0.0.1).
def test_un_nom_d_hote_etranger_est_refuse(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        assert c.get("/api/sante").status_code == 200
        assert c.get("/api/sante", headers={"host": "piege.example"}).status_code == 400


# --- [ ] Page Ajout : l'adresse du service d'identifiants d'un hébergeur est refusée, y compris par redirection.
def test_une_adresse_lien_local_est_refusee(cfg):
    from pilote.ajout import AjoutInvalide, appeler, verifier_adresse

    verifier_adresse("http://127.0.0.1:12345/api")  # une base locale reste un usage voulu
    for mauvaise in ("http://169.254.169.254/latest/meta-data/", "http://[fe80::1]/x"):
        with pytest.raises(AjoutInvalide):
            verifier_adresse(mauvaise)
        with pytest.raises(AjoutInvalide):
            appeler(cfg, mauvaise)


# --- [ ] Un filtre actif garde son bouton, même s'il ne reste qu'une seule valeur (sinon on ne peut plus le retirer).
def test_un_filtre_actif_garde_son_bouton(cfg):
    from pilote import classements as cl
    from pilote import tri_filtres

    lignes = [cl.Ligne(1, "A", "web", 1, ["searxng"], "", "Lille", "FR", "", "", None)]
    f = tri_filtres.facettes(lignes, tri_filtres.lire_filtres(["pays:FR"]), "", lambda t: t, None)
    pays = next((x for x in f if x["id"] == "pays"), None)
    assert pays and [v["valeur"] for v in pays["valeurs"]] == ["FR"] and pays["valeurs"][0]["actif"] is True
    assert not any(x["id"] == "ville" for x in tri_filtres.facettes(lignes, {}, "", lambda t: t, None))  # une seule valeur, aucun filtre : pas de facette


# --- Seconde revue (19/10, soir) : défauts trouvés dans les correctifs eux-mêmes.


# --- [ ] Rejouer l'étape 2 de l'assistant n'annule pas le mode de vérification choisi dans Réglages.
def test_rejouer_l_assistant_ne_perd_pas_le_mode_de_verification(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        verif_active(c, "plus")
        c.put("/api/reglages/source/wayback", json={"verifier": True})
        assert [d.id for d in verificatrices(cfg, {})] == ["wayback"]
        r = c.post("/api/assistant/etape/2", json={"donnees": {"active": True, "verifier": ["wayback"]}})
        assert r.status_code == 200
        assert c.get("/api/reglages").json()["verification"]["mode"] == "plus"  # avant : retombait à « memes », en silence
        assert [d.id for d in verificatrices(cfg, {})] == ["wayback"]
        # le mode se change quand on le DIT
        assert c.post("/api/assistant/etape/2", json={"donnees": {"active": True, "mode": "memes", "verifier": ["wayback"]}}).status_code == 200
        assert c.get("/api/reglages").json()["verification"]["mode"] == "memes" and verificatrices(cfg, {}) == []


# --- [ ] Les adresses où les hébergeurs distribuent leurs identifiants sont toutes refusées, pas seulement les « lien-local ».
def test_toutes_les_adresses_de_metadonnees_sont_refusees():
    from pilote.ajout import AjoutInvalide, verifier_adresse

    for mauvaise in ("http://169.254.169.254/", "http://[fe80::1]/x", "http://100.100.100.200/latest/", "http://[fd00:ec2::254]/"):
        with pytest.raises(AjoutInvalide):
            verifier_adresse(mauvaise)
    for bonne in ("http://127.0.0.1:12345/api", "http://192.168.1.10/base.json", "https://api.exemple.example/v1"):
        verifier_adresse(bonne)  # le réseau local et l'extérieur restent des usages voulus


# --- [ ] Le prix d'un test réel tient compte du quota gratuit déjà consommé : jamais « gratuit » puis facturé.
def test_le_prix_du_test_reel_compte_le_quota_deja_consomme():
    from pilote import tests_source
    from pilote.sources import Declaration

    cout = {"unite": "requete", "vers_dollar": 0.008, "par_appel": 1, "gratuit_par_mois": 1000}
    d = Declaration("x", "X", "", "", ["club"], ["monde"], [], [], ["web"], "seconde", "api", "", cout, 0.3,
                    {"chercher": False, "verifier": False}, ["chercher"], "", {"en_ligne": True, "local": False}, {})  # fmt: skip
    assert tests_source.prix_du_test(d, cout, 0.0)["gratuit"] is True  # quota intact
    paye = tests_source.prix_du_test(d, cout, 1000.0)  # quota épuisé
    assert paye["gratuit"] is False and paye["dollars"] > 0 and "plafond" in paye["phrase"]


# --- [ ] La carte ne nomme dans sa légende que les familles de liens réellement dessinées.
def test_la_carte_ne_promet_que_les_liens_dessines(cfg):
    from pilote import carte_liens
    from pilote.base import Candidat, Recherche, creer_fabrique

    fabrique = creer_fabrique(cfg.url_base)
    with fabrique.begin() as s:
        s.add(Recherche(id="r17c", qui="sednal", sujet={"quoi": "x"}, parametres={}, etat="terminee"))
        s.flush()
        s.add(Candidat(recherche_id="r17c", nom="Mère SA", genre_source="registre", trouve_par=["gleif"], nb_endroits=1, faits={},
                       relations=[{"type": "maison_mere", "vers": "Fille SA"}]))  # fmt: skip
        s.add(Candidat(recherche_id="r17c", nom="Fille SA", genre_source="registre", trouve_par=["gleif"], nb_endroits=1, faits={}))
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        ids = [x["id"] for x in c.get("/api/recherches/r17c/tri").json()["lignes"]]
        c.post("/api/recherches/r17c/decisions", json={"valeur": "garder", "ids": ids})
    carte = carte_liens.construire(fabrique, "r17c")
    assert [a["famille"] for a in carte["aretes"]] == ["maison_mere"]
    assert set(carte["familles"]) == {"maison_mere"}  # « même adresse » n'est plus annoncée : rien ne la fournit


# --- Branchement des sources dont les clés sont obtenues (19/10) : Companies House, CourtListener, Apify, OpenSanctions.


def exemple(nom):
    from pathlib import Path

    return json.loads((Path(__file__).parent.parent / f"config/sources/exemples/{nom}.json").read_text(encoding="utf-8"))


# --- [ ] CourtListener : une information (jamais une alerte), seulement sur une partie au nom EXACT, seulement aux États-Unis.
def test_courtlistener_ne_signale_que_les_parties_au_nom_exact():
    from pilote.adaptateurs import courtlistener

    rep = exemple("courtlistener")
    r = courtlistener.convertir(rep, "apex dynamics, llc")  # casse et ponctuation : sans importance
    assert len(r) == 1 and r[0]["signal"] == "information" and "1 affaire américaine" in r[0]["origine"] and r[0]["numero"].startswith("https://www.courtlistener.com/opinion/")
    assert courtlistener.convertir(rep, "Meridian Systems Corp") [0]["signal"] == "information"  # l'autre partie de l'affaire
    assert courtlistener.convertir(rep, "Apex") == []  # un mot cité n'est pas une partie
    assert courtlistener.convertir(rep, "Club de handball") == [] and courtlistener.convertir(rep, " ") == []


def test_courtlistener_ne_fait_aucun_appel_hors_des_etats_unis_ni_sans_cle():
    from pilote.adaptateurs import ErreurSource, courtlistener

    class SansReseau:
        def get_json(self, *a, **k):
            raise AssertionError("aucun appel ici")

    assert courtlistener.chercher({"nom": "Club", "pays": "FR"}, SansReseau(), {"_cle": "x"}) == []  # hors États-Unis
    with pytest.raises(ErreurSource):
        courtlistener.chercher({"nom": "Club", "pays": "US"}, SansReseau(), {"_cle": ""})


# --- [ ] Companies House : une source de recherche du preset Entreprises, clé en identifiant (mot de passe vide), Royaume-Uni.
def test_companies_house_se_lit_comme_une_source_de_registre(cfg):
    from pilote.adaptateurs import api_json
    from pilote.sources import charger_sources

    d = charger_sources(cfg)[0]["companies-house"]
    assert d.cles == ["COMPANIES_HOUSE_API_KEY"] and d.defaut == {"chercher": False, "verifier": False} and "entreprises" in d.usages and d.pays == ["GB"]
    assert d.moteur["parametres"]["auth"]["type"] == "basic" and d.main == "premiere" and d.origine == "registre"
    noms = api_json.convertir(exemple("companies-house"), d.moteur["parametres"])
    assert len(noms) == 2 and all(n["pays"] == "GB" and n["genre"] == "entreprise" and n["numero"] for n in noms)
    en_tetes, extra = api_json._entetes({"type": "basic"}, "cle-secrete")
    import base64

    assert en_tetes == {"Authorization": "Basic " + base64.b64encode(b"cle-secrete:").decode()} and extra == {}


# --- [ ] Aucune clé n'est lue sans elle : les sources branchées restent éteintes tant que la clé manque.
def test_les_sources_branchees_restent_eteintes_sans_cle(cfg):
    from pilote.moteur_sources import choisies

    with TestClient(creer_app(cfg, lambda c: None)) as c:
        for sid in ("companies-house", "courtlistener", "opensanctions", "apify-instagram", "apify-facebook"):
            c.put(f"/api/reglages/source/{sid}", json={"chercher": sid in ("companies-house", "apify-instagram", "apify-facebook"), "verifier": sid in ("courtlistener", "opensanctions"), "confirme": True})
        c.put("/api/reglages/verification", json={"active": True, "mode": "plus"})
    assert [d.id for d in choisies(cfg, {}) if d.id in ("companies-house", "apify-instagram", "apify-facebook")] == []  # clés absentes
    assert [d.id for d in verificatrices(cfg, {})] == []


# --- [ ] Les sources qui demandent une clé, une fois la clé présente, sont retenues : les verificatrices par nom aussi.
def test_les_cles_presentes_allument_les_sources(cfg):
    from pilote import cles
    from pilote.moteur_sources import choisies

    for nom in ("COMPANIES_HOUSE_API_KEY", "OPENSANCTIONS_API_KEY", "COURTLISTENER_API_KEY"):
        cles.ecrire(cfg, nom, "valeur-de-test-123456")
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        c.put("/api/reglages/source/companies-house", json={"chercher": True})
        c.put("/api/reglages/source/courtlistener", json={"verifier": True})
        c.put("/api/reglages/source/opensanctions", json={"verifier": True})
        c.put("/api/reglages/verification", json={"active": True, "mode": "plus"})
    assert "companies-house" in [d.id for d in choisies(cfg, {})]
    assert {d.id for d in verificatrices(cfg, {})} == {"courtlistener", "opensanctions"}
    mode = oct(cfg.fichiers_secrets[0].stat().st_mode & 0o777)
    assert mode == "0o600"  # le fichier de clés n'est lisible que par son propriétaire


# --- [ ] OpenSanctions rend le type le plus précis (« Company »), pas « Organization » : une société sanctionnée n'est pas manquée.
def test_opensanctions_voit_les_societes_et_jamais_les_personnes():
    from pilote.adaptateurs import opensanctions

    def rep(schema):
        return {"results": [{"id": "NK-1", "caption": "PMC Wagner", "schema": schema, "properties": {"name": ["PMC Wagner"]}, "datasets": ["ua_nsdc_sanctions"]}]}

    for ok in ("Company", "Organization", "PublicBody"):
        assert opensanctions.convertir(rep(ok), "pmc wagner")[0]["signal"] == "alerte", ok  # avant : « Company » était ignorée
    for non in ("Person", "LegalEntity", "Vessel"):
        assert opensanctions.convertir(rep(non), "PMC Wagner") == [], non


# --- [ ] Un compte à recherches limitées : la vérification s'arrête au plafond de candidats, et le DIT.
def test_le_plafond_de_candidats_limite_les_credits_et_est_dit(monkeypatch):
    from pilote import adaptateurs

    appels = []
    monkeypatch.setattr(adaptateurs, "charger", lambda nom: type("M", (), {"chercher": staticmethod(lambda e, c, p: appels.append(e["site"]) or [])}))
    lignes = [{"nom": f"N{i}", "site": f"n{i}.example.fr"} for i in range(25)]
    spec = {"verificateurs": [{"source": "source-limitee", "module": "module_limite", "verifie_sur": "site", "parametres": {"max_candidats": 10}}]}
    b = verifier_candidats(lignes, spec, {}, lambda: False, 60.0, lambda *a, **k: None)[0]
    assert len(appels) == 10 and appels == [f"n{i}.example.fr" for i in range(10)]  # les 10 premiers, donc les mieux classés
    assert b["examines"] == 10 and b["a_verifier"] == 25 and b["complete"] is False and "plafond de 10" in b["raison"]


# --- [ ] Sans clé une vérificatrice est écartée ; avec la clé et le mode « plus », elle est retenue.
def test_une_verificatrice_n_est_retenue_qu_avec_sa_cle_et_le_mode_plus(cfg):
    from pilote import cles

    with TestClient(creer_app(cfg, lambda c: None)) as c:
        c.put("/api/reglages/source/courtlistener", json={"verifier": True})
        verif_active(c, "plus")
        assert "courtlistener" not in [d.id for d in verificatrices(cfg, {})]  # clé absente
        cles.ecrire(cfg, "COURTLISTENER_API_KEY", "valeur-de-test-123456")
        assert "courtlistener" in [d.id for d in verificatrices(cfg, {})]
        verif_active(c, "memes")
        assert "courtlistener" not in [d.id for d in verificatrices(cfg, {})]  # source de vérification seule : réservée au mode « plus »
