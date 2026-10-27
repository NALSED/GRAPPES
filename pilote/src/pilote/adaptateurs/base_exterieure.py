"""Base de données EXTÉRIEURE (PostgreSQL, MySQL ou MariaDB sur une autre machine du réseau), LECTURE SEULE. Même contrat que `base_sql` (une seule instruction SELECT, mots cherchés
par paramètre lié, colonnes `nom` et au choix `ville`, `genre`, `numero`, `site`, `pays`), et les garde-fous qu'une base en réseau exige EN PLUS :

1. la lecture seule est imposée par le SERVEUR (transaction `READ ONLY`), pas seulement par un filtre de mots, qui reste une première barrière et jamais la seule ;
2. un délai maximal d'exécution (`statement_timeout` côté PostgreSQL, `max_execution_time` / `max_statement_time` côté MySQL et MariaDB) : une requête lourde ne bloque pas la recherche ;
3. les identifiants sont dans `secrets.env` (variables nommées par `utilisateur_env` et `mot_de_passe_env`), jamais dans la déclaration, qui est versionnée ;
4. TLS dès que la base n'est pas sur la machine (équivalent de `sslmode=require`) ; sur la machine elle-même, il est facultatif ;
5. l'adresse de la machine est celle de la déclaration de CETTE source, et nulle part ailleurs : aucune règle sur les adresses privées n'est assouplie ailleurs dans le programme.

Limite dite franchement : le test de la règle n° 8 ne peut pas lire la requête d'une base extérieure (l'utilisateur l'écrit, et rien n'empêche `SELECT prenom AS nom`). Ce qui est fait : seules les colonnes
connues sont gardées, un avertissement est montré à l'allumage, la source démarre éteinte. Le contenu de cette base est de la responsabilité de son propriétaire."""

from __future__ import annotations

import ipaddress
import re
import socket
import ssl
from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs
from pilote.adaptateurs.api_json import convertir as _convertir
from pilote.adaptateurs.base_sql import verifier_requete as _verifier_requete

LIT_PARAMETRES = True
SYSTEMES = {"postgresql": 5432, "mysql": 3306}  # MariaDB parle le protocole MySQL : « mysql »
DELAI_MAX_S = 60
DELAI_DEFAUT_S = 10
# en plus de la liste de base_sql : ce qu'un serveur permet et qu'un fichier SQLite ne permet pas
INTERDITS_RESEAU = re.compile(
    r"\b(into|grant|revoke|call|execute|exec|copy|truncate|lock|set|do|handler|outfile|dumpfile|load_file|load|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_sleep|sleep|benchmark|dblink|lo_import|lo_export|lo_create|lo_unlink|lo_put|lowrite|"
    r"pg_terminate_backend|pg_cancel_backend|set_config|current_setting|nextval|setval)\b",
    re.IGNORECASE,
)
PARAMETRE = re.compile(r":q_like\b|:q\b")


def verifier_requete(sql: str) -> str:
    s = _verifier_requete(sql)
    if INTERDITS_RESEAU.search(s):
        raise ErreurSource("Cette requête contient un mot que le serveur autoriserait mais que cette prise refuse (écriture, gestion, fichier, attente) : seule la lecture est permise.")
    return s


