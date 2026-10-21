"""Flux RSS de l'utilisateur (fiche 09) : la liste des journaux et sites à suivre, dans un fichier à lui (`config/flux_rss.yaml`).

On les ajoute à la main (adresse du flux) ou d'un coup par un fichier OPML — le format d'export que tous les lecteurs de flux savent
produire (Feedly, Inoreader, NetNewsWire...). Aucune API de ces plateformes n'est utilisée. Chaque flux ajouté est LU une fois pour
vérifier qu'il rend bien des articles. Pour la recherche, chaque flux devient une prise de grappes (voir `moteur_sources`)."""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, lire_yaml, verrou, yaml_texte

UA = "pilote/0.1 (outil libre de recherche d'acteurs ; lecteur de flux, respecte robots.txt côté grappes)"
MAX_OCTETS = 2_000_000
MAX_FLUX = 500
FORMATS = ("rss", "atom", "inconnu")  # « inconnu » : importé d'un OPML sans être lu ; le format est détecté à la première recherche
ENTETE = "# Flux RSS à suivre (écrit par pilote, lisible à la main). Un flux = un nom et son adresse. Import possible d'un fichier OPML depuis la page.\n"


def identifiant(url: str) -> str:
    """Identifiant stable et lisible d'un flux : « rss- » + domaine + 6 caractères de l'adresse complète."""
    hote = re.sub(r"[^a-z0-9]+", "-", (urllib.parse.urlsplit(url).hostname or "flux").lower()).strip("-")[:40]
    return f"rss-{hote}-{hashlib.sha1(url.encode()).hexdigest()[:6]}"


