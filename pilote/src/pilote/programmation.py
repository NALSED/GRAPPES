"""Lancements datés et récurrents : un petit planificateur qui regarde l'heure et crée de NOUVELLES recherches."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pilote.base import Journal, Programme, Recherche, maintenant
from pilote.lancement import libelle_quand, phrase_du_sujet, prochaine_occurrence

log = logging.getLogger(__name__)


def creer_programme(fabrique: sessionmaker[Session], sujet: dict[str, Any], parametres: dict[str, Any], quand: dict[str, Any], qui: str) -> str:
    phrase = phrase_du_sujet(sujet)
    prochaine = prochaine_occurrence(quand, maintenant())
    if prochaine is None:
        from pilote.lancement import LancementInvalide

        raise LancementInvalide("Cette date est déjà passée.")
    with fabrique.begin() as s:
        p = Programme(qui=qui, libelle=f"{phrase} — {libelle_quand(quand)}", sujet=sujet, parametres=parametres, quand=quand, prochaine=prochaine)
        s.add(p)
        s.flush()
        s.add(Journal(recherche_id=None, qui=qui, evenement="programme_cree", detail={"programme": p.id, "quand": libelle_quand(quand)}))
        return p.id


def echeances(fabrique: sessionmaker[Session], lancer: Callable[[str], None], maint=None, verification: Callable[[], bool] = lambda: True) -> list[str]:
    """Déclenche les programmes échus : une nouvelle recherche chacun, puis calcule la prochaine échéance (ou éteint un
    lancement daté). Rend les identifiants des recherches créées."""
    maint = maint or maintenant()
    crees: list[str] = []
    with fabrique.begin() as s:
        for p in s.scalars(select(Programme).where(Programme.actif.is_(True))):
            if p.prochaine is None or p.prochaine.replace(tzinfo=maint.tzinfo) > maint:
                continue
            params = {**p.parametres, "programme": p.id}
            if params.get("verification") is None:
                params["verification"] = verification()
            r = Recherche(qui=p.qui, sujet=p.sujet, parametres=params)
            s.add(r)
            s.flush()
            s.add(Journal(recherche_id=r.id, qui=p.qui, evenement="creation", detail={"programme": p.id}))
            p.derniere_recherche_id = r.id
            suivante = prochaine_occurrence(p.quand, maint)
            p.prochaine, p.actif = suivante, suivante is not None
            crees.append(r.id)
    for rid in crees:
        lancer(rid)
    return crees


class Planificateur:
    """Les lancements datés et récurrents passent par un VRAI planificateur de tâches (APScheduler), pas par une boucle maison : une seule
    tâche est armée, à l'heure de la prochaine échéance de tous les lancements programmés ; quand elle sonne, les lancements échus partent,
    puis la tâche est réarmée pour la suivante. Les échéances sont dans la base : au redémarrage rien n'est perdu, et un lancement échu
    pendant l'arrêt part tout de suite. `pas_s` n'est gardé que pour la compatibilité."""

    TACHE = "prochaine-echeance"

    def __init__(self, fabrique: sessionmaker[Session], lancer: Callable[[str], None], pas_s: float = 20.0, verification: Callable[[], bool] = lambda: True):
        from apscheduler.schedulers.background import BackgroundScheduler

        self.fabrique, self.lancer, self.verification = fabrique, lancer, verification
        self.planif = BackgroundScheduler(timezone=UTC, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": None})

    def demarrer(self) -> None:
        if not self.planif.running:
            self.planif.start()
        self.sonner()

    def arreter(self) -> None:
        if self.planif.running:
            self.planif.shutdown(wait=False)

    def sonner(self) -> None:
        """Lance les échéances échues, puis réarme la tâche. Ne lève jamais."""
        try:
            echeances(self.fabrique, self.lancer, verification=self.verification)
        except Exception:
            log.exception("planificateur : échéance en erreur")
        self.replanifier()

    def replanifier(self) -> None:
        """Arme (ou désarme) la tâche pour la plus proche échéance des lancements actifs. À rappeler quand un lancement est créé ou repris."""
        from apscheduler.triggers.date import DateTrigger

        if not self.planif.running:
            return
        with self.fabrique() as s:
            prochaines = [p.prochaine for p in s.scalars(select(Programme).where(Programme.actif.is_(True))) if p.prochaine is not None]
        if self.planif.get_job(self.TACHE) is not None:
            self.planif.remove_job(self.TACHE)
        if prochaines:
            quand = min(prochaines).replace(tzinfo=UTC) if min(prochaines).tzinfo is None else min(prochaines)
            self.planif.add_job(self.sonner, DateTrigger(run_date=max(quand, datetime.now(UTC))), id=self.TACHE, replace_existing=True)
