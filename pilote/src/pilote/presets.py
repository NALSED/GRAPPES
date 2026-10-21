"""Presets (fiche 01) : des lots de sources CALCULÉS à partir des usages que les sources déclarent (`usages`), jamais écrits à la
main. Combinables ; une même source peut appartenir à plusieurs presets. Les cartes (nom, phrase) sont dans config/presets/ ;
les presets personnalisés de l'utilisateur dans config/presets_perso/."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from pilote import cles
from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, lire_yaml, verrou, yaml_texte
from pilote.sources import Declaration

SLUG = re.compile(r"[^a-z0-9]+")


def slug(nom: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    return SLUG.sub("-", t).strip("-")[:48]


def _cartes_fichiers(cfg: Config) -> list[dict[str, Any]]:
    out = []
    d = cfg.dossier_presets
    for f in sorted(d.glob("*.yaml")) if d.is_dir() else []:
        try:
            y = lire_yaml(f)
        except ConfigRefusee:
            continue
        if y.get("id") and y.get("nom"):
            out.append(y)
    return sorted(out, key=lambda y: (y.get("ordre", 99), y["id"]))


def _perso(cfg: Config) -> list[dict[str, Any]]:
    out = []
    d = cfg.dossier_presets_perso
    for f in sorted(d.glob("*.yaml")) if d.is_dir() else []:
        try:
            y = lire_yaml(f)
        except ConfigRefusee:
            continue
        if y.get("nom") and isinstance(y.get("sources"), list):
            out.append({**y, "id": f.stem})
    return out


def ids_connus(cfg: Config) -> set[str]:
    return {c["id"] for c in _cartes_fichiers(cfg)} | {c["id"] for c in _perso(cfg)}


def _source_vue(d: Declaration, cfg: Config) -> dict[str, Any]:
    return {"id": d.id, "nom": d.nom, "allumee_par_defaut": d.defaut["chercher"], "payant": d.payant, "cle_requise": bool(d.cles),
            "cle_presente": cles.toutes_presentes(cfg, d.cles) if d.cles else None, "main": d.main, "pays": d.pays}  # fmt: skip


def cartes(cfg: Config, decls: dict[str, Declaration]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in _cartes_fichiers(cfg):
        membres = [d for d in decls.values() if c.get("usage") and c["usage"] in d.usages]
        out.append(_carte(cfg, c["id"], c["nom"], c.get("phrase", ""), membres, perso=False, copie_de=None))
    for c in _perso(cfg):
        membres = [decls[s] for s in c["sources"] if s in decls]
        out.append({**_carte(cfg, c["id"], c["nom"], c.get("phrase") or f"{c['nom']} : preset personnalisé.", membres, perso=True, copie_de=c.get("copie_de")),
                    "phrase_perso": str(c.get("phrase") or "")})  # fmt: skip
    return out


def _carte(cfg: Config, ident: str, nom: str, phrase: str, membres: list[Declaration], perso: bool, copie_de: str | None) -> dict[str, Any]:
    allumees = [d for d in membres if d.defaut["chercher"]]
    payant = any(d.payant for d in allumees)
    return {
        "id": ident, "nom": nom, "phrase": phrase, "perso": perso, "copie_de": copie_de,
        "sources": [_source_vue(d, cfg) for d in sorted(membres, key=lambda d: (not d.defaut["chercher"], d.nom))],
        "cout": "payant avec ta clé" if payant else ("gratuit" if not any(d.payant for d in membres) else "gratuit (options payantes avec ta clé)"),
    }  # fmt: skip


def sources_de(cfg: Config, decls: dict[str, Declaration], preset_id: str) -> list[str]:
    for c in cartes(cfg, decls):
        if c["id"] == preset_id:
            return [s["id"] for s in c["sources"]]
    return []


def personnaliser(cfg: Config, decls: dict[str, Declaration], depuis: str, nom: str, qui: str) -> dict[str, Any]:
    """Copie un preset dans une version modifiable sous le nom choisi ; l'original reste intact."""
    nom = nom.strip()
    if not nom:
        raise ConfigRefusee("Donnez un nom à votre preset personnalisé.")
    ident = slug(nom)
    if not ident:
        raise ConfigRefusee("Ce nom ne contient aucune lettre ni chiffre : choisissez-en un autre.")
    if ident in ids_connus(cfg):
        raise ConfigRefusee(f"Un preset s'appelle déjà « {nom} » : choisissez un autre nom.")
    if depuis not in ids_connus(cfg):
        raise ConfigRefusee("Le preset à copier n'existe pas.")
    src = sources_de(cfg, decls, depuis)
    ecrire_atomique(
        cfg.dossier_presets_perso / f"{ident}.yaml",
        yaml_texte({"nom": nom, "copie_de": depuis, "sources": src}, "# Preset personnalisé (copie modifiable). Partageable : il ne contient aucune clé.\n"),
    )
    return {"id": ident, "nom": nom, "sources": src}


