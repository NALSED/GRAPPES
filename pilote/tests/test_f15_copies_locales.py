"""Fiche 15, chapitre 2 — Copies locales : jamais sans accord, poids et place dits avant, copie partielle toujours affichée, pas de filtre par mot-clé."""

from __future__ import annotations

import json
import shutil
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote import catalogue_pays, copies_locales
from pilote.app import creer_app
from pilote.refus import ConfigRefusee

CONTENU = b"x" * 300_000


@pytest.fixture
def serveur():
    mode = {"tronque": False, "sans_poids": False, "gets": 0}

    class H(BaseHTTPRequestHandler):
        def _entetes(self):
            self.send_response(200)
            if not mode["sans_poids"]:
                self.send_header("Content-Length", str(len(CONTENU)))
            self.end_headers()

        def do_HEAD(self):
            self._entetes()

        def do_GET(self):
            mode["gets"] += 1
            self._entetes()
            self.wfile.write(CONTENU[: len(CONTENU) // 2] if mode["tronque"] else CONTENU)

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}", mode
    s.shutdown()


@pytest.fixture
def cfgc(cfg, serveur):
    """La configuration de test avec UN pays au catalogue dont le fichier est sur le serveur local."""
    d = catalogue_pays.dossier(cfg)
    for f in d.glob("*.yaml"):
        f.unlink()
    base = {"id": "carte", "nom": "Carte", "contenu": "x", "acces": "fichier", "licence": "ODbL", "url": serveur[0] + "/page", "telechargement": serveur[0] + "/f.bin", "verifie_le": "2026-10-18"}
    (d / "FR.yaml").write_text(yaml.safe_dump({"pays": "FR", "nom": "France", "bases": [base, {**base, "id": "en-ligne", "telechargement": None}][:1]}), encoding="utf-8")
    return cfg


def test_sans_accord_rien_n_est_telecharge(cfgc, serveur):
    with pytest.raises(ConfigRefusee, match="non confirmé"):
        copies_locales.telecharger(cfgc, "FR", "carte", confirme=False, qui="t")
    assert serveur[1]["gets"] == 0 and copies_locales.lister(cfgc) == [] and not copies_locales.dossier(cfgc).exists()


def test_la_proposition_dit_poids_place_et_licence_sans_rien_ecrire(cfgc, serveur):
    p = copies_locales.proposer(cfgc, "fr", "carte")
    assert p["octets"] == len(CONTENU) and p["tient"] and p["licence"] == "ODbL" and p["poids"].endswith("Mo")
    assert serveur[1]["gets"] == 0 and not copies_locales.dossier(cfgc).exists()


def test_telechargement_accepte_garde_le_fichier_le_registre_et_le_journal(cfgc):
    r = copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="sednal")
    assert (cfgc.dossier_copies / r["fichier"]).read_bytes() == CONTENU and r["phrase"] == "copie locale complète, FR"
    assert [c["id"] for c in copies_locales.lister(cfgc)] == ["FR-carte"] and "copie_locale_telechargee" in cfgc.journal_actions.read_text(encoding="utf-8")
    assert not list(copies_locales.dossier(cfgc).rglob("*.part"))


def test_place_insuffisante_refuse_avant_d_ecrire(cfgc, serveur, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(10**9, 10**9 - 1000, 1000))
    with pytest.raises(ConfigRefusee, match="Pas assez de place"):
        copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t")
    assert serveur[1]["gets"] == 0 and copies_locales.lister(cfgc) == []


def test_poids_inconnu_refuse(cfgc, serveur):
    serveur[1]["sans_poids"] = True
    with pytest.raises(ConfigRefusee, match="n'annonce pas le poids"):
        copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t")
    assert serveur[1]["gets"] == 0


def test_fichier_tronque_n_est_jamais_garde_comme_une_copie(cfgc, serveur):
    serveur[1]["tronque"] = True
    with pytest.raises(ConfigRefusee, match="échoué"):
        copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t")
    assert copies_locales.lister(cfgc) == [] and not [f for f in copies_locales.dossier(cfgc).rglob("*") if f.is_file()]


def test_pas_de_filtre_par_mot_cle():
    with pytest.raises(ConfigRefusee, match="Pas de filtre par mot-clé"):
        copies_locales.refuser_filtre_mot_cle("handball")
    copies_locales.refuser_filtre_mot_cle("")  # aucun filtre : permis


