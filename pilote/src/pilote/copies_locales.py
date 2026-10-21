"""Copies locales des bases (fiche 15, chapitre 2) : un fichier téléchargé UNE fois, sur accord, pour tourner hors ligne et obtenir des résultats
reproductibles (une API en ligne change sous nos pieds).

Règles en dur : jamais de téléchargement sans accord (`confirme`), poids demandé au serveur et espace disque contrôlé AVANT, une copie partielle
l'affiche toujours, et AUCUN filtre par mot-clé (il serait choisi avant de connaître les recherches futures : une copie « handball » serait vide
pour le basket, et rien ne dirait qu'il manque des noms). Une copie vieille de plus de 30 jours est signalée « à mettre à jour », jamais
mise à jour toute seule."""

from __future__ import annotations

import json
import shutil
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pilote import actions, catalogue_pays
from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, verrou

AGE_MAX_JOURS = 30
MARGE = 1.1  # on exige 10 % de place en plus du poids annoncé
BLOC = 1 << 20


def dossier(cfg: Config) -> Path:
    return cfg.dossier_copies


def _registre(cfg: Config) -> Path:
    return cfg.donnees / "copies_locales.json"


def lister(cfg: Config) -> list[dict[str, Any]]:
    f = _registre(cfg)
    try:
        liste = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except (OSError, ValueError):
        return []
    now = datetime.now(UTC)
    for c in liste:
        try:
            age = (now - datetime.fromisoformat(c["telechargee_le"])).days
        except (KeyError, ValueError):
            age = 0
        c["age_jours"] = age
        c["a_mettre_a_jour"] = age > AGE_MAX_JOURS
        c["phrase"] = phrase(c)
    return liste


def phrase(c: dict[str, Any]) -> str:
    if not c.get("partielle"):
        return f"copie locale complète, {c['pays']}"
    morceaux = [f"zone {c['zone']}" if c.get("zone") else "", f"type {c['type']}" if c.get("type") else ""]
    return f"copie locale, {', '.join(m for m in morceaux if m)} seulement"


def _ecrire(cfg: Config, liste: list[dict[str, Any]]) -> None:
    """Écriture d'un coup (fichier temporaire puis renommage) : un registre à moitié écrit se lisait comme vide, et toutes les copies
    devenaient invisibles alors que leurs fichiers étaient toujours sur le disque. Appelée sous `verrou(_registre(cfg))`."""
    cfg.donnees.mkdir(parents=True, exist_ok=True)
    nettoyees = [{k: v for k, v in c.items() if k not in ("age_jours", "a_mettre_a_jour", "phrase")} for c in liste]
    ecrire_atomique(_registre(cfg), json.dumps(nettoyees, ensure_ascii=False, indent=1))


def place_libre(cfg: Config) -> int:
    """La place du disque où la copie sera écrite (pas celle du disque système), sans rien créer : on mesure le plus proche dossier existant."""
    d = cfg.dossier_copies
    while not d.exists() and d != d.parent:
        d = d.parent
    return shutil.disk_usage(d).free


def _zone(b: dict[str, Any], zone: str) -> dict[str, Any] | None:
    if not zone:
        return None
    z = next((x for x in b.get("zones") or [] if x["id"] == zone), None)
    if z is None:
        raise ConfigRefusee(f"La base « {b['nom']} » n'a pas de zone « {zone} » au catalogue.")
    return z


def _base(cfg: Config, pays: str, base_id: str) -> dict[str, Any]:
    cat, _ = catalogue_pays.charger(cfg)
    for b in (cat.get(pays.strip().upper()) or {}).get("bases", []):
        if b["id"] == base_id:
            if "telechargement" not in b:
                raise ConfigRefusee(f"La base « {b['nom']} » n'a pas de fichier à télécharger : elle se consulte en ligne.")
            return b
    raise ConfigRefusee(f"Le catalogue de {pays.strip().upper() or '?'} ne connaît pas la base « {base_id} ».")


def proposer(cfg: Config, pays: str, base_id: str, poids=catalogue_pays.taille, zone: str = "") -> dict[str, Any]:
    """Ce qui sera dit à l'utilisateur AVANT d'accepter : poids, place libre, et si ça tient. N'écrit rien. `zone` : une copie partielle."""
    b = _base(cfg, pays, base_id)
    z = _zone(b, zone)
    adresse = z["telechargement"] if z else b["telechargement"]
    n = poids(adresse)
    libre = place_libre(cfg)
    tient = n is not None and n * MARGE < libre
    return {"base": base_id, "pays": pays.strip().upper(), "octets": n, "poids": catalogue_pays.phrase_taille(n), "libre_octets": libre,
            "libre": catalogue_pays.phrase_taille(libre), "tient": tient, "adresse": adresse, "licence": b["licence"], "zone": z["nom"] if z else ""}  # fmt: skip


