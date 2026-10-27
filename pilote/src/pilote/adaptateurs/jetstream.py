"""Bluesky Jetstream : le flux public de tous les messages de Bluesky (WebSocket, JSON, sans clé). Il n'a AUCUN filtre par mot : le filtrage par mot-clé est à notre charge. Une écoute en
temps réel ne verrait presque rien (une quarantaine de messages par seconde, dont une ou deux en français) ; Jetstream accepte donc un `cursor` et REJOUE les dernières minutes bien plus vite que le
temps réel (dix minutes de messages en quelques secondes, mesuré le 27/10/2026). La source regarde ainsi les `minutes` dernières minutes (30 par défaut), au plus `fenetre_s` secondes de lecture.

Rend les COMPTES qui ont publié un message contenant tous les mots (et emoji) cherchés, avec leur nom d'affichage (profils publics de Bluesky). Un compte est une personne tant que son nom ne porte pas d'indice
institutionnel (règle 8, appliquée par le pont) : il n'entre alors dans aucun rapprochement. Client WebSocket minimal en bibliothèque standard (aucune bibliothèque WebSocket dans l'interpréteur de grappes)."""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
import urllib.parse
from collections.abc import Iterator
from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs, nom_normalise
from pilote.emoji_texte import reduit, trouver

LIT_PARAMETRES = True
SERVEUR = "jetstream2.us-east.bsky.network"
PROFILS = "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfiles"
MESSAGES_MAX = 400_000  # garde-fou : au-delà, la fenêtre est trop large pour être lue en entier


def messages(url: str, jusqu_a: float, arret=lambda: False) -> Iterator[str]:
    """Les messages texte d'un WebSocket (RFC 6455), jusqu'à l'heure `jusqu_a` (horloge monotone) ou à l'arrêt demandé. Gère les trames fragmentées, les ping et la fermeture."""
    u = urllib.parse.urlsplit(url)
    try:
        sock = ssl.create_default_context().wrap_socket(socket.create_connection((u.hostname, u.port or 443), timeout=10), server_hostname=u.hostname)
    except OSError as exc:
        raise ErreurSource("Le flux Jetstream ne répond pas.") from exc
    try:
        cle = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(f"GET {u.path}?{u.query} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: pilote/0.1\r\n\r\n".encode())
        tete = b""
        while b"\r\n\r\n" not in tete:
            morceau = sock.recv(4096)
            if not morceau:
                raise ErreurSource("Le flux Jetstream a fermé la liaison.")
            tete += morceau
        entete, _, buf = tete.partition(b"\r\n\r\n")
        if b" 101 " not in entete.split(b"\r\n")[0]:
            raise ErreurSource("Le flux Jetstream a refusé la demande.")
        sock.settimeout(1.0)
        fragments = b""
        while time.monotonic() < jusqu_a and not arret():
            try:
                while len(buf) < 2:
                    buf += _recevoir(sock)
                op, long = buf[0] & 0x0F, buf[1] & 0x7F
                debut = 2
                if long == 126:
                    while len(buf) < 4:
                        buf += _recevoir(sock)
                    long, debut = struct.unpack(">H", buf[2:4])[0], 4
                elif long == 127:
                    while len(buf) < 10:
                        buf += _recevoir(sock)
                    long, debut = struct.unpack(">Q", buf[2:10])[0], 10
                while len(buf) < debut + long:
                    buf += _recevoir(sock)
            except TimeoutError:
                continue
            charge, fin_message, buf = buf[debut : debut + long], bool(buf[0] & 0x80), buf[debut + long :]
            if op == 8:
                return
            if op == 9:  # ping : on répond (une trame envoyée par le client est masquée)
                masque = os.urandom(4)
                if len(charge) < 126:
                    sock.sendall(bytes([0x8A, 0x80 | len(charge)]) + masque + bytes(b ^ masque[i % 4] for i, b in enumerate(charge)))
            elif op in (0, 1):
                fragments += charge
                if fin_message:
                    yield fragments.decode("utf-8", "replace")
                    fragments = b""
    finally:
        sock.close()


