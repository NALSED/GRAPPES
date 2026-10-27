"""Sortie (fiche 14) : écrire le résultat d'une recherche dans le format voulu, vers la destination voulue.

* AUCUNE liste de formats ici : chaque format est un petit module qui se déclare (`pilote/formats/` ou `formats_perso/`) et sait écrire.
* Une sortie se REJOUE : tout vient de la base de pilote (les noms, les décisions), jamais d'une source. Changer le format ou le filtre et
  réexporter ne coûte aucune requête.
* Par défaut seuls les noms GARDÉS sortent ; on peut tout sortir ou choisir quelles décisions.
* Chaque sortie porte sa trace (date, sujet, sources, filtre) : dans le fichier quand le format le permet, à côté sinon.
* Le dossier est choisi par l'utilisateur (Réglages, ou pour cette recherche) ; sinon celui de la recherche."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote import classements as cl
from pilote import formats, mentions, tri
from pilote import reglages as rg
from pilote.base import Candidat, Decision, Journal
from pilote.config import Config
from pilote.formats._commun import suffixe

DECISIONS_VALIDES = ("garder", "plus_tard", "rejeter", "aucune")
FILTRES_NOMMES = {"gardes": ["garder"], "tout": list(DECISIONS_VALIDES)}
LIBELLES_FILTRE = {"garder": "gardés", "plus_tard": "mis de côté", "rejeter": "rejetés", "aucune": "pas encore décidés"}


class SortieInvalide(ValueError):
    pass


def lire_filtre(filtre: str | list[str] | None) -> list[str]:
    if filtre is None:
        return list(FILTRES_NOMMES["gardes"])
    if isinstance(filtre, str):
        if filtre in FILTRES_NOMMES:
            return list(FILTRES_NOMMES[filtre])
        filtre = [x for x in filtre.split(",") if x]
    mauvais = [x for x in filtre if x not in DECISIONS_VALIDES]
    if mauvais or not filtre:
        raise SortieInvalide("Le filtre dit quelles décisions sortent : gardés, tout, ou une liste parmi " + ", ".join(DECISIONS_VALIDES) + ".")
    return list(dict.fromkeys(filtre))


def phrase_filtre(decisions: list[str]) -> str:
    if set(decisions) == set(DECISIONS_VALIDES):
        return "tous les noms, décidés ou non"
    return "noms " + ", ".join(LIBELLES_FILTRE[d] for d in decisions)


def reglages_sortie(cfg: Config, parametres: dict[str, Any] | None = None) -> dict[str, Any]:
    """Les choix de sortie EFFECTIFS : ceux de la recherche s'ils existent, sinon ceux de Réglages."""
    reg, _ = rg.charger_tolerant(cfg)
    so = {**(reg.get("sortie") or {})}
    chez_elle = (parametres or {}).get("sortie") or {}
    return {
        "actifs": list(chez_elle.get("actifs") or so.get("actifs") or ["csv"]),
        "contenus": {**(so.get("contenus") or {}), **(chez_elle.get("contenus") or {})},
        "dossier": str(chez_elle.get("dossier") or so.get("dossier") or ""),
        "webhook_url": str(chez_elle.get("webhook_url") or so.get("webhook_url") or ""),
    }


def dossier_de_sortie(cfg: Config, rid: str, choix: str = "") -> Path:
    """Le dossier choisi par l'utilisateur (absolu, ou relatif au dossier de données), sinon `export/` dans le dossier de la recherche."""
    if not choix.strip():
        return cfg.dossier_recherche(rid) / "export"
    p = Path(choix.strip()).expanduser()
    return p if p.is_absolute() else cfg.donnees / p


