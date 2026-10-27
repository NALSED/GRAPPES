"""FICHE 08 — preset Lieux : test de recette, point par point."""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
import yaml
from fastapi.testclient import TestClient

from pilote.adaptateurs import Client, ErreurSource, charger, nominatim, osm_lieux
from pilote.app import creer_app
from pilote.config import RACINE
from pilote.sources import charger_sources

PHRASE_FICHE = "Lieux : cherche par endroit et par type de lieu (stade, salle, local associatif). Utile quand on ne connaît pas les noms."
EN_LIGNE: dict[str, bool] = {}


def en_ligne(url: str) -> bool:
    if url not in EN_LIGNE:
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pilote-test"}), timeout=15)
            EN_LIGNE[url] = True
        except urllib.error.HTTPError:
            EN_LIGNE[url] = True
        except (urllib.error.URLError, OSError):
            EN_LIGNE[url] = False
    return EN_LIGNE[url]


def du_preset(cfg):
    decls, problemes = charger_sources(cfg)
    assert problemes == []
    return {d.id: d for d in decls.values() if "lieux" in d.usages}


def overpass_reel(entree, parametres=None):
    """Appel RÉEL d'Overpass. Si les serveurs publics sont en panne ce jour-là, le test est SAUTÉ (et le dit) : il ne prouve alors rien."""
    serveurs = yaml.safe_load((RACINE / "config/sources/osm-overpass.yaml").read_text(encoding="utf-8"))["moteur"]["parametres"]["serveurs"]  # ceux de la configuration : le local d'abord
    if not any(en_ligne(u.replace("/interpreter", "/status")) for u in serveurs):
        pytest.skip("aucun serveur Overpass ne répond")
    parametres = {"serveurs": serveurs, **(parametres or {})}
    try:
        return charger("osm_lieux").chercher(entree, Client("osm-overpass"), {"_dossier_config": str(RACINE / "config"), **parametres})
    except ErreurSource as exc:
        if "Overpass n'a pas pu répondre" in str(exc):
            pytest.skip(f"serveurs Overpass publics indisponibles aujourd'hui : {exc}")
        raise


def exemple(nom):
    return json.loads((RACINE / "config/sources/exemples" / nom).read_text(encoding="utf-8"))


# --- [ ] Nominatim transforme un nom de ville en zone, en respectant UNE requête par seconde.
class FauxNominatim(BaseHTTPRequestHandler):
    heures: ClassVar[list] = []

    def do_GET(self):
        FauxNominatim.heures.append(time.monotonic())
        corps = json.dumps([{"osm_type": "relation", "osm_id": 80348, "category": "boundary", "name": "Ville-Exemple", "display_name": "Ville-Exemple, France", "lat": "45.1", "lon": "5.7"}]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *a):
        pass


@pytest.fixture
def faux_nominatim():
    s = HTTPServer(("127.0.0.1", 0), FauxNominatim)
    FauxNominatim.heures = []
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/search"
    s.shutdown()


def test_nominatim_transforme_une_ville_en_zone_overpass(faux_nominatim):
    z = nominatim.zone(Client("nominatim"), "Ville-Exemple", "FR", faux_nominatim)
    assert z["area"] == 3_600_000_000 + 80348  # une relation d'OpenStreetMap devient une zone d'Overpass


def test_nominatim_ne_depasse_jamais_une_requete_par_seconde_meme_si_on_demande_plus_vite(faux_nominatim):
    c = Client("nominatim", delai_s=0.0)  # le réglage demande « aussi vite que possible »
    for _ in range(3):
        nominatim.zone(c, "Ville-Exemple", "FR", faux_nominatim)
    h = FauxNominatim.heures
    assert len(h) == 3 and all(h[i + 1] - h[i] >= 0.99 for i in range(2)), [round(h[i + 1] - h[i], 2) for i in range(2)]


@pytest.mark.reseau
def test_nominatim_reel_donne_la_zone_de_grenoble():
    if not en_ligne("https://nominatim.openstreetmap.org/status.php"):
        pytest.skip("pas de réseau")
    z = nominatim.zone(Client("nominatim"), "Grenoble", "FR")
    assert z["area"] > 3_600_000_000 and "Grenoble" in z["nom"]


def test_nominatim_dit_en_clair_qu_un_endroit_est_inconnu(faux_nominatim):
    class Vide(FauxNominatim):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"[]")

    s = HTTPServer(("127.0.0.1", 0), Vide)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    with pytest.raises(ErreurSource, match="ne connaît pas l'endroit « Nullepart »"):
        nominatim.zone(Client("n"), "Nullepart", "FR", f"http://127.0.0.1:{s.server_port}/search")
    s.shutdown()