def _recevoir(sock: socket.socket) -> bytes:
    d = sock.recv(65536)
    if not d:
        raise ErreurSource("Le flux Jetstream a fermé la liaison.")
    return d


def _ce_qui_est_cherche(quoi: str) -> tuple[list[str], list[str]]:
    """(mots, emoji) de la requête, sous leur forme de comparaison : sans accent ni casse pour les mots, sans U+FE0F ni teinte de peau pour les emoji."""
    elements = mots_significatifs(quoi, 6)
    emojis = [reduit(e) for _, _, e in trouver(quoi)]
    mots = [nom_normalise(m) for m in elements if not trouver(m)]
    return [m for m in mots if m], emojis


def correspond(texte: str, mots: list[str], emojis: list[str]) -> bool:
    plat = f" {nom_normalise(texte)} "
    return all(f" {m} " in plat for m in mots) and all(f" {e} " in plat for e in emojis)  # le MOT entier : « rue » n'est pas dans « true », « ski » pas dans « skills »


def comptes_qui_parlent_de(url_flux: str, mots: list[str], emojis: list[str], jusqu_a: float, limite: int, langues: list[str], arret=lambda: False) -> tuple[list[str], int]:
    """(DID des auteurs, nombre de messages lus). S'arrête à la limite de comptes, au temps ou à l'arrêt demandé."""
    vus: dict[str, None] = {}
    lus = 0
    for brut in messages(url_flux, jusqu_a, arret):
        lus += 1
        if lus > MESSAGES_MAX or len(vus) >= limite:
            break
        try:
            m = json.loads(brut)
        except ValueError:
            continue
        c = m.get("commit") or {}
        if m.get("kind") != "commit" or c.get("operation") != "create" or c.get("collection") != "app.bsky.feed.post":
            continue
        rec = c.get("record") or {}
        if langues and not set(langues) & set(rec.get("langs") or []):
            continue
        if correspond(str(rec.get("text") or ""), mots, emojis):
            vus.setdefault(str(m["did"]), None)
    return list(vus), lus


def convertir(rep: Any, minutes: int = 30) -> list[dict[str, Any]]:
    """Réponse de `getProfiles` -> noms. Le nom d'affichage, sinon l'identifiant public (handle)."""
    if not isinstance(rep, dict) or "profiles" not in rep:
        raise ErreurSource("La réponse de Bluesky n'a pas la forme attendue.")
    out = []
    for p in rep.get("profiles") or []:
        nom = str(p.get("displayName") or p.get("handle") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": f"Bluesky Jetstream (compte ayant publié sur ce sujet ces {minutes} dernières minutes)", "site": "https://bsky.app/profile/" + str(p.get("handle", "")), "genre": "compte"})
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    quoi = " ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])]).strip()
    mots, emojis = _ce_qui_est_cherche(quoi)
    if not mots and not emojis:
        return []
    minutes = max(1, min(int(parametres.get("minutes") or 30), 240))
    fenetre = max(5.0, min(float(parametres.get("fenetre_s") or 25), 60.0))
    limite = min(int(entree.get("limite") or 25), 100)
    serveur = str(parametres.get("serveur") or SERVEUR)
    curseur = int((time.time() - minutes * 60) * 1_000_000)
    url = f"wss://{serveur}/subscribe?" + urllib.parse.urlencode({"wantedCollections": "app.bsky.feed.post", "cursor": curseur})
    client._avant()  # un appel compté, arrêt immédiat si demandé
    dids, _ = comptes_qui_parlent_de(url, mots, emojis, time.monotonic() + fenetre, limite, [str(x) for x in parametres.get("langues") or []], client.doit_s_arreter)
    noms: list[dict[str, Any]] = []
    for i in range(0, len(dids), 25):  # 25 profils par appel : le maximum de l'API publique
        lot = dids[i : i + 25]
        noms += convertir(client.get_json(PROFILS + "?" + urllib.parse.urlencode([("actors", d) for d in lot])), minutes)
    return noms[:limite]
