"""Document 22 : le type de source « fichier_local » (CSV / TSV / JSONL / SQLite, zip), interrogé sans appel réseau."""

import json
import sqlite3
import zipfile

import pytest

from pilote import adaptateurs
from pilote import fichier_local as fl
from pilote.adaptateurs import fichier_local as adapt

UNITES = (
    "siren,denominationUniteLegale,sigleUniteLegale,categorieJuridiqueUniteLegale\n"
    "111111111,Boulangerie Exemple,,5499\n"
    "222222222,Association des Amis de l'Étang,AAE,9220\n"
    "333333333,DUPUIS Jean,,1000\n"  # entrepreneur individuel : une personne physique, jamais versée (règle 8)
    "444444444,Fondation Étang Bleu,,9300\n"
    "555555555,Boulangerie Exemple Nord,,5710\n"
)
ETABLISSEMENTS = (
    "siren,etablissementSiege,libelleCommuneEtablissement\n"
    "111111111,true,LYON\n"
    "111111111,false,PARIS\n"
    "222222222,true,GRENOBLE\n"
)
SPEC_SIRENE = {
    "format": "csv", "membre_zip": "unites",
    "colonnes": {"nom": "denominationUniteLegale", "alias": "sigleUniteLegale", "numero": "siren"},
    "defauts": {"pays": "FR", "genre": "entreprise"},
    "exclure": {"categorieJuridiqueUniteLegale": "^1"},
}  # fmt: skip


@pytest.fixture
def dossier(tmp_path):
    z = tmp_path / "sirene.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("unites.csv", UNITES)
    e = tmp_path / "etab.csv"
    e.write_text(ETABLISSEMENTS, encoding="utf-8")
    copies = tmp_path / "copies"
    bilan = fl.importer(z, "sirene-test", copies, {**SPEC_SIRENE, "jointures": [{"fichier": str(e), "format": "csv", "cle": "siren", "colonnes": {"ville": "libelleCommuneEtablissement"}, "garder": {"etablissementSiege": "^true$"}}]})
    assert bilan["lignes"] == 4 and bilan["ecartees"] == 1  # la personne physique est écartée à l'import
    return copies


def test_une_personne_physique_n_est_jamais_versee(dossier):
    assert fl.chercher_par_mots(dossier, "sirene-test", "DUPUIS Jean") == []
    assert fl.exact(dossier, "sirene-test", "dupuis jean") == []


def test_recherche_exacte_insensible_aux_accents_et_aux_alias(dossier):
    assert [r["numero"] for r in fl.exact(dossier, "sirene-test", "ASSOCIATION DES AMIS DE L'ETANG")] == ["222222222"]
    assert [r["numero"] for r in fl.exact(dossier, "sirene-test", "AAE")] == ["222222222"]  # le sigle est un alias
    assert fl.exact(dossier, "sirene-test", "Boulangerie") == []  # jamais de ressemblance en mode exact


def test_recherche_par_mots_exact_d_abord_puis_prefixe_et_numero(dossier):
    r = fl.chercher_par_mots(dossier, "sirene-test", "boulangerie exemple")
    assert [x["numero"] for x in r] == ["111111111", "555555555"]  # le nom identique d'abord, puis celui qui le contient
    assert [x["numero"] for x in fl.chercher_par_mots(dossier, "sirene-test", "boulang")] == ["111111111", "555555555"]  # dernier mot en préfixe
    assert [x["numero"] for x in fl.chercher_par_mots(dossier, "sirene-test", "222222222")] == ["222222222"]
    assert fl.chercher_par_mots(dossier, "sirene-test", "inexistant zzz") == []


def test_la_jointure_complete_la_ville_du_siege_seulement(dossier):
    assert fl.exact(dossier, "sirene-test", "Boulangerie Exemple")[0]["ville"] == "LYON"  # pas PARIS : seul le siège compte
    assert fl.exact(dossier, "sirene-test", "Fondation Étang Bleu")[0].get("ville") is None


def test_tsv_jsonl_sqlite(tmp_path):
    t = tmp_path / "a.tsv"
    t.write_text("n\tv\nAlpha Club\tLille\n", encoding="utf-8")
    fl.importer(t, "tsv", tmp_path, {"format": "tsv", "colonnes": {"nom": "n", "ville": "v"}})
    assert fl.exact(tmp_path, "tsv", "alpha club")[0]["ville"] == "Lille"
    j = tmp_path / "a.jsonl"
    j.write_text(json.dumps({"caption": "Société Beta", "names": ["Beta SA", "Beta Holding"]}) + "\nceci n'est pas du json\n", encoding="utf-8")
    fl.importer(j, "jl", tmp_path, {"format": "jsonl", "colonnes": {"nom": "caption", "alias": "names"}})
    assert fl.exact(tmp_path, "jl", "BETA HOLDING")[0]["nom"] == "Société Beta"
    fl.importer(tmp_path / "bases" / "jl.sqlite", "copie", tmp_path, {"format": "sqlite"})
    assert fl.exact(tmp_path, "copie", "Société Beta")


