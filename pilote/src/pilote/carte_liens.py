"""Vue « carte de liens » de Tri (fiche 15, chapitre 4) : les noms et les relations que les sources ont données pendant la collecte.

Règles de la fiche : un point par nom, sa taille = le nombre d'endroits distincts qui l'ont trouvé, sa couleur = son origine (comme la liste),
un trait par relation avec un style par type. **Jamais tout d'un coup** : on montre les noms GARDÉS, ou le voisinage d'UN nom choisi, avec un
plafond dur de points. Sans relation enregistrée à la collecte, il n'y a rien à tracer et on le dit."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote.base import Candidat
from pilote.rapprochement import nom_nu
from pilote.tri import _recherche, decisions_courantes

PLAFOND = 60  # nombre maximal de points dessinés, quoi qu'on demande : au-delà, la carte devient illisible
TYPES = {  # type de relation donné par les sources -> famille dessinée
    "etablissement_de": "siege", "a_pour_etablissement": "siege", "siege": "siege",
    "maison_mere": "maison_mere", "maison_mere_ultime": "maison_mere", "filiale_de": "maison_mere",
    "trouve_via": "trouve_via", "meme_adresse": "meme_adresse",
}  # fmt: skip
LIBELLES = {"siege": "siège / établissement", "maison_mere": "maison mère", "trouve_via": "trouvé via", "meme_adresse": "même adresse", "autre": "autre lien"}


def _aretes(cands: list[Candidat]) -> list[tuple[int | str, int | str, str, str]]:
    """(de, vers, famille, source). `vers` est l'identifiant du nom s'il est dans les résultats, sinon le texte donné par la source (point « hors résultats»)."""
    par_nom: dict[str, list[int]] = {}
    for c in cands:
        par_nom.setdefault(nom_nu(c.nom), []).append(c.id)
    out: list[tuple[int | str, int | str, str, str]] = []
    vus: set[tuple[Any, ...]] = set()
    for c in cands:
        for r in c.relations or []:
            vers_txt = str(r.get("vers", "")).strip()
            if not vers_txt:
                continue
            famille = TYPES.get(str(r.get("type", "")), "autre")
            cibles: list[int | str] = list(par_nom.get(nom_nu(vers_txt), [])) or [vers_txt]
            for v in cibles:
                if v == c.id:
                    continue
                cle = (min(str(c.id), str(v)), max(str(c.id), str(v)), famille)
                if cle not in vus:
                    vus.add(cle)
                    out.append((c.id, v, famille, str(r.get("source", ""))))
    adresses: dict[str, list[int]] = {}
    for c in cands:
        a = nom_nu(str((c.faits or {}).get("adresse", "")))
        if a:
            adresses.setdefault(a, []).append(c.id)
    for ids in adresses.values():
        for j in ids[1:]:
            cle = (min(str(ids[0]), str(j)), max(str(ids[0]), str(j)), "meme_adresse")
            if cle not in vus:
                vus.add(cle)
                out.append((ids[0], j, "meme_adresse", ""))
    return out


def construire(fabrique: sessionmaker[Session], rid: str, centre: int | None = None, plafond: int = PLAFOND) -> dict[str, Any]:
    plafond = max(1, min(int(plafond), PLAFOND))
    with fabrique() as s:
        _recherche(s, rid)
        cands = list(s.scalars(select(Candidat).where(Candidat.recherche_id == rid).order_by(Candidat.id)))
        dec = decisions_courantes(s, rid)
    par_id = {c.id: c for c in cands}
    aretes = _aretes(cands)
    avec_relations = sum(1 for c in cands if c.relations)
    base = {"relations_enregistrees": avec_relations, "familles": LIBELLES, "plafond": plafond, "noeuds": [], "aretes": [], "tronque": False, "mode": "", "message": ""}
    if centre is not None:
        if centre not in par_id:
            return {**base, "message": "Ce nom n'existe pas dans cette recherche."}
        voisins = [(a, b, f, src) for a, b, f, src in aretes if centre in (a, b)]
        visibles: list[int | str] = [centre]
        for a, b, _, _ in voisins:
            autre = b if a == centre else a
            if autre not in visibles:
                visibles.append(autre)
        mode = "voisinage"
    else:
        gardes = [c.id for c in cands if dec.get(c.id) == "garder"]
        visibles = list(gardes)
        mode = "gardes"
        if not gardes:
            return {**base, "mode": mode, "message": "La carte montre les noms que vous avez gardés, ou le voisinage d'un nom choisi. Gardez des noms, ou ouvrez un nom puis « Voir ses liens »."}
    tronque = len(visibles) > plafond
    visibles = visibles[:plafond]
    ens = set(visibles)
    noeuds = []
    for v in visibles:
        c = par_id.get(v) if isinstance(v, int) else None
        if c is not None:
            noeuds.append({"id": c.id, "nom": c.nom, "o": c.genre_source or "web", "e": c.nb_endroits or 1, "d": dec.get(c.id), "externe": False, "centre": c.id == centre})
        else:
            noeuds.append({"id": f"x:{v}", "nom": str(v), "o": "", "e": 1, "d": None, "externe": True, "centre": False})
    ids_noeud = {(n["id"] if not n["externe"] else n["nom"]): n["id"] for n in noeuds}
    garde = [(ids_noeud[a], ids_noeud[b], f, src) for a, b, f, src in aretes if a in ens and b in ens and a in ids_noeud and b in ids_noeud]
    if not garde and mode == "gardes" and avec_relations == 0:
        base["message"] = "Aucune relation n'a été enregistrée pour cette recherche : les sources utilisées n'en donnent pas (registres d'entreprises, GLEIF en donnent). Rien à tracer."
    elif not garde and mode == "voisinage":
        base["message"] = "Ce nom n'a aucun lien enregistré."
    # la légende ne nomme que les familles de liens RÉELLEMENT dessinées : elle annonçait « même adresse », que rien ne
    # fournit (aucune source n'enregistre d'adresse), et un type de lien promis mais impossible est une promesse fausse.
    familles = {f: LIBELLES.get(f, f) for f in dict.fromkeys(f for _, _, f, _ in garde)}
    return {**base, "mode": mode, "tronque": tronque, "familles": familles, "noeuds": noeuds,
            "aretes": [{"de": a, "vers": b, "famille": f, "source": src} for a, b, f, src in garde]}  # fmt: skip
