"""Score de rapprochement par SPLINK (MIT, modèle probabiliste de Fellegi-Sunter, DuckDB local) — le moteur recommandé par la spécification (15 § 1).

Tourne dans un PROCESSUS À PART (`python -m pilote.rapprochement_splink`, JSON sur l'entrée et la sortie) : si DuckDB plantait sur un processeur qu'il ne
supporte pas (la version 2.0 le fait sur la VM actuelle), seul ce processus tomberait, jamais le service ; `rapprochements.py` le dit alors au lieu de se taire.

Les probabilités m et u de chaque comparaison sont FIXÉES À L'AVANCE dans ce fichier, non entraînées : l'entraînement sans étiquette de Splink demande des
milliers de fiches, et une recherche en compte quelques dizaines. La confiance affichée vaut donc ce que valent ces probabilités a priori (écrites ici,
lisibles, ajustables) ; elle bascule sur l'entraînement quand le volume le permet (QUESTIONS F22-3). Rien ici ne regarde une personne physique : seuls le
nom de l'entité, sa ville, son numéro officiel et son site comptent (règle 8)."""

from __future__ import annotations

import json
import re
import sys
import unicodedata

PRIOR = 0.008  # probabilité a priori que deux fiches tirées au hasard dans une recherche soient la même entité
MOTS_VIDES = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "en", "au", "aux", "a"}
TOUT_LES_PAIRES_JUSQU_A = 300  # au-delà, des règles de blocage évitent de comparer tout avec tout


def _nu(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _niveau(cond: str, m: float | None = None, u: float | None = None, etiquette: str = "", nul: bool = False) -> dict:
    d: dict = {"sql_condition": cond, "label_for_charts": etiquette or cond}
    if nul:
        d["is_null_level"] = True
    else:
        d["m_probability"], d["u_probability"] = m, u
    return d


def reglages(n: int) -> dict:
    jaccard = "len(list_intersect(mots_l, mots_r)) * 1.0 / len(list_distinct(list_concat(mots_l, mots_r)))"
    comparaisons = [
        {"output_column_name": "nom", "comparison_levels": [
            _niveau("nom_l IS NULL OR nom_r IS NULL", nul=True),
            _niveau("nom_l = nom_r", 0.55, 0.004, "identique"),
            _niveau(f"{jaccard} >= 0.8", 0.15, 0.002, "très proche"),
            _niveau(f"{jaccard} >= 0.6", 0.15, 0.01, "proche"),
            _niveau(f"{jaccard} >= 0.4", 0.08, 0.05, "un peu proche"),
            _niveau("ELSE", 0.07, 0.934, "différent"),
        ]},
        {"output_column_name": "ville", "comparison_levels": [
            _niveau("ville_l IS NULL OR ville_r IS NULL", nul=True),
            _niveau("ville_l = ville_r", 0.9, 0.25, "identique"),
            _niveau("ELSE", 0.1, 0.75, "différente"),
        ]},
        {"output_column_name": "numero", "comparison_levels": [
            _niveau("numero_l IS NULL OR numero_r IS NULL", nul=True),
            _niveau("numero_l = numero_r", 0.6, 0.00001, "identique"),
            _niveau("ELSE", 0.4, 0.99999, "différent"),
        ]},
    ]  # fmt: skip
    blocage = ["1 = 1"] if n <= TOUT_LES_PAIRES_JUSQU_A else ["l.ville = r.ville", "l.numero = r.numero", "l.mot1 = r.mot1", "l.mot2 = r.mot2"]
    return {"link_type": "dedupe_only", "probability_two_random_records_match": PRIOR, "retain_intermediate_calculation_columns": True, "blocking_rules_to_generate_predictions": blocage, "comparisons": comparaisons}


def scorer(fiches: list[dict], seuil: float) -> list[dict]:
    """Les paires dont la probabilité de correspondance atteint `seuil`. `fiches` : [{id, nom, ville, numero, site}]. Rend [{a, b, confiance, pourquoi}]."""
    import pandas as pd
    from splink import DuckDBAPI, Linker

    lignes = []
    for f in fiches:
        mots = sorted({w for w in _nu(f["nom"]).split() if w not in MOTS_VIDES})
        lignes.append({
            "unique_id": f["id"], "nom": _nu(f["nom"]) or None, "mots": mots or [""], "mot1": mots[0] if mots else None, "mot2": mots[-1] if mots else None,
            "ville": _nu(f.get("ville", "")) or None, "numero": re.sub(r"\D", "", f.get("numero", "") or "") or None,
        })  # fmt: skip
    if len(lignes) < 2:
        return []
    linker = Linker(DuckDBAPI().register(pd.DataFrame(lignes)), reglages(len(lignes)), log_level=40)
    res = linker.inference.predict(threshold_match_probability=seuil).as_pandas_dataframe()
    out = []
    for _, r in res.iterrows():
        pourquoi = {}
        for champ in ("nom", "ville", "numero"):
            gamma = int(r[f"gamma_{champ}"])
            niveaux = [n for n in reglages(1)["comparisons"][["nom", "ville", "numero"].index(champ)]["comparison_levels"] if not n.get("is_null_level")]
            pourquoi[champ] = {"niveau": "absent d'un côté" if gamma < 0 else niveaux[len(niveaux) - 1 - gamma]["label_for_charts"], "poids": round(float(r[f"mw_{champ}"]), 3)}
        a, b = sorted((r["unique_id_l"], r["unique_id_r"]))
        out.append({"a": int(a), "b": int(b), "confiance": round(float(r["match_probability"]), 4), "pourquoi": pourquoi})
    return out


if __name__ == "__main__":
    entree = json.load(sys.stdin)
    json.dump(scorer(entree["fiches"], float(entree["seuil"])), sys.stdout)
