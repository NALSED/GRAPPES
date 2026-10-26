"""Le plan de travail appliqué par le VRAI moteur (pont + grappes), sur deux programmes locaux hors ligne : les liens décident des sources, un filtre
retire des noms sur sa branche seulement (et le journal dit lesquels), une Traduction change la requête que reçoit la source."""

from __future__ import annotations

import http.server
import json
import sys
import threading
import time

import pytest
from conftest import copier_config
from fastapi.testclient import TestClient

from pilote.app import creer_app
from pilote.config import charger

PROG_A = 'import json, sys\nd = json.load(sys.stdin)\nprint(json.dumps([{"nom": "Club Lyon", "ville": "Lyon", "origine": "a"}, {"nom": "Club Paris", "ville": "Paris", "origine": "a"}]))\n'
PROG_B = 'import json, sys\nd = json.load(sys.stdin)\nprint(json.dumps([{"nom": "Autre Paris", "ville": "Paris", "origine": "b"}]))\n'
PROG_ECHO = (
    'import json, sys\nd = json.load(sys.stdin)\nprint(json.dumps([{"nom": "Requete " + d["quoi"], "origine": "e"}]))\n'
)


def programme(c, tmp_path, nom, code):
    f = tmp_path / f"{nom}.py"
    f.write_text(code, encoding="utf-8")
    r = c.post(
        "/api/programmes-locaux",
        json={"nom": nom, "commande": [sys.executable, str(f)], "genres": ["association"], "pays": ["FR"]},
    )
    assert r.status_code == 201, r.text
    ident = r.json()["id"]
    assert c.post(f"/api/suite/sources/{ident}/allumer", json={}).status_code == 200
    return ident


def attendre(c, rid):
    t0 = time.time()
    while time.time() - t0 < 120 and c.get(f"/api/recherches/{rid}").json()["etat"] not in (
        "terminee",
        "echec",
        "arretee",
        "interrompue",
    ):
        time.sleep(0.3)
    assert c.get(f"/api/recherches/{rid}").json()["etat"] == "terminee", c.get(f"/api/recherches/{rid}").json()[
        "message"
    ]


def noeud(i, nom=None, role=None, ref=None, x=0, y=0, opts=None):
    return {"id": i, "nom": nom or i, "role": role, "ref": ref, "x": x, "y": y, "opts": opts or []}


def lien(a, b, label=None):
    return {"from": a, "to": b, **({"label": label} if label else {})}


def candidats(cfg, rid):
    return json.loads(next(cfg.dossier_recherche(rid).rglob("candidats.json")).read_text(encoding="utf-8"))


def journal(c, rid):
    return c.get(f"/api/recherches/{rid}/journal").json()


@pytest.fixture
def cfg2(tmp_path):
    return charger(copier_config(tmp_path))


def test_le_plan_decide_des_sources_et_un_filtre_ne_juge_que_sa_branche(cfg2, tmp_path):
    with TestClient(creer_app(cfg2)) as c:
        a, b = programme(c, tmp_path, "prog-a", PROG_A), programme(c, tmp_path, "prog-b", PROG_B)
        for s in c.get("/api/suite/etat").json()["sources"]:
            if s["id"] not in (a, b) and s["chercher"]:
                c.post(f"/api/suite/sources/{s['id']}/eteindre", json={})  # rien d'autre ne part : aucun appel réseau
        filtre_opts = [["Garder si le champ", "ville"], ["est égal à", "Lyon"]]
        plan = {
            "nodes": [noeud("saisie", "Ta saisie", "ENTREE"), noeud("grappes", "Grappes", "GRAPPES"), noeud("na", role="CHERCHER", ref=a, x=200), noeud("nb", role="CHERCHER", ref=b, x=200, y=130),
                      noeud("f", "Filtre", "OUTIL", "filtre", x=400, opts=filtre_opts)],
            "edges": [lien("saisie", "na"), lien("na", "f"), lien("f", "grappes"), lien("saisie", "nb"), lien("nb", "grappes")],
        }  # fmt: skip
        r = c.post(
            "/api/suite/lancer",
            json={"saisie": "associations sportives", "mode": "Avancée", "plan": plan, "cats": ["perso"], "pays": "FR"},
        )
        assert r.status_code == 202, r.text
        assert [x["nom"] for x in r.json()["appliques"]] == ["Filtre"] and r.json()["non_appliques"] == []
        rid = r.json()["recherche_id"]
        attendre(c, rid)
        noms = {x["nom"] for x in candidats(cfg2, rid)}
        assert (
            noms == {"Club Lyon", "Autre Paris"}
        )  # « Club Paris » : source A, ville Paris : retiré par le filtre de SA branche ; « Autre Paris » vient de B, sans filtre
        evt = [e for e in journal(c, rid) if e["evenement"] == "plan_noms_retires"]
        assert (
            len(evt) == 1 and evt[0]["detail"]["noms"] == ["Club Paris"] and evt[0]["detail"]["retires"] == 1
        )  # le nom retiré n'est pas en base : il est au journal
        assert c.get(f"/api/recherches/{rid}").json()["avancement"]["plan"]["retires"] == 1