def telecharger(cfg: Config, pays: str, base_id: str, *, confirme: bool, qui: str, poids=catalogue_pays.taille, ouvrir=urllib.request.urlopen, zone: str = "") -> dict[str, Any]:
    """Télécharge une copie (complète, ou d'une seule zone du catalogue : alors elle est marquée PARTIELLE). Sans `confirme`, ne fait RIEN ; si la place manque ou si le poids est inconnu, refuse avant d'écrire."""
    if not confirme:
        raise ConfigRefusee("Téléchargement non confirmé : rien n'a été téléchargé. Dites-le à l'écran (poids et place disque affichés) puis confirmez.")
    p = proposer(cfg, pays, base_id, poids, zone)
    if p["octets"] is None:
        raise ConfigRefusee("Le serveur n'annonce pas le poids du fichier : impossible de vérifier la place disque, rien n'est téléchargé.")
    if not p["tient"]:
        raise ConfigRefusee(f"Pas assez de place : le fichier pèse {p['poids']}, il reste {p['libre']} (marge de 10 % exigée). Rien n'est téléchargé.")
    b = _base(cfg, pays, base_id)
    cible = dossier(cfg) / p["pays"] / base_id / Path(p["adresse"]).name
    cible.parent.mkdir(parents=True, exist_ok=True)
    part = cible.with_name(f"{cible.name}.{uuid.uuid4().hex[:8]}.part")  # un fichier partiel par téléchargement : deux onglets ne s'écrivent plus dessus
    recu = 0
    try:
        req = urllib.request.Request(p["adresse"], headers={"User-Agent": "pilote-copie-locale"})
        with ouvrir(req, timeout=60) as r, part.open("wb") as f:
            while chunk := r.read(BLOC):
                f.write(chunk)
                recu += len(chunk)
        if recu != p["octets"]:
            raise OSError(f"fichier incomplet : {recu} octets reçus sur {p['octets']}")
        part.replace(cible)
    except OSError as exc:
        part.unlink(missing_ok=True)  # jamais de demi-fichier gardé comme une copie
        raise ConfigRefusee(f"Le téléchargement a échoué ({str(exc)[:100]}). Rien n'est gardé.") from exc
    entree = {"id": f"{p['pays']}-{base_id}" + (f"-{zone}" if zone else ""), "pays": p["pays"], "base": base_id, "nom": b["nom"], "fichier": str(cible.relative_to(cfg.dossier_copies)), "octets": recu,
              "zone": p["zone"], "type": "", "partielle": bool(zone), "licence": b["licence"], "telechargee_le": datetime.now(UTC).isoformat(timespec="seconds"), "accord_de": qui}  # fmt: skip
    with verrou(_registre(cfg)):  # lire, modifier, écrire
        _ecrire(cfg, [c for c in lister(cfg) if c["id"] != entree["id"]] + [entree])
    actions.noter(cfg, qui, "copie_locale_telechargee", f"{entree['id']} {recu} octets")
    return {**entree, "phrase": phrase(entree)}


def supprimer(cfg: Config, copie_id: str, qui: str) -> None:
    with verrou(_registre(cfg)):
        liste = lister(cfg)
        c = next((x for x in liste if x["id"] == copie_id), None)
        if c is None:
            raise ConfigRefusee("Cette copie n'existe pas.")
        (cfg.dossier_copies / c["fichier"]).unlink(missing_ok=True)
        _ecrire(cfg, [x for x in liste if x["id"] != copie_id])
    actions.noter(cfg, qui, "copie_locale_supprimee", copie_id)


def couverture(cfg: Config, sujet: dict[str, Any]) -> list[str]:
    """Phrases à afficher dans Recherches quand le sujet sort de ce que les copies couvrent, ou quand une copie partielle est en jeu.
    Une copie ne couvre que son pays : ailleurs, la recherche passe en ligne et on le dit."""
    pays = str(sujet.get("pays") or "").strip().upper()
    out: list[str] = []
    for c in lister(cfg):
        if pays and c["pays"] != pays:
            out.append(f"La copie locale « {c['nom']} » couvre {c['pays']}, pas {pays} : pour ce pays la source reste en ligne.")
        elif c.get("partielle"):
            out.append(f"{c['phrase'][0].upper() + c['phrase'][1:]} — {c['nom']} : vérifiez que votre sujet entre dans ce périmètre, sinon des noms manqueront sans que rien ne le montre.")
        if c["a_mettre_a_jour"]:
            out.append(f"La copie locale « {c['nom']} » a {c['age_jours']} jours : à mettre à jour (rien n'est téléchargé sans votre accord).")
    return out


def refuser_filtre_mot_cle(filtre: str) -> None:
    """Un filtre par mot-clé fin est écarté d'avance (voir l'en-tête) : on le dit plutôt que de l'accepter."""
    if str(filtre or "").strip():
        raise ConfigRefusee("Pas de filtre par mot-clé dans une copie locale : il perdrait des noms sans le montrer. Gardez une zone ou un grand type, et passez par la recherche en ligne pour le reste.")
