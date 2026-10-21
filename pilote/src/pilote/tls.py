"""HTTPS en option : certificat auto-signé créé au premier lancement (dossier `donnees/tls`), sauf certificat fourni."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pilote.config import Config


def certificat(cfg: Config) -> tuple[Path, Path]:
    """(certificat, clé). Ceux de la configuration s'ils sont donnés ; sinon un couple auto-signé, créé une fois."""
    if cfg.service.certificat and cfg.service.cle:
        return Path(cfg.service.certificat).expanduser(), Path(cfg.service.cle).expanduser()
    dossier = cfg.donnees / "tls"
    cert, cle = dossier / "pilote.crt", dossier / "pilote.key"
    if not (cert.exists() and cle.exists()):
        dossier.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "825", "-keyout", str(cle),
             "-out", str(cert), "-subj", "/CN=pilote", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
            check=True, capture_output=True,
        )  # fmt: skip
        cle.chmod(0o600)
    return cert, cle
