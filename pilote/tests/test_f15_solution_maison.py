"""Fiche 15, chapitre 5 — l'exemple de programme local s'ajoute par la page Ajout, sans toucher au cœur du programme."""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from pilote.adaptateurs import programmes
from pilote.config import RACINE

PAGE = "<html><body><ul><li>Chorale des Quais</li><li> Chorale   du Port </li><li>x</li></ul><h2>Les Voix d'Isère</h2><script>var a='<li>Faux</li>'</script></body></html>"


@pytest.fixture
def adresse():
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE.encode())

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/annuaire"
    s.shutdown()


def test_l_exemple_respecte_la_convention_et_ne_rend_que_des_noms_presents_mot_pour_mot(adresse):
    exemple = RACINE / "docs/exemples/lecteur_page.py"
    noms = programmes.executer({"commande": [sys.executable, str(exemple), adresse]}, {"quoi": "chorales", "limite": 10})
    assert [n["nom"] for n in noms] == ["Chorale des Quais", "Chorale du Port", "Les Voix d'Isère"]
    assert all(n["origine"] == "page web" and n["site"] == adresse for n in noms)


def test_l_exemple_dit_ce_qui_manque_sans_adresse():
    exemple = Path(RACINE / "docs/exemples/lecteur_page.py")
    with pytest.raises(Exception, match="erreur"):
        programmes.executer({"commande": [sys.executable, str(exemple)]}, {})
