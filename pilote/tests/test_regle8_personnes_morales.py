"""Règle 8 (personnes morales seulement) : aucune donnée de personne physique n'entre dans une clé de rapprochement ni dans une copie locale.
Principe repris de NIST SP 800-188 : un quasi-identifiant ne sert jamais de clé de liaison entre enregistrements."""

import re
from pathlib import Path

import pytest
import yaml

from pilote import rapprochements
from pilote.base import Candidat

RACINE = Path(__file__).resolve().parents[1]
PERSONNE = re.compile(r"dir_|dirigeant|civilite|naissance|birth|prenom|patronyme|person", re.IGNORECASE)


def test_la_fiche_de_rapprochement_ne_porte_que_des_champs_de_personne_morale():
    fiche = rapprochements._fiche(Candidat(id=1, nom="Club Test", ville="Lyon", numero_officiel="W1", site="x.fr"))
    assert set(fiche) == {"id", "nom", "ville", "numero", "site"}  # rien d'autre ne peut devenir une clé de liaison


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


@pytest.mark.skipif(not Path("/opt/grappes/config/personnes.yaml").exists(), reason="le dépôt grappes n'est pas à côté")
def test_la_config_personnes_de_grappes_reste_desactivee_et_sans_consommateur_de_rapprochement():
    cfg = yaml.safe_load((Path("/opt/grappes/config/personnes.yaml")).read_text(encoding="utf-8"))
    assert cfg["collecte"] is False  # préparé, non activé : l'activer est une décision de Sednal
    for f in (RACINE / "src" / "pilote").glob("rapprochement*.py"):
        assert "personnes.yaml" not in f.read_text(encoding="utf-8")
