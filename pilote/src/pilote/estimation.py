"""Fourchette de temps et de coût d'une recherche, dite AVANT le lancement (fiche 12). Une fourchette, jamais un compte à rebours précis.

* Temps : si au moins trois recherches terminées de même profondeur existent, la fourchette est CE QU'ON A MESURÉ (la plus courte et la plus
  longue des dix dernières) ; sinon elle est volontairement large et dit qu'elle n'est pas mesurée. Elle ne dépasse jamais la limite de temps demandée.
* Coût : bas = un appel de chaque source payante qui sera utilisée ; haut = ce que ces sources peuvent coûter AU PLUS dans les limites d'appels
  de la recherche. Les sources payantes que le plafond mensuel écarte n'y figurent pas, et on le dit."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote import budget, disjoncteur
from pilote import reglages as rg
from pilote.base import Recherche
from pilote.config import Config
from pilote.lancement import FOURCHETTE_GROSSIERE_S, _duree_phrase, limites
from pilote.moteur_sources import choisies


def _durees(fabrique: sessionmaker[Session], profondeur: str) -> list[float]:
    out: list[float] = []
    with fabrique() as s:
        for r in s.scalars(select(Recherche).where(Recherche.etat == "terminee").order_by(Recherche.cree_le.desc())):
            if (r.parametres or {}).get("test_reel") or (r.parametres or {}).get("profondeur", "") != profondeur or not (r.debut and r.fin):
                continue
            d = (r.fin - r.debut).total_seconds()
            if d > 0:
                out.append(d)
            if len(out) >= 10:
                break
    return out


def estimer(cfg: Config, fabrique: sessionmaker[Session], parametres: dict[str, Any]) -> dict[str, Any]:
    lim = limites(cfg, parametres)
    appels = int(lim["appels"])
    profondeur = lim["cran"]["id"]
    mesures = _durees(fabrique, profondeur)
    if len(mesures) >= 3:
        bas, haut, mesure = min(mesures), max(mesures), True
    else:
        bas, haut, mesure = appels * FOURCHETTE_GROSSIERE_S[0], appels * FOURCHETTE_GROSSIERE_S[1], False
    if lim["temps_s"]:
        haut = min(haut, float(lim["temps_s"]))
        bas = min(bas, haut)
    reg, _ = rg.charger_tolerant(cfg)
    voulues = choisies(cfg, parametres)
    en_pause = disjoncteur.en_pause(cfg, [d.id for d in voulues])  # une source en pause n'est pas appelée : elle ne coûte rien
    voulues = [d for d in voulues if d.id not in en_pause]
    noms = {d.id: d.nom for d in voulues}
    efficaces = [(d, rg.choix_source(reg, d)["cout"]) for d in voulues]
    plafond = budget.plafond_mensuel(cfg)
    depense = budget.depense_du_mois(fabrique)
    unites = budget.unites_du_mois(fabrique)
    ok, ecartees = budget.autoriser(efficaces, appels, plafond, depense, unites)
    cout_de = {d.id: c for d, c in efficaces}
    payantes = [d for d in ok if budget.cout_maximal(cout_de[d.id], appels, unites.get(d.id, 0.0)) > 0]
    bas_usd = round(sum(budget.dollars_pour(cout_de[d.id], 1, unites.get(d.id, 0.0)) for d in payantes), 6)
    haut_usd = round(sum(budget.cout_maximal(cout_de[d.id], appels, unites.get(d.id, 0.0)) for d in payantes), 6)
    atteint = depense >= plafond
    if not payantes:
        phrase_cout = "gratuit" + (" (le plafond mensuel est atteint : seules les sources gratuites sont utilisées)" if atteint else "")
    else:
        phrase_cout = f"de {bas_usd:.4f} $ à {haut_usd:.4f} $ au plus".replace(".", ",")
    message = ""
    if ecartees:
        message = ("Le plafond de dépense du mois ne laisse que les sources gratuites : " if atteint else "Le plafond de dépense du mois écarte des sources payantes : ") + ", ".join(noms.get(e["source"], e["source"]) for e in ecartees) + "."
    return {
        "appels": appels, "profondeur": profondeur, "sources": [d.id for d in ok],
        "temps": {"bas_s": round(bas), "haut_s": round(haut), "mesure": mesure,
                  "phrase": _duree_phrase(bas, haut) + ("" if mesure else " (estimation large : pas encore de recherche mesurée)")},
        "cout": {"bas_usd": bas_usd, "haut_usd": haut_usd, "phrase": phrase_cout, "sources_payantes": [d.id for d in payantes]},
        "plafond": {"mensuel_usd": plafond, "depense_usd": depense, "reste_usd": max(0.0, round(plafond - depense, 6)), "atteint": atteint},
        "sources_ecartees": ecartees, "sources_en_pause": list(en_pause), "limitee_aux_gratuites": bool(ecartees) and not payantes, "message": message,
    }  # fmt: skip
