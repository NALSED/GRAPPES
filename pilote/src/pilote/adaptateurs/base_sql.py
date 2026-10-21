"""Base de données personnelle (SQLite), LECTURE SEULE et SELECT uniquement (fiche 11). Le fichier est ouvert en lecture seule par SQLite lui-même,
la requête doit être une seule instruction SELECT, et elle ne reçoit les mots cherchés que par paramètre lié (:q), jamais collés dans le texte
de la requête. Les colonnes rendues se nomment `nom`, et au choix `ville`, `genre`, `numero`, `site`, `pays`. Le niveau de confiance est fixé par
l'utilisateur dans la déclaration de la source."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs
from pilote.adaptateurs.api_json import convertir as _convertir

LIT_PARAMETRES = True
INTERDITS = re.compile(r"\b(attach|detach|pragma|insert|update|delete|drop|alter|create|replace|vacuum|reindex|load_extension)\b", re.IGNORECASE)


def verifier_requete(sql: str) -> str:
    """La requête telle qu'elle sera exécutée, ou un refus en français."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        raise ErreurSource("Écrivez la requête SELECT qui rend les noms.")
    if ";" in s:
        raise ErreurSource("Une seule instruction est permise.")
    if not re.match(r"^select\b", s, re.IGNORECASE) and not re.match(r"^with\b", s, re.IGNORECASE):
        raise ErreurSource("Seules les requêtes SELECT sont permises (lecture seule).")
    if INTERDITS.search(s):
        raise ErreurSource("Cette requête contient une instruction d'écriture ou de gestion : seule la lecture est permise.")
    return s


def lignes(parametres: dict[str, Any], q: str, limite: int) -> list[dict[str, Any]]:
    sql = verifier_requete(str(parametres.get("requete", "")))
    f = Path(str(parametres.get("base", ""))).expanduser()
    if not f.is_file():
        raise ErreurSource("Le fichier de la base est introuvable.")
    try:
        con = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            con.execute("PRAGMA query_only = ON")
            con.row_factory = sqlite3.Row
            cur = con.execute(sql, {"q": q, "q_like": f"%{q}%"} if ":q" in sql else {})
            return [dict(r) for r in cur.fetchmany(limite)]
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise ErreurSource(f"La base a refusé la requête : {exc}") from exc


def convertir(brut: Any, parametres: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _convertir(brut, {**(parametres or {}), "champs": {c: c for c in ("nom", "ville", "genre", "numero", "site", "pays")}, "liste": ""})


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    quoi = str(entree.get("quoi", "")).strip()
    mots = mots_significatifs(quoi, 3)
    if not quoi:
        return []
    client._avant()  # un appel compté, arrêt immédiat si demandé
    return convertir(lignes(parametres, " ".join(mots) or quoi, int(entree.get("limite") or 50)), parametres)
