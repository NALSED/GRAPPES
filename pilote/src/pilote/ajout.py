"""Page Ajout : brancher une nouvelle prise de NOMS (type « registre » de grappes) sans écrire de fichier à la main.

Trois façons d'arriver au même point : catalogue de l'État, adresse collée (on désigne les champs en cliquant dans la réponse),
formulaire manuel. Dans tous les cas : un TEST obligatoire (il montre les noms que grappes en tirerait) avant d'enregistrer ;
l'enregistrement crée `config/recherche/<id>.yaml`, désactivée (`actif: false`), sans jamais écraser un fichier existant.
"""

from __future__ import annotations

import csv
import hashlib
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from pilote.classements import identifiant_depuis
from pilote.config import Config
from pilote.grappes_lib import brancher

UA = "pilote/0.1 (outil local : ajout d'une prise) python-urllib"
MAX_OCTETS = 2_000_000
MOTS_REQUETE = ("q", "query", "search", "recherche", "text", "texte", "nom", "name", "mots", "keywords", "terms")
CIBLES = (("nom", "Nom"), ("ville", "Ville"), ("genre", "Genre de chose"), ("id", "Identifiant officiel"))
_TESTES: set[str] = set()
_VERROU = threading.Lock()


class AjoutInvalide(ValueError):
    pass


METADONNEES_HEBERGEURS = (
    "169.254.0.0/16", "fe80::/10",  # lien-local : AWS, Google, Azure, OVH… y mettent leur service d'identifiants
    "100.100.100.200/32", "fd00:ec2::254/128",  # Alibaba Cloud, AWS en IPv6 : hors lien-local, à nommer une par une
)  # fmt: skip


def _hote_interdit(hote: str) -> str:
    """Adresses où les hébergeurs distribuent leurs identifiants : jamais une source de données. Le reste du réseau local
    est autorisé : une base tournant sur cette machine (Overpass, un fichier servi en local) est un usage voulu."""
    import ipaddress

    try:
        ip = ipaddress.ip_address(hote.strip("[]"))
    except ValueError:
        return ""  # un nom de domaine : il sera résolu par la bibliothèque ; on contrôle ce qu'on peut sans résoudre
    if any(ip in ipaddress.ip_network(r) for r in METADONNEES_HEBERGEURS if ip.version == ipaddress.ip_network(r).version):
        return "cette adresse est celle du service d'identifiants d'un hébergeur, jamais une source de données"
    return ""


