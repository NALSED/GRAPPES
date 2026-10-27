"""Document 26 : Web et Réseaux sociaux (RDAP, emoji, OpenAgenda, base extérieure, YouTube, MatrixRooms, Jetstream)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pilote.adaptateurs import Client, ErreurSource, rdap
from pilote.sources import charger_sources

RACINE = Path(__file__).resolve().parents[1]
EXEMPLES = RACINE / "config" / "sources" / "exemples"
COMMISSARIAT = "Commissariat à l'énergie atomique et aux énergies alternatives"


# --- RDAP (§ 1) : ce que le registre d'un domaine dit de lui, sans aucun contact de personne (règle n° 8)
def test_rdap_garde_registraire_dates_statut_et_organisation_titulaire():
    [e] = rdap.convertir(json.loads((EXEMPLES / "rdap.json").read_text(encoding="utf-8")), "Club Exemple")
    d = e["detail"]
    assert "enregistré le 04/05/2011" in d and "expire le 04/05/2027" in d and "dernière modification le 30/04/2026" in d
    assert "bureau d'enregistrement : Bureau Exemple SA" in d and "titulaire déclaré : Club Exemple" in d and "client transfer prohibited" in d
    assert e["nom"] == "Club Exemple" and e["origine"].startswith("RDAP")


def test_rdap_ne_garde_aucun_champ_de_contact_de_personne():
    """Le registre rend le nom, le courriel et le téléphone des contacts (le registre français le fait) : rien de cela ne sort, même du titulaire."""
    sortie = json.dumps(rdap.convertir(json.loads((EXEMPLES / "rdap.json").read_text(encoding="utf-8"))), ensure_ascii=False)
    for interdit in ("Prénom Nom", "Autre Personne", "contact@", "admin@", "tel:", "+33", "adr"):
        assert interdit not in sortie, interdit


def test_rdap_ignore_un_titulaire_masque_par_le_registre():
    rep = {"objectClassName": "domain", "ldhName": "x.example", "status": ["active"], "entities": [
        {"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "REDACTED FOR PRIVACY"], ["org", {}, "text", "Redacted for privacy"]]]}]}
    assert "titulaire" not in rdap.convertir(rep)[0]["detail"]


def test_rdap_ne_lit_jamais_le_nom_complet_d_un_titulaire():
    """Un titulaire personne physique n'a pas d'`org` : seul son `fn` (son nom) existe, et il n'est pas lu."""
    rep = {"objectClassName": "domain", "ldhName": "x.example", "status": ["active"], "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Marie Dupont"]]]}]}
    assert "Marie" not in json.dumps(rdap.convertir(rep))


def test_rdap_essaie_le_domaine_enregistrable_quand_le_sous_domaine_est_inconnu():
    assert rdap.domaines("https://www.danone.com/fr/") == ["danone.com"]
    assert rdap.domaines("blog.cea.fr") == ["blog.cea.fr", "cea.fr"]
    assert rdap.domaines("https://www.bbc.co.uk/news") == ["bbc.co.uk"] and rdap.domaines("a.b.bbc.co.uk") == ["a.b.bbc.co.uk", "bbc.co.uk"]
    assert rdap.domaines("") == [] and rdap.domaines("pas une adresse") == [] and rdap.domaines("localhost") == []


class _Faux(Client):
    def __init__(self, reponses):
        super().__init__("rdap")
        self.reponses, self.vus = reponses, []

    def get_json(self, url, params=None, headers=None):
        self.vus.append(url.rsplit("/", 1)[-1])
        r = self.reponses[url.rsplit("/", 1)[-1]]
        if isinstance(r, int):
            e = ErreurSource(f"La source a répondu une erreur ({r}).")
            e.code = r
            raise e
        return r


def test_un_domaine_inconnu_du_registre_n_est_pas_une_panne():
    exemple = json.loads((EXEMPLES / "rdap.json").read_text(encoding="utf-8"))
    c = _Faux({"blog.club-exemple.example": 404, "club-exemple.example": exemple})
    assert rdap.chercher({"site": "https://blog.club-exemple.example/", "nom": "Club"}, c, {})[0]["detail"].startswith("domaine club-exemple.example")
    assert c.vus == ["blog.club-exemple.example", "club-exemple.example"]
    assert rdap.chercher({"site": "x.example", "nom": "X"}, _Faux({"x.example": 404}), {}) == []
    with pytest.raises(ErreurSource):  # une vraie panne (429, 500) reste une panne
        rdap.chercher({"site": "x.example", "nom": "X"}, _Faux({"x.example": 500}), {})


def test_rdap_n_est_jamais_une_recherche_par_mot():
    assert rdap.chercher({"quoi": "handball", "nom": "Club"}, _Faux({}), {}) == []  # pas de site : rien à demander au registre