def verifier_adresse(url: str) -> str:
    u = urllib.parse.urlsplit(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ConfigRefusee("L'adresse d'un flux doit commencer par http:// ou https://.")
    return url.strip()


def charger(cfg: Config) -> list[dict[str, str]]:
    f = cfg.fichier_flux_rss
    if not f.exists():
        return []
    y = lire_yaml(f)
    flux = y.get("flux") or []
    if not isinstance(flux, list) or not all(isinstance(x, dict) and x.get("url") for x in flux):
        raise ConfigRefusee("Le fichier des flux RSS est mal écrit : il faut une liste « flux » dont chaque élément a au moins une « url ».")
    return [{"id": identifiant(str(x["url"])), "nom": str(x.get("nom") or x["url"]), "url": str(x["url"]), "pays": str(x.get("pays") or ""),
             "format": x.get("format") if x.get("format") in FORMATS else "rss"} for x in flux]  # fmt: skip


def _ecrire(cfg: Config, flux: list[dict[str, str]]) -> None:
    if len(flux) > MAX_FLUX:
        raise ConfigRefusee(f"Trop de flux ({len(flux)}) : la limite est de {MAX_FLUX}.")
    brut = [{"nom": x["nom"], "url": x["url"], **({"pays": x["pays"]} if x.get("pays") else {}), **({"format": x["format"]} if x.get("format") in ("atom", "inconnu") else {})} for x in flux]
    ecrire_atomique(cfg.fichier_flux_rss, yaml_texte({"flux": brut}, ENTETE))


def _lire_xml(octets: bytes) -> ET.Element:
    if re.search(rb"<!ENTITY|<!DOCTYPE[^>]*\[", octets[:20000]):
        raise ConfigRefusee("Ce fichier XML déclare des entités : refusé par prudence (un flux ou un OPML n'en a pas besoin).")
    try:
        return ET.fromstring(octets)
    except ET.ParseError as exc:
        raise ConfigRefusee("Le fichier n'est pas du XML lisible.") from exc


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def format_du_flux(racine: ET.Element) -> str:
    return "atom" if _local(racine.tag) == "feed" else "rss"


def lire_articles(octets: bytes) -> list[dict[str, str]]:
    """Articles d'un flux RSS 2.0 ou Atom : titre, adresse, date. Rend [] si le XML est valide mais n'est pas un flux."""
    return lire_flux(octets)[1]


def lire_flux(octets: bytes) -> tuple[str, list[dict[str, str]]]:
    racine = _lire_xml(octets)
    out = []
    for el in racine.iter():
        if _local(el.tag) in ("item", "entry"):
            champs = {_local(c.tag): c for c in el}
            titre = (champs["title"].text or "").strip() if "title" in champs else ""
            lien = ""
            if "link" in champs:
                lien = (champs["link"].text or champs["link"].attrib.get("href", "")).strip()
            date = next(((champs[k].text or "").strip() for k in ("pubDate", "published", "updated", "date") if k in champs), "")
            if titre:
                out.append({"titre": titre, "url": lien, "date": date})
    return format_du_flux(racine), out


def telecharger(url: str, delai_s: float = 20.0) -> bytes:
    req = urllib.request.Request(verifier_adresse(url), headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1"})
    try:
        with urllib.request.urlopen(req, timeout=delai_s) as r:
            return r.read(MAX_OCTETS + 1)[:MAX_OCTETS]
    except urllib.error.HTTPError as exc:
        raise ConfigRefusee(f"Le flux a répondu une erreur ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConfigRefusee("Le flux ne répond pas.") from exc


def tester(url: str) -> dict[str, Any]:
    """Lit le flux UNE fois : combien d'articles, et les premiers titres. Refuse ce qui n'est pas un flux d'articles."""
    format_, arts = lire_flux(telecharger(url))
    if not arts:
        raise ConfigRefusee("Cette adresse répond, mais ce n'est pas un flux d'articles (aucun article trouvé).")
    return {"articles": len(arts), "titres": [a["titre"] for a in arts[:5]], "format": format_}


def ajouter(cfg: Config, url: str, nom: str = "", pays: str = "", verifier: bool = True) -> dict[str, Any]:
    url = verifier_adresse(url)
    if any(x["url"] == url for x in charger(cfg)):
        raise ConfigRefusee("Ce flux est déjà dans la liste.")
    lu = tester(url) if verifier else {"articles": 0, "titres": []}  # lecture réseau HORS du verrou : elle peut durer 20 s
    nouveau = {"id": identifiant(url), "nom": (nom or url).strip(), "url": url, "pays": pays.strip().upper(), "format": lu.get("format", "rss")}
    with verrou(cfg.fichier_flux_rss):  # lire, modifier, écrire : deux ajouts simultanés perdaient l'un des deux
        flux = charger(cfg)
        if any(x["url"] == url for x in flux):
            raise ConfigRefusee("Ce flux est déjà dans la liste.")
        _ecrire(cfg, [*flux, nouveau])
    return {**nouveau, **lu}


def supprimer(cfg: Config, ident: str) -> None:
    with verrou(cfg.fichier_flux_rss):
        flux = charger(cfg)
        reste = [x for x in flux if x["id"] != ident]
        if len(reste) == len(flux):
            raise ConfigRefusee("Ce flux n'existe pas.")
        _ecrire(cfg, reste)


def resoudre_formats(cfg: Config, delai_s: float = 10.0) -> int:
    """Détecte le format (RSS ou Atom) des flux importés d'un OPML sans avoir été lus (« inconnu »), en les lisant une fois, et l'enregistre.
    Appelé au lancement d'une recherche, jamais en ouvrant une page. Un flux injoignable reste « inconnu » (traité comme RSS) et sera
    retenté à la recherche suivante. Rend le nombre de flux résolus."""
    a_lire = [x for x in charger(cfg) if x["format"] == "inconnu"]
    trouves: dict[str, str] = {}
    for x in a_lire:  # lectures réseau hors du verrou
        try:
            trouves[x["url"]] = format_du_flux(_lire_xml(telecharger(x["url"], delai_s)))
        except ConfigRefusee:
            continue
    if not trouves:
        return 0
    with verrou(cfg.fichier_flux_rss):
        flux = charger(cfg)
        for x in flux:
            if x["format"] == "inconnu" and x["url"] in trouves:
                x["format"] = trouves[x["url"]]
        _ecrire(cfg, flux)
    return len(trouves)


def lire_opml(octets: bytes) -> list[dict[str, str]]:
    """Flux d'un fichier OPML : chaque « outline » qui porte un `xmlUrl` ; les dossiers (outlines emboîtées) sont parcourus."""
    racine = _lire_xml(octets)
    if _local(racine.tag).lower() != "opml":
        raise ConfigRefusee("Ce fichier n'est pas un OPML (la racine devrait être « opml »).")
    out = []
    for el in racine.iter():
        if _local(el.tag) == "outline" and el.attrib.get("xmlUrl"):
            out.append({"nom": (el.attrib.get("title") or el.attrib.get("text") or el.attrib["xmlUrl"]).strip(), "url": el.attrib["xmlUrl"].strip()})
    return out


def importer_opml(cfg: Config, octets: bytes) -> dict[str, Any]:
    """Crée les flux d'un OPML. Pas de lecture réseau de chacun (il peut y en avoir des centaines) : le test se fait à la première recherche."""
    trouves = lire_opml(octets)
    if not trouves:
        raise ConfigRefusee("Aucun flux trouvé dans ce fichier OPML.")
    with verrou(cfg.fichier_flux_rss):
        return _importer(cfg, trouves)


def _importer(cfg: Config, trouves: list[dict[str, str]]) -> dict[str, Any]:
    flux = charger(cfg)
    connus = {x["url"] for x in flux}
    ajoutes, doublons, ignores = [], 0, []
    for t in trouves:
        try:
            url = verifier_adresse(t["url"])
        except ConfigRefusee:
            ignores.append(t["nom"])
            continue
        if url in connus:
            doublons += 1
            continue
        connus.add(url)
        ajoutes.append({"id": identifiant(url), "nom": t["nom"], "url": url, "pays": "", "format": "inconnu"})  # pas lu ici : détecté à la 1re recherche
    _ecrire(cfg, [*flux, *ajoutes])
    return {"ajoutes": len(ajoutes), "doublons": doublons, "ignores": ignores, "flux": ajoutes}