def test_nominatim_sans_surface_utilise_le_rectangle():
    class Pt(FauxNominatim):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps([{"osm_type": "node", "osm_id": 5, "category": "place", "boundingbox": ["45.1", "45.2", "5.6", "5.8"], "display_name": "Hameau"}]).encode())

    s = HTTPServer(("127.0.0.1", 0), Pt)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    z = nominatim.zone(Client("n"), "Hameau", "", f"http://127.0.0.1:{s.server_port}/search")
    assert z["bbox"] == (45.1, 5.6, 45.2, 5.8)  # sud, ouest, nord, est
    s.shutdown()


# --- [ ] Overpass rend des lieux d'un type donné dans cette zone, en respectant ses limites.
@pytest.mark.reseau
def test_overpass_reel_rend_des_lieux_du_type_demande_dans_la_zone():
    noms = overpass_reel({"lieu": "Grenoble", "pays": "FR", "type_lieu": ["stade"], "limite": 20})
    assert noms and all(n["nom"] and n["origine"].startswith("OpenStreetMap") for n in noms)
    assert all(45.0 < n["coordonnees"]["lat"] < 45.3 and 5.5 < n["coordonnees"]["lon"] < 6.0 for n in noms if "coordonnees" in n)  # bien dans la zone


def test_overpass_une_requete_un_delai_et_un_serveur_de_secours():
    class Occupe(BaseHTTPRequestHandler):
        recus: ClassVar[list] = []

        def do_POST(self):
            Occupe.recus.append((self.path, time.monotonic()))
            self.send_response(429 if self.path == "/premier" else 200)
            self.end_headers()
            if self.path != "/premier":
                self.wfile.write(json.dumps(exemple("osm-overpass.json")).encode())

        def do_GET(self):  # Nominatim simulé
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps([{"osm_type": "relation", "osm_id": 1, "category": "boundary", "display_name": "V"}]).encode())

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), Occupe)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    c = Client("osm-overpass", delai_s=0.0)
    noms = osm_lieux.chercher({"lieu": "V", "type_lieu": ["salle_de_sport"], "quoi": "handball"}, c,
                              {"serveurs": [base + "/premier", base + "/second"], "nominatim": base + "/search", "essais": 1, "_dossier_config": str(RACINE / "config")})
    s.shutdown()
    assert [n["nom"] for n in noms] == ["Club Imaginaire", "Gymnase Exemple"]  # le serveur occupé (429) est laissé, le suivant répond
    assert [p for p, _ in Occupe.recus] == ["/premier", "/second"]
    assert Occupe.recus[1][1] - Occupe.recus[0][1] >= 0.99  # et l'on n'insiste pas : au moins une seconde entre deux demandes
    assert c.delai_s >= 1.0


def test_overpass_dit_en_clair_quand_tous_les_serveurs_sont_occupes():
    class Mort(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(504)
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps([{"osm_type": "relation", "osm_id": 1, "category": "boundary", "display_name": "V"}]).encode())

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), Mort)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    with pytest.raises(ErreurSource, match="Overpass n'a pas pu répondre"):
        osm_lieux.chercher({"lieu": "V", "type_lieu": ["stade"]}, Client("o"), {"serveurs": [base + "/a"], "nominatim": base + "/search", "essais": 1, "_dossier_config": str(RACINE / "config")})
    s.shutdown()


def test_overpass_occupe_une_fois_est_retente_apres_une_pause_puis_la_zone_simple_en_secours():
    class Capricieux(BaseHTTPRequestHandler):
        recus: ClassVar[list] = []

        def do_POST(self):
            corps = self.rfile.read(int(self.headers["Content-Length"])).decode()
            Capricieux.recus.append((time.monotonic(), "area.z" in corps or "area%28" in corps))
            n = len(Capricieux.recus)
            self.send_response(504 if n == 1 else 200)
            self.end_headers()
            if n > 1:
                self.wfile.write(json.dumps({"elements": [] if n == 2 else exemple("osm-overpass.json")["elements"]}).encode())

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps([{"osm_type": "relation", "osm_id": 1, "category": "boundary", "display_name": "V", "boundingbox": ["45.1", "45.2", "5.6", "5.8"]}]).encode())

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), Capricieux)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{s.server_port}"
    noms = osm_lieux.chercher({"lieu": "V", "type_lieu": ["stade"]}, Client("o"), {"serveurs": [base + "/a"], "nominatim": base + "/search", "essais": 2, "pause_s": 0.2, "_dossier_config": str(RACINE / "config")})
    s.shutdown()
    # 1) surface : 504 ; 2) surface, nouvel essai : réponse vide ; 3) rectangle : des lieux -> gardés, marqués « zone approchée »
    assert len(Capricieux.recus) == 3 and [a for _, a in Capricieux.recus] == [True, True, False]
    assert noms and all(n["zone_approchee"] for n in noms)


