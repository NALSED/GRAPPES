"""Préparer la copie de configuration de grappes d'UNE recherche à partir des sources que l'utilisateur a choisies (fiche 01 et 12).

Chaque source déclare son `moteur` : soit une prise qui existe déjà dans la configuration de grappes, soit une définition écrite dans la
déclaration (même format que les prises de grappes). La copie ne reçoit que les sources utilisées et seulement les clés de ces sources.
La vraie configuration de grappes n'est jamais modifiée."""

from __future__ import annotations

import os
import re
import stat
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pilote import budget, cles, disjoncteur, flux_rss
from pilote import reglages as rg
from pilote.config import Config
from pilote.refus import ConfigRefusee, lire_yaml
from pilote.sources import Declaration, charger_sources


def choisies(cfg: Config, params: dict[str, Any]) -> list[Declaration]:
    """Les sources utilisées : celles du paramètre `sources` de la recherche s'il existe, sinon les cases « chercher » de Réglages.
    Une source qui demande une clé absente est laissée de côté."""
    decls, _ = charger_sources(cfg)
    reg, _ = rg.charger_tolerant(cfg)
    voulues = params.get("sources")
    if voulues is None:
        voulues = [d.id for d in decls.values() if rg.choix_source(reg, d)["chercher"]]
        coches = params.get("presets")  # presets cochés sur la page Recherches : ils RESTREIGNENT les sources allumées dans Réglages, jamais ne les élargissent
        if coches:
            from pilote import presets

            dans = {s for p in coches for s in presets.sources_de(cfg, decls, str(p))}
            voulues = [s for s in voulues if s in dans]
    return [decls[s] for s in voulues if s in decls and "chercher" in decls[s].roles and (not decls[s].cles or cles.toutes_presentes(cfg, decls[s].cles))]


def verificatrices(cfg: Config, params: dict[str, Any]) -> list[Declaration]:
    """Les sources qui VÉRIFIENT les candidats trouvés : rôle « vérifier », case cochée dans Réglages, adaptateur de pilote qui
    déclare `verifie_sur: site` (l'adresse du candidat) ou `nom` (son nom). Elles ne cherchent pas : elles ne sont jamais dans
    `choisies`, et une source dont la clé manque est laissée de côté.

    Deux conditions de Réglages : la vérification doit être active, et une source qui ne sait QUE vérifier n'est appelée qu'en
    mode « plus » (« ajouter des sources de vérification seules »). En mode « memes », la vérification reste le recoupement
    entre les sources de recherche, comme le dit le réglage."""
    reg, _ = rg.charger_tolerant(cfg)
    actif = params.get("verification")
    if not (reg["verification"]["active"] if actif is None else actif):
        return []
    mode = str((reg.get("verification") or {}).get("mode") or "memes")
    decls, _ = charger_sources(cfg)
    out = []
    for d in decls.values():
        if "verifier" not in d.roles or "adaptateur" not in d.moteur or d.verifie_sur not in ("site", "nom"):
            continue
        if not rg.choix_source(reg, d)["verifier"] or (d.cles and not cles.toutes_presentes(cfg, d.cles)):
            continue
        if "chercher" not in d.roles and mode != "plus":  # source de vérification SEULE : réservée au mode « plus »
            continue
        out.append(d)
    return out


def definition_flux(flux: dict[str, str]) -> dict[str, Any]:
    """Prise de grappes d'un flux RSS ou Atom : chaque article est ingéré tel quel (titre + résumé) au nom du journal ; aucune page n'est récupérée."""
    hote = (urllib.parse.urlsplit(flux["url"]).hostname or "flux").removeprefix("www.")
    atom = flux.get("format") == "atom"
    return {
        "id": flux["id"], "type": "http", "public": True, "url": flux["url"], "method": "GET", "respecter_robots": True, "sans_mots_cles": True, "limite_resultats": 50,
        "headers": {"User-Agent": "grappes-collecte/1 (collecte automatique ; respecte robots.txt)", "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8"},
        "response": {"format": "xml", "items": "feed.entry" if atom else "rss.channel.item"},
        "fields": {"title": "title", "url": "link.@href" if atom else "link", "description": "summary" if atom else "description", "date": "updated" if atom else "pubDate", "id": "id" if atom else "guid"},
        "observation": {"ecosysteme": "rss", "source": {"default": hote}, "nom": {"default": flux["nom"]}},
        "quota": 2, "raison": f"article du flux {flux['nom']}",
    }  # fmt: skip


