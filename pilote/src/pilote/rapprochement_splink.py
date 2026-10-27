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

PRIOR = 0.008  # probabilité a priori que deux fiches tirées au hasard dans une recherche soient la même entité
MOTS_VIDES = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "en", "au", "aux", "a"}
# Mots qui disent SEULEMENT le genre d'organisation (« association sportive », « club », « mairie »…) : ils ne distinguent rien. Deux noms qui ne diffèrent que par les
# autres mots (« … de Cannes », « … de Monaco ») sont deux entités ; deux noms qui ne se ressemblent que par ces mots ne sont pas des doublons.
GENERIQUES = {"association", "associations", "sportive", "sportif", "club", "union", "societe", "amicale", "federation", "comite", "ligue", "groupe", "groupement", "fondation",
              "mairie", "commune", "ville", "centre", "maison", "cercle", "office", "syndicat", "institut", "ecole", "universite", "football", "judo", "rugby", "basket", "tennis", "sa", "sas", "sarl", "inc", "ltd", "gmbh", "oy"}  # fmt: skip
# Mots qui disent qu'un nom est un ORGANE DISTINCT de ce qu'il complète : « Fondation de l'AP-HP » n'est pas l'AP-HP, « Fédération de X » n'est pas « X ». Dans GENERIQUES aussi (ils ne
# distinguent pas deux noms de club), mais un seul côté qui en porte un est le signe d'une relation mère-fille, pas d'un doublon. « Groupe » n'y est pas : « Groupe Danone » se dit « Danone ».
STRUCTURE = {"fondation", "foundation", "federation", "confederation", "comite", "committee", "syndicat", "direction", "delegation", "antenne", "section", "filiale", "subsidiary", "departement", "department", "division", "fonds", "mouvement"}  # fmt: skip
CHAMPS = ["nom", "distinctif", "structure", "chiffres", "ville", "alias", "numero"]  # dans l'ordre des comparaisons de `reglages`
MUETS = {"alias": (-1, 0), "structure": (-1, 1)}  # niveaux (gamma) à ne pas montrer : alias absent ou sans rien en commun ; structure absente ou identique
TOUT_LES_PAIRES_JUSQU_A = 300  # au-delà, des règles de blocage évitent de comparer tout avec tout


def _nu(t: str) -> str:
    """Le nom mis à plat (sans accents, casse ni ponctuation) ; un emoji y reste sous sa forme de comparaison : « Club ⚽ » et « Club 🏀 » ne sont pas le même nom."""
    from pilote.adaptateurs import nom_normalise

    return nom_normalise(t or "")


def _ville_nu(v: str) -> str | None:
    """La ville mise à plat. Un arrondissement (« Paris 14 », « Lyon 3e ») est la même ville que « Paris » : sans cela, deux fiches de la même ville se lisaient comme deux villes."""
    ville = _nu(v)
    return re.sub(r"^(paris|lyon|marseille) \d{1,2}( ?(e|er|eme))?( arrondissement)?$", r"\1", ville) or None


