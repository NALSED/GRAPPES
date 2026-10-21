"""Budget (fiche 01) : un plafond de dépense mensuel global, en dollars. Toutes les unités déclarées (crédit, jeton, requête...)
sont converties vers cette unique unité. La dépense du mois est la somme de ce que les recherches du mois ont coûté."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote import reglages as rg
from pilote.base import Recherche
from pilote.config import Config
from pilote.sources import Declaration


def plafond_mensuel(cfg: Config) -> float:
    """Le plafond en dollars, jamais en erreur : un fichier retouché à la main reprend le plafond par défaut."""
    return rg._nombre_tolerant(rg.charger_tolerant(cfg)[0].get("budget", {}).get("plafond_mensuel_usd"), float(rg.DEFAUT["budget"]["plafond_mensuel_usd"]), 0.0)


def debut_du_mois(maint: datetime | None = None) -> datetime:
    m = maint or datetime.now(UTC)
    return m.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def depense_du_mois(fabrique: sessionmaker[Session], maint: datetime | None = None) -> float:
    debut = debut_du_mois(maint)
    total = 0.0
    with fabrique() as s:
        for r in s.scalars(select(Recherche).where(Recherche.cree_le >= debut)):
            total += sum(float(v.get("dollars", 0) or 0) for v in (r.couts or {}).values())
    return round(total, 6)


def vue(cfg: Config, fabrique: sessionmaker[Session]) -> dict[str, Any]:
    plafond = plafond_mensuel(cfg)
    dep = depense_du_mois(fabrique)
    return {"plafond_mensuel_usd": plafond, "depense_du_mois_usd": dep, "reste_usd": max(0.0, round(plafond - dep, 6)), "atteint": dep >= plafond}


def cout_phrase(d: Declaration, cout: dict[str, Any]) -> str:
    """Le coût d'une source en français courant : « gratuit », ou « 1 crédit par appel, soit 0,008 $ ; 1 000 gratuits par mois »."""
    unite, taux, par = cout.get("unite", "appel"), float(cout.get("vers_dollar", 0) or 0), float(cout.get("par_appel", 1) or 0)
    gratuit = float(cout.get("gratuit_par_mois", 0) or 0)
    if taux <= 0 or par <= 0:
        return "gratuit"
    dollars = par * taux
    base = f"{par:g} {unite} par appel, soit environ {dollars:.4f} $".replace(".", ",")
    return base + (f" ; {gratuit:,.0f} gratuits par mois".replace(",", " ") if gratuit else "")


def dollars_pour(cout: dict[str, Any], appels: int, deja_utilises_ce_mois: float = 0.0) -> float:
    """Dollars que coûteront `appels` appels, après le quota gratuit du mois (en unités)."""
    taux, par = float(cout.get("vers_dollar", 0) or 0), float(cout.get("par_appel", 1) or 0)
    gratuit = max(0.0, float(cout.get("gratuit_par_mois", 0) or 0) - deja_utilises_ce_mois)
    unites = appels * par
    payantes = max(0.0, unites - gratuit)
    return round(payantes * taux, 6)


def unites_du_mois(fabrique: sessionmaker[Session], maint: datetime | None = None) -> dict[str, float]:
    """Unités déjà consommées ce mois-ci, par source (pour le quota gratuit mensuel)."""
    debut = debut_du_mois(maint)
    out: dict[str, float] = {}
    with fabrique() as s:
        for r in s.scalars(select(Recherche).where(Recherche.cree_le >= debut)):
            for sid, v in (r.couts or {}).items():
                out[sid] = out.get(sid, 0.0) + float(v.get("unites", 0) or 0)
    return out


def cout_maximal(cout: dict[str, Any], appels_max: int, unites_deja: float) -> float:
    """Ce que la source peut coûter AU PLUS dans une recherche limitée à `appels_max` appels (pire cas : tous les appels sur elle)."""
    return dollars_pour(cout, appels_max, unites_deja)


def autoriser(sources: list[tuple[Declaration, dict[str, Any]]], appels_max: int, plafond: float, depense: float,
              unites: dict[str, float]) -> tuple[list[Declaration], list[dict[str, str]]]:  # fmt: skip
    """Sépare les sources utilisables des sources écartées par le plafond. Une source GRATUITE passe toujours. Une source payante passe
    seulement si son coût maximal tient dans ce qui reste du plafond du mois ; au plafond atteint, il ne reste que les gratuites."""
    reste = max(0.0, plafond - depense)
    ok: list[Declaration] = []
    refusees: list[dict[str, str]] = []
    for d, cout in sources:
        pire = cout_maximal(cout, appels_max, unites.get(d.id, 0.0))
        if pire <= 0:
            ok.append(d)
        elif depense >= plafond:  # le nom lisible, jamais l'identifiant technique : c'est ce que la page affiche
            refusees.append({"source": d.id, "nom": d.nom, "raison": f"le plafond de {plafond:g} $ par mois est atteint : seules les sources gratuites sont utilisées"})
        elif pire > reste:
            refusees.append({"source": d.id, "nom": d.nom, "raison": f"elle pourrait coûter jusqu'à {pire:.2f} $ et il ne reste que {reste:.2f} $ sur le plafond du mois".replace(".", ",")})
        else:
            ok.append(d)
    return ok, refusees


def couts_de_la_recherche(sources: dict[str, tuple[Declaration, dict[str, Any]]], appels_par_source: dict[str, int], unites_deja: dict[str, float]) -> dict[str, dict[str, float]]:
    """Ce que la recherche a RÉELLEMENT coûté, source par source (seulement les sources payantes), d'après le nombre exact d'appels."""
    out: dict[str, dict[str, float]] = {}
    for sid, n in appels_par_source.items():
        if sid not in sources:
            continue
        cout = sources[sid][1]
        par = float(cout.get("par_appel", 1) or 0)
        if float(cout.get("vers_dollar", 0) or 0) <= 0 or par <= 0:
            continue
        out[sid] = {"unites": n * par, "dollars": dollars_pour(cout, n, unites_deja.get(sid, 0.0))}
    return out