def enregistrer_perso(cfg: Config, decls: dict[str, Declaration], ident: str, nom: str, sources: list[str]) -> None:
    inconnues = [s for s in sources if s not in decls]
    if inconnues:
        raise ConfigRefusee(f"La source « {inconnues[0]} » n'existe pas.")
    ecrire_atomique(cfg.dossier_presets_perso / f"{ident}.yaml", yaml_texte({"nom": nom, "sources": list(sources)}, "# Preset personnalisé. Aucune clé.\n"))


def lire_perso(cfg: Config, ident: str) -> dict[str, Any]:
    f = cfg.dossier_presets_perso / f"{ident}.yaml"
    if not f.exists():
        raise ConfigRefusee("Ce preset n'existe pas.")
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------------------------------------------------
# Preset personnalisé (fiche 10) : créer vide, modifier, supprimer, exporter, importer

FORMAT_EXPORT = "pilote-preset/1"
MAX_EXEMPLE = 100_000


def _verrou_perso(cfg: Config):
    """UN verrou pour tous les presets personnalisés, à un nom fixe : un verrou nommé d'après l'identifiant reçu créait un fichier
    pour chaque identifiant demandé (même inexistant), et plantait le serveur sur un identifiant trop long pour un nom de fichier."""
    return verrou(cfg.dossier_presets_perso / "presets_perso")


def _perso_existant(cfg: Config, ident: str) -> dict[str, Any]:
    if ident not in {c["id"] for c in _perso(cfg)}:
        raise ConfigRefusee("Seuls les presets personnalisés se modifient ; celui-ci n'existe pas ou est livré avec le programme.")
    return lire_perso(cfg, ident)


def creer_vide(cfg: Config, nom: str) -> dict[str, Any]:
    nom = nom.strip()
    if not nom:
        raise ConfigRefusee("Donnez un nom à votre preset personnalisé.")
    ident = slug(nom)
    if not ident:
        raise ConfigRefusee("Ce nom ne contient aucune lettre ni chiffre : choisissez-en un autre.")
    if ident in ids_connus(cfg):
        raise ConfigRefusee(f"Un preset s'appelle déjà « {nom} » : choisissez un autre nom.")
    ecrire_atomique(cfg.dossier_presets_perso / f"{ident}.yaml", yaml_texte({"nom": nom, "sources": []}, "# Preset personnalisé, parti de zéro. Aucune clé.\n"))
    return {"id": ident, "nom": nom, "sources": []}


def modifier(cfg: Config, decls: dict[str, Declaration], ident: str, sources: list[str]) -> dict[str, Any]:
    """Remplace la liste de sources d'un preset personnalisé (des sources de n'importe quelle famille). Sous verrou : lire, modifier, écrire."""
    _perso_existant(cfg, ident)  # d'abord : un identifiant inconnu est refusé sans rien créer sur le disque
    with _verrou_perso(cfg):
        return _modifier(cfg, decls, ident, sources)


def _modifier(cfg: Config, decls: dict[str, Declaration], ident: str, sources: list[str]) -> dict[str, Any]:
    y = _perso_existant(cfg, ident)
    vues: list[str] = []
    for s in sources:
        if s not in vues:
            vues.append(s)
    inconnues = [s for s in vues if s not in decls]
    if inconnues:
        raise ConfigRefusee(f"La source « {inconnues[0]} » n'existe pas.")
    ecrire_atomique(cfg.dossier_presets_perso / f"{ident}.yaml", yaml_texte({**{k: v for k, v in y.items() if k != "sources"}, "sources": vues}, "# Preset personnalisé. Aucune clé.\n"))
    return {"id": ident, "nom": y["nom"], "sources": vues}