def test_la_couverture_dit_pays_different_copie_partielle_et_age(cfgc):
    copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t")
    assert copies_locales.couverture(cfgc, {"pays": "FR"}) == []
    assert "pas GB" in copies_locales.couverture(cfgc, {"pays": "GB"})[0] and "en ligne" in copies_locales.couverture(cfgc, {"pays": "GB"})[0]
    reg = json.loads((cfgc.donnees / "copies_locales.json").read_text(encoding="utf-8"))
    reg[0].update(partielle=True, zone="Isère", telechargee_le=(datetime.now(UTC) - timedelta(days=45)).isoformat(timespec="seconds"))
    (cfgc.donnees / "copies_locales.json").write_text(json.dumps(reg), encoding="utf-8")
    phrases = copies_locales.couverture(cfgc, {"pays": "FR"})
    assert any("zone Isère seulement" in p for p in phrases) and any("45 jours" in p and "à mettre à jour" in p for p in phrases)


def test_l_api_de_bout_en_bout_et_l_estimation_previent(cfgc):
    c = TestClient(creer_app(cfgc))
    assert c.post("/api/copies-locales", json={"pays": "FR", "base": "carte"}).status_code == 422  # pas d'accord
    assert c.post("/api/copies-locales", json={"pays": "FR", "base": "carte", "confirme": True, "mot_cle": "handball"}).status_code == 422
    assert c.get("/api/copies-locales/proposition", params={"pays": "FR", "base": "carte"}).json()["tient"] is True
    assert c.post("/api/copies-locales", json={"pays": "FR", "base": "carte", "confirme": True, "qui": "sednal"}).status_code == 201
    assert c.get("/api/copies-locales").json()["copies"][0]["phrase"] == "copie locale complète, FR"
    e = c.post("/api/lancement/estimation", json={"sujet": {"pays": "GB"}, "parametres": {}})
    assert e.status_code == 200 and "pas GB" in e.json()["copies_locales"][0]
    assert c.delete("/api/copies-locales/FR-carte").status_code == 200 and c.get("/api/copies-locales").json()["copies"] == []
    assert c.delete("/api/copies-locales/FR-carte").status_code == 404


def test_dans_le_navigateur_le_poids_est_dit_avant_l_accord_puis_la_copie_apparait(chromium, serveur_vivant, cfgc):
    with TestClient(creer_app(cfgc)) as c:  # la première installation est faite (sinon l'assistant cache la page)
        assert c.post("/api/assistant/terminer", json={"etape1": {"pays": "FR", "presets_coches": ["web"], "chercher": [], "plafond": 5},
                                                       "etape2": {"active": True, "mode": "memes", "verifier": []}, "etape3": {"actifs": ["csv"], "dossier": ""}}).status_code == 200
    url = serveur_vivant(creer_app(cfgc))
    page = chromium.new_context(viewport={"width": 1200, "height": 900}).new_page()
    erreurs, dialogues = [], []
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: (dialogues.append(d.message), d.dismiss() if len(dialogues) == 1 else d.accept()))
    page.goto(url + "/")
    page.click('.tab[data-p="reglages"]')
    page.evaluate("document.querySelectorAll('details.bloc').forEach(d => d.open = true)")  # les blocs de Réglages sont repliés au départ
    page.wait_for_selector("button[data-copie]", timeout=10000)
    page.click("button[data-copie]")  # 1re fois : on REFUSE la boîte de confirmation
    for _ in range(100):
        if dialogues:
            break
        page.wait_for_timeout(100)
    assert "Mo" in dialogues[0] and "Place libre" in dialogues[0] and "ODbL" in dialogues[0]
    assert copies_locales.lister(cfgc) == []  # refusé : rien n'a été téléchargé
    page.click("button[data-copie]")  # 2e fois : on ACCEPTE
    page.wait_for_selector("#cop-liste [data-cop-suppr]", timeout=15000)
    assert "copie locale complète, FR" in page.inner_text("#cop-liste") and len(copies_locales.lister(cfgc)) == 1
    assert erreurs == [], erreurs


