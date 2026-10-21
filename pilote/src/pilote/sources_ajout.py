"""Page Ajout (fiche 11) : écrire la DÉCLARATION d'une source (config/sources/<id>.yaml) pour tous les types — API, serveur MCP, fichier local,
base personnelle, programme local — puis lancer le test local (qui ne consomme rien). La source est toujours enregistrée ÉTEINTE ; si son
test échoue elle le reste, avec la raison, et ne peut pas être activée. Elle apparaît dans Réglages comme les autres. Aucun code à écrire :
les types « API », « MCP », « fichier » et « base » s'appuient sur des adaptateurs génériques pilotés par des réglages."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from pilote import cles
from pilote.adaptateurs import ErreurSource, base_sql
from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, yaml_texte
from pilote.sources import Declaration, charger_sources, valider_declaration
from pilote.tests_source import tester

MAX_EXEMPLE = 2_000_000
TYPES = ("api", "mcp", "fichier", "base", "adaptateur")
FAMILLES = {"api": "api", "mcp": "mcp", "fichier": "fichier", "base": "base", "adaptateur": "api"}
# Ce que le déclaratif ne couvre pas : la source est enregistrée quand même, et dit en clair qu'elle demande un adaptateur.
PROTOCOLES = {
    "oauth": "authentification en plusieurs étapes (OAuth)",
    "curseur": "pagination par curseur",
    "graphql": "GraphQL",
    "imbrique": "réponse très imbriquée",
    "autre": "fonctionnement particulier",
}


def nom_de_cle(nom: str) -> str:
    """Le nom de variable de la clé d'une source ajoutée, tiré de son nom (« Annuaire des clubs » -> ANNUAIRE_DES_CLUBS_API_KEY)."""
    base = _identifiant(nom).upper().replace("-", "_")
    return (base if base[0].isalpha() else "SOURCE_" + base)[:48] + "_API_KEY"


def _nom_de_cle_libre(cfg: Config, nom: str, valeur: str) -> str:
    """Un nom de variable qui ne remplace JAMAIS une clé déjà rangée : ANNUAIRE_API_KEY, puis ANNUAIRE_API_KEY_2... (la même valeur peut resservir)."""
    base = nom_de_cle(nom)
    for n in range(1, 100):
        candidat = base if n == 1 else f"{base}_{n}"
        if not cles.presente(cfg, candidat) or cles.valeur(cfg, candidat) == valeur:
            return candidat
    raise ConfigRefusee("Trop de clés portent déjà ce nom : choisissez un autre nom de source.")


def _identifiant(nom: str) -> str:
    from pilote.presets import slug

    ident = slug(nom)
    if not ident:
        raise ConfigRefusee("Donnez un nom à la source (lettres ou chiffres).")
    return ident


def _texte(spec: dict[str, Any], cle: str, defaut: str = "") -> str:
    return str(spec.get(cle) or defaut).strip()


def _commun(spec: dict[str, Any], ident: str, type_: str) -> dict[str, Any]:
    cout = spec.get("cout") or {}
    cle = _texte(spec, "cle")
    roles = [r for r in (spec.get("roles") or ["chercher"]) if r in ("chercher", "verifier")]
    d: dict[str, Any] = {
        "id": ident, "nom": _texte(spec, "nom"), "description": _texte(spec, "description", f"Source ajoutée par l'utilisateur ({type_})."),
        "trouve": _texte(spec, "trouve", "noms lus dans cette source"), "genres": list(spec.get("genres") or ["club"]),
        "pays": [str(p) for p in (spec.get("pays") or ["monde"])], "consomme": ["sujet", "mots_cles", "lieu"], "produit": ["nom", "origine"],
        "usages": list(spec.get("usages") or ["personnalise"]), "main": spec.get("main") or "seconde", "origine": spec.get("origine") or "web",
        "famille": FAMILLES[type_], "roles": roles or ["chercher"], "cle": cle,
        "cout": {"unite": str(cout.get("unite") or "appel"), "vers_dollar": cout.get("vers_dollar", 0), "par_appel": cout.get("par_appel", 1), "gratuit_par_mois": cout.get("gratuit_par_mois", 0)},
        "confiance": float(spec.get("confiance", 0.3)), "defaut": {"chercher": False, "verifier": False},
        "mode": {"en_ligne": type_ in ("api", "mcp"), "local": type_ in ("fichier", "base")}, "exemple_reponse": f"exemples/{ident}.json",
        "note": "Ajoutée par l'utilisateur.",
    }  # fmt: skip
    if spec.get("cle_prefixe"):
        d["cle_prefixe"] = str(spec["cle_prefixe"])
    if spec.get("prestataire"):
        if not _texte(spec, "avertissement"):
            raise ConfigRefusee("Un prestataire de collecte demande un avertissement : écrivez ce que l'utilisateur doit savoir avant de l'activer (coût au résultat, conditions d'usage).")
        d["prestataire"] = True
        d["avertissement"] = _texte(spec, "avertissement")
    if spec.get("test_connexion"):
        d["test_connexion"] = spec["test_connexion"]
    return d


