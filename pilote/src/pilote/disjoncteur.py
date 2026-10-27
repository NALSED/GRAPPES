"""Protection pendant les recherches (fiche 11) : le bilan de ce que chaque source a fait, et le DISJONCTEUR (méthode classique du « circuit breaker »).

* Après chaque recherche, on lit ce que les sources ont rendu (fichier d'avancement de grappes). Une source qui répond remet son compteur à zéro ;
  une source qui échoue l'augmente. Au SEUIL d'échecs de suite, elle est mise en pause : les recherches suivantes l'écartent sans l'appeler
  (elle ne bloque plus rien), et on le dit (« Apify en pause : 3 erreurs de suite »).
* **Reprise automatique après un délai** (décision de Sednal, 20/10) : passé `DELAI_REPRISE_S`, une source en pause est de nouveau ESSAYÉE à la
  recherche suivante — sans rien écrire au disque pour autant (`en_pause` reste une lecture pure ; l'état n'est modifié que quand une recherche
  l'appelle réellement). Si elle répond, `bilan` lève la pause ; si elle échoue encore, `bilan` la remet en pause avec une date fraîche.
  La reprise manuelle (`reprendre`, geste de l'utilisateur) reste disponible à tout moment, immédiate, sans attendre le délai.
* Le bilan dit combien de sources ont répondu sur combien ont été utilisées, pour qu'un résultat où une source a échoué en silence ne ressemble
  jamais à un résultat complet."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pilote import etat_sources
from pilote.config import Config

SEUIL = 3
DELAI_REPRISE_S = 20 * 60  # 20 minutes : assez court pour se remettre d'une panne passagère, assez long pour ne pas marteler un service vraiment en panne


def _expiree(d: dict[str, Any]) -> bool:
    """Vrai si le délai de reprise automatique est passé depuis la mise en pause. Lecture pure : n'écrit rien."""
    try:
        depuis = datetime.fromisoformat(str(d["depuis"]))
    except (KeyError, ValueError):
        return False
    return (datetime.now(UTC) - depuis).total_seconds() >= DELAI_REPRISE_S


def phrase_raison(raison: str) -> str:
    """Une panne dite en français : « guardian : HTTP 401 » ne dit pas quoi faire ; « la clé est refusée » si."""
    import re

    m = re.search(r"HTTP (\d{3})", raison)
    code = m.group(1) if m else ""
    if code in ("401", "403"):
        return f"La clé d'API est refusée par la source (HTTP {code}) : vérifiez-la dans Réglages."
    if code == "402":
        return "Les crédits de la source sont épuisés (HTTP 402)."
    if code == "429":
        return "La source demande d'attendre (HTTP 429) : trop d'appels."
    return raison


def issues(fichier: Path, jetons: dict[str, str]) -> dict[str, dict[str, str]]:
    """source -> {ok|echec, raison}, d'après le fichier d'avancement. Une source dont aucune prise n'a dit ni oui ni non n'y figure pas."""
    par_source: dict[str, dict[str, str]] = {}
    if not fichier.exists():
        return par_source
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        sid = jetons.get(str(e.get("prise", "")))
        if not sid:
            continue
        ev = e.get("evenement")
        if ev == "source_ok":
            par_source[sid] = {"issue": "ok", "raison": ""}
        elif ev == "source_echec":
            par_source[sid] = {"issue": "echec", "raison": phrase_raison(str(e.get("raison", "")) or "la source n'a pas répondu")}
        elif ev == "prise_fin":
            st = str(e.get("statut", ""))
            if st == "ok":
                if par_source.get(sid, {}).get("issue") != "echec":
                    par_source[sid] = {"issue": "ok", "raison": ""}
            elif st.startswith("non appelée"):  # on ne l'a pas interrogée (ex. saisie faite d'emoji qu'elle ne cherche pas) : ni répondu, ni en échec
                par_source.setdefault(sid, {"issue": "non_appelee", "raison": st})
            elif st.startswith(("erreur", "quota")) or (st.startswith("arrêté") and re.search(r"HTTP (401|403)", st)):  # une clé refusée arrête la source pour le cycle : c'est un échec, pas un succès
                par_source[sid] = {"issue": "echec", "raison": phrase_raison(st.partition(" : ")[2] or st)}
    return par_source


