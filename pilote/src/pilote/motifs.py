"""Motifs de rejet (fiche 13, idée reprise de Rayyan) : un rejet peut dire POURQUOI (mauvais type, hors zone, doublon...), à une touche.
Les motifs et leurs touches sont dans `config/motifs_rejet.yaml` ; l'utilisateur les change depuis Tri. Rien n'est écrit si la liste est invalide."""

from __future__ import annotations

import re
from typing import Any

import yaml

from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, verrou, yaml_texte

TOUCHES_PRISES = frozenset("grpzGRPZ/") | {"ArrowUp", "ArrowDown", "Enter", "Escape", " "}
IDENT = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
PAR_DEFAUT = [{"id": "mauvais_type", "libelle": "Mauvais type", "touche": "1"}, {"id": "hors_zone", "libelle": "Hors zone", "touche": "2"}, {"id": "doublon", "libelle": "Doublon", "touche": "3"}]


def fichier(cfg: Config):
    return cfg.dossier_config / "motifs_rejet.yaml"


def lire(cfg: Config) -> list[dict[str, str]]:
    f = fichier(cfg)
    try:
        y = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else None
        liste = (y or {}).get("motifs")
        return valider(liste) if liste else [dict(m) for m in PAR_DEFAUT]
    except (OSError, yaml.YAMLError, ConfigRefusee):
        return [dict(m) for m in PAR_DEFAUT]


def valider(motifs: Any) -> list[dict[str, str]]:
    if not isinstance(motifs, list) or not motifs:
        raise ConfigRefusee("Donnez au moins un motif de rejet.")
    out, ids, touches = [], set(), set()
    for m in motifs:
        if not isinstance(m, dict):
            raise ConfigRefusee("Chaque motif a un identifiant, un libellé et une touche.")
        ident, libelle, touche = str(m.get("id", "")).strip(), str(m.get("libelle", "")).strip(), str(m.get("touche", ""))
        if not IDENT.match(ident):
            raise ConfigRefusee(f"L'identifiant « {ident} » doit tenir en lettres minuscules, chiffres et tirets bas (par exemple hors_zone).")
        if not libelle:
            raise ConfigRefusee(f"Le motif « {ident} » n'a pas de libellé.")
        if len(touche) != 1 or touche in TOUCHES_PRISES:
            raise ConfigRefusee(f"La touche du motif « {libelle} » doit être UNE lettre ou un chiffre, et pas G, R, P, Z ni /, qui ont déjà un rôle.")
        if ident in ids:
            raise ConfigRefusee(f"Le motif « {ident} » est donné deux fois.")
        if touche.lower() in touches:
            raise ConfigRefusee(f"La touche « {touche} » est déjà celle d'un autre motif.")
        ids.add(ident)
        touches.add(touche.lower())
        out.append({"id": ident, "libelle": libelle, "touche": touche})
    return out


def ecrire(cfg: Config, motifs: Any) -> list[dict[str, str]]:
    propres = valider(motifs)
    with verrou(fichier(cfg)):
        ecrire_atomique(fichier(cfg), yaml_texte({"motifs": propres}, "# Motifs de rejet de la page Tri (touches personnalisables).\n"))
    return propres