def _ecrire_yaml(f: Path, d: dict[str, Any]) -> None:
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")


@dataclass(slots=True)
class Materialise:
    ids: list[str] = field(default_factory=list)  # sources utilisées
    adaptateurs: list[dict[str, Any]] = field(default_factory=list)  # {source, module, parametres} : exécutés par le pont
    scripts: list[dict[str, Any]] = field(default_factory=list)  # {source, commande, delai_s} : programmes locaux
    registres: list[str] = field(default_factory=list)  # registres de découverte de grappes à interroger (wikidata, sirene, yaml)
    jetons: dict[str, str] = field(default_factory=dict)  # étiquette de registre de grappes -> identifiant de source
    origines: dict[str, str] = field(default_factory=dict)  # identifiant de source -> classe d'origine
    mains: dict[str, str] = field(default_factory=dict)  # identifiant de source -> première / seconde main
    exclues_budget: list[dict[str, str]] = field(default_factory=list)  # sources payantes écartées par le plafond de dépense
    couts: dict[str, dict[str, Any]] = field(default_factory=dict)  # source -> coût effectif (pour compter la dépense)
    verificateurs: list[dict[str, Any]] = field(default_factory=list)  # {source, module, parametres, cles_noms} : sources « vérifier » appelées sur chaque candidat qui a un site
    en_pause: list[dict[str, str]] = field(default_factory=list)  # sources mises en pause par le disjoncteur (fiche 11) : écartées sans être appelées


