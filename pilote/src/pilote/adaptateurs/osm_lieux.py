"""OpenStreetMap par Overpass : les lieux d'un TYPE donné dans une zone (stade, salle de sport, centre culturel, local associatif...).
Gratuit, usage équitable : un appel à la fois, un délai d'au moins une seconde, des serveurs de secours, aucune insistance.

Universel : OpenStreetMap étiquette les lieux de la même façon dans tous les pays ; le type choisi dans Recherches (`type_lieu`, ou à défaut
le genre : club, association, lieu) est traduit UNE FOIS en étiquettes par `config/lieux_osm.yaml`. Aucun code national.
La zone vient de Nominatim (le nom d'une ville) ou, sans ville, du pays entier. Première main pour le lieu (OpenStreetMap le décrit),
rempli par des bénévoles : un grand club y figure presque toujours, un petit groupe informel rarement."""

from __future__ import annotations

import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import yaml

from pilote.adaptateurs import Client, ErreurSource
from pilote.adaptateurs import nominatim as nom

SERVEURS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter")
DELAI_REPONSE_S = 90.0  # la requête demande 60 s au serveur au plus ; on lui laisse le temps de répondre
DELAI_S = 1.0
ESSAIS, PAUSE_S = 3, 6.0  # par serveur et par zone : trois essais, séparés de pauses de 6 s puis 12 s
FICHIER_CATALOGUE = "lieux_osm.yaml"  # dans le dossier de configuration de pilote (déplaçable : l'exécuteur le donne en `_dossier_config`)
GENRE_PAR_DEFAUT = "club"
N_MAX = 200


def catalogue(dossier_config: str | Path | None) -> dict[str, Any]:
    f = Path(dossier_config or ".") / FICHIER_CATALOGUE
    if not f.exists():
        raise ErreurSource("Le catalogue des types de lieu (lieux_osm.yaml) est introuvable.")
    y = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    if not isinstance(y.get("types"), dict) or not isinstance(y.get("genres"), dict):
        raise ErreurSource("Le catalogue des types de lieu est mal écrit (il faut « types » et « genres »).")
    return y


def etiquettes(entree: dict[str, Any], cat: dict[str, Any]) -> list[tuple[str, str]]:
    """Les étiquettes OpenStreetMap à chercher pour le type (ou, à défaut, le genre) choisi."""
    voulus = entree.get("type_lieu") or []
    if isinstance(voulus, str):
        voulus = [voulus]
    if not voulus:
        voulus = cat["genres"].get(str(entree.get("genre") or GENRE_PAR_DEFAUT)) or cat["genres"].get(GENRE_PAR_DEFAUT) or []
    inconnus = [v for v in voulus if v not in cat["types"]]
    if inconnus:
        raise ErreurSource(f"Le type de lieu « {inconnus[0]} » n'existe pas. Types connus : {', '.join(sorted(cat['types']))}.")
    out: list[tuple[str, str]] = []
    for v in voulus:
        for cle, val in cat["types"][v]["osm"]:
            if (cle, val) not in out:
                out.append((cle, val))
    return out


def _echapper(mot: str) -> str:
    return re.sub(r'(["\\])', r"\\\1", re.sub(r"([.^$*+?()\[\]{}|])", r"\\\1", mot))


def requete(preambule: str, cadre: str, filtres: list[tuple[str, str]], mots: list[str], limite: int, etendue: bool = False) -> str:
    """Texte Overpass QL. `preambule` fabrique la zone (« area(...)->.z; » ou rien), `cadre` la désigne (« area.z » ou un rectangle sud,ouest,nord,est) ;
    `mots` : si donnés, on ne garde que les lieux dont le sport ou le nom les contient. `etendue` : zone d'un pays entier — la recherche dans les noms
    (expression régulière sur des millions d'objets) est trop lourde pour un service partagé, on ne garde alors que l'étiquette exacte « sport »."""
    lignes: list[str] = []
    for cle, val in filtres:
        f = f'["{cle}"]' if val == "*" else f'["{cle}"="{val}"]'
        if mots and etendue:
            lignes += [f'nwr({cadre}){f}["sport"="{_echapper(m)}"];' for m in mots]
        elif mots:
            motif = _echapper("|".join(mots))
            lignes += [f'nwr({cadre}){f}["sport"~"{motif}",i];', f'nwr({cadre}){f}["name"~"{motif}",i];']
        else:
            lignes.append(f'nwr({cadre}){f}["name"];')
    return "[out:json][timeout:60];\n" + (preambule + "\n" if preambule else "") + "(\n  " + "\n  ".join(lignes) + f"\n);\nout center tags {int(limite)};"


def mots_de_la_recherche(entree: dict[str, Any], cat: dict[str, Any]) -> list[str]:
    """Les mots qui précisent le lieu (un sport, une activité), sans les mots qui NOMMENT le type de lieu (« club », « salle », « stade »...)."""
    vides = {"club", "clubs", "lieu", "lieux", "salle", "salles", "stade", "stades", "centre", "centres", "center", "centers", "association", "associations", "hall", "halls"}
    for t, d in cat["types"].items():
        vides |= {m for m in re.findall(r"[^\W\d_]{3,}", f"{t} {d.get('libelle', '')}".lower())}
    vides |= {g for g in cat["genres"]}
    texte = " ".join([*map(str, entree.get("mots_cles") or []), str(entree.get("quoi", ""))]).lower()
    mots: list[str] = []
    for m in re.findall(r"[^\W\d_]{3,}", texte):
        base = m[:-1] if m.endswith("s") and len(m) > 4 else m
        if m not in vides and base not in vides and m not in mots:
            mots.append(m)
    return mots[:3]