def test_la_source_rdap_est_un_enrichissement_sur_le_site_eteint_et_sans_cle(cfg):
    d = charger_sources(cfg)[0]["rdap"]
    assert d.roles == ["enrichir"] and d.verifie_sur == "site" and d.cles == [] and d.fiabilite == "B" and "web" in d.usages
    assert d.mode["en_ligne"] and not d.defaut.get("chercher") and not d.defaut.get("verifier")
    assert d.moteur["parametres"]["delai_s"] >= 1.0  # 10 requêtes par 10 secondes sur rdap.org


def test_intelligence_x_reste_eteinte_et_dit_que_rdap_la_remplace(cfg):
    d = charger_sources(cfg)[0]["intelligencex"]
    assert not d.defaut.get("chercher") and "RDAP" in d.note


@pytest.mark.reseau
def test_rdap_reel_rend_le_registraire_de_danone():
    try:
        trouves = rdap.chercher({"site": "https://www.danone.com/", "nom": "Danone"}, Client("rdap", delai_s=1.1), {})
    except ErreurSource as exc:
        pytest.skip(f"rdap.org indisponible : {exc}")
    assert trouves and "bureau d'enregistrement" in trouves[0]["detail"] and "enregistré le" in trouves[0]["detail"]


# --- l'emoji (§ 4) : la norme UTS #51, pas une expression régulière faite à la main
def test_un_emoji_tape_dans_la_recherche_n_est_plus_jete():
    from pilote.adaptateurs import mots_significatifs

    assert mots_significatifs("collectif ♻️ Isère") == ["collectif", "♻️", "Isère"]  # emoji compris, tel que tapé (U+FE0F compris)
    assert mots_significatifs("♻️") == ["♻️"]  # un emoji seul est une requête valable
    assert mots_significatifs("Air France") == ["Air", "France"] and mots_significatifs("AS Lyon") == ["AS", "Lyon"]  # rien ne change pour les mots


def test_un_drapeau_arc_en_ciel_traverse_la_chaine_en_un_seul_morceau():
    from pilote.adaptateurs import mots_significatifs

    drapeau = "\U0001f3f3️‍\U0001f308"  # drapeau, sélecteur, liant, arc-en-ciel
    assert mots_significatifs(f"fierté {drapeau} Lyon") == ["fierté", drapeau, "Lyon"]


def test_deux_teintes_de_peau_se_comparent_egales_mais_la_forme_envoyee_reste_celle_tapee():
    from pilote.adaptateurs import mots_significatifs, nom_normalise
    from pilote.emoji_texte import reduit

    assert reduit("✊🏽") == reduit("✊🏿") == "✊"
    assert nom_normalise("Collectif ✊🏽") == nom_normalise("Collectif ✊🏿")  # en interne : égaux
    assert mots_significatifs("✊🏽") == ["✊🏽"] and mots_significatifs("✊🏿") == ["✊🏿"]  # vers la source : la forme tapée, jamais la forme réduite
    assert reduit("\U0001f3f3️‍\U0001f308") == "\U0001f3f3‍\U0001f308"  # la séquence ZWJ reste entière


def test_un_emoji_dans_un_nom_n_est_plus_efface_a_la_comparaison():
    from pilote.adaptateurs import nom_normalise

    assert nom_normalise("Club ⚽ de Lyon") != nom_normalise("Club 🏀 de Lyon")  # avant : les deux devenaient « club de lyon »
    assert nom_normalise("Dupont & Dupont, SAS") == "dupont dupont sas"  # sans emoji, rien ne change
    assert nom_normalise("Café ♻️ Vert") == nom_normalise("cafe ♻️ vert")  # sans accent, sans casse
    assert nom_normalise("Dupont ©") == nom_normalise("Dupont")  # un caractère qui n'est emoji qu'avec U+FE0F (©, ™, ✓) reste du texte : un nom d'entreprise n'est pas un emoji


def test_les_points_de_code_sont_ceux_de_la_norme_emoji_par_emoji():
    """Oracle : le paquet `emoji` (données UTS #51) et `regex` (`\\X`, grappes de graphèmes). Chaque emoji complètement qualifié est reconnu d'un seul tenant, au même endroit."""
    import emoji
    import regex

    from pilote.emoji_texte import trouver

    for s, d in emoji.EMOJI_DATA.items():
        if d["status"] == emoji.STATUS["fully_qualified"]:
            assert [e for _, _, e in trouver(s)] == [s], s.encode("unicode_escape")
    texte = "a ✊🏽 b 🏳️‍🌈 c 🇫🇷 d 1️⃣ e ♻️ f 👨‍👩‍👧‍👦 g"
    assert [e for _, _, e in trouver(texte)] == [x["emoji"] for x in emoji.emoji_list(texte)] == [g for g in regex.findall(r"\X", texte) if emoji.is_emoji(g)]
    assert trouver("Dupont © 2020 ✓ ™ #collectif 12") == []  # ni le droit d'auteur, ni une coche, ni des chiffres ne sont des emoji