def _adresses(hote: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Les adresses auxquelles l'hôte RÉSOUT vraiment (`2852039166` et `0xa9fea9fe` sont 169.254.169.254 pour le système, pas pour `ipaddress`). Un nom que le système ne résout pas : liste vide."""
    try:
        return [ipaddress.ip_address(i[4][0].split("%")[0]) for i in socket.getaddrinfo(hote, None, type=socket.SOCK_STREAM)]
    except (OSError, ValueError):
        return []


def _est_sur_cette_machine(hote: str) -> bool:
    if hote in ("localhost", "::1"):
        return True
    adresses = _adresses(hote)
    return bool(adresses) and all(a.is_loopback for a in adresses)


def verifier_adresse(parametres: dict[str, Any]) -> tuple[str, str, int]:
    """(système, hôte, port) de la déclaration, ou un refus en français. L'adresse ne vient jamais de la requête de recherche."""
    systeme = str(parametres.get("systeme", "")).lower()
    if systeme not in SYSTEMES:
        raise ErreurSource("Le système de la base extérieure doit être « postgresql » ou « mysql » (MariaDB aussi).")
    hote = str(parametres.get("hote", "")).strip()
    if not hote or not re.fullmatch(r"[A-Za-z0-9._:-]+", hote):
        raise ErreurSource("Donnez l'adresse de la machine qui porte la base (un nom ou une adresse IP).")
    if any(a.is_link_local or a.is_multicast or a.is_unspecified for a in _adresses(hote)):  # 169.254.169.254 : le service de métadonnées d'un hébergeur, jamais une base (même écrite 2852039166)
        raise ErreurSource("Cette adresse n'est pas celle d'une base extérieure (adresse de lien local ou réservée).")
    try:
        port = int(parametres.get("port") or SYSTEMES[systeme])
    except ValueError as exc:
        raise ErreurSource("Le port doit être un nombre.") from exc
    if not 1 <= port <= 65535:
        raise ErreurSource("Le port doit être compris entre 1 et 65535.")
    return systeme, hote, port


def _contexte_tls(parametres: dict[str, Any], hote: str) -> ssl.SSLContext | None:
    """TLS obligatoire hors de la machine ; sur la machine, seulement si `tls: true`. Par défaut le chiffrement est exigé sans vérifier le certificat (comme `sslmode=require`,
    car un réseau privé a souvent un certificat auto-signé) ; `tls_verifier: true` vérifie le certificat et le nom de la machine."""
    local = _est_sur_cette_machine(hote)
    voulu = parametres.get("tls")
    if not local and voulu is False:
        raise ErreurSource("Cette base n'est pas sur cette machine : la liaison doit être chiffrée (TLS), elle ne peut pas être désactivée.")
    if local and not voulu:
        return None
    ctx = ssl.create_default_context()
    if not parametres.get("tls_verifier"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _delai(parametres: dict[str, Any]) -> int:
    try:
        d = int(float(parametres.get("delai_requete_s") or DELAI_DEFAUT_S))
    except ValueError:
        d = DELAI_DEFAUT_S
    return max(1, min(d, DELAI_MAX_S))


def _identifiants(parametres: dict[str, Any]) -> tuple[str, str]:
    """(utilisateur, mot de passe) lus dans les clés de la source (`secrets.env`), nommées par la déclaration. Jamais écrits dans la déclaration."""
    cles = parametres.get("_cles") or {}
    u, m = str(cles.get(str(parametres.get("utilisateur_env", "")), "")), str(cles.get(str(parametres.get("mot_de_passe_env", "")), ""))
    if not u:
        raise ErreurSource("L'identifiant de cette base extérieure est absent : la source reste éteinte sans lui.")
    return u, m


def _sql_et_valeurs(sql: str, q: str) -> tuple[str, list[str]]:
    """Le texte de la requête avec des marques « %s » du pilote (ordre d'apparition), et les valeurs liées. Un « % » déjà dans le texte (LIKE) est doublé."""
    valeurs: list[str] = []

    def marque(m: re.Match[str]) -> str:
        valeurs.append(f"%{q}%" if m.group().startswith(":q_like") else q)
        return "%s"

    morceaux, fin = [], 0
    for m in PARAMETRE.finditer(sql):
        morceaux += [sql[fin : m.start()].replace("%", "%%"), marque(m)]
        fin = m.end()
    morceaux.append(sql[fin:].replace("%", "%%"))
    return "".join(morceaux), valeurs


def lignes(parametres: dict[str, Any], q: str, limite: int) -> list[dict[str, Any]]:
    sql = verifier_requete(str(parametres.get("requete", "")))
    systeme, hote, port = verifier_adresse(parametres)
    base = str(parametres.get("base_nom", "")).strip()
    if not base:
        raise ErreurSource("Donnez le nom de la base à interroger.")
    utilisateur, mot_de_passe = _identifiants(parametres)
    ctx, delai = _contexte_tls(parametres, hote), _delai(parametres)
    texte, valeurs = _sql_et_valeurs(sql, q)
    try:
        return _postgresql(hote, port, base, utilisateur, mot_de_passe, ctx, delai, texte, valeurs, limite) if systeme == "postgresql" else _mysql(hote, port, base, utilisateur, mot_de_passe, ctx, delai, texte, valeurs, limite)
    except ErreurSource:
        raise
    except Exception as exc:
        raise ErreurSource(_message(exc)) from exc


def _message(exc: Exception) -> str:
    t = f"{type(exc).__name__} {exc}".lower()
    if "can't create a connection" in t or "refused" in t or "can't connect" in t or "name or service" in t or "unreachable" in t or "no route" in t:
        return "La base extérieure ne répond pas (machine éteinte, adresse ou port faux, ou pare-feu)."
    if "password" in t or "authentication" in t or "access denied" in t or "28p01" in t or "28000" in t:
        return "La base extérieure a refusé l'identifiant ou le mot de passe."
    if "canceling statement" in t or "max_statement_time" in t or "maximum statement execution time" in t or "interrupted" in t or "timed out" in t or "timeout" in t:
        return "La base extérieure a mis trop de temps à répondre : la requête a été coupée."
    if "ssl" in t or "tls" in t:
        return "La liaison chiffrée (TLS) avec la base extérieure a échoué."
    if "read-only" in t or "read only" in t:
        return "La base extérieure a refusé la requête : elle n'est permise qu'en lecture."
    return f"La base extérieure a refusé la requête ({type(exc).__name__})."


def _postgresql(hote, port, base, utilisateur, mot_de_passe, ctx, delai, texte, valeurs, limite):
    import pg8000.dbapi as pg

    con = pg.connect(user=utilisateur, password=mot_de_passe, host=hote, port=port, database=base, ssl_context=ctx, timeout=delai + 5)
    try:
        cur = con.cursor()
        cur.execute("SET TRANSACTION READ ONLY")  # imposé par le serveur : même un rôle qui peut écrire ne le peut pas dans cette transaction
        cur.execute(f"SET LOCAL statement_timeout = {delai * 1000}")
        cur.execute(f"SELECT * FROM ({texte}) AS _q LIMIT {int(limite)}", valeurs)  # la limite est posée côté serveur : pg8000 charge tout le résultat en mémoire avant `fetchmany`
        noms = [c[0] for c in cur.description or []]
        return [dict(zip(noms, r, strict=False)) for r in cur.fetchmany(limite)]
    finally:
        con.rollback()
        con.close()


def _mysql(hote, port, base, utilisateur, mot_de_passe, ctx, delai, texte, valeurs, limite):
    import pymysql

    con = pymysql.connect(host=hote, port=port, user=utilisateur, password=mot_de_passe, database=base, ssl=ctx if ctx else None, connect_timeout=delai, read_timeout=delai + 5, write_timeout=delai, autocommit=False)
    try:
        cur = con.cursor(pymysql.cursors.DictCursor)
        cur.execute("SET SESSION TRANSACTION READ ONLY")
        cur.execute(f"SET SESSION sql_select_limit = {int(limite)}")  # la limite est posée côté serveur : pymysql charge tout le résultat en mémoire avant `fetchmany`
        for requete in (f"SET SESSION max_execution_time = {delai * 1000}", f"SET SESSION max_statement_time = {delai}"):  # MySQL (ms) ou MariaDB (s) : l'un des deux existe
            try:
                cur.execute(requete)
            except pymysql.MySQLError:
                pass
        cur.execute("START TRANSACTION READ ONLY")
        cur.execute(texte, valeurs)
        return [dict(r) for r in cur.fetchmany(limite)]
    finally:
        try:
            con.rollback()
        finally:
            con.close()


def convertir(brut: Any, parametres: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Seules les colonnes connues sont gardées (nom, ville, genre, numero, site, pays) : tout autre champ de la requête est ignoré."""
    return _convertir(brut, {**(parametres or {}), "champs": {c: c for c in ("nom", "ville", "genre", "numero", "site", "pays")}, "liste": ""})


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    quoi = str(entree.get("quoi", "")).strip()
    mots = mots_significatifs(quoi, 3)
    if not quoi:
        return []
    client._avant()  # un appel compté, arrêt immédiat si demandé
    return convertir(lignes(parametres, " ".join(mots) or quoi, int(entree.get("limite") or 50)), parametres)
