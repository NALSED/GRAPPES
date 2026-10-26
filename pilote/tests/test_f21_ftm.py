"""Format FollowTheMoney (idée reprise d'Aleph, voir inspi/sources.md) : entités valides, identifiants stables, provenance dans les notes."""

from __future__ import annotations

import json

import pytest

from pilote import formats
from pilote.formats import ftm

TRACE = {
    "date": "2026-10-26T10:00:00+01:00",
    "recherche": "r21",
    "sources": [],
    "sujet": "x",
    "nombre": 3,
    "filtre": "tout",
}


def ligne(**k):
    base = {
        "id": 1,
        "nom": "Club Alpin",
        "ville": "Lyon",
        "pays": "FR",
        "genre": "association",
        "site": "https://alpin.example",
        "numero_officiel": "W691",
        "decision": "garder",
        "sources": ["Registre des associations", "Wikidata"],
    }
    return {**base, **k}


def ecrire(tmp_path, lignes):
    f = tmp_path / "resultat.ftm"
    ftm.ecrire({"lignes": lignes, "trace": TRACE}, "detail", {}, f)
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]


def test_le_format_est_decouvert():
    assert "ftm" in formats.decouvrir()


def test_entites_valides_pour_la_bibliotheque_followthemoney(tmp_path):
    model = pytest.importorskip("followthemoney").model
    ents = ecrire(
        tmp_path,
        [
            ligne(),
            ligne(nom="ACME SA", genre="entreprise", numero_officiel="123"),
            ligne(nom="Jean Test", genre="personne", numero_officiel=""),
            ligne(nom="Salle des fêtes", genre="lieu"),
            ligne(nom="Fête", genre="evenement"),
            ligne(nom="Page", genre="page", pays="France"),
        ],
    )
    assert [e["schema"] for e in ents] == ["Organization", "Company", "Address", "Event", "LegalEntity"]
    for e in ents:
        assert model.get_proxy(e).id == e["id"]  # la bibliothèque officielle accepte chaque entité
    assert "country" not in ents[-1]["properties"]  # « France » n'est pas un code à deux lettres : rien n'est deviné


def test_identifiant_stable_et_distinct(tmp_path):
    a = ecrire(tmp_path, [ligne()])[0]["id"]
    assert (
        ecrire(tmp_path, [ligne(id=99, ville="Paris", decision=None)])[0]["id"] == a
    )  # même nom, même numéro, même pays : même entité
    assert ecrire(tmp_path, [ligne(numero_officiel="W999")])[0]["id"] != a
    assert ecrire(tmp_path, [ligne(nom="CLUB ALPIN ")])[0]["id"] == a  # casse et espaces ne créent pas de doublon


def test_la_provenance_est_dans_les_notes(tmp_path):
    notes = ecrire(tmp_path, [ligne()])[0]["properties"]["notes"]
    assert "Trouvé par : Registre des associations" in notes and "Trouvé par : Wikidata" in notes
    assert any("Collecté le 2026-10-26 par pilote (recherche r21)" in n for n in notes)
    assert "Décision de l'utilisateur : gardé." in notes
    sans = ecrire(tmp_path, [ligne(decision=None)])[0]["properties"]["notes"]
    assert not any("Décision" in n for n in sans)  # pas de décision, rien d'écrit à sa place


def test_aucune_fiche_de_personne_physique_n_est_ecrite(tmp_path):
    """Règle 8 : grappes vise les personnes morales. Une fiche « personne » ne sort jamais en `Person`, et l'absence est dite."""
    f = tmp_path / "r.ftm"
    res = ftm.ecrire({"lignes": [ligne(), ligne(nom="Jean Test", genre="personne")], "trace": TRACE}, "detail", {}, f)
    assert [json.loads(x)["properties"]["name"][0] for x in f.read_text(encoding="utf-8").splitlines()] == ["Club Alpin"]
    assert res["ignorees_personnes_physiques"] == 1