def test_une_adresse_n_a_jamais_un_emoji_brut(monkeypatch):
    import urllib.request

    vues = []

    class _Rep:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b"{}"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: vues.append(req.full_url) or _Rep())
    Client("x").get_json("https://exemple.example/recherche", {"q": "✊ 🏳️‍🌈"})
    assert vues[0] == "https://exemple.example/recherche?q=%E2%9C%8A+%F0%9F%8F%B3%EF%B8%8F%E2%80%8D%F0%9F%8C%88"  # urlencode : UTF-8 en %XX
    Client("x").get_json("https://exemple.example/✊/café")
    assert vues[1] == "https://exemple.example/%E2%9C%8A/caf%C3%A9"  # y compris dans le chemin


def test_une_source_qui_ne_declare_pas_l_emoji_ne_le_recoit_pas():
    from pilote.emoji_texte import requete_pour

    entree = {"sujet": "collectif ♻️ Isère", "quoi": "collectif ♻️", "mots_cles": ["♻️", "tri"], "lieu": "Isère ✊🏽", "limite": 20}
    assert requete_pour(entree, True) == entree
    assert requete_pour(entree, False) == {"sujet": "collectif Isère", "quoi": "collectif", "mots_cles": ["", "tri"], "lieu": "Isère", "limite": 20}


def test_seules_bluesky_et_jetstream_declarent_chercher_l_emoji_apres_mesure(cfg):
    """Mesuré le 27/10/2026 contre les services réels (voir docs/emoji.md) : un emoji seul rend des comptes chez Bluesky (4 sur 4) ; Lemmy, Mastodon, SepiaSearch sont
    incohérents (1 à 2 sur 4) et Arctic Shift cherche des préfixes de noms (0 sur 4). Une source ne le déclare qu'essayée contre son service réel, avec sa date."""
    decls = charger_sources(cfg)[0]
    avec = sorted(i for i, d in decls.items() if "emoji" in d.consomme)
    assert avec == ["bluesky", "jetstream"] and all(decls[i].verifie_le == "2026-10-27" for i in avec)  # Jetstream filtre le texte lui-même : l'emoji y est cherché pour de bon


def _plan_et_sources(emoji_bluesky: bool, etat: str = "on"):
    sources = [{"id": "s1", "nom": "Source", "role": "CHERCHER", "etat": etat, "retiree": False, "emoji": emoji_bluesky, "langue": "", "quota": None}]
    nodes = [{"id": "e", "role": "ENTREE", "nom": "Saisie"}, {"id": "t", "role": "CHERCHER", "nom": "Source", "ref": "s1"}, {"id": "g", "role": "GRAPPES", "nom": "Grappes"}]
    edges = [{"from": "e", "to": "t"}, {"from": "t", "to": "g"}]
    return {"plan": {"nodes": nodes, "edges": edges}, "sources": sources, "outils": []}


def test_l_aide_signale_un_emoji_qu_aucune_source_allumee_ne_cherche():
    from pilote import suite

    constats = suite.verifier_plan(_plan_et_sources(False), None, saisie_emoji=True)
    assert [c["regle"] for c in constats] == [6] and "emoji" in constats[0]["texte"] and constats[0]["niveau"] == "remarque"  # elle signale, elle n'éteint rien
    assert suite.verifier_plan(_plan_et_sources(True), None, saisie_emoji=True) == []  # une source qui le cherche : rien à dire
    assert suite.verifier_plan(_plan_et_sources(False), None, saisie_emoji=False) == []  # pas d'emoji dans la saisie : rien à dire


def test_le_bilan_dit_a_combien_de_sources_l_emoji_n_a_pas_ete_transmis(cfg):
    from types import SimpleNamespace

    from pilote.executeur_grappes import ExecuteurGrappes

    evenements, avance = [], {}
    ctx = SimpleNamespace(avancer=lambda **k: avance.update(k), noter=lambda e, **k: evenements.append((e, k)))
    ExecuteurGrappes(cfg).dire_l_emoji(ctx, {"sources": ["bluesky", "ror", "wikidata"], "emoji": {"saisie": True, "ok": ["bluesky"]}})
    assert avance["emoji"] == {"transmis": ["bluesky"], "non_transmis": ["ror", "wikidata"], "a_l_aveugle": []} and evenements == [("emoji_non_transmis", {"sources": ["ror", "wikidata"]})]
    avance.clear()
    ExecuteurGrappes(cfg).dire_l_emoji(ctx, {"sources": ["ror"], "emoji": {"saisie": False, "ok": []}})
    assert avance == {}  # pas d'emoji dans la saisie : le bilan n'en parle pas