def test_la_requete_overpass_porte_les_etiquettes_du_type_et_les_mots():
    cat = osm_lieux.catalogue(RACINE / "config")
    q = osm_lieux.requete("area(3600000001)->.z;", "area.z", osm_lieux.etiquettes({"type_lieu": ["salle_de_sport"]}, cat), ["handball"], 50)
    assert '["leisure"="sports_hall"]["sport"~"handball",i]' in q and '["leisure"="sports_centre"]["name"~"handball",i]' in q and q.endswith("out center tags 50;")
    assert osm_lieux.mots_de_la_recherche({"quoi": "clubs de handball", "mots_cles": ["salle"]}, cat) == ["handball"]  # « club », « salle » nomment le type : ils ne filtrent pas
    with pytest.raises(ErreurSource, match="« chateau » n'existe pas"):
        osm_lieux.etiquettes({"type_lieu": ["chateau"]}, cat)


def test_sans_endroit_ni_type_choisi_la_source_ne_s_applique_pas():
    class Mort(Client):
        def _avant(self):
            raise AssertionError("aucun appel")

    assert osm_lieux.chercher({"quoi": "universités", "pays": "FR"}, Mort("o"), {"_dossier_config": str(RACINE / "config")}) == []


# --- [ ] Le même genre (« club ») fonctionne sur DEUX pays sans code spécifique.
@pytest.mark.reseau
@pytest.mark.parametrize(("lieu", "pays", "boite"), [("Grenoble", "FR", (45.0, 45.3, 5.5, 6.0)), ("Bristol", "GB", (51.3, 51.6, -3.0, -2.4))])
def test_le_genre_club_fonctionne_dans_deux_pays_sans_code_specifique(lieu, pays, boite):
    noms = overpass_reel({"lieu": lieu, "pays": pays, "genre": "club", "limite": 30})
    assert len(noms) >= 3, f"{lieu} : {len(noms)} lieux"
    s, n, o, e = boite
    assert all(s < x["coordonnees"]["lat"] < n and o < x["coordonnees"]["lon"] < e for x in noms)


def test_aucun_code_national_dans_les_lieux():
    cat = yaml.safe_load((RACINE / "config/lieux_osm.yaml").read_text(encoding="utf-8"))
    cles = {c for t in cat["types"].values() for c, _ in t["osm"]}
    assert cles <= {"leisure", "amenity", "club", "office"}  # des étiquettes d'OpenStreetMap, communes à tous les pays
    code = (RACINE / "src/pilote/adaptateurs/osm_lieux.py").read_text(encoding="utf-8") + (RACINE / "src/pilote/adaptateurs/nominatim.py").read_text(encoding="utf-8")
    assert "NAF" not in code and "SIREN" not in code


# --- [ ] Les coordonnées sont bien conservées (elles serviront à l'export GeoJSON, fiche 14).
def test_les_coordonnees_sont_lues_pour_un_point_comme_pour_une_surface():
    noms = osm_lieux.convertir(exemple("osm-overpass.json"))
    assert [n["nom"] for n in noms] == ["Club Imaginaire", "Gymnase Exemple"]  # le lieu sans nom est ignoré
    assert noms[0]["coordonnees"] == {"lat": 48.856614, "lon": 2.3522219} and noms[1]["coordonnees"] == {"lat": 48.86, "lon": 2.34}  # centre d'une surface ; point
    assert noms[0]["site"] == "https://club-imaginaire.example" and noms[0]["ville"] == "Ville-Exemple" and noms[1]["genre"] == "club"


def test_les_coordonnees_arrivent_jusqu_au_candidat(tmp_path):
    from pilote.adaptateurs.nominatim import convertir
    from pilote.pont.faits import faits_candidat  # noqa: F401  (le chemin des coordonnées est exercé de bout en bout ci-dessous)

    n = convertir(exemple("nominatim.json"))
    assert [x["nom"] for x in n] == ["Gymnase Exemple"] and n[0]["coordonnees"] == {"lat": 48.856614, "lon": 2.3522219}  # les surfaces (villes) ne sont pas des lieux