def jeu_de_donnees(cfg: Config, fabrique: sessionmaker[Session], rid: str, decisions: list[str]) -> dict[str, Any]:
    """Les noms de la recherche (filtrés par décision) avec tout ce que la base sait d'eux, et la trace. Ne lit QUE la base de pilote."""
    nom_source = tri.noms_de_sources(cfg)
    with fabrique() as s:
        r = tri._recherche(s, rid)
        lignes = tri.lignes_de(s, rid)
        cands = {c.id: c for c in s.scalars(select(Candidat).where(Candidat.recherche_id == rid))}
        quoi = (r.sujet or {}).get("quoi", "")
        sujet = " ".join(x for x in (quoi, ", ".join(map(str, (r.sujet or {}).get("inclure") or [])), (r.sujet or {}).get("lieu", ""), (r.sujet or {}).get("pays", "")) if x).strip()
        cree = r.cree_le
    rows = []
    for l in lignes:
        d = l.decision or "aucune"
        if d not in decisions:
            continue
        c = cands[l.id]
        faits = c.faits or {}
        rows.append({
            "id": l.id, "nom": l.nom, "ville": l.ville, "pays": l.pays, "origine": l.origine, "origine_phrase": cl.ORIGINE_LIBELLE.get(l.origine, l.origine),
            "confirmations": min(max(l.endroits, 1), 3), "endroits": l.endroits, "fonction": l.fonction, "genre": l.genre_de_chose, "site": l.site,
            "numero_officiel": l.numero_officiel, "decision": l.decision, "motif_rejet": l.motif if l.decision == "rejeter" else "",
            "sources": [nom_source(t) for t in sorted(set(l.trouve_par))], "relations": [x for x in (c.relations or []) if isinstance(x, dict)],
            "coordonnees": faits.get("coordonnees") if isinstance(faits.get("coordonnees"), dict) else None,
            # Règle 8 : le constat de la collecte et la levée éventuelle, pour les formats qui ont à les distinguer (voir `formats/ftm.py`)
            "regle8_personne": bool(faits.get("regle8_personne")), "regle8_leve": bool(faits.get("regle8_leve")),
        })  # fmt: skip
    ids = mentions.sources_de_la_recherche(cfg.dossier_recherche(rid)) or sorted({t for l in lignes for t in l.trouve_par})
    trace = {
        "date": datetime.now().astimezone().isoformat(timespec="seconds"), "sujet": sujet or quoi, "recherche": rid, "recherche_lancee_le": cree.isoformat(timespec="seconds") if cree else "",
        "sources": [{"id": i, "nom": nom_source(i)} for i in ids], "filtre": phrase_filtre(decisions), "nombre": len(rows),
    }  # fmt: skip
    return {"lignes": rows, "trace": trace}