# --- OpenAgenda (§ 2) : P2 tant que la clé gratuite n'est pas créée
def test_openagenda_se_charge_eteinte_demande_une_cle_et_lit_l_exemple(cfg):
    d = charger_sources(cfg)[0]["openagenda"]
    assert d.cles == ["OPENAGENDA_API_KEY"] and d.roles == ["chercher"] and d.fiabilite == "C" and not d.defaut.get("chercher")
    assert "NON vérifiée" in d.note  # aucune clé : on ne prétend pas l'avoir essayée
    from pilote.adaptateurs import api_json

    noms = api_json.convertir(json.loads((EXEMPLES / "openagenda.json").read_text(encoding="utf-8")), d.moteur["parametres"])
    assert [n["nom"] for n in noms] == ["Club Exemple — agenda", "Médiathèque Exemple"] and noms[0]["pays"] == "FR"


def test_openagenda_envoie_la_cle_dans_l_en_tete_key_et_jamais_dans_l_adresse(cfg):
    from pilote.adaptateurs import Client, api_json

    d = charger_sources(cfg)[0]["openagenda"]
    vus = {}

    class _C(Client):
        def get_json(self, url, params=None, headers=None):
            vus.update(url=url, params=params, headers=headers)
            return json.loads((EXEMPLES / "openagenda.json").read_text(encoding="utf-8"))

    api_json.chercher({"quoi": "club", "pays": "FR", "limite": 5}, _C("openagenda"), {**d.moteur["parametres"], "_cle": "CLE-DE-TEST"})
    assert vus["headers"] == {"key": "CLE-DE-TEST"} and "CLE-DE-TEST" not in str(vus["params"]) and vus["params"]["search"] == "club"


# --- La prise « base extérieure » (§ 3) : garde-fous d'une base en réseau, sans serveur
from pilote.adaptateurs import base_exterieure


def test_une_requete_d_ecriture_ou_de_gestion_est_refusee_avant_d_atteindre_le_serveur():
    assert base_exterieure.verifier_requete("select nom from organisations where nom ilike :q_like") == "select nom from organisations where nom ilike :q_like"
    for mauvaise in ("select * into copie from organisations", "select pg_sleep(30)", "select set_config('a','b',false)", "select nom from t; drop table t", "update t set nom = 'x'",
                     "select load_file('/etc/passwd')", "select nom into outfile '/tmp/x' from t", "with x as (delete from t returning nom) select nom from x", "call ma_procedure()", "copy t to program 'ls'"):
        with pytest.raises(ErreurSource):
            base_exterieure.verifier_requete(mauvaise)


def test_l_adresse_vient_de_la_declaration_et_refuse_ce_qui_n_est_pas_une_base():
    assert base_exterieure.verifier_adresse({"systeme": "postgresql", "hote": "192.168.1.20"}) == ("postgresql", "192.168.1.20", 5432)
    assert base_exterieure.verifier_adresse({"systeme": "mysql", "hote": "db.interne.example", "port": "3307"}) == ("mysql", "db.interne.example", 3307)
    for mauvais in ({"systeme": "oracle", "hote": "x"}, {"systeme": "mysql", "hote": ""}, {"systeme": "mysql", "hote": "a b"}, {"systeme": "mysql", "hote": "169.254.169.254"}, {"systeme": "mysql", "hote": "x", "port": "0"},
                    {"systeme": "mysql", "hote": "x", "port": "abc"}, {"systeme": "mysql", "hote": "0.0.0.0"}):
        with pytest.raises(ErreurSource):
            base_exterieure.verifier_adresse(mauvais)


def test_le_chiffrement_est_exige_hors_de_la_machine_et_facultatif_sur_la_machine():
    assert base_exterieure._contexte_tls({}, "127.0.0.1") is None and base_exterieure._contexte_tls({}, "localhost") is None
    distant = base_exterieure._contexte_tls({}, "192.168.1.20")
    assert distant is not None and distant.check_hostname is False  # comme sslmode=require : chiffré, certificat non vérifié
    assert base_exterieure._contexte_tls({"tls_verifier": True}, "db.example").check_hostname is True
    with pytest.raises(ErreurSource):
        base_exterieure._contexte_tls({"tls": False}, "192.168.1.20")  # impossible à désactiver hors de la machine


def test_les_mots_cherches_sont_lies_et_un_pour_cent_du_texte_est_double():
    sql, valeurs = base_exterieure._sql_et_valeurs("select nom from t where nom ilike :q_like or nom = :q or ville like 'Gre%'", "club")
    assert sql == "select nom from t where nom ilike %s or nom = %s or ville like 'Gre%%'" and valeurs == ["%club%", "club"]
    assert "club" not in sql  # jamais collés dans le texte de la requête


def test_les_identifiants_viennent_de_secrets_env_et_leur_absence_est_dite():
    p = {"utilisateur_env": "U", "mot_de_passe_env": "M", "_cles": {"U": "lecteur", "M": "secret"}}
    assert base_exterieure._identifiants(p) == ("lecteur", "secret")
    with pytest.raises(ErreurSource):
        base_exterieure._identifiants({**p, "_cles": {}})


