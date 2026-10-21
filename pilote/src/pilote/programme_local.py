"""Ajouter un programme local (fiche 10, convention ; fiche 11, page Ajout) : n'importe quel programme qui lit un JSON sur l'entrée
standard et rend une liste de noms sur la sortie standard. La source est écrite ÉTEINTE, puis passée au test local (qui lance le
programme dans un processus séparé, avec limite de temps) : s'il échoue, elle reste éteinte et ne peut pas être activée."""

from __future__ import annotations

import json
import re
from typing import Any

from pilote.adaptateurs import ErreurSource
from pilote.adaptateurs.programmes import DELAI_DEFAUT_S, DELAI_MAX_S, lire_sortie
from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, yaml_texte
from pilote.sources import Declaration, charger_sources
from pilote.tests_source import tester


def _identifiant(nom: str) -> str:
    from pilote.presets import slug

    return slug(nom)


def enregistrer(cfg: Config, spec: dict[str, Any]) -> tuple[Declaration, dict[str, Any]]:
    """Écrit la déclaration (jamais par-dessus une source existante) puis lance le test local. Rend la source et le résultat du test."""
    nom = str(spec.get("nom", "")).strip()
    ident = _identifiant(nom)
    if not ident or not re.match(r"^[a-z0-9][a-z0-9-]*$", ident):
        raise ConfigRefusee("Donnez un nom au programme (lettres ou chiffres).")
    commande = [str(c) for c in spec.get("commande") or [] if str(c).strip()]
    if not commande:
        raise ConfigRefusee("Indiquez la commande qui lance le programme (par exemple python3 mon_script.py).")
    delai = float(spec.get("delai_s") or DELAI_DEFAUT_S)
    if not 0 < delai <= DELAI_MAX_S:
        raise ConfigRefusee(f"La limite de temps doit être comprise entre 0 et {DELAI_MAX_S:g} secondes.")
    exemple = spec.get("exemple")
    if exemple is not None:
        try:
            lire_sortie(exemple if isinstance(exemple, str) else json.dumps(exemple))
        except ErreurSource as exc:
            raise ConfigRefusee(f"L'exemple de sortie est refusé : {exc}") from exc
    f = cfg.dossier_sources / f"{ident}.yaml"
    if f.exists() or ident in charger_sources(cfg)[0]:
        raise ConfigRefusee(f"Une source s'appelle déjà « {nom} » : choisissez un autre nom.")
    exemple_texte = exemple if isinstance(exemple, str) else json.dumps(exemple or [{"nom": "Exemple", "origine": "programme local"}], ensure_ascii=False)
    decl = {
        "id": ident, "nom": nom, "description": str(spec.get("description") or f"Programme local : {nom}."), "trouve": str(spec.get("trouve") or "noms rendus par un programme local"),
        "genres": list(spec.get("genres") or ["club"]), "pays": list(spec.get("pays") or ["monde"]), "consomme": ["sujet", "mots_cles", "lieu"], "produit": ["nom", "origine"],
        "usages": list(spec.get("usages") or ["personnalise"]), "main": spec.get("main") or "seconde", "origine": spec.get("origine") or "texte", "famille": "python",
        "roles": ["chercher"], "cle": "", "cout": {"unite": "appel", "vers_dollar": 0, "par_appel": 1, "gratuit_par_mois": 0},
        "confiance": float(spec.get("confiance", 0.3)), "defaut": {"chercher": False, "verifier": False}, "mode": {"en_ligne": False, "local": True},
        "exemple_reponse": f"exemples/{ident}.json", "moteur": {"script": {"commande": commande, "delai_s": delai}}, "note": "Ajouté par l'utilisateur (programme local).",
    }  # fmt: skip
    from pilote.sources import valider_declaration

    valider_declaration(decl, cfg, f"{ident}.yaml")  # refus clair avant d'écrire quoi que ce soit
    ecrire_atomique(cfg.dossier_sources / "exemples" / f"{ident}.json", exemple_texte)
    ecrire_atomique(f, yaml_texte(decl, "# Programme local ajouté par l'utilisateur. Éteint tant que son test local n'a pas passé.\n"))
    d = charger_sources(cfg)[0][ident]
    return d, tester(cfg, d)
