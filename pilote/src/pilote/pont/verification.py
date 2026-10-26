"""Vérification des candidats par les sources « vérifier » (adresse d'un site, liste de sanctions...). Séparé de `executer.py` pour pouvoir
être essayé sans la bibliothèque grappes : il ne reçoit que les candidats, la déclaration du lancement et la fonction d'avancement."""

from __future__ import annotations

import time


def verifier_candidats(lignes: list[dict], spec: dict, secrets: dict[str, str], doit_s_arreter, limite_source: float, signaler) -> list[dict]:
    """Appelle chaque source « vérifier » sur chaque candidat à vérifier, APRÈS le classement. Une vérification ne trouve rien et ne compte
    pas comme endroit de plus : elle s'ajoute dans `faits.verifications` ({source, origine, preuve, signal} ; signal = « confirmation »
    ou « alerte »). Une source qui échoue ou dépasse son temps est laissée de côté pour le reste de la recherche ; un arrêt demandé coupe
    la vérification, les candidats restent.

    Rend un BILAN par source ({source, examines, a_verifier, trouves, complete, raison}) : une vérification coupée au milieu ne doit pas
    ressembler à une vérification qui n'a rien trouvé, sinon l'absence de preuve se lirait comme une preuve d'absence."""
    from pilote import adaptateurs

    bilans: list[dict] = []
    for v in spec.get("verificateurs", []):
        source, debut, hors_service = v["source"], time.time(), ""
        sur_le_nom = v.get("verifie_sur", "site") == "nom"
        client = adaptateurs.Client(source, doit_s_arreter, signaler=signaler, delai_s=v.get("delai_s", 0.2))
        parametres = {**v.get("parametres", {}), **({"_cle": secrets.get(v["cles_noms"][0], ""), "_cles": {n: secrets.get(n, "") for n in v["cles_noms"]}} if v.get("cles_noms") else {})}
        signaler("prise_debut", prise=source)
        a_verifier = [l for l in lignes if sur_le_nom or l.get("site")]
        if v.get("en_amont") is not None:  # posée après certaines sources sur le plan : elle ne vérifie que les noms que ces sources ont trouvés
            a_verifier = [l for l in a_verifier if set(l.get("trouve_par") or []) & set(v["en_amont"])]
        faits_ok, examines, coupee = 0, 0, ""
        plafond = int(v.get("parametres", {}).get("max_candidats") or 0)  # source à crédits comptés : on n'examine que les premiers (les mieux classés)
        for ligne in a_verifier:
            if hors_service:
                break
            if doit_s_arreter():
                coupee = "arrêt ou limite d'appels atteinte"
                break
            if plafond and examines >= plafond:
                coupee = f"plafond de {plafond} noms examinés par recherche (crédits de la source)"
                break
            if time.time() - debut > limite_source:
                coupee = f"limite de temps de la source atteinte ({limite_source:g} s)"
                break
            try:
                trouves = adaptateurs.charger(v["module"]).chercher({"site": ligne.get("site", ""), "nom": ligne["nom"], "quoi": ligne["nom"], "pays": ligne.get("pays", "")}, client, parametres)
            except adaptateurs.LimiteAtteinte:
                coupee = "arrêt ou limite d'appels atteinte"
                break
            except Exception as exc:  # noqa: BLE001 - une vérification qui échoue n'arrête ni la recherche ni les autres sources
                hors_service = f"{type(exc).__name__} : {str(exc)[:150]}"
                signaler("source_echec", prise=source, raison=hors_service)
                continue
            examines += 1
            if trouves:
                faits_ok += 1
                ligne.setdefault("faits", {}).setdefault("verifications", []).append(
                    {"source": source, "origine": str(trouves[0].get("origine", "")), "preuve": str(trouves[0].get("numero", "")), "signal": str(trouves[0].get("signal") or "confirmation")})  # fmt: skip
        if not hors_service:
            signaler("source_ok", prise=source)
        complete = not hors_service and not coupee
        signaler("prise_fin", prise=source, trouves=faits_ok, noms=0, examines=examines, a_verifier=len(a_verifier),
                 statut="erreur : défaut" if hors_service else "ok" if complete else "partielle")  # fmt: skip
        bilans.append({"source": source, "examines": examines, "a_verifier": len(a_verifier), "trouves": faits_ok,
                       "complete": complete, "raison": hors_service or coupee})  # fmt: skip
    return bilans
