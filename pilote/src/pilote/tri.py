"""Page Tri : les noms d'une recherche, groupés par un classement, et les décisions de l'utilisateur (annulables).

Les décisions sont celles de l'UTILISATEUR, jamais du programme. Chaque action groupée est un « lot » : on l'annule d'un
coup. La décision d'un nom est la dernière non annulée ; annuler un lot fait réapparaître la précédente.
"""

from __future__ import annotations

import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote import classements as cl
from pilote import motifs, tri_filtres
from pilote.base import DECISIONS, Candidat, Decision, Journal, Recherche
from pilote.config import Config

SOURCES_ECOSYSTEMES = {"web": "Recherche web", "wikipedia": "Wikipédia", "rss": "Flux de presse", "texte": "Lecture d'articles"}


def _iso(d):
    return d.isoformat(timespec='seconds') if d else None


class Introuvable(KeyError):
    pass


def _recherche(s: Session, rid: str) -> Recherche:
    r = s.get(Recherche, rid)
    if r is None:
        raise Introuvable(rid)
    return r


def decisions_courantes(s: Session, rid: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for d in s.scalars(select(Decision).where(Decision.recherche_id == rid, Decision.annulee.is_(False)).order_by(Decision.id)):
        out[d.candidat_id] = d.valeur
    return out


def motifs_courants(s: Session, rid: str) -> dict[int, str]:
    """Le motif de la décision courante d'un nom rejeté (vide si la décision courante n'est pas un rejet motivé)."""
    out: dict[int, str] = {}
    for d in s.scalars(select(Decision).where(Decision.recherche_id == rid, Decision.annulee.is_(False)).order_by(Decision.id)):
        out[d.candidat_id] = (d.motif or "") if d.valeur == "rejeter" else ""
    return out


def noms_nouveaux(s: Session, rid: str, lignes: list[cl.Ligne]) -> set[str]:
    """Les noms de cette recherche qui ne figurent pas parmi ceux que vous avez GARDÉS dans les autres recherches. Un nom rejeté
    ailleurs peut donc réapparaître comme nouveau : c'est voulu (la comparaison se fait avec ce qui a été gardé)."""
    courantes: dict[int, str] = {}  # une seule lecture pour toutes les autres recherches (c'était une requête par recherche)
    for cid, valeur in s.execute(select(Decision.candidat_id, Decision.valeur).where(Decision.recherche_id != rid, Decision.annulee.is_(False)).order_by(Decision.id)):
        courantes[cid] = valeur  # dans l'ordre : la dernière décision non annulée gagne
    ids = [i for i, v in courantes.items() if v == "garder"]
    gardes: set[str] = set()
    for debut in range(0, len(ids), 500):  # par paquets : une liste d'identifiants sans fin ne tient pas dans une requête
        gardes |= {cl.normaliser(n) for (n,) in s.execute(select(Candidat.nom).where(Candidat.id.in_(ids[debut : debut + 500])))}
    return {cl.normaliser(l.nom) for l in lignes} - gardes


_CACHE_RESSEMBLANCES: dict[tuple, dict[int, str]] = {}
_CACHE_RAPPROCHEMENTS: dict[tuple, tuple[Any, Any]] = {}


def lignes_de(s: Session, rid: str) -> list[cl.Ligne]:
    dec = decisions_courantes(s, rid)
    mot = motifs_courants(s, rid)
    cands = list(s.scalars(select(Candidat).where(Candidat.recherche_id == rid).order_by(Candidat.id)))
    separes = {c.id for c in cands if (c.faits or {}).get("separe")}
    empreinte = hash(tuple((c.id, c.nom, c.numero_officiel, (c.faits or {}).get("fonction", "")) for c in cands))
    cle = (rid, len(cands), len(separes), empreinte)  # les noms d'une recherche ne changent plus une fois la recherche finie ; s'ils changeaient, l'empreinte le dirait
    if cle not in _CACHE_RESSEMBLANCES:
        if len(_CACHE_RESSEMBLANCES) > 16:
            _CACHE_RESSEMBLANCES.clear()
        _CACHE_RESSEMBLANCES[cle] = cl.ressemblances({c.id: c.nom for c in cands}, separes)
    prox = _CACHE_RESSEMBLANCES[cle]
    from pilote import rapprochement as rp

    if cle not in _CACHE_RAPPROCHEMENTS:  # les noms d'une recherche ne changent plus une fois la recherche finie : on ne recalcule pas à chaque clic
        if len(_CACHE_RAPPROCHEMENTS) > 16:
            _CACHE_RAPPROCHEMENTS.clear()
        registre = {c.id: c.nom for c in cands if c.genre_source == "registre"}
        _CACHE_RAPPROCHEMENTS[cle] = (
            rp.blocs([{"id": c.id, "nom": c.nom, "numero": c.numero_officiel, "fonction": (c.faits or {}).get("fonction", ""), "relations": c.relations or []} for c in cands]),
            rp.rapprocher({c.id: c.nom for c in cands if c.genre_source != "registre"}, registre),
        )
    bl, rapp = _CACHE_RAPPROCHEMENTS[cle]
    return [
        cl.Ligne(c.id, c.nom, c.genre_source or "web", c.nb_endroits or 1, list(c.trouve_par or []), c.genre_de_chose or "", c.ville or "",
                 c.pays or "", c.site or "", c.numero_officiel or "", dec.get(c.id), prox.get(c.id), c.faits or {},
                 (c.faits or {}).get("fonction", ""), bl.get(c.id, {}).get("bloc", ""), bl.get(c.id, {}).get("racine", ""), rapp.get(c.id, {}).get("phrase", ""), mot.get(c.id, ""))
        for c in cands
    ]  # fmt: skip


def noms_de_sources(cfg: Config):
    """token de source -> nom lisible (jamais un identifiant technique), d'après les déclarations des sources."""
    from pilote.sources import charger_sources

    decls, _ = charger_sources(cfg)
    par_id = {d.id: d.nom for d in decls.values()}
    fixes = {**SOURCES_ECOSYSTEMES, "sirene_naf": "Annuaire des entreprises", "sirene_nom": "Annuaire des entreprises", "wikidata": "Wikidata (encyclopédie)"}

    def nom(token: str) -> str:
        return fixes.get(token) or par_id.get(token) or token.replace("_", " ")

    return nom


def _filtrees(s: Session, rid: str, lignes: list[cl.Ligne], nom_source, filtres: list[str] | None, q: str, nouveaux: bool) -> list[cl.Ligne]:
    """Les lignes qui passent les filtres de la page (facettes, texte, nouveaux noms) : ce que l'écran montre ET ce que les actions groupées touchent."""
    nouveau = noms_nouveaux(s, rid, lignes) if nouveaux else None
    return tri_filtres.appliquer(lignes, tri_filtres.lire_filtres(filtres), q, nom_source, nouveau)


def tri_vue(cfg: Config, fabrique: sessionmaker[Session], rid: str, classement_id: str | None, filtres: list[str] | None = None, q: str = "", nouveaux: bool = False) -> dict[str, Any]:
    nom_source = noms_de_sources(cfg)
    cls = cl.lister(cfg)
    c = next((x for x in cls if x.id == classement_id), None) or next((x for x in cls if x.id == "solides"), None) or (cls[0] if cls else cl.Classement("tous", "Tous les noms", ["decision"]))
    with fabrique() as s:
        r = _recherche(s, rid)
        toutes = lignes_de(s, rid)
        nouveau = noms_nouveaux(s, rid, toutes) if nouveaux else None
        lignes = tri_filtres.appliquer(toutes, tri_filtres.lire_filtres(filtres), q, nom_source, nouveau)
        facettes = tri_filtres.facettes(toutes, tri_filtres.lire_filtres(filtres), q, nom_source, nouveau)
        pas_annulable = s.scalar(select(Decision.id).where(Decision.recherche_id == rid, Decision.annulee.is_(False)).limit(1)) is None
        verification = (r.parametres or {}).get("verification")
        bilans_verif = [b for b in ((r.avancement or {}).get("verifications") or []) if isinstance(b, dict)]
        quoi = (r.sujet or {}).get("quoi", "")
        mots = tri_filtres.mots_de(" ".join([quoi, *map(str, (r.sujet or {}).get("inclure") or []), q or ""]))
    paquets = cl.grouper(c, lignes, nom_source)
    par_origine = Counter(l.origine for l in lignes)
    cle_de = {l.id: p["cle"] for p in paquets for l in p["lignes"]}
    return {
        "recherche": {"id": rid, "quoi": quoi, "etat": r.etat, "verification": True if verification is None else bool(verification), "mots": mots,
                      "verifications": [{**b, "nom": nom_source(str(b.get("source", "")))} for b in bilans_verif]},
        "facettes": facettes, "filtres": sorted(f"{k}:{v}" for k, vs in tri_filtres.lire_filtres(filtres).items() for v in vs), "q": q or "", "nouveaux": bool(nouveaux),
        "total_tout": len(toutes), "motifs": motifs.lire(cfg), "sources_noms": {t: nom_source(t) for t in sorted({t for l in toutes for t in l.trouve_par})},
        "date": _iso(r.cree_le),
        "total": len(lignes), "a_decider": sum(1 for l in lignes if l.decision is None),
        "origines": [{"id": k, "libelle": v, "n": par_origine.get(k, 0)} for k, v in cl.ORIGINES],
        "classement": c.vue(), "classements": [x.vue() for x in cls],
        "faits": cl.FAITS, "ordres_paquets": cl.ORDRES_PAQUETS, "ordres_noms": cl.ORDRES_NOMS,
        "paquets": [
            {"cle": p["cle"], "phrase": p["phrase"], "n": len(p["lignes"]), "a_decider": sum(1 for l in p["lignes"] if l.decision is None),
             "composition": dict(Counter(l.origine for l in p["lignes"]))}
            for p in paquets
        ],
        "lignes": [
            {"id": l.id, "nom": l.nom, "o": l.origine, "e": l.endroits, "v": l.ville, "g": l.genre_de_chose, "s": bool(l.site),
             "n": bool(l.numero_officiel), "d": l.decision, "p": cle_de[l.id], "r": l.ressemble_a, "f": l.fonction, "b": l.bloc, "m": l.rapproche, "mo": l.motif,
             "t": sorted(l.trouve_par), "u": l.site, "nu": l.numero_officiel, "pa": l.pays}
            for p in paquets for l in p["lignes"]
        ],
        "peut_annuler": not pas_annulable,
    }  # fmt: skip


def _membres_du_paquet(cfg, s, rid, classement_id, cle, filtres=None, q="", nouveaux=False) -> list[int]:
    c = cl.trouver(cfg, classement_id)
    nom_source = noms_de_sources(cfg)
    lignes = _filtrees(s, rid, lignes_de(s, rid), nom_source, filtres, q, nouveaux)  # une action groupée ne touche QUE ce que l'écran montre
    for p in cl.grouper(c, lignes, nom_source):
        if p["cle"] == cle:
            return [l.id for l in p["lignes"]]
    raise Introuvable(cle)


def decider(cfg: Config, fabrique: sessionmaker[Session], rid: str, valeur: str, qui: str, ids: list[int] | None = None,
            paquet: dict[str, Any] | None = None, seulement_non_decides: bool = True, motif: str | None = None) -> dict[str, Any]:  # fmt: skip
    """Une décision (ou une action groupée sur un paquet entier) = un lot, annulable d'un coup."""
    if valeur not in DECISIONS:
        raise ValueError("Cette décision n'existe pas.")
    motif = (motif or "").strip()
    if motif and valeur != "rejeter":
        raise ValueError("Un motif ne va qu'avec un rejet.")
    if motif and motif not in {m["id"] for m in motifs.lire(cfg)}:
        raise ValueError("Ce motif de rejet n'existe pas.")
    lot = uuid.uuid4().hex[:16]
    with fabrique.begin() as s:
        _recherche(s, rid)
        if paquet:
            ids = _membres_du_paquet(cfg, s, rid, paquet["classement"], paquet["cle"], paquet.get("filtres"), paquet.get("q", ""), bool(paquet.get("nouveaux")))
        existants = {c.id for c in s.scalars(select(Candidat).where(Candidat.recherche_id == rid, Candidat.id.in_(ids or [])))}
        courantes = decisions_courantes(s, rid)
        touches = [i for i in (ids or []) if i in existants and (courantes.get(i) is None if (paquet and seulement_non_decides) else courantes.get(i) != valeur)]
        for i in touches:
            s.add(Decision(recherche_id=rid, candidat_id=i, valeur=valeur, qui=qui, lot=lot, motif=motif))
        if touches:
            s.add(Journal(recherche_id=rid, qui=qui, evenement="decision_groupee" if paquet else "decision", detail={"lot": lot, "valeur": valeur, "n": len(touches), **({"motif": motif} if motif else {})}))
    return {"lot": lot, "touches": touches}


def annuler(fabrique: sessionmaker[Session], rid: str, qui: str) -> dict[str, Any]:
    """Annule le dernier lot de décisions non annulé de cette recherche (celui de `qui`)."""
    with fabrique.begin() as s:
        _recherche(s, rid)
        dernier = s.scalar(select(Decision).where(Decision.recherche_id == rid, Decision.annulee.is_(False)).order_by(Decision.id.desc()).limit(1))
        if dernier is None:
            return {"lot": None, "touches": []}
        lot = s.scalars(select(Decision).where(Decision.recherche_id == rid, Decision.lot == dernier.lot, Decision.annulee.is_(False))).all()
        for d in lot:
            d.annulee = True
        s.add(Journal(recherche_id=rid, qui=qui, evenement="decision_annulee", detail={"lot": dernier.lot, "n": len(lot)}))
        return {"lot": dernier.lot, "touches": [d.candidat_id for d in lot]}


def separer(fabrique: sessionmaker[Session], rid: str, cid: int, qui: str) -> None:
    """« Ce n'est pas le même nom » : le nom ne sera plus signalé comme ressemblant."""
    with fabrique.begin() as s:
        c = s.get(Candidat, cid)
        if c is None or c.recherche_id != rid:
            raise Introuvable(cid)
        c.faits = {**(c.faits or {}), "separe": True}
        s.add(Journal(recherche_id=rid, qui=qui, evenement="noms_separes", detail={"candidat": cid}))


def fiche(cfg: Config, fabrique: sessionmaker[Session], rid: str, cid: int) -> dict[str, Any]:
    nom_source = noms_de_sources(cfg)
    with fabrique() as s:
        r = _recherche(s, rid)
        c = s.get(Candidat, cid)
        if c is None or c.recherche_id != rid:
            raise Introuvable(cid)
        ligne = next((l for l in lignes_de(s, rid) if l.id == cid), None)
        if ligne is None:
            raise Introuvable(cid)
    from pilote import reglages as rg
    from pilote.sources import charger_sources

    decls, _ = charger_sources(cfg)
    reg, _ = rg.charger_tolerant(cfg)
    sources = [{"id": t if t in decls else "", "nom": nom_source(t), "detail": "", "confiance": rg.choix_source(reg, decls[t])["confiance"] if t in decls else None}
               for t in sorted(set(c.trouve_par or []))]  # la confiance s'ajuste d'ici, sans passer par Réglages
    for ref in (c.faits or {}).get("sources", []):
        eco, _, ident = ref.partition(":")
        detail = f"article « {ident.split('/', 1)[-1]} »" if eco == "wikipedia" else ident
        sources.append({"nom": SOURCES_ECOSYSTEMES.get(eco, eco), "detail": detail})
    verifications = [{"nom": nom_source(v.get("source", "")), "origine": str(v.get("origine", "")), "preuve": str(v.get("preuve", "")), "signal": str(v.get("signal") or "confirmation")}
                     for v in (c.faits or {}).get("verifications", []) if isinstance(v, dict)]  # ce que les sources « vérifier » ont rendu (ex. capture Wayback)
    enrichissements = [{"nom": nom_source(v.get("source", "")), "origine": str(v.get("origine", "")), "champs": v.get("champs") or {}}
                       for v in (c.faits or {}).get("enrichissements", []) if isinstance(v, dict)]  # ce que les sources « enrichir » ont AJOUTÉ à côté de la fiche, sans l'écraser
    return {
        "id": c.id, "nom": c.nom, "verifications": verifications, "enrichissements": enrichissements, "origine": c.genre_source, "origine_phrase": cl.ORIGINE_LIBELLE.get(c.genre_source, ""), "endroits": c.nb_endroits,
        "ville": c.ville, "pays": c.pays, "site": c.site, "numero_officiel": c.numero_officiel, "genre_de_chose": c.genre_de_chose,
        "decision": ligne.decision, "ressemble_a": ligne.ressemble_a, "sources": sources, "fonction": ligne.fonction, "bloc": ligne.racine,
        "relations": c.relations or [], "rapprochement": ligne.rapproche,
        "verification": True if (r.parametres or {}).get("verification") is None else bool((r.parametres or {}).get("verification")),
    }  # fmt: skip


def exporter(cfg: Config, fabrique: sessionmaker[Session], rid: str, qui: str, demandes: list[dict[str, Any]] | None = None, filtre: Any = None, dossier: str = "") -> dict[str, Any]:
    """Voir `pilote.sortie` : les formats se déclarent eux-mêmes, la sortie se rejoue sans rien appeler, seuls les noms gardés sortent par défaut."""
    from pilote import sortie

    try:
        return sortie.exporter(cfg, fabrique, rid, qui, demandes, filtre, dossier)
    except sortie.SortieInvalide as exc:
        raise ValueError(str(exc)) from exc


def _cellule(t: str) -> str:
    """Neutralise l'injection de formule tableur (même règle que les sorties de grappes)."""
    t = str(t).replace("\n", " ")
    return "'" + t if t[:1] in ("=", "+", "-", "@", "\t", "\r") else t


def dossier_export(cfg: Config, rid: str) -> Path:
    return cfg.dossier_recherche(rid) / "export"


def rejets(cfg: Config, fabrique: sessionmaker[Session], rid: str) -> dict[str, Any]:
    """D'où vient le bruit : pour chaque source, combien de ses noms ont été rejetés, et pour quel motif. Un nom trouvé par plusieurs sources
    est compté pour chacune (c'est ce qui dit quelle source corriger)."""
    nom_source = noms_de_sources(cfg)
    with fabrique() as s:
        _recherche(s, rid)
        lignes = lignes_de(s, rid)
    libelles = {m["id"]: m["libelle"] for m in motifs.lire(cfg)}
    par: dict[str, dict[str, Any]] = {}
    for l in lignes:
        for t in set(l.trouve_par):
            e = par.setdefault(t, {"source": t, "nom": nom_source(t), "total": 0, "rejetes": 0, "motifs": {}})
            e["total"] += 1
            if l.decision == "rejeter":
                e["rejetes"] += 1
                m = l.motif or "sans_motif"
                e["motifs"][m] = e["motifs"].get(m, 0) + 1
    out = sorted(par.values(), key=lambda e: (-e["rejetes"], -e["total"], e["nom"]))
    for e in out:
        e["part"] = round(e["rejetes"] / e["total"], 3) if e["total"] else 0.0
    return {"sources": out, "motifs": {**libelles, "sans_motif": "Sans motif"}, "total_rejetes": sum(1 for l in lignes if l.decision == "rejeter")}
