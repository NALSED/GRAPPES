"""Règle 8 (personnes morales seulement) : aucune donnée de personne physique n'entre dans une clé de rapprochement ni dans une copie locale.
Principe repris de NIST SP 800-188 : un quasi-identifiant ne sert jamais de clé de liaison entre enregistrements."""

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select

from pilote import rapprochements
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


def test_la_config_personnes_de_grappes_reste_desactivee_et_sans_consommateur_de_rapprochement(cfg):
    """Ne se saute JAMAIS : la racine de grappes vient de la configuration (comme `grappes_lib`), pas d'un chemin en dur. Configuration introuvable : échec."""
    fichier = cfg.grappes_racine / cfg.grappes_config / "personnes.yaml"
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
