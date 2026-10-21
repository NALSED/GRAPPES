"""Catalogue des bases officielles par pays (fiche 15, chapitre 3).

Un fichier texte par pays dans `config/catalogue_pays/` : c'est une DONNÉE, pas du code. Le poids d'un fichier n'y est jamais écrit
(il serait vite faux) : on le demande au serveur (requête HEAD) avant de proposer un téléchargement. Rien n'est téléchargé ici."""

from __future__ import annotations

import re
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pilote.config import Config
from pilote.refus import ConfigRefusee

ACCES = ("api", "fichier", "site")
CHAMPS = {"id", "nom", "contenu", "usage", "acces", "licence", "url", "telechargement", "source", "verifie_le", "zones"}
REQUIS = ("id", "nom", "contenu", "acces", "licence", "url", "verifie_le")


def dossier(cfg: Config) -> Path:
    return cfg.dossier_config / str(cfg.chemins.get("catalogue_pays", "catalogue_pays"))


def _http(v: Any) -> bool:
    return isinstance(v, str) and v.startswith(("http://", "https://"))


def valider(d: Any, fichier: str) -> dict[str, Any]:
    """Une entrée fausse est refusée avec la phrase qui dit où ; elle n'empêche pas les autres pays d'être lus."""
    if not isinstance(d, dict) or not re.fullmatch(r"[A-Z]{2}", str(d.get("pays", ""))) or not isinstance(d.get("bases"), list):
        raise ConfigRefusee(f"{fichier} : il faut « pays » (deux lettres majuscules) et une liste « bases ». (Le code doit être entre guillemets : NO sans guillemets est lu « non » par YAML.)")
    if Path(fichier).stem != d["pays"]:
        raise ConfigRefusee(f"{fichier} : le fichier doit s'appeler {d['pays']}.yaml.")
    vus: set[str] = set()
    for b in d["bases"]:
        if not isinstance(b, dict):
            raise ConfigRefusee(f"{fichier} : chaque base est un bloc « clé: valeur ».")
        for k in sorted(set(b) - CHAMPS):
            raise ConfigRefusee(f"{fichier} : réglage inconnu « {k} » dans la base « {b.get('id', '?')} ».")
        for k in REQUIS:
            if not str(b.get(k, "")).strip():
                raise ConfigRefusee(f"{fichier} : la base « {b.get('id', '?')} » n'a pas de « {k} ».")
        if b["id"] in vus:
            raise ConfigRefusee(f"{fichier} : l'identifiant « {b['id']} » est donné deux fois.")
        vus.add(b["id"])
        if b["acces"] not in ACCES:
            raise ConfigRefusee(f"{fichier} : l'accès « {b['acces']} » n'existe pas ({', '.join(ACCES)}).")
        if not _http(b["url"]) or ("telechargement" in b and not _http(b["telechargement"])):
            raise ConfigRefusee(f"{fichier} : les adresses doivent commencer par http:// ou https://.")
        for z in b.get("zones") or []:  # fichiers par zone (région, pays...) : une copie PARTIELLE, jamais confondue avec la complète
            if not isinstance(z, dict) or not str(z.get("id", "")).strip() or not str(z.get("nom", "")).strip() or not _http(z.get("telechargement")):
                raise ConfigRefusee(f"{fichier} : chaque zone de « {b['id']} » demande un id, un nom et une adresse http(s).")
        if isinstance(b["verifie_le"], date):
            b["verifie_le"] = b["verifie_le"].isoformat()
    return d


def charger(cfg: Config) -> tuple[dict[str, dict[str, Any]], list[str]]:
    out: dict[str, dict[str, Any]] = {}
    problemes: list[str] = []
    for f in sorted(dossier(cfg).glob("*.yaml")):
        try:
            d = valider(yaml.safe_load(f.read_text(encoding="utf-8")), f.name)
            out[d["pays"]] = d
        except (ConfigRefusee, yaml.YAMLError, OSError) as exc:
            problemes.append(str(exc).splitlines()[0])
    return out, problemes


def pour_pays(cfg: Config, pays: str, usages_coches: list[str]) -> dict[str, Any]:
    """Les bases connues d'un pays, cochées d'après les presets de l'utilisateur ; ou la phrase qui dit qu'il n'y a pas de catalogue."""
    code = pays.strip().upper()
    cat, problemes = charger(cfg)
    if code not in cat:
        return {"pays": code, "trouve": False, "bases": [], "problemes": problemes,
                "message": f"Pas de catalogue pour ce pays ({code or '?'}). Utilisez la source CKAN générique si le pays a un portail, ou ajoutez la source à la main (page Ajout)."}  # fmt: skip
    bases = [{**b, "coche": b.get("usage") in usages_coches, "telechargeable": "telechargement" in b, "zones": [{"id": z["id"], "nom": z["nom"]} for z in b.get("zones") or []]} for b in cat[code]["bases"]]
    return {"pays": code, "nom": cat[code]["nom"], "trouve": True, "bases": bases, "problemes": problemes, "message": ""}


def adresses_connues(cfg: Config) -> set[str]:
    out: set[str] = set()
    for d in charger(cfg)[0].values():
        for b in d["bases"]:
            out |= {u for u in [b.get("telechargement"), *[z["telechargement"] for z in b.get("zones") or []]] if u}
    return out


def taille(url: str, delai: float = 15.0, essais: int = 3) -> int | None:
    """Le poids annoncé par le serveur (requête HEAD) ; None s'il ne le dit pas. Ne télécharge rien. Geofabrik répond parfois sans
    en-tête de poids (relevé le 18/10 : une requête sur trois) : on réessaie avant de dire « poids inconnu »."""
    for _ in range(essais):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "pilote-catalogue"})
            with urllib.request.urlopen(req, timeout=delai) as r:
                n = r.headers.get("Content-Length")
                if n and n.isdigit():
                    return int(n)
        except (OSError, ValueError):
            pass
    return None


def phrase_taille(n: int | None) -> str:
    if n is None:
        return "poids inconnu (le serveur ne l'annonce pas)"
    return f"{n / 1e9:.1f} Go" if n >= 1e9 else f"{n / 1e6:.0f} Mo"


def verifier_adresses(cfg: Config, delai: float = 20.0) -> list[dict[str, str]]:
    """Contrôle les adresses : rend les mortes (code HTTP ou erreur). Les adresses de page sont lues par GET, les fichiers par HEAD."""
    morts: list[dict[str, str]] = []
    for code, d in charger(cfg)[0].items():
        for b in d["bases"]:
            cibles = [("url", b["url"], "GET")] + ([("telechargement", b["telechargement"], "HEAD")] if "telechargement" in b else []) + [("zone " + z["id"], z["telechargement"], "HEAD") for z in b.get("zones") or []]
            for champ, adresse, methode in cibles:
                erreur = ""
                for _ in range(2):  # un délai dépassé isolé n'est pas une adresse morte : un seul nouvel essai
                    try:
                        req = urllib.request.Request(adresse, method=methode, headers={"User-Agent": "Mozilla/5.0 (pilote-catalogue)"})
                        with urllib.request.urlopen(req, timeout=delai) as r:
                            erreur = str(r.status) if r.status >= 400 else ""
                    except OSError as exc:
                        erreur = str(exc)[:80]
                    if not erreur:
                        break
                if erreur:
                    morts.append({"pays": code, "base": b["id"], "adresse": adresse, "erreur": erreur})
    return morts
