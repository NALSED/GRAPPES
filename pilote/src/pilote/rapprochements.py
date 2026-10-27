"""L'onglet Tri (spécification 16) : la file des rapprochements que Splink propose et qu'une PERSONNE tranche.

Patron d'Aleph et de Splink (15 § 1) : rappel large, score, validation humaine. Ici :
 * `proposer` compare les noms (Candidat) d'une recherche terminée et range en file les paires dont la confiance atteint `SEUIL` ; la confiance est le
   score de Splink (`rapprochement_splink`), jamais une saisie ;
 * `file` rend les cartes, du moins certain au plus certain, avec la comparaison champ par champ calculée ici (accord / désaccord / absence) ;
 * `trancher` enregistre la décision. CONFIRMER écrit un lien « même entité » des deux côtés (`Candidat.relations`) ; SÉPARER n'écrit rien, il empêche
   seulement de reproposer la paire. Ni l'un ni l'autre n'efface une fiche, une source ou un fichier, et les deux se refont.

Règle 8 : une fiche de genre « personne » n'entre jamais dans un rapprochement, et seuls nom d'entité, ville, numéro officiel et site servent de clé."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote import suite, tri
from pilote.base import Candidat, Journal, Rapprochement
from pilote.config import Config

SEUIL = 0.2  # en dessous, la paire n'est pas proposée : trop incertaine pour mériter l'attention d'une personne
DELAI_S = 120
SRC = Path(__file__).resolve().parents[1]
ETATS_DE_COMPARAISON = ("accord", "desaccord", "absence")
GENRES = {"association": "d'association", "entreprise": "d'entreprise", "club": "de club", "administration": "d'administration", "lieu": "de lieu", "evenement": "d'événement"}


class Indisponible(RuntimeError):
    """Le moteur de rapprochement n'a pas pu tourner : la raison est donnée en français, jamais avalée."""


def _fiche(c: Candidat) -> dict[str, Any]:
    return {"id": c.id, "nom": c.nom, "ville": c.ville or "", "numero": c.numero_officiel or "", "site": c.site or "", "alias": list((c.faits or {}).get("alias") or [])}