def _api(spec: dict[str, Any]) -> dict[str, Any]:
    url = _texte(spec, "url")
    if not url.startswith(("http://", "https://")):
        raise ConfigRefusee("L'adresse doit commencer par http:// ou https://.")
    champs = {k: str(v).strip() for k, v in (spec.get("champs") or {}).items() if str(v).strip()}
    if "nom" not in champs:
        raise ConfigRefusee("Dites quel champ contient le NOM.")
    params = {str(k): str(v) for k, v in (spec.get("params") or {}).items()}
    pr = _texte(spec, "parametre_requete")
    if pr:
        params[pr] = "{quoi}"
    p: dict[str, Any] = {"url": url, "methode": "POST" if _texte(spec, "methode").upper() == "POST" else "GET", "params": params, "format": _texte(spec, "format", "json"),
                         "liste": _texte(spec, "liste"), "champs": champs, "origine_texte": _texte(spec, "origine_texte", _texte(spec, "nom"))}  # fmt: skip
    if p["format"] not in ("json", "csv"):
        raise ConfigRefusee("Le format doit être JSON ou CSV.")
    if p["format"] == "csv":
        p["delimiteur"] = _texte(spec, "delimiteur", ";")
    if spec.get("auth"):
        p["auth"] = {k: str(v) for k, v in spec["auth"].items() if k in ("type", "nom", "prefixe")}
        if p["auth"].get("type") not in ("header", "bearer", "basic", "query"):
            raise ConfigRefusee("La façon d'envoyer la clé doit être : header, bearer, basic ou query.")
        if not _texte(spec, "cle"):
            raise ConfigRefusee("Collez la clé d'API : le programme la range lui-même, vous n'avez pas à la placer dans un fichier.")
    for k, cible in (("genre", "genre"), ("correspondance_genres", "genres"), ("pays_code", "pays")):
        if spec.get(k):
            p[cible] = spec[k]
    return {"adaptateur": "api_json", "parametres": p}


def _mcp(spec: dict[str, Any]) -> dict[str, Any]:
    url, outil = _texte(spec, "mcp"), _texte(spec, "outil")
    if not url.startswith(("http://", "https://")):
        raise ConfigRefusee("L'adresse du serveur MCP doit commencer par http:// ou https://.")
    if not outil:
        raise ConfigRefusee("Dites quel outil du serveur appeler.")
    p: dict[str, Any] = {"mcp": url, "outil": outil, "arguments": spec.get("arguments") or {"query": "{mots_et_lieu}"}, "champs": spec.get("champs") or {},
                         "origine_texte": _texte(spec, "origine_texte", _texte(spec, "nom")), "cle_requise": bool(_texte(spec, "cle"))}  # fmt: skip
    if spec.get("liste"):
        p["liste"] = _texte(spec, "liste")
    if spec.get("genre"):
        p["genre"] = _texte(spec, "genre")
    return {"adaptateur": "mcp_generique", "parametres": p}