def verifier_adresse(url: str) -> str:
    u = urllib.parse.urlsplit(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise AjoutInvalide("L'adresse doit commencer par http:// ou https://.")
    interdit = _hote_interdit(u.hostname or "")
    if interdit:
        raise AjoutInvalide(f"Adresse refusée : {interdit}.")
    return url.strip()


class _SansLienLocal(urllib.request.HTTPRedirectHandler):
    """Une redirection est une nouvelle adresse : elle est contrôlée comme la première. Sans cela, une adresse publique
    pouvait renvoyer vers le service d'identifiants de l'hébergeur."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _hote_interdit(urllib.parse.urlsplit(newurl).hostname or ""):
            raise urllib.error.HTTPError(newurl, code, "redirection refusée", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# ---------------------------------------------------------------------------------------------------------------------
# ② Appeler une fois et lire la réponse


def appeler(cfg: Config, url: str, delai_s: float = 30.0) -> dict[str, Any]:
    """UN appel réel, poli. Rend le corps (borné) et ce qu'on en tire pour désigner les champs."""
    url = verifier_adresse(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/csv;q=0.9, */*;q=0.5"})
    try:
        with urllib.request.build_opener(_SansLienLocal()).open(req, timeout=delai_s) as r:
            corps = r.read(MAX_OCTETS + 1)
            type_contenu = r.headers.get("Content-Type", "")
            statut = r.status
    except urllib.error.HTTPError as exc:
        raise AjoutInvalide(f"La source a répondu une erreur ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AjoutInvalide("La source ne répond pas.") from exc
    if len(corps) > MAX_OCTETS:
        raise AjoutInvalide("La réponse est trop volumineuse pour être examinée ici (plus de 2 Mo).")
    return {"statut": statut, **analyser(cfg, corps, type_contenu, url)}


def _format(corps: bytes, type_contenu: str, url: str) -> str:
    t, ext = type_contenu.lower(), urllib.parse.urlsplit(url).path.lower()
    if "json" in t or ext.endswith(".json"):
        return "json"
    if "xml" in t or "rss" in t or "atom" in t or ext.endswith((".xml", ".rss")):
        return "xml"
    if "csv" in t or ext.endswith(".csv"):
        return "csv"
    debut = corps[:1].lstrip() or b" "
    return "json" if debut in (b"{", b"[") else "xml" if corps.lstrip()[:1] == b"<" else "csv"


def _delimiteur(texte: str) -> str:
    try:
        return csv.Sniffer().sniff(texte[:4000], delimiters=";,\t|").delimiter
    except csv.Error:
        return ";"


def _meilleure_liste(obj: Any, chemin: str = "", profondeur: int = 0) -> tuple[str, list] | None:
    """La plus longue liste d'objets de la réponse (les « noms » en sont les éléments)."""
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        return chemin, obj
    if isinstance(obj, dict) and profondeur < 4:
        meilleur: tuple[str, list] | None = None
        for k, v in obj.items():
            r = _meilleure_liste(v, f"{chemin}.{k}" if chemin else str(k), profondeur + 1)
            if r and (meilleur is None or len(r[1]) > len(meilleur[1])):
                meilleur = r
        return meilleur
    return None


def aplatir(obj: Any, prefixe: str = "", sortie: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    sortie = [] if sortie is None else sortie
    if len(sortie) >= 60:
        return sortie
    if isinstance(obj, dict):
        for k, v in obj.items():
            aplatir(v, f"{prefixe}.{k}" if prefixe else str(k), sortie)
    elif isinstance(obj, list):
        if obj and all(not isinstance(x, (dict, list)) for x in obj):
            sortie.append((prefixe, ", ".join(str(x) for x in obj[:5])[:120]))
        elif obj:
            aplatir(obj[0], f"{prefixe}[0]", sortie)
    elif obj not in (None, ""):
        sortie.append((prefixe, str(obj)[:120]))
    return sortie


def analyser(cfg: Config, corps: bytes, type_contenu: str, url: str) -> dict[str, Any]:
    brancher(cfg)
    from grappes.search.formats import decode

    fmt = _format(corps, type_contenu, url)
    delim = _delimiteur(corps.decode("utf-8-sig", "replace")) if fmt == "csv" else ","
    try:
        racine = decode(corps, fmt, delimiter=delim)
    except Exception as exc:
        raise AjoutInvalide("La réponse n'a pas pu être lue (ni JSON, ni CSV, ni XML).") from exc
    trouve = _meilleure_liste(racine)
    if trouve is None:
        raise AjoutInvalide("Je ne trouve aucune liste de résultats dans cette réponse.")
    items_chemin, items = trouve
    params = urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)
    return {
        "format": fmt, "delimiteur": delim if fmt == "csv" else "", "items": items_chemin, "nb_items": len(items),
        "echantillon": [{"champ": c, "valeur": v} for c, v in aplatir(items[0])],
        "parametres_url": [{"nom": k, "valeur": v} for k, v in params],
        "parametre_requete": next((k for k, _ in params if k.lower() in MOTS_REQUETE), ""),
        "mot_essai": next((v for k, v in params if k.lower() in MOTS_REQUETE), ""),
    }  # fmt: skip


# ---------------------------------------------------------------------------------------------------------------------
# Spécification -> source de grappes, test, enregistrement


def _normaliser(spec: dict[str, Any]) -> dict[str, Any]:
    url = verifier_adresse(str(spec.get("url", "")))
    fmt = str(spec.get("format", "json"))
    if fmt == "xml":
        raise AjoutInvalide("Cette réponse est un flux (XML) : les prises de noms lisent du JSON ou du CSV.")
    if fmt not in ("json", "csv"):
        raise AjoutInvalide("Le format doit être JSON ou CSV.")
    champs = {k: str(v).strip() for k, v in (spec.get("champs") or {}).items() if str(v).strip() and k in dict(CIBLES)}
    if "nom" not in champs:
        raise AjoutInvalide("Dites quel champ contient le NOM.")
    nom = str(spec.get("nom", "")).strip()
    if not nom:
        raise AjoutInvalide("Donnez un nom lisible à cette prise.")
    return {
        "id": identifiant_depuis(str(spec.get("id") or nom)), "nom": nom, "url": url, "format": fmt, "items": str(spec.get("items", "")).strip(),
        "parametre_requete": str(spec.get("parametre_requete", "")).strip(), "delimiteur": str(spec.get("delimiteur") or ";"),
        "encodage": str(spec.get("encodage") or "utf-8-sig"), "champs": champs,
    }  # fmt: skip


def _source(cfg: Config, n: dict[str, Any]):
    brancher(cfg)
    from grappes.decouverte.sources_yaml import Source

    fields = {"nom": n["champs"]["nom"], "id": n["champs"].get("id") or n["champs"]["nom"]}
    if n["champs"].get("ville"):
        fields["ville"] = n["champs"]["ville"]
    if n["champs"].get("genre"):
        fields["type"] = n["champs"]["genre"]
    if n["format"] == "csv":
        return Source(n["id"], n["url"], "csv", fields=fields, relaxation=2, delimiter=n["delimiteur"], encoding=n["encodage"], description=n["nom"])
    u = urllib.parse.urlsplit(n["url"])
    params = {k: ("{requete}" if k == n["parametre_requete"] else v) for k, v in urllib.parse.parse_qsl(u.query)}
    if n["parametre_requete"] and n["parametre_requete"] not in params:
        params[n["parametre_requete"]] = "{requete}"
    base = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, "", ""))
    return Source(n["id"], base, "json", params=params, items=n["items"], fields=fields, relaxation=2, description=n["nom"])


def _empreinte(n: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(n, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def tester(cfg: Config, spec: dict[str, Any], mot: str) -> dict[str, Any]:
    """Interroge la prise comme grappes le ferait (une à trois requêtes réelles) et montre les trois premiers noms."""
    n = _normaliser(spec)
    mot = mot.strip()
    if not mot:
        raise AjoutInvalide("Donnez un mot d'essai (par exemple « handball »).")
    from grappes.decouverte.client import Http
    from grappes.decouverte.sources_yaml import interroger

    http = Http(cfg.donnees / "ajout_cache", delai_s=1.0, ttl_jours=1)
    avant = http.appels_reseau
    trouves = interroger(_source(cfg, n), mot, http)
    appels = http.appels_reseau - avant
    if not trouves:
        return {"ok": False, "message": f"La prise n'a rendu aucun nom pour « {mot} ». Vérifiez le champ du nom et le paramètre des mots cherchés.", "total": 0, "noms": [], "appels": appels}
    with _VERROU:
        _TESTES.add(_empreinte(n))
    return {
        "ok": True, "total": len(trouves), "appels": appels, "essai": mot,
        "noms": [{"nom": d.nom, "ville": d.ville, "genre": d.type_candidat, "id": d.identifiant if d.identifiant != d.nom else ""} for d in trouves[:3]],
    }  # fmt: skip


def yaml_de(cfg: Config, n: dict[str, Any], qui: str, total: int | None = None) -> str:
    fields: dict[str, Any] = {"nom": n["champs"]["nom"], "id": n["champs"].get("id") or n["champs"]["nom"]}
    if n["champs"].get("ville"):
        fields["ville"] = n["champs"]["ville"]
    if n["champs"].get("genre"):
        fields["type"] = n["champs"]["genre"]
    d: dict[str, Any] = {"id": n["id"], "type": "registre", "public": True, "actif": False, "description": n["nom"], "format": n["format"]}
    if n["format"] == "csv":
        d.update(url=n["url"], delimiter=n["delimiteur"], encoding=n["encodage"])
    else:
        src = _source(cfg, n)
        d.update(url=src.url, params=src.params, response={"items": n["items"]})
    d.update(fields=fields, relaxation=2)
    entete = (f"# {n['nom']}\n# Ajoutée avec pilote le {datetime.now():%Y-%m-%d} par {qui} ; testée avant l'enregistrement"
              + (f" ({total} noms rendus)" if total else "") + ".\n# Désactivée : à activer dans Réglages.\n")
    return entete + yaml.safe_dump(d, allow_unicode=True, sort_keys=False)


def enregistrer(cfg: Config, spec: dict[str, Any], qui: str) -> dict[str, Any]:
    """Écrit `config/recherche/<id>.yaml` (désactivée). Refuse sans test réussi de CETTE spécification, et n'écrase jamais."""
    n = _normaliser(spec)
    with _VERROU:
        teste = _empreinte(n) in _TESTES
    if not teste:
        raise AjoutInvalide("Testez la prise d'abord : elle ne s'enregistre qu'après un test qui a rendu des noms.")
    dossier = cfg.dossier_grappes_config / "recherche"
    cible = dossier / f"{n['id']}.yaml"
    if cible.exists() or any(_id_du_fichier(f) == n["id"] for f in dossier.glob("*.yaml")):
        raise AjoutInvalide(f"Une prise « {n['id']} » existe déjà ; choisissez un autre nom.")
    dossier.mkdir(parents=True, exist_ok=True)
    cible.write_text(yaml_de(cfg, n, qui), encoding="utf-8")
    return {"id": n["id"], "fichier": cible.name, "active": False}


def _id_du_fichier(f: Path) -> str:
    try:
        return str((yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("id", ""))
    except (OSError, yaml.YAMLError):
        return ""