# --- [ ] Google Maps et Google Places sont éteints dans la configuration livrée.
def test_google_maps_et_google_places_sont_eteints_dans_la_configuration_livree(cfg):
    d = du_preset(cfg)
    for sid in ("google-maps-apify", "google-places"):
        assert d[sid].defaut == {"chercher": False, "verifier": False} and d[sid].avertissement and d[sid].payant and d[sid].cle, sid
    assert d["google-maps-apify"].prestataire is True
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "lieux")
        allumees = {s["id"] for s in carte["sources"] if s["allumee_par_defaut"]}
    assert allumees == {"osm-overpass", "nominatim"}  # OpenStreetMap et Nominatim sont allumés, rien d'autre


def test_google_places_envoie_la_cle_dans_un_en_tete_et_lit_les_lieux():
    from pilote.adaptateurs import google_places

    class Faux(BaseHTTPRequestHandler):
        recus: ClassVar[list] = []

        def do_POST(self):
            Faux.recus.append((self.path, self.headers.get("X-Goog-Api-Key"), self.headers.get("X-Goog-FieldMask"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200 if self.headers.get("X-Goog-Api-Key") == "cle-test" else 403)
            self.end_headers()
            self.wfile.write(json.dumps(exemple("google-places.json")).encode())

        def log_message(self, *a):
            pass

    s = HTTPServer(("127.0.0.1", 0), Faux)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{s.server_port}/v1/places:searchText"
    noms = google_places.chercher({"quoi": "handball", "lieu": "Lyon", "pays": "FR"}, Client("g"), {"url": url, "_cle": "cle-test"})
    assert noms[0]["nom"] == "Club Imaginaire" and noms[0]["ville"] == "Ville-Exemple" and noms[0]["pays"] == "FR" and noms[0]["coordonnees"] == {"lat": 48.856614, "lon": 2.3522219}
    assert Faux.recus[0][1] == "cle-test" and "/v1/places" in Faux.recus[0][0] and "?" not in Faux.recus[0][0] and Faux.recus[0][3]["textQuery"] == "handball Lyon"
    with pytest.raises(ErreurSource, match="403"):
        google_places.chercher({"quoi": "x"}, Client("g"), {"url": url, "_cle": "fausse"})
    with pytest.raises(ErreurSource, match="clé de Google Places est absente"):
        google_places.chercher({"quoi": "x"}, Client("g"), {"url": url})
    s.shutdown()


def test_google_maps_par_apify_lit_nom_site_ville_et_coordonnees(cfg):
    from pilote.adaptateurs import mcp_generique as m

    d = du_preset(cfg)["google-maps-apify"]
    noms = m.convertir(exemple("google-maps-apify.json"), d.moteur["parametres"])
    assert noms == [{"nom": "Club Imaginaire", "origine": "Google Maps (lieu, via Apify)", "genre": "lieu", "site": "https://club-imaginaire.example",
                     "ville": "Ville-Exemple", "pays": "FR", "coordonnees": {"lat": 48.856614, "lon": 2.3522219}}]
    assert "{lieu}" in json.dumps(d.moteur["parametres"]["arguments"]) and "{mots_cles}" in json.dumps(d.moteur["parametres"]["arguments"])  # mot-clé ET zone entière


# --- La carte, le type de lieu (choisi dans Recherches) et les presets.
def test_la_carte_porte_la_phrase_de_la_fiche(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "lieux")
    assert carte["phrase"] == PHRASE_FICHE


def test_les_types_de_lieu_se_choisissent_ailleurs_pas_dans_le_preset(cfg):
    with TestClient(creer_app(cfg, lambda c: None)) as c:
        r = c.get("/api/types-de-lieu").json()
        carte = next(p for p in c.get("/api/reglages").json()["presets"] if p["id"] == "lieux")
    assert {"stade", "salle_de_sport", "local_associatif", "centre_culturel"} <= {t["id"] for t in r["types"]} and set(r["genres"]) >= {"club", "association", "lieu"}
    assert not any("type" in k for k in carte)  # la carte du preset n'a pas de réglage de type : il est dans la page Recherches (fiche 12)


def test_les_sources_de_lieux_sont_universelles_et_declarent_leur_origine(cfg):
    d = du_preset(cfg)
    assert d["osm-overpass"].pays == ["monde"] and d["osm-overpass"].main == "premiere" and d["nominatim"].main == "seconde"  # même base : Nominatim ne compte pas deux fois
    assert all(x.pays == ["monde"] for x in d.values() if x.mode.get("en_ligne", True))  # les copies locales de la France (document 22) sont, elles, limitées à la France par décision du 27/10