def test_une_source_non_reliee_de_bout_en_bout_ne_part_pas(cfg2, tmp_path):
    with TestClient(creer_app(cfg2)) as c:
        a, b = programme(c, tmp_path, "prog-a", PROG_A), programme(c, tmp_path, "prog-b", PROG_B)
        for s in c.get("/api/suite/etat").json()["sources"]:
            if s["id"] not in (a, b) and s["chercher"]:
                c.post(f"/api/suite/sources/{s['id']}/eteindre", json={})
        plan = {"nodes": [noeud("saisie", "Ta saisie", "ENTREE"), noeud("grappes", "Grappes", "GRAPPES"), noeud("na", role="CHERCHER", ref=a), noeud("nb", role="CHERCHER", ref=b)],
                "edges": [lien("saisie", "na"), lien("na", "grappes"), lien("saisie", "nb")]}  # B ne rend rien à Grappes  # fmt: skip
        r = c.post(
            "/api/suite/lancer", json={"saisie": "associations", "mode": "Avancée", "plan": plan, "cats": ["perso"]}
        )
        assert r.status_code == 202 and r.json()["lancees"] == ["prog-a"], r.text
        rid = r.json()["recherche_id"]
        attendre(c, rid)
        assert {x["nom"] for x in candidats(cfg2, rid)} == {"Club Lyon", "Club Paris"}


def test_un_plan_incoherent_est_refuse_avant_tout_appel(cfg2, tmp_path):
    with TestClient(creer_app(cfg2)) as c:
        a = programme(c, tmp_path, "prog-a", PROG_A)
        base = [
            noeud("saisie", "Ta saisie", "ENTREE"),
            noeud("grappes", "Grappes", "GRAPPES"),
            noeud("na", role="CHERCHER", ref=a),
        ]
        mauvais = noeud("f", "Filtre", "OUTIL", "filtre", opts=[["Garder si le champ", "couleur"], ["est égal à", "x"]])
        r = c.post(
            "/api/suite/lancer",
            json={
                "saisie": "x",
                "mode": "Avancée",
                "plan": {
                    "nodes": [*base, mauvais],
                    "edges": [lien("saisie", "na"), lien("na", "f"), lien("f", "grappes")],
                },
            },
        )
        assert r.status_code == 422 and "n'existe pas" in r.json()["detail"]
        assert c.get("/api/recherches").json() == []  # rien n'est parti


def test_la_traduction_change_la_requete_de_la_source_et_garde_l_original(tmp_path):
    recu = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            q = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            recu.append(q)
            corps = json.dumps({"translatedText": "TRADUIT " + q["q"]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = charger(copier_config(tmp_path, suite={"traduction_url": f"http://127.0.0.1:{srv.server_port}"}))
    try:
        with TestClient(creer_app(cfg)) as c:
            e = programme(c, tmp_path, "prog-echo", PROG_ECHO)
            c.put(f"/api/suite/sources/{e}", json={"langue": "en"})  # cette source cherche en anglais
            for s in c.get("/api/suite/etat").json()["sources"]:
                if s["id"] != e and s["chercher"]:
                    c.post(f"/api/suite/sources/{s['id']}/eteindre", json={})
            opts = [
                ["Langue d'entrée", "détecter"],
                ["Traduire vers", "français, anglais"],
                ["Ne pas traduire", "rien"],
            ]
            plan = {"nodes": [noeud("saisie", "Ta saisie", "ENTREE"), noeud("grappes", "Grappes", "GRAPPES"), noeud("t", "Traduction", "OUTIL", "traduction", opts=opts), noeud("ne", role="CHERCHER", ref=e)],
                    "edges": [lien("saisie", "t"), lien("t", "ne"), lien("ne", "grappes")]}  # fmt: skip
            r = c.post(
                "/api/suite/lancer",
                json={
                    "saisie": "je cherche une association de boxe",
                    "mode": "Avancée",
                    "plan": plan,
                    "cats": ["perso"],
                },
            )
            assert r.status_code == 202, r.text
            assert "requête traduite pour" in r.json()["appliques"][0]["texte"]
            rid = r.json()["recherche_id"]
            attendre(c, rid)
            assert [x["nom"] for x in candidats(cfg, rid)] == [
                "Requete TRADUIT je cherche une association de boxe"
            ]  # la source a reçu la requête traduite
            evt = [x for x in journal(c, rid) if x["evenement"] == "plan_requete_traduite"]
            assert (
                evt
                and evt[0]["detail"]["original"]["quoi"] == "je cherche une association de boxe"
                and evt[0]["detail"]["vers"] == "en"
            )  # l'original est gardé au journal
            assert recu[0]["source"] == "fr" and recu[0]["target"] == "en"
            # sans moteur de traduction réglé, la même tuile n'est pas appliquée, et le dit
    finally:
        srv.shutdown()
    cfg0 = charger(copier_config(tmp_path / "sans"))
    with TestClient(creer_app(cfg0)) as c:
        e = programme(c, tmp_path, "prog-echo", PROG_ECHO)
        c.put(f"/api/suite/sources/{e}", json={"langue": "en"})
        r = c.post(
            "/api/suite/lancer",
            json={"saisie": "je cherche une association de boxe", "mode": "Avancée", "plan": plan, "cats": ["perso"]},
        )
        assert r.status_code == 202 and "moteur de traduction" in r.json()["non_appliques"][0]["raison"]
