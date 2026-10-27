"""Règle 8 (personnes morales seulement) : aucune donnée de personne physique n'entre dans une clé de rapprochement ni dans une copie locale.
Principe repris de NIST SP 800-188 : un quasi-identifiant ne sert jamais de clé de liaison entre enregistrements."""

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select

from pilote import rapprochements, tri
from pilote.app import creer_app
from pilote.base import Candidat, Recherche
from pilote.grappes_lib import brancher

RACINE = Path(__file__).resolve().parents[1]
PERSONNE = re.compile(r"dir_|dirigeant|civilite|naissance|birth|prenom|patronyme|person", re.IGNORECASE)


def test_la_fiche_de_rapprochement_ne_porte_que_des_champs_de_personne_morale():
    fiche = rapprochements._fiche(Candidat(id=1, nom="Club Test", ville="Lyon", numero_officiel="W1", site="x.fr"))
    assert set(fiche) == {"id", "nom", "ville", "numero", "site", "alias"}  # rien d'autre ne peut devenir une clé de liaison


def test_les_copies_locales_ne_versent_aucune_colonne_de_personne():
    for f in sorted((RACINE / "config" / "sources").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        imp = (((d.get("moteur") or {}).get("parametres") or {}).get("installation") or {}).get("import")
        if not imp:
            continue
        colonnes = str(imp.get("colonnes")) + str(imp.get("jointures") or "")
        assert not PERSONNE.search(colonnes), f"{f.name} verse une colonne de personne : {colonnes}"
        # et un filtre de classe écarte les personnes physiques à l'import
        if f.stem in ("sirene-local", "opensanctions-local"):
            assert imp.get("exclure") or imp.get("garder"), f"{f.name} : aucun filtre de classe contre les personnes physiques"


def test_la_config_personnes_de_grappes_reste_desactivee_et_sans_consommateur_de_rapprochement():
    """Ne se saute JAMAIS, et ne dépend pas de l'endroit où le dépôt est posé.

    On lit la configuration LIVRÉE (`charger()` sans argument), pas la copie temporaire de la fixture `cfg` : cette copie vit dans un dossier
    de test, où « ../grappes » ne mène nulle part, et le test échouait alors sur son propre montage au lieu de vérifier la règle 8."""
    from pilote.config import charger

    livree = charger()
    fichier = livree.grappes_racine / livree.grappes_config / "personnes.yaml"
    assert fichier.exists(), f"config/personnes.yaml de grappes introuvable ({fichier}) : la règle 8 ne peut pas être vérifiée"
    assert yaml.safe_load(fichier.read_text(encoding="utf-8"))["collecte"] is False  # préparé, non activé : l'activer est une décision de Sednal
    for f in (RACINE / "src" / "pilote").glob("rapprochement*.py"):
        assert "personnes.yaml" not in f.read_text(encoding="utf-8")


# --- un compte est une personne tant que son nom ne porte pas d'indice institutionnel (document 24, point 1)
@pytest.fixture
def moteur(cfg):
    brancher(cfg)


def test_un_compte_sans_indice_institutionnel_devient_une_personne(moteur):
    from pilote.regle8 import genre_retenu

    assert genre_retenu("compte", "Marie Dupont") == "personne"
    assert genre_retenu("compte", "mdupont38") == "personne"  # identifiant seul, sans nom lisible : dans le doute, une personne
    assert genre_retenu("compte", "") == "personne"
    assert genre_retenu("compte", "Association des Amis du Vercors") == "compte"
    assert genre_retenu("association", "Marie Dupont") == "association"  # seul le genre « compte » est converti


def _creer(app, noms):
    """Une recherche de comptes ; chaque genre passe par la conversion du pont, comme une vraie source de réseau social."""
    from pilote.regle8 import genre_retenu

    with app.state.fabrique.begin() as s:
        r = Recherche(qui="test", sujet={"quoi": "x"}, parametres={}, etat="terminee")
        s.add(r)
        s.flush()
        for nom, ville in noms:
            s.add(Candidat(recherche_id=r.id, nom=nom, ville=ville, genre_source="compte", nb_endroits=1, pays="FR", faits={}, relations=[], trouve_par=["bluesky"], genre_de_chose=genre_retenu("compte", nom)))
        return r.id


def test_un_compte_de_personne_n_entre_dans_aucune_paire_de_rapprochement(cfg, moteur):
    app = creer_app(cfg)
    with TestClient(app):
        rid = _creer(app, [("Marie Dupont", "Lyon"), ("Marie Dupont", "Lyon"), ("mdupont38", "")])
        assert rapprochements.proposer(cfg, app.state.fabrique, rid) == {"proposes": 0, "comparees": 0}  # écartés avant tout calcul
        rid = _creer(app, [("Association des Amis du Vercors", "Grenoble"), ("Association des amis du Vercors", "Grenoble")])
        assert rapprochements.proposer(cfg, app.state.fabrique, rid)["comparees"] == 2  # un compte d'association entre normalement


def test_la_fiche_d_un_compte_de_personne_reste_affichee_avec_son_genre(cfg, moteur):
    app = creer_app(cfg)
    with TestClient(app):
        rid = _creer(app, [("Marie Dupont", "Lyon")])
        with app.state.fabrique() as s:
            c = s.scalars(select(Candidat).where(Candidat.recherche_id == rid)).one()
            assert (c.nom, c.genre_de_chose) == ("Marie Dupont", "personne")  # rien n'est supprimé (règle 1) : le genre le dit à l'écran


# --- les trois leviers de 27-leviers-regle8-a-faire-par-sednal.md : ni l'un ni l'autre ne débride la règle par défaut


def test_genre_retenu_accepte_des_indices_supplementaires_sans_toucher_au_defaut(moteur):
    """Lever 1 : la liste que Sednal tient dans `config/scoring.yaml` (resultat.indices_institution), passée en plus de celle du moteur."""
    from grappes.personnes import DEFAULT_INSTITUTION_HINTS
    from pilote.regle8 import genre_retenu

    assert genre_retenu("compte", "Comité de Quartier Saint-Bruno") == "personne"  # « comité » n'est pas un indice par défaut
    plus = (*DEFAULT_INSTITUTION_HINTS, "comité")
    assert genre_retenu("compte", "Comité de Quartier Saint-Bruno", plus) == "compte"  # avec l'indice ajouté par configuration
    assert genre_retenu("compte", "Marie Dupont", plus) == "personne"  # un indice en plus ne change rien pour les autres noms


def test_marquer_personne_morale_n_ecrase_pas_le_genre_et_s_annule(cfg, moteur):
    """Lever 2 : une décision sur UNE fiche, qui s'AJOUTE au constat au lieu de l'écraser (règle 1), et qui s'annule."""
    app = creer_app(cfg)
    with TestClient(app):
        rid = _creer(app, [("Les Amis Discrets", "Lyon"), ("Les Amis Discrets", "Lyon"), ("Marie Dupont", "Lyon")])  # aucun indice institutionnel : écartées par défaut
        assert rapprochements.proposer(cfg, app.state.fabrique, rid) == {"proposes": 0, "comparees": 0}
        with app.state.fabrique() as s:
            ids = [c.id for c in s.scalars(select(Candidat).where(Candidat.recherche_id == rid, Candidat.nom == "Les Amis Discrets"))]
        for cid in ids:
            assert tri.marquer_personne_morale(app.state.fabrique, rid, cid, "sednal")["leve"] is True
        with app.state.fabrique() as s:
            c = s.get(Candidat, ids[0])
            assert c.genre_de_chose == "personne"  # le CONSTAT n'est pas réécrit : la levée vit à côté
            assert c.faits["regle8_leve"]["qui"] == "sednal"
            marie = s.scalars(select(Candidat).where(Candidat.recherche_id == rid, Candidat.nom == "Marie Dupont")).one()
            assert marie.genre_de_chose == "personne" and not (marie.faits or {}).get("regle8_leve")  # les autres fiches ne bougent pas
        res = rapprochements.proposer(cfg, app.state.fabrique, rid)  # la levée se lit ici, et nulle part ailleurs
        assert res["comparees"] == 2 and res["proposes"] == 1
        # … et elle s'annule : la fiche ressort du rapprochement, les paires en attente sont retirées
        annule = tri.annuler_personne_morale(app.state.fabrique, rid, ids[0], "sednal")
        assert annule["leve"] is False and annule["rapprochements_retires"] == 1
        with app.state.fabrique() as s:
            assert not (s.get(Candidat, ids[0]).faits or {}).get("regle8_leve")
        assert rapprochements.proposer(cfg, app.state.fabrique, rid)["comparees"] == 1  # une seule fiche levée reste


def test_marquer_personne_morale_refuse_une_fiche_que_la_regle_n_ecarte_pas(cfg, moteur):
    app = creer_app(cfg)
    with TestClient(app):
        rid = _creer(app, [("Association des Amis du Vercors", "Grenoble")])
        with app.state.fabrique() as s:
            cid = s.scalars(select(Candidat).where(Candidat.recherche_id == rid)).one().id
        with pytest.raises(ValueError):
            tri.marquer_personne_morale(app.state.fabrique, rid, cid, "sednal")
        with pytest.raises(ValueError):  # et on n'annule pas une levée qui n'existe pas
            tri.annuler_personne_morale(app.state.fabrique, rid, cid, "sednal")


def test_la_sortie_followthemoney_n_est_pas_ouverte_par_le_levier_de_recherche():
    """Correctif du point 8 de la revue : le levier d'une RECHERCHE ne doit pas écrire une personne physique dans la sortie FtM.

    Le genre seul ne suffit pas à l'en empêcher : avec le levier, il vaut « compte ». C'est le constat de la collecte
    (`regle8_personne`) qui tient la porte, et seule une décision humaine fiche par fiche (`regle8_leve`) la rouvre."""
    import tempfile

    from pilote.formats import ftm

    def ecrit(ligne):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.ftm.json"
            bilan = ftm.ecrire({"lignes": [{"nom": "Marie Dupont", "decision": None, "endroits": 1, "confirmations": 1, "site": "", "fonction": "", **ligne}], "trace": {"recherche": "r"}}, "", {}, f)
            return bool(f.read_text(encoding="utf-8").strip()), bilan["ignorees_personnes_physiques"]

    assert ecrit({"genre": "personne"}) == (False, 1)  # règle 8 par défaut
    assert ecrit({"genre": "compte", "regle8_personne": True}) == (False, 1)  # levier de recherche : le constat tient la porte
    assert ecrit({"genre": "compte"}) == (True, 0)  # un compte d'organisation sort normalement
    assert ecrit({"genre": "personne", "regle8_personne": True, "regle8_leve": True}) == (True, 0)  # décision humaine sur CETTE fiche : elle sort


def test_regle8_afficher_comptes_se_valide_comme_une_case_oui_non():
    """Lever 3 : la case d'une recherche précise, validée par `lancement.valider_options` comme les autres options avancées."""
    from pilote.config import Config
    from pilote.lancement import LancementInvalide, valider_options

    assert valider_options(Config(), {"regle8_afficher_comptes": True})["regle8_afficher_comptes"] is True
    assert valider_options(Config(), {})  == {}  # absente par défaut : la règle s'applique comme partout ailleurs
    with pytest.raises(LancementInvalide):
        valider_options(Config(), {"regle8_afficher_comptes": "oui"})  # pas un booléen : refusé, comme « page entière ou extrait »