def _scorer(fiches: list[dict[str, Any]], seuil: float) -> list[dict[str, Any]]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    try:
        p = subprocess.run([sys.executable, "-m", "pilote.rapprochement_splink"], input=json.dumps({"fiches": fiches, "seuil": seuil}), capture_output=True, text=True, timeout=DELAI_S, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Indisponible(f"Le moteur de rapprochement a dépassé {DELAI_S} secondes.") from exc
    if p.returncode != 0:
        derniere = (p.stderr.strip().splitlines() or ["il s'est arrêté sans message"])[-1][:200]
        raise Indisponible(f"Le moteur de rapprochement (Splink) n'a pas pu tourner : {derniere}")
    try:
        return json.loads(p.stdout)
    except ValueError as exc:
        raise Indisponible("Le moteur de rapprochement a rendu une réponse illisible.") from exc


def _deja_liees(cands: list[Candidat]) -> set[tuple[int, int]]:
    """Deux noms que les sources ont elles-mêmes liés (siège et établissement, maison mère) sont des entités DIFFÉRENTES : on ne les propose pas."""
    from pilote.rapprochement import nom_nu

    par_nom: dict[str, list[int]] = {}
    for c in cands:
        par_nom.setdefault(nom_nu(c.nom), []).append(c.id)
    out: set[tuple[int, int]] = set()
    for c in cands:
        for r in c.relations or []:
            if not isinstance(r, dict) or r.get("type") == "meme_entite":
                continue
            for j in par_nom.get(nom_nu(str(r.get("vers", ""))), []):
                if j != c.id:
                    out.add((min(c.id, j), max(c.id, j)))
    return out


def proposer(cfg: Config, fabrique: sessionmaker[Session], rid: str) -> dict[str, Any]:
    """Range en file les rapprochements d'une recherche. Rend {proposes, comparees}. Lève `Indisponible` si le moteur ne tourne pas."""
    with fabrique() as s:
        # Règle 8 : une fiche de genre « personne » n'entre pas dans un rapprochement, SAUF si une personne a explicitement levé la règle sur
        # cette fiche-là (`tri.marquer_personne_morale`, trace dans `faits.regle8_leve`). Le genre n'est jamais réécrit : il dit ce que la
        # collecte a constaté, la levée dit ce qu'une personne a décidé, et les deux restent lisibles côte à côte.
        cands = [c for c in s.scalars(select(Candidat).where(Candidat.recherche_id == rid))
                 if (c.genre_de_chose or "").strip().lower() != "personne" or (c.faits or {}).get("regle8_leve")]  # fmt: skip
        deja = {(r.a, r.b) for r in s.scalars(select(Rapprochement).where(Rapprochement.recherche_id == rid))}
        liees = _deja_liees(cands)
    if len(cands) < 2:
        return {"proposes": 0, "comparees": len(cands)}
    paires = [p for p in _scorer([_fiche(c) for c in cands], SEUIL) if (p["a"], p["b"]) not in deja and (p["a"], p["b"]) not in liees and p["confiance"] >= SEUIL]
    with fabrique.begin() as s:
        for p in paires:
            s.add(Rapprochement(recherche_id=rid, a=p["a"], b=p["b"], confiance=p["confiance"], pourquoi=p["pourquoi"]))
        if paires:
            s.add(Journal(recherche_id=rid, qui="pilote", evenement="rapprochements_proposes", detail={"n": len(paires)}))
    return {"proposes": len(paires), "comparees": len(cands)}


# ---------------------------------------------------------------- la file


def _norme(champ: str, v: str) -> str:
    v = re.sub(r"\s+", " ", (v or "").strip().lower())
    return re.sub(r"[\s.\-]", "", v) if champ == "numero" else v  # un numéro s'écrit avec ou sans espaces : « 412 345 678 » et « 412345678 » sont le même


def comparer(champ: str, a: str, b: str) -> str:
    """accord / desaccord / absence, calculé champ par champ : une valeur absente d'un côté n'est JAMAIS une différence (il n'y a rien à comparer)."""
    if not (a or "").strip() or not (b or "").strip():
        return "absence"
    return "accord" if _norme(champ, a) == _norme(champ, b) else "desaccord"


def _titre(a: Candidat, b: Candidat) -> str:
    nom, num = comparer("nom", a.nom, b.nom), comparer("numero", a.numero_officiel, b.numero_officiel)
    genre = (a.genre_de_chose or b.genre_de_chose or "").strip().lower()
    quoi = f"deux fiches {GENRES[genre]}" if genre in GENRES else "deux fiches"
    if num == "accord":
        return f"{quoi}, identifiant officiel identique"
    if nom == "accord":
        return f"{quoi}, nom identique" + (", un identifiant manquant" if num == "absence" else ", identifiants différents")
    return f"{quoi}, nom proche"


def _source_principale(c: Candidat, nom_source, fiabilites: dict[str, str]) -> tuple[str, str]:
    """La source la plus fiable parmi celles qui ont trouvé ce nom, et sa lettre : c'est la colonne que la personne lit en premier."""
    jetons = sorted(set(c.trouve_par or []), key=lambda t: (fiabilites.get(t, "F"), t))
    if not jetons:
        return "source inconnue", "F"
    return nom_source(jetons[0]), fiabilites.get(jetons[0], "F")


def _carte(r: Rapprochement, a: Candidat, b: Candidat, nom_source, fiabilites: dict[str, str]) -> dict[str, Any]:
    champs = [("nom", "Nom", a.nom, b.nom), ("ville", "Ville", a.ville, b.ville), ("numero", "Identifiant", a.numero_officiel, b.numero_officiel), ("site", "Site", a.site, b.site), ("genre", "Genre", a.genre_de_chose, b.genre_de_chose)]
    lignes = [(c, lib, va or "", vb or "", comparer(c, va or "", vb or "")) for c, lib, va, vb in champs if c == "nom" or (va or "").strip() or (vb or "").strip()]  # une ligne par propriété que l'une des fiches porte
    fiches = []
    for cand, cote in ((a, 2), (b, 3)):
        source, lettre = _source_principale(cand, nom_source, fiabilites)
        fiches.append({"candidat": cand.id, "source": source, "fiabilite": lettre, "lignes": [{"champ": c, "libelle": lib, "valeur": ligne[cote], "etat": ligne[4]} for ligne in lignes for c, lib in [(ligne[0], ligne[1])]]})
    return {
        "id": r.id, "recherche": r.recherche_id, "titre": _titre(a, b), "confiance": round(r.confiance * 100), "pourquoi": r.pourquoi, "fiches": fiches, "etat": r.etat,
        "decide_par": r.decide_par, "decide_le": r.decide_le.replace(tzinfo=UTC).isoformat() if r.decide_le else None,
    }  # fmt: skip


def file(cfg: Config, fabrique: sessionmaker[Session]) -> dict[str, Any]:
    """{a_examiner: du moins certain au plus certain, tranches: les plus récentes d'abord}. Rien ne disparaît : une décision reste lisible."""
    nom_source = tri.noms_de_sources(cfg)
    fiabilites = {s["id"]: s["fiabilite"] for s in suite.charger(cfg)["sources"]}
    with fabrique() as s:
        rapps = list(s.scalars(select(Rapprochement)))
        ids = {i for r in rapps for i in (r.a, r.b)}
        cands = {c.id: c for c in s.scalars(select(Candidat).where(Candidat.id.in_(ids)))} if ids else {}
        cartes = [_carte(r, cands[r.a], cands[r.b], nom_source, fiabilites) for r in rapps if r.a in cands and r.b in cands]
    a_examiner = sorted((c for c in cartes if c["etat"] == "a_examiner"), key=lambda c: (c["confiance"], c["id"]))
    tranches = sorted((c for c in cartes if c["etat"] != "a_examiner"), key=lambda c: c["decide_le"] or "", reverse=True)
    return {"a_examiner": a_examiner, "tranches": tranches}


def trancher(cfg: Config, fabrique: sessionmaker[Session], ident: int, action: str, qui: str) -> dict[str, Any]:
    """CONFIRMER : écrit le lien « même entité » des deux côtés (relations des deux fiches). SÉPARER : l'ôte s'il y était, sans rien effacer d'autre."""
    if action not in ("confirme", "separe"):
        raise ValueError("Une décision est « confirmer » ou « séparer ».")
    with fabrique.begin() as s:
        r = s.get(Rapprochement, ident)
        if r is None:
            raise LookupError("Ce rapprochement n'existe pas.")
        a, b = s.get(Candidat, r.a), s.get(Candidat, r.b)
        assert a is not None and b is not None
        for cand, autre in ((a, b), (b, a)):  # on repart toujours des liens SANS ce rapprochement : changer d'avis ne laisse rien derrière
            cand.relations = [x for x in (cand.relations or []) if not (isinstance(x, dict) and x.get("rapprochement") == r.id)]
            if action == "confirme":
                cand.relations = [*cand.relations, {"type": "meme_entite", "vers": autre.nom, "source": "tri", "rapprochement": r.id}]
        r.etat, r.decide_par, r.decide_le = action, qui, datetime.now(UTC)
        s.add(Journal(recherche_id=r.recherche_id, qui=qui, evenement=f"rapprochement_{action}", detail={"rapprochement": r.id, "a": a.nom, "b": b.nom, "confiance": r.confiance}))
    return {"id": ident, "etat": action}