def _numero(v: str) -> str | None:
    """Les chiffres du numéro officiel. Un SIRET (14 chiffres) et son SIREN (9) concordent (voir le niveau « identique » de la comparaison) ; deux SIRET
    DIFFÉRENTS sont deux établissements distincts d'une même entreprise : jamais un doublon."""
    return re.sub(r"\D", "", v or "") or None


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
            _niveau("levenshtein(nom_l, nom_r) <= CASE WHEN length(nom_l) >= 15 THEN 2 WHEN length(nom_l) >= 8 THEN 1 ELSE 0 END", 0.12, 0.002, "très proche (fautes de frappe)"),  # une ou deux lettres selon la longueur ; jamais sur un sigle (ASM, ASB sont deux clubs)
            _niveau(f"{jaccard} >= 0.8", 0.1, 0.002, "très proche"),
            _niveau(f"{jaccard} >= 0.6", 0.15, 0.01, "proche"),
            _niveau(f"{jaccard} >= 0.4", 0.08, 0.05, "un peu proche"),
            _niveau("ELSE", 0.07, 0.934, "différent"),
        ]},
        {"output_column_name": "distinctif", "comparison_levels": [
            _niveau("len(mots_d_l) = 0 OR len(mots_d_r) = 0", nul=True),
            _niveau("nom_l = nom_r", 0.2, 0.2, "nom identique : déjà compté"),  # sans cela, un même nom comptait deux fois (nom + mots distinctifs) et deux homonymes de villes différentes montaient à 70 %
            _niveau("list_sort(mots_d_l) = list_sort(mots_d_r)", 0.8, 0.05, "mêmes mots distinctifs"),
            _niveau("levenshtein(array_to_string(list_sort(mots_d_l), ' '), array_to_string(list_sort(mots_d_r), ' ')) <= CASE WHEN length(array_to_string(mots_d_l, ' ')) >= 12 THEN 2 WHEN length(array_to_string(mots_d_l, ' ')) >= 8 THEN 1 ELSE 0 END", 0.1, 0.01, "mots distinctifs à une faute près"),
            _niveau("len(list_intersect(mots_d_l, mots_d_r)) * 1.0 / len(list_distinct(list_concat(mots_d_l, mots_d_r))) >= 0.5", 0.15, 0.05, "mots distinctifs en commun"),
            _niveau("ELSE", 0.05, 0.9, "mots distinctifs différents"),  # « Cannes » contre « Monaco » : deux clubs
        ]},
        {"output_column_name": "structure", "comparison_levels": [
            _niveau("len(struct_l) = 0 AND len(struct_r) = 0", nul=True),
            _niveau("list_sort(struct_l) = list_sort(struct_r)", 0.5, 0.5, "même mot de structure"),
            _niveau("ELSE", 0.005, 0.8, "un mot de structure d'un seul côté"),  # « Fondation de X » contre « X », « Fédération de X » contre « Comité de X » : deux organes, pas une faute de frappe
        ]},
        {"output_column_name": "chiffres", "comparison_levels": [
            _niveau("chiffres_l IS NULL AND chiffres_r IS NULL", nul=True),
            _niveau("chiffres_l IS NULL OR chiffres_r IS NULL", 0.4, 0.7, "chiffres d'un seul côté"),  # « Ligue des champions » et « Ligue des champions 2024 » : plutôt deux choses
            _niveau("chiffres_l = chiffres_r", 0.95, 0.3, "mêmes chiffres"),
            _niveau("ELSE", 0.005, 0.8, "chiffres différents"),  # « Innovation 3 » et « Innovation 5 » : deux fonds, pas une faute de frappe
        ]},
        {"output_column_name": "ville", "comparison_levels": [
            _niveau("ville_l IS NULL OR ville_r IS NULL", nul=True),
            _niveau("ville_l = ville_r", 0.9, 0.25, "identique"),
            _niveau("ELSE", 0.1, 0.75, "différente"),
        ]},
        {"output_column_name": "alias", "comparison_levels": [
            _niveau("len(alias_l) = 0 AND len(alias_r) = 0", nul=True),
            _niveau("list_contains(alias_l::VARCHAR[], nom_r) OR list_contains(alias_r::VARCHAR[], nom_l) OR len(list_intersect(alias_l::VARCHAR[], alias_r::VARCHAR[])) > 0", 0.7, 0.0001, "un nom déclaré en commun (sigle, acronyme, ancien nom)"),  # une PREUVE, pas une identité : le numéro officiel garde son veto (la société « CEA » n'est pas le Commissariat, qui a pour sigle CEA)
            _niveau("ELSE", 0.5, 0.5, "aucun nom déclaré en commun"),  # des alias absents ou différents ne disent rien : les listes sont incomplètes
        ]},
        {"output_column_name": "numero", "comparison_levels": [
            _niveau("numero_l IS NULL OR numero_r IS NULL", nul=True),
            _niveau("numero_l = numero_r OR (length(numero_l) = 9 AND length(numero_r) = 14 AND substr(numero_r, 1, 9) = numero_l) OR (length(numero_r) = 9 AND length(numero_l) = 14 AND substr(numero_l, 1, 9) = numero_r)", 0.6, 0.00001, "identique"),
            _niveau("ELSE", 0.003, 0.99999, "différent"),  # deux numéros officiels différents : deux entités distinctes, sauf faute de saisie (rare)
        ]},
    ]  # fmt: skip
    blocage = ["1 = 1"] if n <= TOUT_LES_PAIRES_JUSQU_A else ["l.ville = r.ville", "l.numero = r.numero", "l.mot1 = r.mot1", "l.mot2 = r.mot2", "list_contains(l.alias::VARCHAR[], r.nom) OR list_contains(r.alias::VARCHAR[], l.nom)", "substr(l.nom, 1, 4) = substr(r.nom, 1, 4)", "substr(l.mot1, 1, 3) = substr(r.mot1, 1, 3) AND substr(l.mot2, 1, 3) = substr(r.mot2, 1, 3)"]  # y compris des débuts de mot communs : une faute de frappe ne doit pas suffire à ne jamais comparer deux fiches
    return {"link_type": "dedupe_only", "probability_two_random_records_match": PRIOR, "retain_intermediate_calculation_columns": True, "blocking_rules_to_generate_predictions": blocage, "comparisons": comparaisons}