def materialiser(cfg: Config, cible: Path, params: dict[str, Any]) -> Materialise:
    """Écrit dans `cible` (copie de config/ de grappes) les prises à utiliser ; rend ce que le pont devra exécuter en plus."""
    utilisees = choisies(cfg, params)
    verif = verificatrices(cfg, params)
    pauses = disjoncteur.en_pause(cfg, [d.id for d in (*utilisees, *verif)])
    en_pause = [{"source": d.id, "nom": d.nom, "raison": str(pauses[d.id].get("raison", "plusieurs erreurs de suite"))} for d in (*utilisees, *verif) if d.id in pauses]
    utilisees = [d for d in utilisees if d.id not in pauses]
    verif = [d for d in verif if d.id not in pauses]
    reg, _ = rg.charger_tolerant(cfg)
    exclues: list[dict[str, str]] = []
    b = params.get("_budget")
    if b is not None:  # plafond de dépense : une source payante dont le coût maximal dépasse ce qui reste est écartée
        # les sources de vérification comptent dans le même plafond : elles sont appelées une fois par candidat, donc elles
        # peuvent coûter autant qu'une source de recherche. Sans ce passage, une vérificatrice payante dépensait sans plafond.
        efficaces = [(d, rg.choix_source(reg, d)["cout"]) for d in (*utilisees, *verif)]
        ok, exclues = budget.autoriser(efficaces, int(b["appels_max"]), float(b["plafond"]), float(b["depense"]), b.get("unites") or {})
        gardes = {d.id for d in ok}
        utilisees = [d for d in utilisees if d.id in gardes]
        verif = [d for d in verif if d.id in gardes]
    res = Materialise(ids=[d.id for d in utilisees], origines={d.id: d.origine for d in utilisees}, mains={d.id: d.main for d in utilisees},
                      exclues_budget=exclues, couts={d.id: rg.choix_source(reg, d)["cout"] for d in utilisees}, en_pause=en_pause)
    dossier = cible / "recherche"
    dossier.mkdir(exist_ok=True)
    par_id: dict[str, Path] = {}
    for f in sorted(dossier.glob("*.yaml")):
        try:
            par_id[str(lire_yaml(f).get("id", ""))] = f
        except ConfigRefusee:
            continue
    actifs: list[str] = []
    registres_voulus: set[str] = set()
    for d in utilisees:
        m = d.moteur
        if "prise" in m:
            f = par_id.get(m["prise"])
            if f is None:
                continue
            definition = lire_yaml(f)
            pid = str(definition["id"])
        elif "registre_grappes" in m:
            nom_reg = str(m["registre_grappes"])
            if nom_reg not in res.registres:
                res.registres.append(nom_reg)
            for jeton in ({"sirene": ["sirene_naf", "sirene_nom"]}.get(nom_reg, [nom_reg])):
                res.jetons[jeton] = d.id
            continue
        elif "adaptateur" in m:
            donnes = {**(m.get("parametres") or {}), **rg.parametres_donnes(reg, d.id)}
            donnes["_dossier_config"] = str(cfg.dossier_config)  # où l'adaptateur retrouve les catalogues de données (types de lieu...)
            res.adaptateurs.append({"source": d.id, "module": str(m["adaptateur"]), "parametres": donnes, "cles_noms": d.cles})
            res.jetons[d.id] = d.id
            continue
        elif "flux_rss" in m:  # la liste de flux de l'utilisateur : une prise de grappes par flux
            flux_rss.resoudre_formats(cfg)  # un flux importé d'un OPML n'a jamais été lu : son format (RSS ou Atom) est détecté ici, une fois
            for flux in flux_rss.charger(cfg):
                pid = flux["id"]
                definition = definition_flux(flux)
                _ecrire_yaml(dossier / f"{pid}.yaml", definition)
                par_id[pid] = dossier / f"{pid}.yaml"
                actifs.append(pid)
                res.jetons[pid] = d.id
            continue
        elif "script" in m:
            res.scripts.append({"source": d.id, **m["script"]})
            res.jetons[d.id] = d.id
            continue
        elif "definition" in m:
            definition = dict(m["definition"])
            pid = str(definition.get("id", d.id))
            f = dossier / f"{pid}.yaml"
            definition["id"] = pid
            _ecrire_yaml(f, definition)
            par_id[pid] = f
        else:
            continue
        if definition.get("type") == "registre":
            registres_voulus.add(pid)
            res.jetons[pid] = d.id
        else:
            actifs.append(pid)
            res.jetons[pid] = d.id
    for pid, f in par_id.items():  # les prises de découverte (type registre) non choisies sont éteintes dans la copie
        definition = lire_yaml(f)
        if definition.get("type") == "registre":
            definition["actif"] = pid in registres_voulus
            _ecrire_yaml(f, definition)
    rf = cible / "recherche.yaml"
    texte = rf.read_text(encoding="utf-8") if rf.exists() else "actifs: []\n"
    if re.search(r"^actifs:", texte, re.MULTILINE):
        texte = re.sub(r"^actifs:\s*\[[^\]]*\]", "actifs: [" + ", ".join(actifs) + "]", texte, flags=re.MULTILINE)
    else:
        texte += "\nactifs: [" + ", ".join(actifs) + "]\n"
    rf.write_text(texte, encoding="utf-8")
    for d in verif:
        donnes = {**(d.moteur.get("parametres") or {}), **rg.parametres_donnes(reg, d.id)}
        res.verificateurs.append({"source": d.id, "verifie_sur": d.verifie_sur, "module": str(d.moteur["adaptateur"]), "parametres": donnes, "cles_noms": d.cles})
        res.jetons[d.id] = d.id
        res.origines[d.id], res.mains[d.id] = d.origine, d.main
        res.couts[d.id] = rg.choix_source(reg, d)["cout"]
    # clés : seulement celles des sources utilisées, dans un fichier à droits restreints
    lignes = sorted({f"{n}={(d.cle_prefixe if n == d.cle else '')}{cles.valeur(cfg, n)}" for d in [*utilisees, *verif] for n in d.cles if cles.presente(cfg, n)})
    sec = cible / "secrets.env"
    sec.write_text("\n".join(lignes) + ("\n" if lignes else ""), encoding="utf-8")
    os.chmod(sec, stat.S_IRUSR | stat.S_IWUSR)
    if registres_voulus or res.adaptateurs or res.scripts:
        res.registres.append("yaml")  # prises de découverte de config/recherche/ et noms rendus par les adaptateurs et programmes
    return res