def _fichier(spec: dict[str, Any]) -> dict[str, Any]:
    f = Path(_texte(spec, "chemin")).expanduser()
    if not f.is_file():
        raise ConfigRefusee("Le fichier est introuvable.")
    fmt = _texte(spec, "format") or ("csv" if f.suffix.lower() in (".csv", ".tsv", ".txt") else "json")
    champs = {k: str(v).strip() for k, v in (spec.get("champs") or {}).items() if str(v).strip()}
    if "nom" not in champs:
        raise ConfigRefusee("Dites quelle colonne ou quel champ contient le NOM.")
    p: dict[str, Any] = {"fichier": str(f.resolve()), "format": fmt, "liste": _texte(spec, "liste"), "champs": champs, "origine_texte": _texte(spec, "origine_texte", _texte(spec, "nom"))}
    if fmt == "csv":
        p["delimiteur"] = _texte(spec, "delimiteur", ";")
    if spec.get("genre"):
        p["genre"] = _texte(spec, "genre")
    return {"adaptateur": "api_json", "parametres": p}


def _base(spec: dict[str, Any]) -> dict[str, Any]:
    f = Path(_texte(spec, "base")).expanduser()
    if not f.is_file():
        raise ConfigRefusee("Le fichier de la base est introuvable.")
    try:
        sql = base_sql.verifier_requete(_texte(spec, "requete"))
    except ErreurSource as exc:
        raise ConfigRefusee(str(exc)) from exc
    p: dict[str, Any] = {"base": str(f.resolve()), "requete": sql, "origine_texte": _texte(spec, "origine_texte", _texte(spec, "nom"))}
    if spec.get("genre"):
        p["genre"] = _texte(spec, "genre")
    return {"adaptateur": "base_sql", "parametres": p}


def _exemple(cfg: Config, type_: str, spec: dict[str, Any], moteur: dict[str, Any]) -> str:
    """L'exemple de réponse ENREGISTRÉ avec la source (le test local n'appelle jamais le service). Fourni par l'utilisateur pour une API ou un serveur MCP
    (c'est la réponse qu'il a vue en préparant la source) ; tiré du fichier ou de la base elle-même, en local, pour ceux-là."""
    if type_ in ("api", "mcp"):
        ex = spec.get("exemple")
        if ex in (None, ""):
            raise ConfigRefusee("Collez un exemple de réponse du service : il sert à vérifier la sortie sans jamais l'appeler.")
        texte = ex if isinstance(ex, str) else json.dumps(ex, ensure_ascii=False)
        if len(texte.encode()) > MAX_EXEMPLE:
            raise ConfigRefusee("L'exemple de réponse est trop volumineux (plus de 2 Mo).")
        return texte
    p = moteur["parametres"]
    if type_ == "fichier":
        octets = Path(p["fichier"]).read_bytes()[:MAX_EXEMPLE]
        return octets.decode("utf-8-sig", "replace")
    try:
        lignes = base_sql.lignes(p, _texte(spec, "mot_essai", "a"), 20)
    except ErreurSource as exc:
        raise ConfigRefusee(str(exc)) from exc
    except sqlite3.Error as exc:
        raise ConfigRefusee(f"La base a refusé la requête : {exc}") from exc
    if not lignes:
        raise ConfigRefusee("La requête n'a rendu aucune ligne pour le mot d'essai : donnez un « mot_essai » qui existe dans la base.")
    return json.dumps(lignes, ensure_ascii=False, default=str)