def decrire(cfg: Config, ident: str, nom: str, phrase: str = "") -> dict[str, Any]:
    """Change le nom et la description d'un preset personnalisé. L'identifiant (le nom du fichier) ne change pas : les presets cochés restent cochés."""
    _perso_existant(cfg, ident)
    with _verrou_perso(cfg):
        return _decrire(cfg, ident, nom, phrase)


def _decrire(cfg: Config, ident: str, nom: str, phrase: str) -> dict[str, Any]:
    y = _perso_existant(cfg, ident)
    nom = nom.strip()
    if not nom:
        raise ConfigRefusee("Le nom d'un preset ne peut pas rester vide.")
    suite = {k: v for k, v in y.items() if k not in ("nom", "phrase")}
    nouveau = {"nom": nom, **({"phrase": phrase.strip()} if phrase.strip() else {}), **suite}
    ecrire_atomique(cfg.dossier_presets_perso / f"{ident}.yaml", yaml_texte(nouveau, "# Preset personnalisé. Aucune clé.\n"))
    return {"id": ident, "nom": nom, "phrase": phrase.strip()}


def supprimer(cfg: Config, ident: str) -> None:
    _perso_existant(cfg, ident)
    (cfg.dossier_presets_perso / f"{ident}.yaml").unlink()


def source_locale(d: Declaration) -> bool:
    """Vrai pour une source « fichier » ou « base » (lit un fichier de CETTE machine) : son exemple de réponse, embarqué tel quel
    dans un export, peut contenir n'importe quoi de ce fichier (F17-5)."""
    m = d.moteur or {}
    return m.get("adaptateur") == "base_sql" or (m.get("adaptateur") == "api_json" and "fichier" in (m.get("parametres") or {}))


def domaine_source(d: Declaration) -> str:
    """Le domaine vers lequel une source écrit, quand il est DANS SA DÉCLARATION (type « api » : `moteur.parametres.url` ; type « mcp » :
    `moteur.parametres.mcp`). Pour une source du catalogue (adaptateur dédié, « prise » grappes), l'adresse est dans du code revu, pas
    dans la déclaration : rendre « » plutôt que deviner (F17-4a — savoir où une source écrit avant de l'allumer)."""
    import urllib.parse

    p = (d.moteur or {}).get("parametres") or {}
    url = p.get("url") or p.get("mcp") or ""
    if not url:
        return ""
    try:
        return urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _valeurs_de_cles(cfg: Config) -> set[str]:
    out: set[str] = set()
    for f in cfg.fichiers_secrets:
        out |= {v for v in cles._lire_fichier(f).values() if len(v) >= 6}
    return out


def exporter(cfg: Config, decls: dict[str, Declaration], ident: str) -> str:
    """Le preset en fichier texte lisible : sa liste de sources et leurs déclarations (qui ne nomment une clé que par son NOM).
    Aucune valeur de clé, aucun réglage personnel, aucun choix d'activation n'y entre ; un dernier contrôle refuse l'export si une valeur de clé s'y trouvait quand même."""
    from pilote.tests_source import _brut

    y = _perso_existant(cfg, ident)
    ids = [s for s in y.get("sources") or [] if s in decls]
    declarations, exemples = [], {}
    for s in ids:
        b = _brut(decls[s])
        b["defaut"] = {"chercher": False, "verifier": False}  # le choix d'allumer reste à celui qui importe
        declarations.append(b)
        ex = decls[s].exemple_reponse
        # une source « fichier » ou « base » lit un fichier DE CETTE MACHINE : son exemple peut contenir n'importe quoi de ce fichier (F17-5)
        f = cfg.dossier_sources / ex if ex and not source_locale(decls[s]) else None
        if f and f.is_file() and f.stat().st_size <= MAX_EXEMPLE:
            try:
                exemples[ex] = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                pass
    texte = yaml_texte(
        {"format": FORMAT_EXPORT, "preset": {"nom": y["nom"], "phrase": y.get("phrase", ""), "sources": ids}, "declarations": declarations, "exemples": exemples},
        "# Preset Pilote partageable. Aucune clé n'y figure : les sources qui en demandent attendent la vôtre.\n",
    )
    for v in _valeurs_de_cles(cfg):
        if v in texte:
            raise ConfigRefusee("Export refusé : une valeur de clé se trouve dans le fichier. Rien n'a été écrit.")
    return texte


