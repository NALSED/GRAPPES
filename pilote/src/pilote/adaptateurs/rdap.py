"""RDAP (Registration Data Access Protocol, RFC 7480 à 7483 ; amorçage par l'IANA, RFC 9224) : ce que le registre d'un nom de domaine dit de lui, en JSON structuré.
Le successeur normalisé de WHOIS. Sans clé : le serveur d'amorçage rdap.org redirige vers le registre compétent. Rôle ENRICHIR : on lui donne le site d'une fiche, il rend de
l'information EN PLUS (bureau d'enregistrement, dates, statut, organisation titulaire), jamais une recherche par mot.

Règle n° 8 : on ne garde AUCUN champ de contact de personne (nom, adresse, courriel, téléphone du titulaire, du contact administratif ou technique), même quand le registre
les rend (le registre français les rend). Les registres européens masquent déjà les titulaires personnes physiques, mais la règle ne dépend pas de leur politique : on lit le nom
du bureau d'enregistrement et l'`org` du seul titulaire, et rien d'autre dans les fiches de contact."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from pilote.adaptateurs import Client, ErreurSource

URL = "https://rdap.org/domain/"
ENTETES = {"Accept": "application/rdap+json"}
MASQUE = re.compile(r"redacted|privacy|withheld|not disclosed|data protected|gdpr", re.IGNORECASE)  # ce que les registres écrivent à la place d'un titulaire masqué
SECOND_NIVEAU = {"co", "com", "org", "net", "gov", "ac", "edu"}
STATUTS_MAX = 3
# Un site hébergé sur une plateforme n'a pas de domaine à lui : le registre du domaine de la plateforme parlerait de la plateforme, pas de l'organisation (« titulaire déclaré : WordPress »).
# Approximation sans liste publique des suffixes (aucune bibliothèque dans l'interpréteur de grappes) : les plateformes courantes et les suffixes à nom d'usage libre.
PLATEFORMES = frozenset({
    "wordpress.com", "blogspot.com", "wixsite.com", "wix.com", "github.io", "gitlab.io", "netlify.app", "vercel.app", "herokuapp.com", "weebly.com", "squarespace.com", "over-blog.com", "canalblog.com",
    "free.fr", "orange.fr", "wanadoo.fr", "sfr.fr", "laposte.net", "facebook.com", "fb.com", "instagram.com", "x.com", "twitter.com", "linkedin.com", "youtube.com", "youtu.be", "tiktok.com", "bsky.app",
    "reddit.com", "t.me", "telegram.me", "mastodon.social", "meetup.com", "helloasso.com", "linktr.ee", "google.com", "sites.google.com", "notion.site", "carrd.co", "jimdofree.com", "jimdosite.com", "webself.net",
    "asso.fr", "gouv.fr", "com.fr", "nom.fr", "co.uk", "org.uk", "gov.uk",
})  # fmt: skip
ACTIONS = (("registration", "enregistré le"), ("expiration", "expire le"), ("last changed", "dernière modification le"))


def domaines(site: str) -> list[str]:
    """Les domaines à essayer pour l'adresse d'un site : l'hôte tel quel (sans `www.`), puis son domaine enregistrable approché (deux libellés, trois sous un second niveau co/com/org…)."""
    brut = str(site or "").strip()
    hote = (urlsplit(brut if "//" in brut else "//" + brut).hostname or "").lower().removeprefix("www.").rstrip(".")
    if not hote or "." not in hote or not re.fullmatch(r"[a-z0-9.-]+", hote):
        return []
    libelles = hote.split(".")
    garde = 3 if len(libelles) > 2 and libelles[-2] in SECOND_NIVEAU and len(libelles[-1]) == 2 else 2
    approche = ".".join(libelles[-garde:])
    if hote in PLATEFORMES:  # le site est la plateforme elle-même (une page de réseau social) : son registre ne dit rien de l'organisation
        return []
    if approche in PLATEFORMES:  # « club.asso.fr » est un domaine à lui ; « monclub.wordpress.com » n'en est pas un (404) : dans les deux cas, jamais le parent
        return [hote]
    return [hote] if approche == hote else [hote, approche]


def _date(t: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t or "")
    return f"{m[3]}/{m[2]}/{m[1]}" if m else ""


def _fn_registraire(entites: list[dict[str, Any]]) -> str:
    for e in entites:
        if "registrar" in (e.get("roles") or []):
            for champ in (e.get("vcardArray") or [None, []])[1]:
                if isinstance(champ, list) and champ[:1] == ["fn"] and len(champ) > 3:
                    return str(champ[3]).strip()
    return ""


def _org_titulaire(entites: list[dict[str, Any]]) -> str:
    """L'organisation déclarée du titulaire (champ `org`), sinon rien : le `fn` d'un titulaire peut être le nom d'une personne, il n'est jamais lu."""
    for e in entites:
        if "registrant" in (e.get("roles") or []):
            for champ in (e.get("vcardArray") or [None, []])[1]:
                if isinstance(champ, list) and champ[:1] == ["org"] and len(champ) > 3:
                    org = champ[3][0] if isinstance(champ[3], list) and champ[3] else champ[3]
                    org = str(org or "").strip()
                    if org and not MASQUE.search(org):
                        return org
    return ""


def convertir(rep: dict[str, Any], nom: str = "") -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or rep.get("objectClassName") != "domain":
        raise ErreurSource("La réponse du registre n'a pas la forme attendue (RDAP, objet « domain »).")
    domaine = str(rep.get("ldhName") or "").lower()
    dates = {e.get("eventAction"): _date(str(e.get("eventDate") or "")) for e in rep.get("events") or [] if isinstance(e, dict)}
    morceaux = [f"{libelle} {dates[action]}" for action, libelle in ACTIONS if dates.get(action)]
    entites = [e for e in rep.get("entities") or [] if isinstance(e, dict)]
    registraire, titulaire = _fn_registraire(entites), _org_titulaire(entites)
    if registraire:
        morceaux.append(f"bureau d'enregistrement : {registraire}")
    if titulaire:
        morceaux.append(f"titulaire déclaré : {titulaire}")
    statuts = [str(s) for s in rep.get("status") or []][:STATUTS_MAX]
    if statuts:
        morceaux.append("statut : " + ", ".join(statuts))
    if not morceaux:
        return []
    return [{"nom": nom or domaine, "origine": "RDAP (registre du nom de domaine)", "detail": f"domaine {domaine} : " + " ; ".join(morceaux)}]


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    """Le domaine du site de la fiche. Un domaine inconnu du registre (404) n'est pas une panne : on essaie le domaine enregistrable, puis on ne rend rien."""
    nom = str(entree.get("nom") or entree.get("quoi") or "").strip()
    for domaine in domaines(str(entree.get("site") or "")):
        try:
            rep = client.get_json(URL + domaine, headers=ENTETES)
        except ErreurSource as exc:
            if exc.code == 404:
                continue
            raise
        trouves = convertir(rep, nom)
        if trouves:
            return trouves
    return []