def test_un_message_d_erreur_ne_cite_jamais_le_mot_de_passe_ni_l_adresse():
    brut = Exception("FATAL: password authentication failed for user lecteur at 192.168.1.20 with MOTDEPASSE-SECRET")
    m = base_exterieure._message(brut)
    assert "MOTDEPASSE" not in m and "192.168" not in m and "lecteur" not in m and "identifiant" in m
    for texte in ("connexion", "serveur SQL", "base distante", "base locale"):  # vocabulaire fermé (charte/nommage.md) : jamais à l'écran
        assert texte not in m.lower()


def test_seules_les_colonnes_connues_sont_gardees():
    sortie = base_exterieure.convertir([{"nom": "Club", "ville": "Lyon", "prenom": "Marie", "date_naissance": "1980-01-01", "email": "m@x.fr"}])
    assert sortie == [{"nom": "Club", "origine": "source ajoutée par l'utilisateur", "ville": "Lyon"}]  # rien d'une personne ne passe, même si la requête le rend


def test_ajouter_une_base_exterieure_demande_une_adresse_une_requete_et_un_identifiant(cfg):
    from pilote import sources_ajout
    from pilote.refus import ConfigRefusee

    spec = {"nom": "Ma base", "systeme": "postgresql", "hote": "192.168.1.20", "base_nom": "orgs", "requete": "select nom from organisations where nom ilike :q_like", "utilisateur": "lecteur", "mot_de_passe": "x"}
    for manque in ("hote", "base_nom", "utilisateur"):
        with pytest.raises(ConfigRefusee):
            sources_ajout.enregistrer(cfg, "base_exterieure", {k: v for k, v in spec.items() if k != manque})
    with pytest.raises(ConfigRefusee, match="lecture"):
        sources_ajout.enregistrer(cfg, "base_exterieure", {**spec, "requete": "delete from organisations"})
    assert not (cfg.dossier_sources / "ma-base.yaml").exists()  # rien d'écrit quand on refuse


# --- avec de vrais serveurs (PostgreSQL et MariaDB sur 127.0.0.1:55432 et :53306, lancés pour l'occasion)
def _serveur(port):
    import socket

    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    except OSError:
        pytest.skip(f"aucun serveur de base de données sur 127.0.0.1:{port}")


BASE = {"hote": "127.0.0.1", "base_nom": "orgs", "utilisateur_env": "U", "mot_de_passe_env": "P", "_cles": {"U": "lecteur", "P": "essai"}}


@pytest.mark.reseau
def test_postgresql_reel_rend_les_noms_et_refuse_d_ecrire_meme_a_un_super_utilisateur():
    _serveur(55432)
    p = {**BASE, "systeme": "postgresql", "port": 55432, "requete": "select nom, ville, numero from organisations where nom ilike :q_like"}
    assert [n["nom"] for n in base_exterieure.chercher({"quoi": "club alpin"}, Client("x"), p)] == ["Club Alpin de Grenoble"]
    # Le rôle `lecteur` est super-utilisateur : c'est la transaction en lecture seule, imposée par le serveur, qui refuse. `lo_create` est une fonction qui ÉCRIT et qu'une
    # requête SELECT peut appeler : elle passe le filtre de mots et l'emballage `SELECT * FROM (…) LIMIT n`, seul le serveur l'arrête.
    with pytest.raises(Exception, match="read-only"):
        base_exterieure._postgresql("127.0.0.1", 55432, "orgs", "lecteur", "essai", None, 5, "select lo_create(0) as nom", [], 10)
    with pytest.raises(Exception):  # et l'emballage refuse déjà une instruction d'écriture déguisée en sous-requête
        base_exterieure._postgresql("127.0.0.1", 55432, "orgs", "lecteur", "essai", None, 5, "insert into organisations(nom) values ('x') returning nom", [], 10)


@pytest.mark.reseau
def test_postgresql_reel_coupe_une_requete_trop_longue_et_ne_cite_pas_le_mot_de_passe():
    _serveur(55432)
    lourde = {**BASE, "systeme": "postgresql", "port": 55432, "delai_requete_s": 1, "requete": "select count(*) as nom from generate_series(1, 2000000000)"}
    with pytest.raises(ErreurSource, match="trop de temps"):
        base_exterieure.lignes(lourde, "x", 5)
    with pytest.raises(ErreurSource) as e:
        base_exterieure.lignes({**BASE, "systeme": "postgresql", "port": 55432, "_cles": {"U": "lecteur", "P": "MOTDEPASSE-SECRET"}, "requete": "select nom from organisations"}, "x", 5)
    assert "MOTDEPASSE" not in str(e.value) and "mot de passe" in str(e.value)