def enregistrer(cfg: Config, type_: str, spec: dict[str, Any]) -> tuple[Declaration, dict[str, Any]]:
    """Écrit la déclaration (jamais par-dessus une source existante), puis lance le test local."""
    if type_ not in TYPES:
        raise ConfigRefusee(f"Type de source inconnu : {type_}. Types : {', '.join(TYPES)} (programme local et flux RSS ont leur propre voie).")
    nom = _texte(spec, "nom")
    if not nom:
        raise ConfigRefusee("Donnez un nom à la source.")
    ident = _identifiant(nom)
    if (cfg.dossier_sources / f"{ident}.yaml").exists() or ident in charger_sources(cfg)[0]:
        raise ConfigRefusee(f"Une source s'appelle déjà « {nom} » : choisissez un autre nom.")
    valeur_cle = str(spec.get("cle_valeur") or "").strip()
    if valeur_cle and not _texte(spec, "cle"):
        spec = {**spec, "cle": _nom_de_cle_libre(cfg, nom, valeur_cle)}  # le programme choisit le nom ; l'utilisateur ne voit que « clé présente »
    elif valeur_cle and cles.presente(cfg, _texte(spec, "cle")) and cles.valeur(cfg, _texte(spec, "cle")) != valeur_cle:
        # une clé déjà rangée n'est jamais remplacée par l'ajout d'une source (elle peut appartenir à une autre source)
        raise ConfigRefusee(f"Une clé nommée {_texte(spec, 'cle')} existe déjà : elle n'est pas remplacée. Laissez le nom vide, le programme en choisira un libre.")
    if type_ == "adaptateur":
        return _enregistrer_sans_adaptateur(cfg, spec, ident, valeur_cle)
    moteur = {"api": _api, "mcp": _mcp, "fichier": _fichier, "base": _base}[type_](spec)
    d = _commun(spec, ident, type_)
    d["moteur"] = moteur
    ex = _exemple(cfg, type_, spec, moteur)
    if type_ == "fichier" and moteur["parametres"]["format"] == "csv" or type_ == "api" and moteur["parametres"]["format"] == "csv":
        d["exemple_reponse"] = f"exemples/{ident}.txt"  # un exemple CSV est lu comme du texte
    valider_declaration(d, cfg, f"{ident}.yaml")  # refus clair avant d'écrire quoi que ce soit
    if valeur_cle:
        cles.ecrire(cfg, d["cle"], valeur_cle)  # rangée dans le fichier de clés (droits 600), jamais dans la déclaration ni dans une réponse
    ecrire_atomique(cfg.dossier_sources / d["exemple_reponse"], ex)
    ecrire_atomique(cfg.dossier_sources / f"{ident}.yaml", yaml_texte(d, "# Source ajoutée par l'utilisateur (page Ajout). Éteinte tant que son test local n'a pas passé.\n"))
    decl = charger_sources(cfg)[0][ident]
    return decl, tester(cfg, decl)


def _enregistrer_sans_adaptateur(cfg: Config, spec: dict[str, Any], ident: str, valeur_cle: str) -> tuple[Declaration, dict[str, Any]]:
    """Une source que le déclaratif ne sait pas décrire (OAuth, curseur, GraphQL, réponse très imbriquée). On l'enregistre quand même,
    avec ce qu'on sait d'elle, et elle dit en clair « cette source demande un adaptateur » : jamais un refus sans explication."""
    protocole = _texte(spec, "protocole", "autre")
    if protocole not in PROTOCOLES:
        raise ConfigRefusee(f"Le type de fonctionnement doit être l'un de : {', '.join(PROTOCOLES)}.")
    module = "source_" + ident.replace("-", "_")  # préfixe : jamais le nom d'un adaptateur existant (« api_json », « base_sql »...)
    d = _commun(spec, ident, "adaptateur")
    d["moteur"] = {"adaptateur": module, "parametres": {"url": _texte(spec, "url"), "protocole": protocole}}
    d["note"] = f"Demande un adaptateur ({PROTOCOLES[protocole]}). Ajoutée par l'utilisateur."
    d.pop("exemple_reponse")
    valider_declaration(d, cfg, f"{ident}.yaml")
    if valeur_cle:
        cles.ecrire(cfg, d["cle"], valeur_cle)
    ecrire_atomique(cfg.dossier_sources / f"{ident}.yaml", yaml_texte(d, "# Source ajoutée par l'utilisateur (page Ajout). Elle demande un adaptateur : elle ne peut pas être activée avant.\n"))
    decl = charger_sources(cfg)[0][ident]
    return decl, tester(cfg, decl)


def lire_declaration(cfg: Config, ident: str) -> dict[str, Any]:
    f = cfg.dossier_sources / f"{ident}.yaml"
    return yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