def test_erreurs_en_francais(tmp_path):
    with pytest.raises(fl.BaseLocaleErreur, match="pas installée"):
        fl.exact(tmp_path, "absente", "x")
    with pytest.raises(fl.BaseLocaleErreur, match="minuscules"):
        fl.chemin_base(tmp_path, "../evasion")
    with pytest.raises(fl.BaseLocaleErreur, match="colonne porte le nom"):
        fl.importer(tmp_path / "x", "b", tmp_path, {"format": "csv", "colonnes": {}})
    vide = sqlite3.connect(tmp_path / "vide.sqlite")
    vide.close()
    with pytest.raises(fl.BaseLocaleErreur, match="tables"):
        fl.importer(tmp_path / "vide.sqlite", "v", tmp_path, {"format": "sqlite"})



def test_adaptateur_recherche_et_verification_sans_reseau(dossier):
    mod = adaptateurs.charger("fichier_local")
    client = adaptateurs.Client("sirene-test")
    p = {"base": "sirene-test", "_dossier_copies": str(dossier), "origine": "Base SIRENE (copie locale)"}
    trouves = mod.chercher({"quoi": "amis etang"}, client, p)
    assert trouves[0]["numero"] == "222222222" and client.appels == 0  # aucun appel compté : pas de quota
    v = mod.chercher({"nom": "BOULANGERIE EXEMPLE", "quoi": "BOULANGERIE EXEMPLE"}, client, p)
    assert v[0]["signal"] == "confirmation" and v[0]["numero"] == "111111111"
    assert mod.chercher({"nom": "Société Inconnue"}, client, p) == []


def test_signalements_graves_et_informations(tmp_path):
    t = tmp_path / "os.csv"
    t.write_text("caption,schema,topics\nRosneft,Company,sanction\nDanone,Company,export.risk\nJean Martin,Person,sanction\n", encoding="utf-8")
    bilan = fl.importer(t, "os", tmp_path, {"format": "csv", "colonnes": {"nom": "caption", "themes": "topics"}, "garder": {"schema": "^(Company|Organization|PublicBody)$"}})
    assert bilan["lignes"] == 2  # la personne n'entre jamais
    p = {"base": "os", "_dossier_copies": str(tmp_path), "themes_graves": ["sanction", "crime"]}
    client = adaptateurs.Client("os")
    assert adaptateurs.charger("fichier_local").chercher({"nom": "Rosneft"}, client, p)[0]["signal"] == "alerte"
    assert adaptateurs.charger("fichier_local").chercher({"nom": "Danone"}, client, p)[0]["signal"] == "information"


def test_arret_demande_arrete_la_source_locale(dossier):
    client = adaptateurs.Client("sirene-test", doit_s_arreter=lambda: True)
    with pytest.raises(adaptateurs.LimiteAtteinte):
        adapt.chercher({"quoi": "x"}, client, {"base": "sirene-test", "_dossier_copies": str(dossier)})


def test_la_copie_n_apparait_qu_entiere(tmp_path):
    t = tmp_path / "a.csv"
    t.write_text("n\nAlpha\n", encoding="utf-8")
    jointure = {"fichier": str(tmp_path / "absent.csv"), "format": "csv", "cle": "n", "colonnes": {"pays": "p"}}
    with pytest.raises(OSError):
        fl.importer(t, "casse", tmp_path, {"format": "csv", "colonnes": {"nom": "n"}, "jointures": [jointure]})
    assert list((tmp_path / "bases").iterdir()) == []  # ni copie définitive ni fichier partiel


