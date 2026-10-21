"""Choix de l'utilisateur (fiche 01) : `config/reglages.yaml`. Ce fichier est la référence ; la base ne garde que les recherches
et les décisions. Toute modification est vérifiée AVANT écriture : si elle est refusée, l'ancien fichier reste intact."""

from __future__ import annotations

import math
from typing import Any

from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, lire_yaml, verrou, yaml_texte
from pilote.sources import Declaration

DEFAUT: dict[str, Any] = {
    "version": 1,
    "budget": {"plafond_mensuel_usd": 10.0},
    "verification": {"active": True, "mode": "memes"},  # mode : « memes » = vérifier avec les sources cochées en recherche ; « plus » = ajouter des sources de vérification seules
    "sortie": {"actifs": ["csv"], "dossier": "", "contenus": {}, "webhook_url": ""},  # contenus : par format, ce qu'on écrit (nom, tsites, detail) ; sinon celui que le format propose
    "pays": "",
    "presets_coches": [],
    "sources": {},
    "assistant": {"termine": False},
    # Sources retirées de l'AFFICHAGE d'une partie de Réglages (jamais des fichiers) : on peut les remettre depuis « Ajouter une source existante ».
    "affichage": {"sources_masquees": [], "verification_masquees": []},
    "avertissements_vus": [],  # sources dont l'avertissement a déjà été montré et accepté (il n'est montré qu'une fois)
    # Place réservée (fiche 15, rien n'est branché) : la liste des modèles d'IA que l'utilisateur ajoutera un jour (nom, adresse, clé).
    "modeles_ia": [],
}
ENTETE = "# Choix de l'utilisateur (écrit par pilote, lisible à la main). Les déclarations des sources sont dans sources/.\n"


def _defauts() -> dict[str, Any]:
    return {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in DEFAUT.items()}


def charger(cfg: Config) -> dict[str, Any]:
    """Les réglages, avec les valeurs par défaut pour ce qui manque. Une valeur de la mauvaise FORME (une liste là où il
    faut un dictionnaire) est ignorée au profit du défaut : la page doit s'afficher même après une retouche à la main."""
    f = cfg.fichier_reglages
    y = lire_yaml(f) if f.exists() else {}
    out = _defauts()
    for k, v in y.items():
        attendu = DEFAUT.get(k)
        if isinstance(attendu, dict):
            if isinstance(v, dict):
                out[k] = {**out[k], **v}
        elif isinstance(attendu, list):
            if isinstance(v, list):
                out[k] = v
        else:
            out[k] = v
    return out


def charger_tolerant(cfg: Config) -> tuple[dict[str, Any], str | None]:
    """Comme `charger`, mais un fichier cassé ne fait pas tomber la page : valeurs par défaut et raison en français."""
    try:
        return charger(cfg), None
    except ConfigRefusee as exc:
        return _defauts(), str(exc)


def _nombre_tolerant(v: Any, defaut: float, minimum: float | None = None, maximum: float | None = None) -> float:
    """Un nombre retouché à la main et devenu illisible ne doit jamais faire tomber une page : on reprend le défaut."""
    try:
        if isinstance(v, bool):
            raise TypeError
        x = float(v)
    except (TypeError, ValueError):
        return defaut
    if math.isnan(x) or (minimum is not None and x < minimum) or (maximum is not None and x > maximum):
        return defaut
    return x


LIBELLE_SECTION = {"budget": "le budget", "verification": "la vérification", "sortie": "la sortie", "sources": "les réglages des sources",
                   "presets_coches": "les presets cochés", "avertissements_vus": "les avertissements déjà vus", "modeles_ia": "les modèles d'IA",
                   "assistant": "l'assistant", "affichage": "les sources retirées de l'affichage"}  # fmt: skip