def bilan(cfg: Config, fichier: Path, jetons: dict[str, str], utilisees: list[str], noms: dict[str, str]) -> dict[str, Any]:
    """Met à jour les compteurs et le disjoncteur de chaque source utilisée, et rend le bilan de la recherche."""
    resultat = issues(fichier, jetons)
    etats = etat_sources.lire(cfg)
    repondu, echecs, nouvelles_pauses, non_appelees = 0, [], [], 0
    for sid in utilisees:
        r = resultat.get(sid)
        if r is None:
            repondu += 1  # aucune panne signalée : comptée comme ayant répondu
            continue
        if r["issue"] == "non_appelee":
            non_appelees += 1
            continue
        e = etats.get(sid, {})
        if r["issue"] == "ok":
            repondu += 1
            if e.get("erreurs_de_suite") or e.get("disjoncteur"):  # une source rappelée après reprise automatique qui répond lève sa pause
                etat_sources.noter(cfg, sid, erreurs_de_suite=0, disjoncteur=None)
            continue
        n = int(e.get("erreurs_de_suite", 0)) + 1
        champs: dict[str, Any] = {"erreurs_de_suite": n, "derniere_erreur": {"le": etat_sources.maintenant_iso(), "raison": r["raison"]}}
        if n >= SEUIL:
            # toujours réarmée, même si une pause y figurait déjà (reprise automatique expirée : on vient de la retenter, elle rate encore)
            champs["disjoncteur"] = {"depuis": etat_sources.maintenant_iso(), "raison": f"{n} erreurs de suite"}
            nouvelles_pauses.append({"source": sid, "nom": noms.get(sid, sid), "raison": f"{n} erreurs de suite"})
        etat_sources.noter(cfg, sid, **champs)
        echecs.append({"source": sid, "nom": noms.get(sid, sid), "raison": r["raison"]})
    total = len(utilisees) - non_appelees  # une source qu'on n'a pas interrogée n'a ni répondu ni manqué à répondre
    phrase = f"{repondu} source{'s' if repondu > 1 else ''} sur {total} {'ont' if repondu > 1 else 'a'} répondu" if total else "Aucune source n'a été utilisée"
    return {"repondu": repondu, "total": total, "phrase": phrase, "echecs": echecs, "nouvelles_pauses": nouvelles_pauses}


def en_pause(cfg: Config, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Les sources encore en pause MAINTENANT (le délai de reprise automatique n'est pas écarté) : ni plus ni moins que ce qui doit être
    écarté des appels de cette recherche. Lecture pure : une source dont le délai est passé n'y figure plus, mais rien n'est écrit — elle
    ne redevient « active » pour de bon que si elle répond vraiment (voir `bilan`)."""
    etats = etat_sources.lire(cfg)
    out = {}
    for i in ids:
        d = etats.get(i, {}).get("disjoncteur")
        if d and not _expiree(d):
            out[i] = d
    return out


def reprise_dans_s(d: dict[str, Any]) -> float:
    """Pour l'affichage (Réglages) : secondes avant la reprise automatique, 0 si déjà passé. Ne modifie rien."""
    try:
        depuis = datetime.fromisoformat(str(d["depuis"]))
    except (KeyError, ValueError):
        return 0.0
    return max(0.0, DELAI_REPRISE_S - (datetime.now(UTC) - depuis).total_seconds())


def reprendre(cfg: Config, sid: str) -> None:
    etat_sources.noter(cfg, sid, erreurs_de_suite=0, disjoncteur=None)