def test_geojson_et_plusieurs_fichiers(tmp_path):
    g = tmp_path / "limites.geojson"
    g.write_text(json.dumps({"features": [{"properties": {"shapeName": "Auvergne-Rhône-Alpes", "shapeID": "A1"}, "geometry": {"type": "Polygon", "coordinates": [[[2.0, 44.0], [7.0, 44.0], [7.0, 47.0], [2.0, 47.0]]]}}]}), encoding="utf-8")
    a = tmp_path / "a.csv"
    a.write_text("n\nAlpha Club\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("n\nBeta Club\n", encoding="utf-8")
    fl.importer(g, "geo", tmp_path, {"format": "geojson", "colonnes": {"nom": "shapeName", "numero": "shapeID", "detail": "emprise"}})
    assert fl.exact(tmp_path, "geo", "auvergne rhone alpes")[0]["detail"] == "2.0000,44.0000,7.0000,47.0000"
    fl.importer([a, b], "deux", tmp_path, {"format": "csv", "colonnes": {"nom": "n"}})
    assert {r["nom"] for r in fl.chercher_par_mots(tmp_path, "deux", "club")} == {"Alpha Club", "Beta Club"}


def test_colonnes_alternatives_et_motif(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("﻿id;observation;titre;libcom\n111P0110001731;W111003619;Stade Un;Rieux\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("﻿id;titre;adrs_libcommune\nW511000001;Compagnie Deux;Burcy\n", encoding="utf-8")
    spec = {"format": "csv", "delimiteur": ";", "encodage": "utf-8-sig", "colonnes": {"nom": "titre", "numero": {"premier": ["id", "observation"], "motif": r"^W\d{9}$"}, "ville": "adrs_libcommune|libcom"}}
    fl.importer([a, b], "rna-t", tmp_path, spec)
    assert fl.exact(tmp_path, "rna-t", "stade un")[0]["numero"] == "W111003619" and fl.exact(tmp_path, "rna-t", "stade un")[0]["ville"] == "Rieux"
    assert fl.exact(tmp_path, "rna-t", "compagnie deux")[0]["numero"] == "W511000001"


# --- Le VRAI moteur : une copie locale vérifie TOUS les noms, sans être bornée par la limite d'appels (la limite constatée au test du 26/10 : 3 à 4 noms sur plus de 100)
def test_le_moteur_verifie_tous_les_noms_contre_la_copie_locale(tmp_path):
    import sys
    import time

    from conftest import copier_config
    from fastapi.testclient import TestClient

    from pilote.app import creer_app
    from pilote.config import charger

    cfg = charger(copier_config(tmp_path))
    cible = tmp_path / "cibles.csv"
    cible.write_text("name,aliases,schema,sanctions,dataset\nClub 007,,Company,Mesure UE 2023,Liste UE\nClub 031,,Company,,Registre de risque\n", encoding="utf-8")
    fl.importer(cible, "opensanctions", cfg.dossier_copies, {"format": "csv", "colonnes": {"nom": "name", "alias": "aliases", "themes": "sanctions", "detail": "dataset"}, "garder": {"schema": "^Company$"}})
    prog = tmp_path / "quarante.py"
    prog.write_text('import json, sys\njson.load(sys.stdin)\nprint(json.dumps([{"nom": "Club %03d" % i, "origine": "p"} for i in range(40)]))\n', encoding="utf-8")
    with TestClient(creer_app(cfg)) as c:
        r = c.post("/api/programmes-locaux", json={"nom": "quarante", "commande": [sys.executable, str(prog)], "genres": ["association"], "pays": ["FR"]})
        assert r.status_code == 201, r.text
        src = r.json()["id"]
        for s in c.get("/api/suite/etat").json()["sources"]:
            if s["id"] != src and s["chercher"]:
                c.post(f"/api/suite/sources/{s['id']}/eteindre", json={})
        assert c.post(f"/api/suite/sources/{src}/allumer", json={}).status_code == 200
        assert c.post("/api/suite/sources/opensanctions-local/allumer", json={"confirme": True}).status_code == 200
        etat = {s["id"]: s for s in c.get("/api/suite/etat").json()["sources"]}
        assert etat["opensanctions-local"]["copie"]["installee"] is True and etat["opensanctions-local"]["quota"] is None  # illimité : pas de quota
        assert etat["sirene-local"]["copie"]["installee"] is False  # la copie n'est pas là : dit, et la source reste « à vérifier »
        plan = {"nodes": [{"id": "saisie", "nom": "Ta saisie", "role": "ENTREE", "ref": None, "x": 0, "y": 0, "opts": []}, {"id": "grappes", "nom": "Grappes", "role": "GRAPPES", "ref": None, "x": 0, "y": 0, "opts": []},
                          {"id": "p", "nom": "p", "role": "CHERCHER", "ref": src, "x": 0, "y": 0, "opts": []}, {"id": "os", "nom": "os", "role": "VERIFIER", "ref": "opensanctions-local", "x": 0, "y": 0, "opts": []}],
                "edges": [{"from": "saisie", "to": "p"}, {"from": "p", "to": "os"}, {"from": "os", "to": "grappes"}]}  # fmt: skip
        r = c.post("/api/suite/lancer", json={"saisie": "clubs", "mode": "Avancée", "plan": plan, "cats": ["perso"], "pays": "FR", "profondeur": "strict"})
        assert r.status_code == 202, r.text
        rid = r.json()["recherche_id"]
        t0 = time.time()
        while time.time() - t0 < 120 and c.get(f"/api/recherches/{rid}").json()["etat"] not in ("terminee", "echec", "arretee", "interrompue"):
            time.sleep(0.3)
        assert c.get(f"/api/recherches/{rid}").json()["etat"] == "terminee"
        bilan = c.get("/api/suite/etat").json()["recherches"][0]["verification"]
        assert "40 sur 40 noms vérifiés" in bilan, bilan  # profondeur « strict » = 5 appels : une API n'aurait examiné qu'une poignée de noms
        cands = json.loads(next(cfg.dossier_recherche(rid).rglob("candidats.json")).read_text(encoding="utf-8"))
        signaux = {x["nom"]: [v["signal"] for v in (x.get("faits") or {}).get("verifications", [])] for x in cands}
        assert signaux["Club 007"] == ["alerte"] and signaux["Club 031"] == ["information"] and signaux["Club 005"] == []


def test_le_poids_classe_les_homonymes_et_l_expression_passe_avant_les_mots(tmp_path):
    t = tmp_path / "u.csv"
    t.write_text(
        "siren,nom,effectif,etat\n"
        "100000001,RENAULT,00,C\n"  # homonyme cessé
        "100000002,RENAULT,53,A\n"  # la vraie : grande, active
        "100000003,RENAULT,01,A\n"
        "100000004,FRANCE AIR,05,A\n"
        "100000005,SOCIETE AIR FRANCE,53,A\n",
        encoding="utf-8",
    )
    spec = {"format": "csv", "colonnes": {"nom": "nom", "numero": "siren"}, "poids": {"colonne": "effectif", "actif": {"colonne": "etat", "valeur": "A", "bonus": 100}}}
    fl.importer(t, "u", tmp_path, spec)
    assert [r["numero"] for r in fl.exact(tmp_path, "u", "renault")] == ["100000002", "100000003", "100000001"]
    assert fl.chercher_par_mots(tmp_path, "u", "air france")[0]["numero"] == "100000005"  # l'expression « air france » avant « france air »


def test_la_traduction_pivote_par_l_anglais_en_deux_appels(monkeypatch):
    from pilote import suite_traduction as st

    appels = []
    monkeypatch.setattr(st, "_appel", lambda url, texte, de, vers: appels.append((de, vers)) or f"{texte}>{vers}")
    assert st.traduire("http://x", "Association", "fr", "es") == "Association>en>es"
    assert appels == [("fr", "en"), ("en", "es")]
    appels.clear()
    assert st.traduire("http://x", "Association", "fr", "en") == "Association>en" and appels == [("fr", "en")]


def test_gdelt_garde_la_presse_francaise_et_les_organisations_seulement(monkeypatch):
    import io
    import zipfile

    sys_path = __import__("sys").path
    sys_path.insert(0, "outils")
    import gdelt_local as g

    def ligne(source, orgs, traduction=""):
        c = [""] * 27
        c[1], c[3], c[4], c[11], c[12], c[14], c[25] = "20261026120000", source, "https://" + source + "/a", "Jean Dupont", "Jean Dupont,10", orgs, traduction
        return "\t".join(c)

    contenu = "\n".join([
        ligne("lemonde.fr", "Danone,12;Croix-Rouge,40;Danone,90"),  # site en .fr : gardé, une ligne par organisation
        ligne("example.com", "Acme,5"),  # ni .fr ni français : écarté
        ligne("example.be", "Fondation Test,5", "srclc:fra;eng:Moses"),  # article en français : gardé
        ligne("lefigaro.fr", ""),  # aucune organisation : rien
    ])
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("x.gkg.csv", contenu)
    monkeypatch.setattr(g, "_telecharger", lambda url: zbuf.getvalue() if "translation" not in url else None)
    lignes = g.lire("20261026120000")
    assert {(n, s) for n, s, _, _ in lignes} == {("Danone", "lemonde.fr"), ("Croix-Rouge", "lemonde.fr"), ("Fondation Test", "example.be")}
    assert not any("Dupont" in n for n, *_ in lignes)  # les personnes ne sont jamais lues
    monkeypatch.setattr(g, "_telecharger", lambda url: None)
    assert g.lire("20261026120000") is None  # fichier absent : rien à noter comme traité