def importer(cfg: Config, decls: dict[str, Declaration], texte: str) -> dict[str, Any]:
    """Recrée un preset à partir d'un fichier exporté. Les sources absentes sont ajoutées ÉTEINTES (et en attente de clé s'il en faut une) ;
    une source déjà présente n'est jamais écrasée ; un programme local n'est jamais importé (il s'exécuterait sur cette machine)."""
    from pilote.sources import valider_declaration

    try:
        y = yaml.safe_load(texte)
    except yaml.YAMLError as exc:
        raise ConfigRefusee("Ce fichier n'est pas lisible (YAML invalide).") from exc
    if not isinstance(y, dict) or y.get("format") != FORMAT_EXPORT or not isinstance(y.get("preset"), dict):
        raise ConfigRefusee("Ce fichier n'est pas un preset exporté par Pilote.")
    nom = str(y["preset"].get("nom", "")).strip()
    ident = slug(nom)
    if not ident:
        raise ConfigRefusee("Le preset du fichier n'a pas de nom exploitable.")
    if ident in ids_connus(cfg):
        raise ConfigRefusee(f"Un preset s'appelle déjà « {nom} » : supprimez-le ou renommez-le avant d'importer.")
    ids = [str(s) for s in y["preset"].get("sources") or []]
    brutes = {str(d.get("id")): d for d in y.get("declarations") or [] if isinstance(d, dict)}
    exemples = y.get("exemples") if isinstance(y.get("exemples"), dict) else {}
    # tout est vérifié AVANT d'écrire quoi que ce soit
    a_ecrire: list[tuple[str, dict[str, Any]]] = []
    ajoutees, existantes, ignorees, cles_deja_presentes = [], [], [], []
    for s in ids:
        if s in decls:
            existantes.append(s)
            continue
        b = brutes.get(s)
        if b is None:
            raise ConfigRefusee(f"Le fichier cite la source « {s} » sans la décrire.")
        if isinstance(b.get("moteur"), dict) and "script" in b["moteur"]:
            ignorees.append({"source": s, "raison": "programme local : jamais importé (il s'exécuterait ici). Ajoutez-le vous-même par la page Ajout."})
            continue
        b = {**b, "defaut": {"chercher": False, "verifier": False}}
        cle_brute = b.get("cle")
        noms_cle = cle_brute if isinstance(cle_brute, list) else [cle_brute] if cle_brute else []
        if any(cles.presente(cfg, n) for n in noms_cle):
            # la source réclame une clé que vous avez déjà : elle reste importée (éteinte), mais c'est SIGNALÉ en gros avant toute activation
            # (F17-4b — une source déclarée peut envoyer cette clé à l'adresse de son choix ; voir le domaine, Réglages > Détails)
            cles_deja_presentes.append({"source": s, "cle": noms_cle[0] if len(noms_cle) == 1 else noms_cle})
        ex = str(b.get("exemple_reponse") or "")
        if ex and (Path(ex).is_absolute() or ".." in Path(ex).parts):
            raise ConfigRefusee(f"{s} : le chemin de l'exemple de réponse est refusé.")
        valider_declaration(b, cfg, f"{s}.yaml")
        a_ecrire.append((s, b))
        ajoutees.append(s)
    for s, b in a_ecrire:
        ecrire_atomique(cfg.dossier_sources / f"{s}.yaml", yaml_texte(b, "# Source importée avec un preset. Éteinte tant que vous ne l'allumez pas.\n"))
        ex = str(b.get("exemple_reponse") or "")
        if ex and isinstance(exemples.get(ex), str) and not (cfg.dossier_sources / ex).exists():
            ecrire_atomique(cfg.dossier_sources / ex, exemples[ex])
    gardees = [s for s in ids if s not in {i["source"] for i in ignorees}]
    ecrire_atomique(cfg.dossier_presets_perso / f"{ident}.yaml",
                    yaml_texte({"nom": nom, "phrase": str(y["preset"].get("phrase") or ""), "sources": gardees}, "# Preset personnalisé importé. Aucune clé.\n"))
    en_attente = [s for s in gardees if s in {a for a, _ in a_ecrire} and (brutes[s].get("cle"))]
    return {"id": ident, "nom": nom, "ajoutees": ajoutees, "existantes": existantes, "ignorees": ignorees, "en_attente_de_cle": en_attente,
            "cles_deja_presentes": cles_deja_presentes}  # fmt: skip
