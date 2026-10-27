"""Fixtures communes : une COPIE de la configuration livrée dans un dossier temporaire (jamais la vraie), avec ses données à part."""

import shutil
from pathlib import Path

import pytest
import yaml

from pilote.config import RACINE, charger


def copier_config(dest: Path, grappes_secrets: str = "", **surcharges) -> Path:
    """Copie `config/` dans `dest/config` et rend le chemin de `pilote.yaml`. `surcharges` : sections de pilote.yaml à remplacer."""
    shutil.copytree(RACINE / "config", dest / "config", ignore=shutil.ignore_patterns("secrets.env", "reglages.yaml", "presets_perso"))
    shutil.copytree(RACINE / "classements", dest / "classements")  # les classements livrés sont relatifs à la racine du projet
    f = dest / "config" / "pilote.yaml"
    y = yaml.safe_load(f.read_text(encoding="utf-8"))
    y["service"]["https"] = False
    y["service"]["hotes_autorises"] = ["testserver"]  # le nom d'hôte du client de test (l'application n'accepte que la boucle locale)
    y.pop("suite", None)  # jamais le vrai service de traduction de la machine : un test qui en veut un le passe en surcharge
    y["donnees"].pop("copies", None)  # jamais le vrai disque des copies : elles vont dans le dossier temporaire du test
    y["grappes"]["secrets"] = grappes_secrets
    for k, v in surcharges.items():
        y[k] = {**y.get(k, {}), **v} if isinstance(v, dict) else v
    f.write_text(yaml.safe_dump(y, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return f


@pytest.fixture
def cfg(tmp_path):
    return charger(copier_config(tmp_path))


# --- Navigateur de TEST (jamais dans l'application) : vérifier les pages à l'œil, au clavier, en niveaux de gris. Sauté s'il est absent
# (voir outils/installer_navigateur_test.sh).
@pytest.fixture(scope="session")
def chromium():
    import os

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright absent (outils/installer_navigateur_test.sh)")
    libs = Path(os.environ.get("PILOTE_LIBS") or Path.home() / ".cache/pilote-libs/usr/lib/x86_64-linux-gnu")
    if libs.is_dir():
        os.environ["LD_LIBRARY_PATH"] = f"{libs}:{os.environ.get('LD_LIBRARY_PATH', '')}"
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"navigateur de test indisponible : {str(exc)[:120]}")
        yield b
        b.close()


@pytest.fixture
def serveur_vivant():
    """Lance l'application sur un port libre, dans un fil de travail, pour un navigateur de test. Rend `(url, arreter)` pour une app donnée."""
    import socket
    import threading
    import time

    import uvicorn

    arrets = []

    def lancer(app):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
        fil = threading.Thread(target=serveur.run, daemon=True)
        fil.start()
        t0 = time.time()
        while not serveur.started and time.time() - t0 < 20:
            time.sleep(0.05)
        arrets.append((serveur, fil))
        return f"http://127.0.0.1:{port}"

    yield lancer
    for serveur, fil in arrets:
        serveur.should_exit = True
        fil.join(timeout=10)