@pytest.mark.reseau
def test_mariadb_reel_rend_les_noms_refuse_d_ecrire_et_coupe_une_requete_trop_longue():
    _serveur(53306)
    p = {**BASE, "systeme": "mysql", "port": 53306, "requete": "select nom, ville from organisations where nom like :q_like"}
    assert [n["nom"] for n in base_exterieure.chercher({"quoi": "boulangerie"}, Client("x"), p)] == ["Boulangerie Martin"]
    with pytest.raises(Exception, match="READ ONLY"):
        base_exterieure._mysql("127.0.0.1", 53306, "orgs", "lecteur", "essai", None, 5, "insert into organisations(nom) values ('x')", [], 10)
    lourde = {**p, "delai_requete_s": 1, "requete": "select count(*) as nom from seq_1_to_100000 a, seq_1_to_100000 b where a.seq * b.seq % 7 = 1"}
    with pytest.raises(ErreurSource, match="trop de temps"):
        base_exterieure.lignes(lourde, "x", 5)


@pytest.mark.reseau
def test_ajouter_une_base_postgresql_range_les_identifiants_a_part_et_dit_l_acces(cfg):
    from pilote import cles, suite_reel
    from pilote import reglages as rg
    from pilote.sources_ajout import AVERTISSEMENT_BASE_EXTERIEURE, enregistrer

    _serveur(55432)
    spec = {"nom": "Mes organisations", "systeme": "postgresql", "hote": "127.0.0.1", "port": 55432, "base_nom": "orgs", "utilisateur": "lecteur", "mot_de_passe": "essai",
            "requete": "select nom, ville from organisations where nom ilike :q_like", "mot_essai": "club", "genre": "association"}
    decl, test = enregistrer(cfg, "base_exterieure", spec)
    assert test["statut"] == "ok" and decl.avertissement == AVERTISSEMENT_BASE_EXTERIEURE and decl.moteur["adaptateur"] == "base_exterieure"
    brut = (cfg.dossier_sources / "mes-organisations.yaml").read_text(encoding="utf-8") + (cfg.dossier_sources / "exemples" / "mes-organisations.json").read_text(encoding="utf-8")
    assert "mot_de_passe: essai" not in brut and "essai\n" not in brut and "lecteur" not in brut  # ni le mot de passe ni l'identifiant dans la déclaration versionnée
    assert cles.valeur(cfg, "MES_ORGANISATIONS_MOT_DE_PASSE") == "essai" and cfg.fichiers_secrets[0].stat().st_mode & 0o777 == 0o600
    vue = next(s for s in suite_reel.sources(cfg, {}, {}) if s["id"] == "mes-organisations")
    assert vue["acces"] == "base_exterieure" and vue["machine"] == "127.0.0.1:55432/orgs" and vue["etat"] == "off" and vue["avertissement"]  # éteinte, avec son avertissement
    requis = rg.avertissements_requis(rg.charger(cfg), {decl.id: decl}, {"source": {"id": decl.id, "chercher": True}})
    assert [a["source"] for a in requis] == ["mes-organisations"]  # l'allumage montre l'avertissement (le même composant que l'Aide IA et les prestataires)


# --- YouTube, MatrixRooms.info, OpenAgenda : formes lues sur la documentation ou sur le service
def test_matrixrooms_lit_les_salons_de_la_page_markdown_et_les_etiquette_comme_des_communautes(cfg):
    from pilote.adaptateurs import matrixrooms

    noms = matrixrooms.convertir((EXEMPLES / "matrixrooms.txt").read_text(encoding="utf-8"))
    assert [n["nom"] for n in noms] == ["Club Exemple - discussion", "Médiathèque Exemple"]  # les échappements markdown sont retirés
    assert noms[0]["site"] == "https://matrixrooms.info/room/club-exemple:serveur.example" and "42 membres" in noms[0]["origine"] and noms[0]["genre"] == "compte"
    with pytest.raises(ErreurSource):
        matrixrooms.convertir("<html>autre chose</html>")
    d = charger_sources(cfg)[0]["matrixrooms"]
    assert not d.defaut.get("chercher") and d.cles == [] and d.roles == ["chercher"]


def test_youtube_envoie_la_cle_dans_l_adresse_la_region_et_rend_des_chaines(cfg):
    from pilote.adaptateurs import api_json

    d = charger_sources(cfg)[0]["youtube"]
    assert d.cles == ["YOUTUBE_API_KEY"] and not d.defaut.get("chercher") and "100 quota per day" in d.note and "NON vérifiée" in d.note
    vus = {}

    class _C(Client):
        def get_json(self, url, params=None, headers=None):
            vus.update(url=url, params=params, headers=headers)
            return json.loads((EXEMPLES / "youtube.json").read_text(encoding="utf-8"))

    noms = api_json.chercher({"quoi": "club", "pays": "fr", "limite": 5}, _C("youtube"), {**d.moteur["parametres"], "_cle": "CLE-DE-TEST"})
    assert vus["params"]["key"] == "CLE-DE-TEST" and vus["params"]["regionCode"] == "FR" and vus["params"]["type"] == "channel" and vus["params"]["part"] == "snippet"
    assert [n["nom"] for n in noms] == ["Club Exemple", "Médiathèque Exemple"] and noms[0]["site"] == "https://www.youtube.com/channel/UCexemple0000000000000001"
    api_json.chercher({"quoi": "club", "limite": 5}, _C("youtube"), {**d.moteur["parametres"], "_cle": "CLE-DE-TEST"})
    assert "regionCode" not in vus["params"]  # sans pays, le paramètre vide n'est pas envoyé


