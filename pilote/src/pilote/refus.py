"""Un réglage cassé est refusé AVANT écriture, avec la raison en français (règle 3 du cadre)."""

from __future__ import annotations

import contextlib
import os
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

_VERROUS: dict[str, threading.Lock] = {}
_VERROU_DES_VERROUS = threading.Lock()


class ConfigRefusee(ValueError):
    """Le message est une phrase en français courant, affichable telle quelle."""


@contextlib.contextmanager
def verrou(chemin: Path) -> Iterator[None]:
    """Protège un « lire, modifier, écrire » sur un fichier de configuration : sans lui, deux requêtes qui se recouvrent
    écrivent chacune à partir d'un état lu avant l'autre, et le premier changement est perdu en silence.

    Deux niveaux : un verrou de fil pour les requêtes du service (un seul processus, plusieurs fils), et un verrou de
    fichier pour un autre processus (ligne de commande, test). Un système sans `fcntl` garde le verrou de fil."""
    with _VERROU_DES_VERROUS:
        v = _VERROUS.setdefault(str(chemin.resolve() if chemin.parent.exists() else chemin), threading.Lock())
    with v:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - systèmes sans fcntl
            yield
            return
        chemin.parent.mkdir(parents=True, exist_ok=True)
        f = chemin.with_name(chemin.name + ".verrou")
        with f.open("a+") as poignee:
            fcntl.flock(poignee.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(poignee.fileno(), fcntl.LOCK_UN)


def ecrire_atomique(chemin: Path, texte: str) -> None:
    """Écrit sans jamais laisser un fichier à moitié écrit : fichier temporaire, puis remplacement."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=chemin.parent, prefix=chemin.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texte)
        if chemin.exists():
            os.chmod(tmp, chemin.stat().st_mode & 0o777)
        os.replace(tmp, chemin)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def lire_yaml(chemin: Path) -> dict[str, Any]:
    try:
        y = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        ligne = getattr(getattr(exc, "problem_mark", None), "line", None)
        où = f" (ligne {ligne + 1})" if ligne is not None else ""
        raise ConfigRefusee(f"Le fichier {chemin.name} est illisible{où} : ce n'est pas du YAML valide.") from exc
    except OSError as exc:
        raise ConfigRefusee(f"Le fichier {chemin.name} ne peut pas être lu.") from exc
    if y is None:
        return {}
    if not isinstance(y, dict):
        raise ConfigRefusee(f"Le fichier {chemin.name} doit contenir une liste de réglages (clé: valeur).")
    return y


def yaml_texte(d: dict[str, Any], entete: str = "") -> str:
    return entete + yaml.safe_dump(d, allow_unicode=True, sort_keys=False)
