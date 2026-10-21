"""Tâches de fond (fondation 2 de D70) : une recherche tourne dans un fil de travail, jamais dans la requête web.

Le gestionnaire reçoit un identifiant, passe la recherche « en cours », laisse un exécuteur travailler, puis note la fin.
L'exécuteur écrit ses résultats au fur et à mesure (candidats, avancement) : un arrêt ou un échec GARDE l'acquis.
Au démarrage du service, toute recherche restée « en cours » est marquée « interrompue » (le service s'est arrêté).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from pilote.base import ETATS_FINAUX, Candidat, Journal, Recherche, maintenant


class Arret(Exception):
    """Levée par l'exécuteur quand l'arrêt demandé est pris en compte."""


@dataclass(slots=True)
class ContexteRecherche:
    """Ce que voit l'exécuteur : le sujet, les paramètres, son dossier de travail et trois gestes."""

    recherche_id: str
    sujet: dict[str, Any]
    parametres: dict[str, Any]
    dossier: Path
    qui: str
    arret: threading.Event
    _fabrique: sessionmaker[Session] = field(repr=False)

    def doit_s_arreter(self) -> bool:
        return self.arret.is_set()

    def avancer(self, **champs: Any) -> None:
        """Dit où l'on en est (source en cours, appels faits sur prévus, noms collectés...)."""
        with self._fabrique.begin() as s:
            r = s.get(Recherche, self.recherche_id)
            assert r is not None
            r.avancement = {**(r.avancement or {}), **champs}

    def ajouter_candidats(self, lignes: list[dict[str, Any]]) -> int:
        """Écrit des noms trouvés (faits seulement). Rend le nombre écrit."""
        with self._fabrique.begin() as s:
            for ligne in lignes:
                s.add(Candidat(recherche_id=self.recherche_id, **ligne))
        return len(lignes)

    def depense_du_mois(self) -> tuple[float, dict[str, float]]:
        """(dollars, unités par source) déjà consommés ce mois-ci par toutes les recherches."""
        from pilote import budget

        return budget.depense_du_mois(self._fabrique), budget.unites_du_mois(self._fabrique)

    def enregistrer_couts(self, couts: dict[str, dict[str, float]]) -> None:
        """Garde ce que cette recherche a coûté (la dépense du mois en est la somme)."""
        with self._fabrique.begin() as s:
            r = s.get(Recherche, self.recherche_id)
            assert r is not None
            r.couts = couts

    def noter(self, evenement: str, **detail: Any) -> None:
        with self._fabrique.begin() as s:
            s.add(Journal(recherche_id=self.recherche_id, qui=self.qui, evenement=evenement, detail=detail))


class Executeur(Protocol):
    def __call__(self, ctx: ContexteRecherche) -> None: ...


class ExecuteurNonBranche:
    """Exécuteur par défaut de l'étape 1 : la liaison avec grappes arrive à l'étape 3."""

    def __call__(self, ctx: ContexteRecherche) -> None:
        raise NotImplementedError("Le lancement réel d'une recherche n'est pas encore branché à grappes.")


class Gestionnaire:
    def __init__(self, fabrique: sessionmaker[Session], dossier_de: Callable[[str], Path], executeur: Executeur, fils: int = 2):
        self.fabrique, self.dossier_de, self.executeur = fabrique, dossier_de, executeur
        self.pool = ThreadPoolExecutor(max_workers=max(1, fils), thread_name_prefix="recherche")
        self._arrets: dict[str, threading.Event] = {}
        self._futurs: dict[str, Future] = {}
        self._verrou = threading.Lock()

    def reprendre_apres_arret_du_service(self) -> int:
        """Recherches restées en attente ou en cours quand le service s'est arrêté : « interrompue » (acquis gardé)."""
        n = 0
        with self.fabrique.begin() as s:
            for r in s.query(Recherche).filter(Recherche.etat.in_(("en_attente", "en_cours"))):
                r.etat, r.fin = "interrompue", maintenant()
                r.message = "Le service s'est arrêté pendant cette recherche ; ce qui avait été trouvé est gardé."
                s.add(Journal(recherche_id=r.id, qui="systeme", evenement="interrompue_au_redemarrage", detail={}))
                n += 1
        return n

    def lancer(self, recherche_id: str) -> None:
        """Une recherche déjà confiée au pool n'est pas relancée : deux fils sur le même dossier se marcheraient dessus, et
        le second remplacerait l'événement d'arrêt du premier (l'arrêt n'en arrêterait plus qu'un)."""
        arret = threading.Event()
        with self._verrou:
            if recherche_id in self._arrets:
                return
            self._arrets[recherche_id] = arret
            self._futurs[recherche_id] = self.pool.submit(self._executer, recherche_id, arret)

    def demander_arret(self, recherche_id: str) -> bool:
        with self._verrou:
            ev = self._arrets.get(recherche_id)
        if ev is None:
            return False
        ev.set()
        return True

    def attendre(self, recherche_id: str, delai: float | None = None) -> None:
        with self._verrou:
            f = self._futurs.get(recherche_id)
        if f is not None:
            f.result(timeout=delai)

    def _executer(self, recherche_id: str, arret: threading.Event) -> None:
        with self.fabrique.begin() as s:
            r = s.get(Recherche, recherche_id)
            assert r is not None
            if r.etat in ETATS_FINAUX:
                return
            r.etat, r.debut, r.message = "en_cours", maintenant(), "La recherche est en cours."
            sujet, params, qui = dict(r.sujet or {}), dict(r.parametres or {}), r.qui
            s.add(Journal(recherche_id=recherche_id, qui=qui, evenement="debut", detail={}))
        dossier = self.dossier_de(recherche_id)
        dossier.mkdir(parents=True, exist_ok=True)
        ctx = ContexteRecherche(recherche_id, sujet, params, dossier, qui, arret, self.fabrique)
        etat, message = "terminee", "La recherche est terminée."
        try:
            if arret.is_set():
                raise Arret()
            self.executeur(ctx)
            if arret.is_set():
                etat, message = "arretee", "Vous avez arrêté la recherche ; ce qui avait été trouvé est gardé."
        except Arret:
            etat, message = "arretee", "Vous avez arrêté la recherche ; ce qui avait été trouvé est gardé."
        except Exception as exc:  # noqa: BLE001 - toute panne d'un exécuteur doit finir en état « échec » lisible
            etat, message = "echec", f"La recherche s'est arrêtée sur une panne : {exc}"
        with self.fabrique.begin() as s:
            r = s.get(Recherche, recherche_id)
            assert r is not None
            r.etat, r.fin, r.message = etat, maintenant(), message
            s.add(Journal(recherche_id=recherche_id, qui=qui, evenement="fin", detail={"etat": etat}))
        with self._verrou:
            self._arrets.pop(recherche_id, None)
            self._futurs.pop(recherche_id, None)  # sinon un Future par recherche restait en mémoire tant que le service tourne

    def fermer(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