def test_openagenda_deduit_l_adresse_de_l_agenda_de_son_slug(cfg):
    from pilote.adaptateurs import api_json

    d = charger_sources(cfg)[0]["openagenda"]
    noms = api_json.convertir(json.loads((EXEMPLES / "openagenda.json").read_text(encoding="utf-8")), d.moteur["parametres"])
    assert noms[0]["site"] == "https://openagenda.com/club-exemple"


# --- Bluesky Jetstream : le filtrage par mot et par emoji est à notre charge
def test_jetstream_filtre_les_messages_par_mots_et_par_emoji(monkeypatch):
    from pilote.adaptateurs import jetstream

    def msg(did, texte, langs=("fr",)):
        return json.dumps({"did": did, "kind": "commit", "commit": {"operation": "create", "collection": "app.bsky.feed.post", "record": {"text": texte, "langs": list(langs)}}})

    flux = [msg("did:1", "Le collectif de Lyon recycle ♻️"), msg("did:2", "Un autre message sans rapport"), msg("did:3", "COLLECTIF écologique de Grenoble"), msg("did:4", "collectif ♻ sans sélecteur"),
            json.dumps({"did": "did:5", "kind": "identity"}), msg("did:6", "collectif anglais", ("en",)), msg("did:1", "le collectif encore ♻️")]
    monkeypatch.setattr(jetstream, "messages", lambda url, jusqu_a, arret=lambda: False: iter(flux))
    mots, emojis = jetstream._ce_qui_est_cherche("collectif ♻️")
    assert mots == ["collectif"] and emojis == ["♻"]
    dids, lus = jetstream.comptes_qui_parlent_de("wss://x", mots, emojis, 0, 10, [])
    assert dids == ["did:1"] and lus == 7  # mots ET emoji ; accents et casse ignorés ; un compte une seule fois
    assert jetstream.comptes_qui_parlent_de("wss://x", ["collectif"], [], 0, 10, ["fr"])[0] == ["did:1", "did:3", "did:4"]  # la langue filtre
    assert jetstream.comptes_qui_parlent_de("wss://x", ["collectif"], [], 0, 2, [])[0] == ["did:1", "did:3"]  # la limite arrête la lecture


def test_jetstream_rend_des_comptes_etiquetes_comme_tels_et_lit_l_exemple(cfg):
    from pilote.adaptateurs import jetstream

    noms = jetstream.convertir(json.loads((EXEMPLES / "jetstream.json").read_text(encoding="utf-8")), 30)
    assert [n["nom"] for n in noms] == ["Club Exemple", "Médiathèque Exemple"] and noms[0]["genre"] == "compte" and noms[0]["site"] == "https://bsky.app/profile/club-exemple.bsky.social"
    d = charger_sources(cfg)[0]["jetstream"]
    assert not d.defaut.get("chercher") and d.cles == []
    with pytest.raises(ErreurSource):
        jetstream.convertir({"autre": 1})


def test_jetstream_sans_mot_ni_emoji_n_ouvre_aucune_liaison():
    from pilote.adaptateurs import jetstream

    assert jetstream.chercher({"quoi": "de la"}, _Faux({}), {}) == []


@pytest.mark.reseau
def test_jetstream_reel_rejoue_les_dernieres_minutes_et_trouve_des_comptes():
    from pilote.adaptateurs import jetstream

    try:
        trouves = jetstream.chercher({"quoi": "♻️", "limite": 3}, Client("jetstream"), {"minutes": 15, "fenetre_s": 20})
    except ErreurSource as exc:
        pytest.skip(f"Jetstream indisponible : {exc}")
    assert trouves and all(n["genre"] == "compte" and n["site"].startswith("https://bsky.app/profile/") for n in trouves)


# --- points de la revue du 27/10 (code-review high)
def test_une_adresse_ecrite_en_decimal_ou_en_hexadecimal_est_resolue_avant_d_etre_jugee():
    for deguisee in ("2852039166", "0xa9fea9fe", "0251.0376.0251.0376"):  # tous = 169.254.169.254, le service de métadonnées d'un hébergeur
        with pytest.raises(ErreurSource):
            base_exterieure.verifier_adresse({"systeme": "mysql", "hote": deguisee})
    assert base_exterieure._est_sur_cette_machine("0x7f000001") and base_exterieure._est_sur_cette_machine("127.1")  # 127.0.0.1 écrite autrement : sur la machine
    assert not base_exterieure._est_sur_cette_machine("192.168.1.20")


