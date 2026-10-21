"""Faits d'un candidat : preuves, origine (la plus solide), endroits, numéro officiel. Les objets sont ceux de grappes."""

import sys
from types import SimpleNamespace as NS

from pilote.config import charger

sys.path.insert(0, str(charger().grappes_racine / "src"))
from grappes.canon import site_key

from pilote.pont.faits import Provenance, faits_candidat, origine_de, preuves


def cand(ref, nom="X", registres=(), citants=(), ner=(), ville=""):
    return NS(ref=ref, nom=nom, registres=set(registres), citants=set(citants), ner_sites=set(ner), ville=ville)


PROV = Provenance(
    jetons={"sirene_naf": "recherche-entreprises", "sirene_nom": "recherche-entreprises", "wikidata": "wikidata"},
    origines={"recherche-entreprises": "registre", "wikidata": "registre", "searxng": "web", "rss_liberation": "presse", "ror": "registre"},
    mains={"recherche-entreprises": "premiere", "wikidata": "premiere", "searxng": "seconde", "rss_liberation": "seconde", "ror": "premiere"},
    eco_par_site={"exemple.org": "web", "journal.fr": "rss"},
    fournisseurs_par_site={"exemple.org": {"searxng"}, "journal.fr": {"rss_liberation"}},
)


def test_origine_la_plus_solide_des_preuves():
    assert origine_de(preuves(cand("reg:x:1", registres={"sirene_nom"}, ner={"exemple.org"}), PROV, site_key)) == "registre"
    assert origine_de(preuves(cand("ner:a", ner={"journal.fr", "exemple.org"}), PROV, site_key)) == "presse"
    assert origine_de(preuves(cand("ner:a", ner={"exemple.org"}), PROV, site_key)) == "web"
    assert origine_de(preuves(cand("ner:a", ner={"inconnu"}), PROV, site_key)) == "texte"


def test_un_nom_est_rattache_aux_sources_pas_a_des_etiquettes_techniques():
    p = preuves(cand("reg:x:1", registres={"sirene_naf", "sirene_nom", "wikidata"}, ner={"exemple.org"}), PROV, site_key)
    sources = sorted({x["source"] for x in p})
    assert sources == ["recherche-entreprises", "searxng", "wikidata"]  # sirene_naf et sirene_nom ne font qu'une source
    assert {x["source"]: x["main"] for x in p} == {"recherche-entreprises": "premiere", "searxng": "seconde", "wikidata": "premiere"}


def test_faits_complets_et_relations_des_sources():
    d = NS(siren="422893214", domaine="fenix.fr", type_candidat="administration", liens={"relations": '[{"type": "fait_partie_de", "vers": "Groupe Exemple"}]', "coordonnees": '{"lat": 1.5, "lon": 2.5}'})
    f = faits_candidat(cand("reg:ror:1", "Fenix", {"ror"}, {"web:fenix.fr"}, ville="Toulouse"), [d], site_key, "FR", PROV)
    assert f["genre_source"] == "registre" and f["numero_officiel"] == "422893214" and f["site"] == "fenix.fr" and f["ville"] == "Toulouse"
    assert f["genre_de_chose"] == "administration" and f["relations"] == [{"type": "fait_partie_de", "vers": "Groupe Exemple"}]
    assert f["faits"]["coordonnees"] == {"lat": 1.5, "lon": 2.5} and f["nb_endroits"] == 1 and "ror" in f["trouve_par"]  # le site web peut recopier le registre : pas de second point


def test_aucun_code_national_ni_identifiant_d_encyclopedie_dans_le_numero():
    d = NS(siren="", domaine="", type_candidat="", liens={})
    assert faits_candidat(cand("reg:wikidata:Q3126705", "X", {"wikidata"}), [d], site_key, "FR", PROV)["numero_officiel"] == ""
