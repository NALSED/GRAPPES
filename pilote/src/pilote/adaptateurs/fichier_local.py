"""Source « fichier_local » : une base téléchargée et versée dans SQLite (module `pilote.fichier_local`), interrogée SANS appel réseau.

Paramètres de la déclaration : `base` (nom de la copie), `mode_verification` (« exact » : seule l'égalité du nom compte), `themes_graves`
(préfixes de thèmes qui font une ALERTE ; les autres thèmes sont une information), `origine` (la phrase qui dit d'où vient la donnée).
Une source locale n'a ni quota ni compte d'appels : le moteur ne la compte pas dans la limite d'appels de la recherche."""

from __future__ import annotations

from typing import Any

from pilote import fichier_local as fl
from pilote.adaptateurs import Client, ErreurSource, LimiteAtteinte

LIT_PARAMETRES = True


def _convertir(lignes: list[dict[str, Any]], parametres: dict[str, Any], verification: bool, nom: str = "") -> list[dict[str, Any]]:
    origine = str(parametres.get("origine") or f"copie locale « {parametres.get('base')} »")
    graves = tuple(parametres.get("themes_graves") or ())
    out = []
    for r in lignes:
        item = {"nom": r["nom"], "origine": origine}
        for c in ("ville", "numero", "pays", "genre", "site"):
            if r.get(c):
                item[c] = r[c]
        if verification:
            themes = [t.strip() for t in str(r.get("themes") or "").replace(";", ",").split(",") if t.strip()]
            if parametres.get("signal"):  # base de signalements : figurer avec une mesure (colonne « themes » non vide) est une ALERTE ; figurer sans mesure (registre de risque, de propriété) est une information
                avec, sans = (parametres["signal"] if isinstance(parametres["signal"], list) else [parametres["signal"]] * 2)[:2]
                item["signal"] = str(avec if themes else sans)
                listes = ";".join(str(r["detail"]).split(";")[:4]) if r.get("detail") else ""
                item["origine"] = f"{origine} : ce nom figure sur une liste" + (f" [{listes}]" if listes else "") + (" sous le coup d'une mesure" if themes else " sans mesure de sanction") + ", à vérifier à la main"
            elif graves:  # base de signalements : une inscription est une ALERTE si un thème grave y figure (ou si aucun thème n'est connu), sinon une information
                grave = not themes or any(t.startswith(graves) for t in themes)
                item["signal"] = "alerte" if grave else "information"
                item["origine"] = f"{origine} : ce nom figure sur une liste" + (f" ({', '.join(themes)})" if themes else "") + ", à vérifier à la main"
            else:
                item["signal"] = "confirmation"
            item["nom"] = nom or r["nom"]
        out.append(item)
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    base = str(parametres.get("base") or "")
    dossier = str(parametres.get("_dossier_copies") or "")
    if not dossier:
        raise ErreurSource("Le dossier des copies locales n'est pas connu de la source.")
    if client.doit_s_arreter():
        raise LimiteAtteinte
    if entree.get("fonction") == "enrichir":
        return _enrichir(entree, dossier, parametres)
    verification = bool(entree.get("nom"))  # une vérification donne le nom d'un résultat déjà trouvé ; une recherche donne `quoi`
    try:
        if verification:
            return _convertir(fl.exact(dossier, base, str(entree["nom"])), parametres, True, str(entree["nom"]))
        quoi = str(entree.get("quoi") or "").strip()
        if not quoi:
            return []
        lieu = str(entree.get("lieu") or "").strip()
        trouves = _convertir(fl.chercher_par_mots(dossier, base, quoi, int(entree.get("limite") or 50), lieu), parametres, False)
        n = 0 if lieu else fl.homonymes(dossier, base, quoi)
        if n > 3:  # un nom partagé : la liste ne dit pas laquelle est la bonne, on dit ce qui la départagerait
            for t in trouves:
                t["origine"] += f" ({n} entités portent exactement ce nom : précisez la ville ou le département, ou donnez le numéro officiel)"
        return trouves
    except fl.BaseLocaleErreur as exc:
        raise ErreurSource(str(exc)) from exc


def _enrichir(entree: dict[str, Any], dossier: str, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    """ENRICHIR : la copie rend de l'information EN PLUS pour une fiche déjà trouvée, retrouvée par son nom ou par sa ville (`enrichit_par`).
    `classes` : préfixes du champ « thèmes » à retenir (ex. GeoNames : PPL = lieu habité). Le plus lourd (poids) d'abord."""
    cle = str(parametres.get("enrichit_par") or "nom")
    valeur = str(entree.get(cle) or "").strip()
    if not valeur:
        return []
    classes = tuple(parametres.get("classes") or ())
    try:
        lignes = [r for r in fl.exact(dossier, str(parametres.get("base") or ""), valeur, 50) if not classes or str(r.get("themes") or "").startswith(classes)]
    except fl.BaseLocaleErreur as exc:
        raise ErreurSource(str(exc)) from exc
    if not lignes:
        return []
    if classes:  # l'ordre de `classes` est un ordre de préférence (le lieu habité avant la division administrative)
        lignes.sort(key=lambda r: next(i for i, c in enumerate(classes) if str(r.get("themes") or "").startswith(c)))
    r = lignes[0]
    item = {"nom": str(entree.get("nom") or valeur), "origine": str(parametres.get("origine") or f"copie locale « {parametres.get('base')} »")}
    for c in ("site", "numero", "pays"):
        if r.get(c):
            item[c] = r[c]
    morceaux = str(r.get("detail") or "").split()
    if len(morceaux) == 2 and all(m.replace(".", "", 1).replace("-", "", 1).isdigit() for m in morceaux):
        item["coordonnees"] = {"lat": float(morceaux[0]), "lon": float(morceaux[1])}
    elif r.get("detail"):
        item["detail"] = r["detail"]
    return [item]
