"""Clés d'API (règle 2 du cadre) : elles restent dans `config/secrets.env`, jamais dans un fichier de configuration et jamais
envoyées au navigateur. Le reste du programme ne voit que « présente » ou « absente »."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, verrou

_LIGNE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_NOM = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_LU: dict[tuple[str, int, int], dict[str, str]] = {}  # (fichier, date de modification, taille) -> clés lues


def _lire_fichier(f: Path) -> dict[str, str]:
    """Clés d'un fichier, gardées en mémoire tant que le fichier ne change pas : la page Réglages demande « présente ou
    absente » deux fois par source, ce qui relisait les fichiers quatre-vingts fois par affichage."""
    try:
        st = f.stat()
    except OSError:
        return {}
    cle = (str(f), st.st_mtime_ns, st.st_size)
    if cle in _LU:
        return _LU[cle]
    out: dict[str, str] = {}
    try:
        for ligne in f.read_text(encoding="utf-8").splitlines():
            if not ligne.strip() or ligne.lstrip().startswith("#"):
                continue
            m = _LIGNE.match(ligne)
            if m:
                out[m.group(1)] = m.group(2).strip("'\"")
    except OSError:
        return {}
    if len(_LU) > 8:
        _LU.clear()
    _LU[cle] = out
    return out


def valeur(cfg: Config, nom: str) -> str:
    """La valeur d'une clé — pour l'exécuteur seulement, jamais pour une réponse de l'API."""
    for f in cfg.fichiers_secrets:
        v = _lire_fichier(f).get(nom)
        if v:
            return v
    return os.environ.get(nom, "")


def presente(cfg: Config, nom: str) -> bool:
    return bool(nom) and bool(valeur(cfg, nom))


def ecrire(cfg: Config, nom: str, valeur_: str) -> None:
    """Ajoute ou remplace une clé dans le fichier de clés de pilote (droits 600). Refuse un nom ou une valeur impossible."""
    if not _NOM.match(nom):
        raise ConfigRefusee("Le nom de la clé doit s'écrire en majuscules et tirets bas, comme MA_CLE_API.")
    v = valeur_.strip()
    if not v or "\n" in v or "\r" in v:
        raise ConfigRefusee("La clé est vide ou contient un retour à la ligne : collez-la sur une seule ligne.")
    f = cfg.fichiers_secrets[0]
    with verrou(f):  # deux clés enregistrées en même temps : sans verrou, la seconde écrasait la première
        lignes = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
        nouvelles, vu = [], False
        for ligne in lignes:
            m = _LIGNE.match(ligne)
            if m and m.group(1) == nom:
                nouvelles.append(f"{nom}={v}")
                vu = True
            else:
                nouvelles.append(ligne)
        if not vu:
            nouvelles.append(f"{nom}={v}")
        ecrire_atomique(f, "\n".join(nouvelles) + "\n")
        f.chmod(stat.S_IRUSR | stat.S_IWUSR)


def toutes_presentes(cfg: Config, noms: list[str]) -> bool:
    return bool(noms) and all(presente(cfg, n) for n in noms)


def manquantes(cfg: Config, noms: list[str]) -> list[str]:
    return [n for n in noms if not presente(cfg, n)]