def test_une_copie_par_zone_est_marquee_partielle_et_la_couverture_le_dit(cfgc, serveur):
    d = catalogue_pays.dossier(cfgc)
    y = yaml.safe_load((d / "FR.yaml").read_text(encoding="utf-8"))
    y["bases"][0]["zones"] = [{"id": "isere", "nom": "Isère", "telechargement": serveur[0] + "/isere.bin"}]
    (d / "FR.yaml").write_text(yaml.safe_dump(y), encoding="utf-8")
    p = copies_locales.proposer(cfgc, "FR", "carte", zone="isere")
    assert p["zone"] == "Isère" and p["adresse"].endswith("/isere.bin")
    with pytest.raises(ConfigRefusee, match="pas de zone"):
        copies_locales.proposer(cfgc, "FR", "carte", zone="mars")
    r = copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t", zone="isere")
    assert r["id"] == "FR-carte-isere" and r["partielle"] is True and r["phrase"] == "copie locale, zone Isère seulement"
    assert (cfgc.dossier_copies / r["fichier"]).name == "isere.bin"
    assert any("zone Isère seulement" in x for x in copies_locales.couverture(cfgc, {"pays": "FR"}))  # une copie partielle prévient toujours
    complete = copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t")  # la complète s'ajoute à côté, sans écraser la partielle
    assert {c["id"] for c in copies_locales.lister(cfgc)} == {"FR-carte-isere", complete["id"]}


def test_les_zones_du_catalogue_francais_sont_valides_et_joignables(cfg):
    cat, problemes = catalogue_pays.charger(cfg)
    assert problemes == []
    zones = next(b for b in cat["FR"]["bases"] if b["id"] == "osm-geofabrik")["zones"]
    assert len(zones) == 27 and all(z["telechargement"].endswith("-latest.osm.pbf") for z in zones)
    assert "ile-de-france" in {z["id"] for z in zones}
    assert all(z["telechargement"] in catalogue_pays.adresses_connues(cfg) for z in zones)  # l'API de poids n'accepte que des adresses du catalogue
    n = catalogue_pays.taille(next(z["telechargement"] for z in zones if z["id"] == "corse"))
    if n is not None:
        assert 5e6 < n < 200e6


def test_les_copies_vont_dans_le_dossier_configure_pas_dans_les_donnees(cfgc, tmp_path):
    import dataclasses

    ailleurs = tmp_path / "autre_disque"
    c2 = dataclasses.replace(cfgc, copies=ailleurs)
    r = copies_locales.telecharger(c2, "FR", "carte", confirme=True, qui="t")
    assert (ailleurs / r["fichier"]).read_bytes() == CONTENU and not (cfgc.donnees / "copies").exists()
    assert copies_locales.proposer(c2, "FR", "carte")["libre_octets"] == copies_locales.place_libre(c2)  # la place dite est celle du disque configuré
    copies_locales.supprimer(c2, r["id"], "t")
    assert not (ailleurs / r["fichier"]).exists()


# --- [ ] Deux téléchargements de la même base en même temps (deux onglets) : chacun écrit dans son propre fichier partiel ; aucune
#         erreur fantôme, une copie exacte, une seule entrée au registre.
def test_deux_telechargements_simultanes_de_la_meme_base(cfgc):
    import time
    from concurrent.futures import ThreadPoolExecutor

    contenu = bytes(range(256)) * 1200  # non uniforme : un mélange de deux écritures se verrait

    class Lent:
        def __init__(self):
            self.pos = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            time.sleep(0.01)
            bloc = contenu[self.pos : self.pos + min(n, 50_000)]
            self.pos += len(bloc)
            return bloc

    def un(_):
        return copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t", poids=lambda url: len(contenu), ouvrir=lambda req, timeout: Lent())

    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(un, range(2)))
    assert all(r["octets"] == len(contenu) for r in res)
    assert (cfgc.dossier_copies / res[0]["fichier"]).read_bytes() == contenu
    assert [c["id"] for c in copies_locales.lister(cfgc)] == ["FR-carte"]
    assert not list(copies_locales.dossier(cfgc).rglob("*.part"))


# --- [ ] Le registre des copies est écrit d'un coup (fichier temporaire puis renommage) : jamais à moitié.
def test_le_registre_des_copies_est_ecrit_de_facon_atomique(cfgc, monkeypatch):
    from pilote import refus

    appels = []
    vrai = refus.ecrire_atomique
    monkeypatch.setattr(copies_locales, "ecrire_atomique", lambda f, t: (appels.append(f), vrai(f, t))[1], raising=False)
    copies_locales.telecharger(cfgc, "FR", "carte", confirme=True, qui="t")
    assert appels and appels[-1].name == copies_locales._registre(cfgc).name