def problemes_de_valeurs(cfg: Config, r: dict[str, Any], decls: dict[str, Declaration]) -> list[dict[str, str]]:
    """Valeurs inutilisables trouvées dans les réglages (retouche à la main) : la page les montre et garde le défaut."""
    out: list[dict[str, str]] = []
    nom_f = cfg.fichier_reglages.name
    try:  # sections de la mauvaise FORME : `charger` a déjà repris le défaut, encore faut-il le dire
        brut = lire_yaml(cfg.fichier_reglages) if cfg.fichier_reglages.exists() else {}
    except ConfigRefusee:
        brut = {}
    for k, attendu in DEFAUT.items():
        if k in brut and isinstance(attendu, (dict, list)) and not isinstance(brut[k], type(attendu)):
            quoi = "des réglages (clé: valeur)" if isinstance(attendu, dict) else "une liste"
            out.append({"fichier": nom_f, "raison": f"{LIBELLE_SECTION.get(k, k)} : la forme attendue est {quoi} ; ce qui est écrit est ignoré et le réglage par défaut est utilisé."})
    b = (r.get("budget") or {}).get("plafond_mensuel_usd")
    if _nombre_tolerant(b, -1.0, 0.0) < 0:
        out.append({"fichier": nom_f, "raison": f"le plafond de dépense mensuel (« {b} ») n'est pas un nombre : {DEFAUT['budget']['plafond_mensuel_usd']:g} $ est utilisé."})
    if not isinstance((r.get("verification") or {}).get("active"), bool):
        out.append({"fichier": nom_f, "raison": "la vérification doit être oui ou non : elle est considérée comme active."})
    for cle_a in ("sources_masquees", "verification_masquees"):
        v = (r.get("affichage") or {}).get(cle_a, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            out.append({"fichier": nom_f, "raison": "la liste des sources retirées de l'affichage est mal écrite : elle est ignorée (toutes les sources s'affichent)."})
            break
    for sid, s in (r.get("sources") or {}).items():
        nom = decls[sid].nom if sid in decls else sid
        if not isinstance(s, dict):
            out.append({"fichier": nom_f, "raison": f"les réglages de la source « {nom} » sont mal écrits : ceux de sa déclaration sont utilisés."})
            continue
        if "confiance" in s and _nombre_tolerant(s["confiance"], -1.0, 0.0, 1.0) < 0:
            out.append({"fichier": nom_f, "raison": f"le niveau de confiance de « {nom} » (« {s['confiance']} ») n'est pas un nombre entre 0 et 1 : celui de sa déclaration est utilisé."})
        for k, v in (s.get("cout") or {}).items() if isinstance(s.get("cout"), dict) else []:
            if k != "unite" and _nombre_tolerant(v, -1.0, 0.0) < 0:
                out.append({"fichier": nom_f, "raison": f"le coût de « {nom} » : « {k} » (« {v} ») n'est pas un nombre : celui de sa déclaration est utilisé."})
    return out


def ids_de_liste(v: Any) -> set[str]:
    """Une liste de noms de sources retouchée à la main et devenue autre chose ne fait jamais tomber la page : on la lit comme vide."""
    return {x for x in v if isinstance(x, str)} if isinstance(v, list) else set()


def parametres_donnes(r: dict[str, Any], sid: str) -> dict[str, Any]:
    """Les réglages propres à une source donnés par l'utilisateur ; vide si l'entrée a été retouchée en autre chose qu'un dictionnaire (jamais fatal)."""
    s = (r.get("sources") or {}).get(sid) if isinstance(r.get("sources"), dict) else None
    p = s.get("parametres") if isinstance(s, dict) else None
    return p if isinstance(p, dict) else {}


def existe(cfg: Config) -> bool:
    return cfg.fichier_reglages.exists()


def _nombre(v: Any, nom: str, minimum: float, maximum: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigRefusee(f"{nom} doit être un nombre.")
    if v < minimum or (maximum is not None and v > maximum):
        raise ConfigRefusee(f"{nom} doit être " + (f"entre {minimum:g} et {maximum:g}." if maximum is not None else f"d'au moins {minimum:g}."))
    return float(v)


def verifier(r: dict[str, Any], decls: dict[str, Declaration], presets_connus: set[str]) -> None:
    """Lève ConfigRefusee, en français, si les réglages ne tiennent pas."""
    b = r.get("budget") or {}
    _nombre(b.get("plafond_mensuel_usd"), "Le plafond de dépense mensuel", 0.0, 100000.0)
    if not isinstance((r.get("verification") or {}).get("active"), bool):
        raise ConfigRefusee("La vérification doit être activée ou désactivée (oui ou non).")
    if (r.get("verification") or {}).get("mode", "memes") not in ("memes", "plus"):
        raise ConfigRefusee("Le mode de vérification doit être « memes » (les sources de recherche) ou « plus » (avec des sources de vérification en plus).")
    so = r.get("sortie") or {}
    if not isinstance(so.get("actifs", []), list) or not all(isinstance(x, str) for x in so.get("actifs", [])):
        raise ConfigRefusee("Les formats de sortie doivent être une liste de noms de formats.")
    if not isinstance(so.get("dossier", ""), str):
        raise ConfigRefusee("Le dossier de sortie doit être un chemin écrit en toutes lettres.")
    co = so.get("contenus", {})
    if not isinstance(co, dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(x, str) for x in v) for k, v in co.items()):
        raise ConfigRefusee("Le contenu de chaque format de sortie est une liste de mots (nom, tsites, detail).")
    w = so.get("webhook_url", "")
    if not isinstance(w, str) or (w.strip() and not w.strip().startswith(("http://", "https://"))):
        raise ConfigRefusee("L'adresse du webhook doit commencer par http:// ou https://.")
    pays = r.get("pays", "")
    if pays and not (isinstance(pays, str) and len(pays) == 2 and pays.isalpha()):
        raise ConfigRefusee("Le pays se donne par son code à deux lettres (FR, GB, NZ...).")
    for cle_a in ("sources_masquees", "verification_masquees"):
        v = (r.get("affichage") or {}).get(cle_a, [])
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ConfigRefusee("La liste des sources retirées de l'affichage doit être une liste de noms de sources.")
    vus = r.get("avertissements_vus", [])
    if not isinstance(vus, list) or not all(isinstance(x, str) for x in vus):
        raise ConfigRefusee("La liste des avertissements déjà acceptés doit être une liste de noms de sources.")
    coches = r.get("presets_coches", [])
    if not isinstance(coches, list) or any(c not in presets_connus for c in coches):
        mauvais = [c for c in (coches if isinstance(coches, list) else []) if c not in presets_connus]
        raise ConfigRefusee(f"Le preset « {mauvais[0] if mauvais else '?'} » n'existe pas.")
    for sid, s in (r.get("sources") or {}).items():
        if sid not in decls:
            raise ConfigRefusee(f"La source « {sid} » n'existe pas : aucune déclaration à ce nom.")
        d = decls[sid]
        if not isinstance(s, dict):
            raise ConfigRefusee(f"Les réglages de la source « {d.nom} » sont mal écrits.")
        for role in ("chercher", "verifier"):
            if role in s:
                if not isinstance(s[role], bool):
                    raise ConfigRefusee(f"« {role} » pour la source « {d.nom} » doit être oui ou non.")
                if s[role] and role not in d.roles:
                    raise ConfigRefusee(f"La source « {d.nom} » ne peut pas servir à {'chercher' if role == 'chercher' else 'vérifier'}.")
        if "confiance" in s:
            _nombre(s["confiance"], f"Le niveau de confiance de « {d.nom} »", 0.0, 1.0)
        donnes = s.get("parametres") or {}
        if not isinstance(donnes, dict) or set(donnes) - set(d.parametres):
            inconnu = min(set(donnes) - set(d.parametres)) if isinstance(donnes, dict) and set(donnes) - set(d.parametres) else "?"
            raise ConfigRefusee(f"Le réglage « {inconnu} » n'existe pas pour la source « {d.nom} ».")
        for nom_p, spec in d.parametres.items():
            v = str(donnes.get(nom_p, "")).strip()
            if v and spec.get("type") == "url" and not v.startswith(("http://", "https://")):
                raise ConfigRefusee(f"{str(spec.get('libelle', nom_p)).capitalize()} doit commencer par https:// (ou http://).")
            if not v and spec.get("requis") and (s.get("chercher") or s.get("verifier")):
                raise ConfigRefusee(f"Pour activer « {d.nom} », donne d'abord : {str(spec.get('libelle', nom_p)).lower()}.")
        if "cout" in s:
            c = s["cout"]
            if not isinstance(c, dict) or set(c) - {"unite", "vers_dollar", "par_appel", "gratuit_par_mois"}:
                raise ConfigRefusee(f"Le coût de « {d.nom} » se décrit par : unite, vers_dollar, par_appel, gratuit_par_mois.")
            for k in ("vers_dollar", "par_appel", "gratuit_par_mois"):
                if k in c:
                    _nombre(c[k], f"Le champ « {k} » du coût de « {d.nom} »", 0.0)


def avertissements_requis(r: dict[str, Any], decls: dict[str, Declaration], patch: dict[str, Any]) -> list[dict[str, str]]:
    """Sources que ce changement ALLUME et dont l'avertissement n'a jamais été accepté (prestataires payants, services à risque)."""
    allumees: list[str] = []
    if "source" in patch and (patch["source"].get("chercher") or patch["source"].get("verifier")):
        allumees.append(patch["source"]["id"])
    for sid, ch in (patch.get("sources") or {}).items():
        if ch.get("chercher") or ch.get("verifier"):
            allumees.append(sid)
    vus = set(r.get("avertissements_vus") or [])
    return [{"source": sid, "nom": decls[sid].nom, "texte": decls[sid].avertissement}
            for sid in dict.fromkeys(allumees) if sid in decls and decls[sid].avertissement and sid not in vus]  # fmt: skip


def appliquer(cfg: Config, decls: dict[str, Declaration], presets_connus: set[str], patch: dict[str, Any]) -> dict[str, Any]:
    """Fusionne `patch` dans les réglages, vérifie, puis écrit. Rien n'est écrit si la vérification refuse.

    Sous verrou : deux changements envoyés en même temps (plusieurs cases cochées de suite) se recouvraient, et le
    premier était perdu sans un mot."""
    with verrou(cfg.fichier_reglages):
        return _appliquer(cfg, decls, presets_connus, patch)


def _appliquer(cfg: Config, decls: dict[str, Declaration], presets_connus: set[str], patch: dict[str, Any]) -> dict[str, Any]:
    r = charger(cfg)
    for k, v in patch.items():
        if k == "source":
            sid = v["id"]
            cur = dict(r["sources"].get(sid) or {})
            cur.update({a: b for a, b in v.items() if a != "id"})
            r["sources"][sid] = cur
        elif k == "sources":  # plusieurs sources d'un coup (assistant) : {id: {chercher: ..., verifier: ...}}
            for sid, ch in v.items():
                r["sources"][sid] = {**(r["sources"].get(sid) or {}), **ch}
        elif k in ("budget", "verification", "assistant", "sortie", "affichage") and isinstance(v, dict):
            r[k] = {**r[k], **v}
        else:
            r[k] = v
    _rendre_visibles_les_sources_allumees(r, decls)
    verifier(r, decls, presets_connus)
    ecrire_atomique(cfg.fichier_reglages, yaml_texte(r, ENTETE))
    return r


PARTIES_AFFICHAGE = {"recherche": ("sources_masquees", "chercher"), "verification": ("verification_masquees", "verifier")}


def _rendre_visibles_les_sources_allumees(r: dict[str, Any], decls: dict[str, Declaration]) -> None:
    """Invariant : une source retirée de l'affichage est éteinte pour ce rôle. Si un autre chemin la rallume (assistant, preset, appel
    direct), elle revient à l'affichage : jamais une source active qu'on ne voit pas."""
    aff = r.get("affichage")
    if not isinstance(aff, dict):
        return
    for cle_liste, role in PARTIES_AFFICHAGE.values():
        ids = aff.get(cle_liste)
        if isinstance(ids, list):
            aff[cle_liste] = [s for s in ids if not (isinstance(s, str) and s in decls and choix_source(r, decls[s])[role])]


def masquer(cfg: Config, decls: dict[str, Declaration], presets_connus: set[str], sid: str, partie: str, masquee: bool) -> dict[str, Any]:
    """Retire une source de l'AFFICHAGE d'une partie (ou la remet). Rien n'est supprimé sur disque. Une source retirée est aussi
    éteinte pour ce rôle : sinon elle continuerait de servir sans qu'on puisse la voir."""
    if partie not in PARTIES_AFFICHAGE:
        raise ConfigRefusee("Cette partie de la page n'existe pas.")
    if sid not in decls:
        raise ConfigRefusee(f"La source « {sid} » n'existe pas.")
    cle_liste, role = PARTIES_AFFICHAGE[partie]
    with verrou(cfg.fichier_reglages):
        r = charger(cfg)
        liste = sorted(ids_de_liste((r.get("affichage") or {}).get(cle_liste)) - {sid})
        if masquee:
            liste.append(sid)
        patch: dict[str, Any] = {"affichage": {cle_liste: liste}}
        if masquee and role in decls[sid].roles:
            patch["source"] = {"id": sid, role: False}
        return _appliquer(cfg, decls, presets_connus, patch)


def choix_source(r: dict[str, Any], d: Declaration) -> dict[str, Any]:
    """Réglages EFFECTIFS d'une source : le choix de l'utilisateur s'il existe, sinon la valeur par défaut de sa déclaration.

    Ne lève JAMAIS : une valeur retouchée à la main et illisible reprend celle de la déclaration (et `problemes_de_valeurs`
    le dit en haut de la page). Sans cela, un seul caractère de trop dans le fichier rendait Réglages inaccessible — donc
    impossible à corriger depuis l'application."""
    s = (r.get("sources") or {}).get(d.id) or {}
    if not isinstance(s, dict):
        s = {}
    donne = s.get("cout") if isinstance(s.get("cout"), dict) else {}
    cout = {**d.cout}
    for k, v in (donne or {}).items():
        cout[k] = str(v) if k == "unite" else _nombre_tolerant(v, float(d.cout.get(k, 0) or 0), 0.0)
    coche = {role: (s[role] if isinstance(s.get(role), bool) else d.defaut[role]) for role in ("chercher", "verifier")}  # autre chose qu'un oui/non : on reprend la déclaration
    return {
        "chercher": coche["chercher"] and "chercher" in d.roles,
        "verifier": coche["verifier"] and "verifier" in d.roles,
        "confiance": _nombre_tolerant(s.get("confiance", d.confiance), d.confiance, 0.0, 1.0),
        "cout": cout,
    }
