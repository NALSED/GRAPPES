"""Déclaration des sources (fiche 01) : chaque source dit CE QU'ELLE FAIT dans un petit fichier, et c'est de là que viennent
les presets, la page Réglages et le coût. Aucun code d'activité national n'est connu du cœur : une source fait correspondre
son vocabulaire à des genres génériques (club, entreprise, association...).

Une déclaration = un fichier `config/sources/<id>.yaml`. Les CHOIX de l'utilisateur (cases chercher/vérifier, confiance, plafond)
sont dans `config/reglages.yaml`, jamais ici : la déclaration livrée n'est pas modifiée par l'usage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pilote.config import Config
from pilote.refus import ConfigRefusee, lire_yaml

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
MAINS = {"premiere": "première main", "seconde": "seconde main"}
ROLES = ("chercher", "verifier")  # les rôles par défaut d'une source
ROLES_VALIDES = (*ROLES, "enrichir")  # « enrichir » doit être demandé : il n'est jamais un rôle par défaut
ORIGINES = ("registre", "presse", "encyclo", "web", "texte")  # d'où vient un nom : du plus solide au plus fragile
MOTEURS = ("prise", "definition", "registre_grappes", "adaptateur", "script", "flux_rss")  # comment une source est interrogée
CHAMPS_CONNUS = {
    "id", "nom", "description", "trouve", "genres", "pays", "consomme", "produit", "usages", "main", "famille", "cle", "cout", "confiance",
    "defaut", "roles", "avertissement", "mode", "exemple_reponse", "test_connexion", "moteur", "verifie_le", "prestataire", "note", "origine",
    "parametres", "cle_prefixe", "attribution", "verifie_sur", "fiabilite",
}  # fmt: skip


@dataclass(slots=True)
class Declaration:
    id: str
    nom: str
    description: str
    trouve: str
    genres: list[str]
    pays: list[str]
    consomme: list[str]
    produit: list[str]
    usages: list[str]
    main: str
    famille: str
    cle: str  # nom de la (première) variable de secrets.env, "" = pas de clé
    cout: dict[str, Any]
    confiance: float
    defaut: dict[str, bool]
    roles: list[str]
    avertissement: str
    mode: dict[str, bool]
    moteur: dict[str, Any]
    cles: list[str] = field(default_factory=list)  # toutes les variables de clé de la source (une seule le plus souvent)
    cle_prefixe: str = ""  # texte ajouté devant la valeur de la clé dans la copie de configuration d'une recherche (ex. « Bearer »)
    origine: str = "web"  # classe des noms que la source rend : registre, presse, encyclo, web, texte (la couleur dans Tri)
    parametres: dict[str, Any] = field(default_factory=dict)  # réglages propres à la source que l'utilisateur doit donner (ex. adresse d'un portail)
    exemple_reponse: str = ""
    test_connexion: dict[str, Any] = field(default_factory=dict)
    verifie_le: str = ""
    prestataire: bool = False
    note: str = ""
    verifie_sur: str = ""  # « site » (adresse du candidat) ou « nom » (son nom) : la source vérifie chaque candidat après la recherche, elle ne cherche pas ; vide = elle cherche seulement
    fiabilite: str = ""  # lettre A–F (code Admiralty) donnée par la déclaration quand l'origine ne suffit pas à la deviner (ex. A : registre officiel de première main) ; vide = défaut selon la classe
    attribution: dict[str, str] = field(default_factory=dict)  # mention OBLIGATOIRE de la source dans les sorties et le README : {texte, url} (ex. GDELT)

    @property
    def payant(self) -> bool:
        return float(self.cout.get("vers_dollar", 0) or 0) > 0 and float(self.cout.get("par_appel", 1) or 0) > 0

    def vue(self) -> dict[str, Any]:
        return {
            "id": self.id, "nom": self.nom, "description": self.description, "trouve": self.trouve, "genres": self.genres, "pays": self.pays,
            "usages": self.usages, "main": self.main, "main_phrase": MAINS[self.main], "famille": self.famille, "cle_requise": bool(self.cle), "cles_noms": self.cles,
            "cout": self.cout, "payant": self.payant, "confiance_defaut": self.confiance, "defaut": self.defaut, "roles": self.roles,
            "avertissement": self.avertissement, "mode": self.mode, "prestataire": self.prestataire, "note": self.note, "verifie_le": self.verifie_le,
            "origine": self.origine, "parametres_attendus": self.parametres, "attribution": self.attribution,
        }  # fmt: skip


def _liste(d: dict[str, Any], cle: str, nom: str, *, requis: bool = True) -> list[str]:
    v = d.get(cle)
    if v is None and not requis:
        return []
    if not isinstance(v, list) or (requis and not v) or not all(isinstance(x, str) and x.strip() for x in v):
        raise ConfigRefusee(f"{nom} : « {cle} » doit être une liste de mots" + (" (au moins un)." if requis else "."))
    return [x.strip() for x in v]


def _nombre(v: Any, nom: str, minimum: float = 0.0, maximum: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigRefusee(f"{nom} doit être un nombre.")
    if v < minimum or (maximum is not None and v > maximum):
        raise ConfigRefusee(f"{nom} doit être " + (f"entre {minimum:g} et {maximum:g}." if maximum is not None else f"au moins {minimum:g}."))
    return float(v)


def valider_declaration(d: dict[str, Any], cfg: Config, fichier: str = "") -> Declaration:
    nom_f = f"La source « {d.get('id', fichier) or fichier} »"
    inconnus = sorted(set(d) - CHAMPS_CONNUS)
    if inconnus:
        raise ConfigRefusee(f"{nom_f} contient un réglage inconnu : « {inconnus[0]} ». Vérifiez l'orthographe.")
    ident = d.get("id")
    if not isinstance(ident, str) or not ID.match(ident):
        raise ConfigRefusee(f"{nom_f} : l'identifiant doit tenir en lettres minuscules, chiffres, tirets (ex. « registre-asso »).")
    if fichier and Path(fichier).stem != ident:
        raise ConfigRefusee(f"{nom_f} : le fichier doit s'appeler {ident}.yaml (il s'appelle {fichier}).")
    nom = d.get("nom")
    if not isinstance(nom, str) or not nom.strip():
        raise ConfigRefusee(f"{nom_f} : il manque son nom.")
    genres = _liste(d, "genres", nom_f)
    if cfg.genres:
        mauvais = [g for g in genres if g not in cfg.genres]
        if mauvais:
            raise ConfigRefusee(f"{nom_f} : le genre « {mauvais[0]} » n'existe pas. Genres connus : {', '.join(cfg.genres)}.")
    pays = [p.strip() for p in _liste(d, "pays", nom_f)]
    for p in pays:
        if p.lower() != "monde" and not re.fullmatch(r"[A-Za-z]{2}", p):
            raise ConfigRefusee(f"{nom_f} : « {p} » n'est pas un code pays à deux lettres (FR, GB, NZ...) ni « monde ».")
    main = d.get("main")
    if main not in MAINS:
        raise ConfigRefusee(f"{nom_f} : dites si la source est de première main (écrire « premiere ») ou de seconde main (écrire « seconde »).")
    famille = d.get("famille")
    if cfg.ordre_familles and famille not in cfg.ordre_familles:
        raise ConfigRefusee(f"{nom_f} : la famille « {famille} » n'existe pas. Familles connues : {', '.join(cfg.ordre_familles)}.")
    brut_cle = d.get("cle") or ""
    liste_cles = [brut_cle] if isinstance(brut_cle, str) and brut_cle else list(brut_cle) if isinstance(brut_cle, list) else []
    if brut_cle and (not liste_cles or any(not isinstance(c, str) or not VARIABLE.match(c) for c in liste_cles)):
        raise ConfigRefusee(f"{nom_f} : le nom de la clé doit s'écrire en majuscules, comme MA_CLE_API.")
    cle = liste_cles[0] if liste_cles else ""
    cout = d.get("cout") or {}
    if not isinstance(cout, dict):
        raise ConfigRefusee(f"{nom_f} : le coût doit être décrit par : unite, vers_dollar, par_appel, gratuit_par_mois.")
    cout = {"unite": str(cout.get("unite", "appel")), "vers_dollar": _nombre(cout.get("vers_dollar", 0), f"{nom_f} : le taux vers le dollar"),
            "par_appel": _nombre(cout.get("par_appel", 1), f"{nom_f} : le nombre d'unités par appel"),
            "gratuit_par_mois": _nombre(cout.get("gratuit_par_mois", 0), f"{nom_f} : le quota gratuit mensuel")}  # fmt: skip
    confiance = _nombre(d.get("confiance", 0.5), f"{nom_f} : le niveau de confiance", 0.0, 1.0)
    defaut = d.get("defaut") or {}
    if not isinstance(defaut, dict) or any(not isinstance(v, bool) for v in defaut.values()) or set(defaut) - set(ROLES):
        raise ConfigRefusee(f"{nom_f} : « defaut » donne seulement chercher et verifier, chacun à oui ou non.")
    roles = _liste(d, "roles", nom_f) if d.get("roles") is not None else list(ROLES)
    if set(roles) - set(ROLES_VALIDES):
        raise ConfigRefusee(f"{nom_f} : un rôle ne peut être que « chercher », « verifier » ou « enrichir ».")
    mode = d.get("mode") or {"en_ligne": True, "local": False}
    if not isinstance(mode, dict) or any(not isinstance(v, bool) for v in mode.values()):
        raise ConfigRefusee(f"{nom_f} : « mode » dit si la source tourne en ligne et/ou en copie locale (oui ou non).")
    moteur = d.get("moteur")
    if not isinstance(moteur, dict) or not moteur:
        raise ConfigRefusee(f"{nom_f} : il manque « moteur », qui dit comment interroger la source.")
    genre_moteur = [k for k in moteur if k in MOTEURS]
    if len(genre_moteur) != 1 or set(moteur) - set(MOTEURS) - {"parametres"}:
        raise ConfigRefusee(f"{nom_f} : « moteur » doit contenir exactement un de : {', '.join(MOTEURS)}.")
    origine = d.get("origine", "web")
    if origine not in ORIGINES:
        raise ConfigRefusee(f"{nom_f} : l'origine « {origine} » n'existe pas. Origines connues : {', '.join(ORIGINES)}.")
    params = d.get("parametres") or {}
    if not isinstance(params, dict) or any(not isinstance(v, dict) for v in params.values()):
        raise ConfigRefusee(f"{nom_f} : « parametres » décrit chaque réglage attendu (libelle, type, requis).")
    attribution = d.get("attribution") or {}
    if attribution and (not isinstance(attribution, dict) or not str(attribution.get("texte", "")).strip() or not str(attribution.get("url", "")).startswith(("http://", "https://"))):
        raise ConfigRefusee(f"{nom_f} : « attribution » demande un « texte » et une « url » (http:// ou https://).")
    fiabilite = str(d.get("fiabilite") or "")
    if fiabilite and fiabilite not in tuple("ABCDEF"):
        raise ConfigRefusee(f"{nom_f} : « fiabilite » est une lettre de A à F (code Admiralty).")
    verifie_sur = str(d.get("verifie_sur") or "")
    if verifie_sur and (verifie_sur not in ("site", "nom", "ville") or not ({"verifier", "enrichir"} & set(roles)) or "adaptateur" not in moteur or (verifie_sur == "ville" and "enrichir" not in roles)):
        raise ConfigRefusee(f"{nom_f} : « verifie_sur » vaut « site » ou « nom » (rôle « verifier » ou « enrichir » avec un adaptateur), ou « ville » (rôle « enrichir »).")
    return Declaration(
        id=ident, nom=nom.strip(), description=str(d.get("description", "")).strip(), trouve=str(d.get("trouve", "")).strip(), genres=genres, pays=pays,
        consomme=_liste(d, "consomme", nom_f, requis=False), produit=_liste(d, "produit", nom_f, requis=False), usages=_liste(d, "usages", nom_f),
        main=main, famille=famille or "", cle=cle, cout=cout, confiance=confiance,
        defaut={"chercher": bool(defaut.get("chercher", False)), "verifier": bool(defaut.get("verifier", False))}, roles=roles,
        avertissement=str(d.get("avertissement") or "").strip(), mode={"en_ligne": bool(mode.get("en_ligne", True)), "local": bool(mode.get("local", False))},
        moteur=moteur, cles=liste_cles, cle_prefixe=str(d.get("cle_prefixe") or ""), origine=origine, parametres=params, exemple_reponse=str(d.get("exemple_reponse") or ""), test_connexion=dict(d.get("test_connexion") or {}),
        verifie_le=str(d.get("verifie_le") or ""), prestataire=bool(d.get("prestataire", False)), note=str(d.get("note") or "").strip(), attribution=attribution, verifie_sur=verifie_sur, fiabilite=fiabilite,
    )  # fmt: skip


def charger_sources(cfg: Config) -> tuple[dict[str, Declaration], list[dict[str, str]]]:
    """Toutes les déclarations lisibles, et la liste des fichiers refusés avec leur raison (un fichier cassé n'arrête pas les autres)."""
    out: dict[str, Declaration] = {}
    problemes: list[dict[str, str]] = []
    d = cfg.dossier_sources
    for f in sorted(d.glob("*.yaml")) if d.is_dir() else []:
        try:
            decl = valider_declaration(lire_yaml(f), cfg, f.name)
        except ConfigRefusee as exc:
            problemes.append({"fichier": f.name, "raison": str(exc)})
            continue
        if decl.id in out:
            problemes.append({"fichier": f.name, "raison": f"Deux fichiers déclarent la source « {decl.id} »."})
            continue
        out[decl.id] = decl
    return out, problemes