def convertir(rep: Any) -> list[dict[str, Any]]:
    """Réponse d'Overpass -> lieux (nom, ville, site, coordonnées). Un lieu sans nom est ignoré : il n'y a rien à garder."""
    if not isinstance(rep, dict) or not isinstance(rep.get("elements"), list):
        raise ErreurSource("La réponse d'Overpass n'a pas la forme attendue.")
    if "runtime error" in str(rep.get("remark", "")):  # délai dépassé ou serveur surchargé : une réponse vide n'est pas « aucun lieu »
        raise ErreurSource("Overpass a abandonné la requête (serveur surchargé ou zone trop grande).")
    out, vus = [], set()
    for el in rep["elements"]:
        t = el.get("tags") or {}
        nom_ = str(t.get("name") or "").strip()
        if not nom_:
            continue
        c = el.get("center") or el
        lat, lon = c.get("lat"), c.get("lon")
        cle = (nom_.lower(), round(lat or 0, 3), round(lon or 0, 3))  # le même lieu cartographié deux fois (salle + terrain) ne compte qu'une fois
        if cle in vus:
            continue
        vus.add(cle)
        e: dict[str, Any] = {
            "nom": nom_, "origine": "OpenStreetMap (lieu cartographié)", "numero": f"{el.get('type', 'node')}/{el.get('id', '')}",
            "ville": str(t.get("addr:city") or t.get("addr:town") or t.get("addr:village") or ""),
            "site": str(t.get("website") or t.get("contact:website") or ""), "genre": "club" if "club" in t else "lieu",
        }  # fmt: skip
        if lat is not None and lon is not None:
            e["coordonnees"] = {"lat": float(lat), "lon": float(lon)}
        out.append(e)
    return out


def zones_overpass(client: Client, entree: dict[str, Any], parametres: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """Façons de désigner la zone, de la plus juste à la plus approchée : (préambule, cadre, approchée). La ville demandée vient de Nominatim
    (la surface exacte, puis son rectangle en secours) ; sans ville, le pays entier."""
    lieu = str(entree.get("lieu") or "").strip()
    pays = str(entree.get("pays") or "").strip().upper()
    if lieu:
        z = nom.zone(client, lieu, pays, str(parametres.get("nominatim", nom.URL)))
        out: list[tuple[str, str, bool]] = []
        if z.get("area"):
            out.append((f"area({z['area']})->.z;", "area.z", False))
        if z.get("bbox"):
            s, w, n, e = z["bbox"]
            out.append(("", f"{s},{w},{n},{e}", True))
        return out
    if pays:
        return [(f'area["ISO3166-1"="{pays}"][admin_level=2]->.z;', "area.z", False)]
    raise ErreurSource("Il faut un endroit (une ville) ou un pays pour chercher des lieux.")


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    client.delai_s = max(client.delai_s, DELAI_S)
    client.timeout = max(client.timeout, DELAI_REPONSE_S)
    if not str(entree.get("lieu") or "").strip() and not entree.get("type_lieu"):
        return []  # sans endroit ni type choisi, une recherche de lieux sur un pays entier serait lourde et sans objet : la source ne s'applique pas
    cat = catalogue(parametres.get("_dossier_config"))
    filtres = etiquettes(entree, cat)
    if not filtres:
        raise ErreurSource("Aucun type de lieu à chercher : choisissez un type de lieu ou un genre.")
    limite = min(int(entree.get("limite") or 100), int(parametres.get("n_max") or N_MAX))  # 200 par défaut : protège les serveurs publics ; un serveur local peut relever le plafond
    zones = zones_overpass(client, entree, parametres)
    mots = mots_de_la_recherche(entree, cat)
    derniere: Exception | None = None
    reponse_vide = False
    client.tentatives_429 = 1  # Overpass a ses propres essais et son serveur de secours : pas de double attente
    essais, pause = int(parametres.get("essais", ESSAIS)), float(parametres.get("pause_s", PAUSE_S))
    for url in parametres.get("serveurs") or SERVEURS:
        for preambule, cadre, approchee in zones:
            for essai in range(essais):
                try:
                    rep = client.post_texte(url, "data=" + urllib.parse.quote(requete(preambule, cadre, filtres, mots, limite * 2, etendue=not str(entree.get("lieu") or "").strip())))
                    lieux = convertir(rep)[:limite]
                except ErreurSource as exc:
                    derniere = exc
                    if "ne répond pas" in str(exc):
                        break  # le serveur ne répond pas du tout : inutile de lui redemander
                    if essai + 1 < essais:
                        time.sleep(pause * (essai + 1))  # serveur occupé (429, 504...) : une pause croissante, puis un nouvel essai
                    continue
                if lieux:
                    if approchee:
                        for lieu_ in lieux:
                            lieu_["zone_approchee"] = True  # le serveur n'a su répondre que pour le rectangle autour de la ville : des lieux voisins peuvent s'y glisser
                    return lieux
                reponse_vide = True  # réponse valide mais vide : on tente la zone plus simple et le serveur suivant avant de conclure « aucun lieu »
                break
    if reponse_vide:
        return []
    raise ErreurSource(f"Overpass n'a pas pu répondre ({derniere}). Réessayez plus tard : le service est partagé et limite les demandes.")