def demandes_par_defaut(cfg: Config, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    """Les formats voulus sans qu'on les ait précisés : ceux de Réglages (ou de la recherche), chacun avec ses contenus."""
    so = reglages_sortie(cfg, parametres)
    out = []
    for fid in so["actifs"]:
        d: dict[str, Any] = {"format": fid}
        if fid in so["contenus"]:
            d["contenus"] = so["contenus"][fid]
        out.append(d)
    return out


def exporter(cfg: Config, fabrique: sessionmaker[Session], rid: str, qui: str, demandes: list[dict[str, Any]] | None = None, filtre: str | list[str] | None = None,
             dossier: str = "", base: str = "resultat") -> dict[str, Any]:  # fmt: skip
    """Écrit la sortie. Rend les fichiers, les envois, et les erreurs par format (un format qui échoue n'empêche pas les autres)."""
    decisions = lire_filtre(filtre)
    with fabrique() as s:
        r = tri._recherche(s, rid)
        parametres = dict(r.parametres or {})
    so = reglages_sortie(cfg, parametres)
    connus = formats.decouvrir(cfg)
    demandes = demandes if demandes else demandes_par_defaut(cfg, parametres)
    for d in demandes:
        if d.get("format") not in connus:
            raise SortieInvalide(f"Le format « {d.get('format')} » n'existe pas.")
        mauvais = [c for c in (d.get("contenus") or []) if c not in connus[d["format"]]["contenus"]]
        if mauvais:
            raise SortieInvalide(f"Le format « {connus[d['format']]['nom']} » n'a pas de contenu « {mauvais[0]} » (contenus possibles : {', '.join(connus[d['format']]['contenus'])}).")
    dest = dossier_de_sortie(cfg, rid, dossier or so["dossier"])
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SortieInvalide(f"Le dossier de sortie « {dest} » ne peut pas être créé ({exc.strerror or 'refusé'}).") from exc
    jeu = jeu_de_donnees(cfg, fabrique, rid, decisions)
    fichiers: list[str] = []
    envois: list[dict[str, Any]] = []
    erreurs: list[dict[str, str]] = []
    for d in demandes:
        fmt = connus[d["format"]]
        options = {**(d.get("options") or {})}
        if fmt["famille"] == "outil" and "url" in fmt["besoin"]:
            options.setdefault("url", so["webhook_url"])
        for contenu in d.get("contenus") or fmt["contenus_defaut"]:
            chemin = dest / f"{base}{suffixe(contenu, fmt['contenus'], fmt['contenus_defaut'])}{fmt['extension']}"
            try:
                res = fmt["module"].ecrire(jeu, contenu, options, chemin)
            except Exception as exc:  # noqa: BLE001 - un format qui échoue (réseau, disque, bibliothèque) n'empêche pas les autres
                erreurs.append({"format": fmt["nom"], "raison": str(exc) or type(exc).__name__})
                continue
            fichiers += [Path(p).name for p in res.get("fichiers", [])]
            if res.get("envoye"):
                envois.append({"format": fmt["nom"], **res["envoye"]})
    extra = _decisions_et_mentions(cfg, fabrique, rid, dest)
    fichiers += extra
    with fabrique.begin() as s:
        s.add(Journal(recherche_id=rid, qui=qui, evenement="export", detail={"formats": [d["format"] for d in demandes], "fichiers": fichiers, "filtre": jeu["trace"]["filtre"], "nombre": jeu["trace"]["nombre"],
                                                                              "envois": len(envois), "erreurs": len(erreurs)}))  # fmt: skip
    return {"dossier": str(dest), "gardes": len([r for r in jeu["lignes"] if r["decision"] == "garder"]), "exportes": jeu["trace"]["nombre"], "decisions": _nb_decisions(fabrique, rid),
            "fichiers": fichiers, "envois": envois, "erreurs": erreurs, "trace": jeu["trace"], "sujet": jeu["trace"]["sujet"]}  # fmt: skip


def _nb_decisions(fabrique: sessionmaker[Session], rid: str) -> int:
    with fabrique() as s:
        return len({d.candidat_id for d in s.scalars(select(Decision).where(Decision.recherche_id == rid, Decision.annulee.is_(False)))})


def _decisions_et_mentions(cfg: Config, fabrique: sessionmaker[Session], rid: str, dest: Path) -> list[str]:
    """`decisions.csv` (ce que VOUS avez décidé, nom par nom) et la mention obligatoire des sources qui l'exigent : ils accompagnent toute sortie."""
    out = []
    with fabrique() as s:
        lignes = tri.lignes_de(s, rid)
        decs = {d.candidat_id: d for d in s.scalars(select(Decision).where(Decision.recherche_id == rid, Decision.annulee.is_(False)).order_by(Decision.id))}
    with (dest / "decisions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(["nom", "ville", "pays", "numero_officiel", "site", "d_ou_il_vient", "decision", "decide_par", "decide_le", "motif_rejet"])
        for l in lignes:
            d = decs.get(l.id)
            if d is None:
                continue
            w.writerow([tri._cellule(x) for x in (l.nom, l.ville, l.pays, l.numero_officiel, l.site, cl.ORIGINE_LIBELLE.get(l.origine, ""),
                                                  {"garder": "gardé", "rejeter": "rejeté", "plus_tard": "mis de côté"}[d.valeur], d.qui, d.le.isoformat(timespec="seconds"),
                                                  l.motif if d.valeur == "rejeter" else "")])  # fmt: skip
    out.append("decisions.csv")
    m = mentions.ecrire(cfg, cfg.dossier_recherche(rid), dest)
    if m:
        out.append(m.name)
    return out