def test_une_base_sans_mot_de_passe_s_enregistre_sans_cle_vide_ni_identifiant_orphelin(cfg):
    from pilote import cles, sources_ajout
    from pilote.refus import ConfigRefusee

    moteur, identifiants = sources_ajout._base_exterieure(
        {"nom": "Base locale sans mot de passe", "systeme": "postgresql", "hote": "127.0.0.1", "base_nom": "orgs", "requete": "select nom from organisations", "utilisateur": "lecteur"}, "x")
    assert list(identifiants.values()) == ["lecteur"] and "mot_de_passe_env" not in moteur["parametres"]  # une seule clé, aucune clé vide
    spec = {"nom": "Base à deux lignes", "systeme": "postgresql", "hote": "192.168.1.20", "base_nom": "orgs", "requete": "select nom from organisations", "utilisateur": "lecteur", "mot_de_passe": "a\nb"}
    with pytest.raises(ConfigRefusee):
        sources_ajout.enregistrer(cfg, "base_exterieure", spec)
    assert not cles.presente(cfg, "BASE_A_DEUX_LIGNES_UTILISATEUR")  # rien n'a été rangé avant le refus


def test_au_dela_de_300_fiches_une_paire_par_sigle_declare_est_quand_meme_comparee():
    from pilote.rapprochement_splink import scorer

    fiches = [{"id": i, "nom": f"Entreprise numéro {i} {chr(97 + i % 26)}{chr(97 + i // 26 % 26)}", "ville": f"Ville{i}", "numero": ""} for i in range(1, 320)]
    fiches += [{"id": 1000, "nom": "CEA", "ville": "Paris", "numero": ""},
               {"id": 1001, "nom": COMMISSARIAT, "ville": "Paris", "numero": "775685019", "alias": ["CEA"]}]
    paires = [p for p in scorer(fiches, 0.2) if {p["a"], p["b"]} == {1000, 1001}]
    assert paires and "alias" in paires[0]["pourquoi"]  # sans règle de blocage sur les alias, ces deux-là n'avaient ni mot ni préfixe en commun


def test_rdap_ne_prend_jamais_le_domaine_d_une_plateforme_pour_celui_de_l_organisation():
    assert rdap.domaines("https://monclub.wordpress.com/") == ["monclub.wordpress.com"]  # pas de repli sur wordpress.com
    assert rdap.domaines("https://www.facebook.com/monclub") == [] and rdap.domaines("https://bsky.app/profile/x") == []  # la plateforme elle-même : rien à demander
    assert rdap.domaines("https://club.asso.fr/") == ["club.asso.fr"]  # un vrai domaine sous un suffixe à usage libre
    assert rdap.domaines("https://blog.cea.fr/") == ["blog.cea.fr", "cea.fr"]


def test_un_delai_declare_s_applique_aux_sources_qui_cherchent_et_une_valeur_illisible_est_ignoree():
    from pilote.moteur_sources import _delai

    assert _delai({"delai_s": 1.0}) == {"delai_s": 1.0} and _delai({"delai_s": "abc"}) == {} and _delai({}) == {} and _delai({"delai_s": 9999}) == {"delai_s": 30.0}


def test_un_nom_de_domaine_accentue_est_encode_en_idna_et_le_reste_en_pourcent():
    from pilote.adaptateurs import _url_ascii

    assert _url_ascii("https://café.fr/été?q=✊") == "https://xn--caf-dma.fr/%C3%A9t%C3%A9?q=%E2%9C%8A"
    assert _url_ascii("https://exemple.example:8080/a b") == "https://exemple.example:8080/a b"  # une adresse ASCII n'est pas touchée


def test_jetstream_cherche_le_mot_entier():
    from pilote.adaptateurs import jetstream

    assert not jetstream.correspond("this is true", ["rue"], []) and not jetstream.correspond("skills", ["ski"], [])
    assert jetstream.correspond("Une rue, au calme", ["rue"], []) and jetstream.correspond("recyclage ♻️ local", [], ["♻"])


def test_une_saisie_faite_seulement_d_emoji_dit_que_le_moteur_l_a_recue_telle_quelle(cfg):
    from types import SimpleNamespace

    from pilote.executeur_grappes import ExecuteurGrappes

    avance, evenements = {}, []
    ctx = SimpleNamespace(avancer=lambda **k: avance.update(k), noter=lambda e, **k: evenements.append(e))
    spec = {"sources": ["bluesky", "ror", "wikidata"], "adaptateurs": [{"source": "bluesky"}, {"source": "ror"}], "scripts": [], "emoji": {"saisie": True, "ok": ["bluesky"], "moteur_recoit": True}}
    ExecuteurGrappes(cfg).dire_l_emoji(ctx, spec)
    assert avance["emoji"]["non_transmis"] == ["ror"] and avance["emoji"]["a_l_aveugle"] == ["wikidata"]  # ror a été privée de l'emoji ; wikidata (moteur) l'a reçu
    assert evenements == ["emoji_non_transmis", "emoji_envoye_sans_garantie"]