def scorer(fiches: list[dict], seuil: float) -> list[dict]:
    """Les paires dont la probabilité de correspondance atteint `seuil`. `fiches` : [{id, nom, ville, numero, site}]. Rend [{a, b, confiance, pourquoi}]."""
    import pandas as pd
    from splink import DuckDBAPI, Linker

    lignes = []
    for f in fiches:
        nom = _nu(f["nom"])
        mots = sorted({w for w in nom.split() if w not in MOTS_VIDES})
        lignes.append({
            "unique_id": f["id"], "nom": nom or None, "mots": mots or [""], "mots_d": [w for w in mots if w not in GENERIQUES], "struct": sorted(STRUCTURE & set(mots)), "mot1": mots[0] if mots else None, "mot2": mots[-1] if mots else None, "chiffres": "-".join(re.findall(r"\d+", f["nom"])) or None,
            "ville": _ville_nu(f.get("ville", "")), "numero": _numero(f.get("numero", "")),
            "alias": sorted({a for a in (_nu(x) for x in f.get("alias") or []) if a and a != nom}),
        })  # fmt: skip
    if len(lignes) < 2:
        return []
    linker = Linker(DuckDBAPI().register(pd.DataFrame(lignes)), reglages(len(lignes)), log_level=40)
    res = linker.inference.predict(threshold_match_probability=seuil).as_pandas_dataframe()
    out = []
    for _, r in res.iterrows():
        pourquoi = {}
        for champ in CHAMPS:
            gamma = int(r[f"gamma_{champ}"])
            if gamma in MUETS.get(champ, ()):  # un niveau neutre ou absent n'apprend rien à la personne qui tranche : on ne l'affiche pas
                continue
            niveaux = [n for n in reglages(1)["comparisons"][CHAMPS.index(champ)]["comparison_levels"] if not n.get("is_null_level")]
            pourquoi[champ] = {"niveau": "absent d'un côté" if gamma < 0 else niveaux[len(niveaux) - 1 - gamma]["label_for_charts"], "poids": round(float(r[f"mw_{champ}"]), 3)}
        a, b = sorted((r["unique_id_l"], r["unique_id_r"]))
        out.append({"a": int(a), "b": int(b), "confiance": round(float(r["match_probability"]), 4), "pourquoi": pourquoi})
    return out


if __name__ == "__main__":
    entree = json.load(sys.stdin)
    json.dump(scorer(entree["fiches"], float(entree["seuil"])), sys.stdout)
