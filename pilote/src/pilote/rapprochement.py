"""Rapprocher des noms d'entreprise (fiche 06) : « SAS DUPONT SPORTS » au registre, « Dupont Sports Grenoble » sur la vitrine.

Outil repris tel quel : cleanco (licence MIT) retire les formes juridiques (SAS, Ltd, GmbH, Oy...), devant ou derrière le nom, avant la
comparaison. Il peut rater des formes rares. Le regroupement des noms par nomenklatura a un défaut connu dans grappes (il enchaîne des
noms sans rapport) : tant qu'il n'est pas corrigé, un nom APPROCHANT n'est jamais dit « confirmé », seulement « correspondance probable »."""

from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache

from cleanco import basename

from pilote.classements import normaliser

EXACT, APPROCHANT = "exact", "approchant"
PHRASES = {EXACT: "confirmé : même nom", APPROCHANT: "correspondance probable"}


@lru_cache(maxsize=50_000)  # le même nom est normalisé des milliers de fois (chaque comparaison) : une seule fois suffit
def nom_nu(nom: str) -> str:
    """Le nom sans forme juridique, sans accents ni ponctuation ni casse."""
    return normaliser(basename(nom, prefix=True, suffix=True, middle=False) or nom)


def comparer(a: str, b: str) -> str | None:
    """`exact` (mêmes mots une fois la forme juridique retirée), `approchant` (l'un est le début ou la fin de l'autre, ou presque identiques), sinon None."""
    na, nb = nom_nu(a), nom_nu(b)
    if not na or not nb:
        return None
    if na == nb:
        return EXACT
    ta, tb = na.split(), nb.split()
    petit, grand = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(petit) >= 2 and (grand[: len(petit)] == petit or grand[-len(petit) :] == petit):
        return APPROCHANT
    if abs(len(na) - len(nb)) <= 3 and SequenceMatcher(None, na, nb).ratio() >= 0.92:
        return APPROCHANT
    return None


def rapprocher(inconnus: dict[int, str], references: dict[int, str]) -> dict[int, dict[str, str]]:
    """Pour chaque nom `inconnus` (id -> nom), la meilleure référence (id -> nom d'une source de registre) : {id: {avec, exactitude, phrase}}."""
    par_mot: dict[str, list[int]] = {}
    for i, n in references.items():
        t = nom_nu(n).split()
        for mot in {t[0], t[-1]} if t else ():
            par_mot.setdefault(mot, []).append(i)
    out: dict[int, dict[str, str]] = {}
    for i, n in inconnus.items():
        t = nom_nu(n).split()
        meilleur: tuple[str, int] | None = None
        for mot in {t[0], t[-1]} if t else ():
            for j in par_mot.get(mot, ()):
                if j == i:
                    continue
                r = comparer(n, references[j])
                if r == EXACT or (r == APPROCHANT and meilleur is None):
                    meilleur = (r, j)
                    if r == EXACT:
                        break
        if meilleur:
            out[i] = {"avec": references[meilleur[1]], "exactitude": meilleur[0], "phrase": PHRASES[meilleur[0]]}
    return out


def blocs(candidats: list[dict]) -> dict[int, dict[str, str]]:
    """Regroupe en un seul bloc le siège, ses établissements et les sociétés d'un même groupe, d'après les RELATIONS que les sources ont
    données (« établissement de », « maison mère »...) et les numéros (un SIRET commence par le SIREN de son siège).
    `candidats` : [{id, nom, numero, fonction, relations}] ; rend {id: {bloc, racine}} pour les noms qui ont au moins un lien."""
    parent: dict[int, int] = {c["id"]: c["id"] for c in candidats}

    def racine(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = racine(a), racine(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    par_nom: dict[str, list[int]] = {}
    par_siren: dict[str, list[int]] = {}
    for c in candidats:
        par_nom.setdefault(nom_nu(c["nom"]), []).append(c["id"])
        num = "".join(ch for ch in str(c.get("numero", "")) if ch.isdigit())
        if len(num) in (9, 14):
            par_siren.setdefault(num[:9], []).append(c["id"])
    for c in candidats:
        for r in c.get("relations") or []:
            for j in par_nom.get(nom_nu(str(r.get("vers", ""))), ()):
                union(c["id"], j)
    for ids in par_siren.values():
        for j in ids[1:]:
            union(ids[0], j)
    membres: dict[int, list[dict]] = {}
    for c in candidats:
        membres.setdefault(racine(c["id"]), []).append(c)
    out: dict[int, dict[str, str]] = {}
    for r, ms in membres.items():
        if len(ms) < 2:
            continue
        tete = next((m for m in ms if m.get("fonction") in ("maison mère", "siège")), ms[0])
        for m in ms:
            out[m["id"]] = {"bloc": str(r), "racine": tete["nom"]}
    return out
