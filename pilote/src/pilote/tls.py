"""HTTPS en option : certificat auto-signé créé au premier lancement (dossier `donnees/tls`), sauf certificat fourni."""

from __future__ import annotations

import ipaddress
import shutil
import socket
import subprocess
from pathlib import Path

from pilote.config import Config


class TlsIndisponible(RuntimeError):
    """Message en français, prêt à être montré : il manque `openssl` sur la machine."""


def _noms_de_la_machine(cfg: Config) -> list[str]:
    """Les noms et adresses à mettre dans le certificat : la boucle locale, le nom de la machine, l'adresse d'écoute et les hôtes
    autorisés de la configuration. Sans eux, un certificat qui ne porte que « localhost » est inutilisable depuis un autre poste."""
    noms = ["DNS:localhost", "IP:127.0.0.1"]
    vus = set(noms)

    def ajouter(valeur: str) -> None:
        v = (valeur or "").strip()
        if not v or v in ("0.0.0.0", "::", "localhost", "127.0.0.1"):  # noqa: S104 - 0.0.0.0 n'est pas un nom de certificat
            return
        try:
            entree = f"IP:{ipaddress.ip_address(v)}"
        except ValueError:
            entree = f"DNS:{v}"
        if entree not in vus:
            vus.add(entree)
            noms.append(entree)

    ajouter(cfg.service.hote)
    for h in cfg.service.hotes_autorises or []:
        ajouter(str(h))
    try:
        hote = socket.gethostname()
        ajouter(hote)
        ajouter(socket.gethostbyname(hote))  # l'adresse de la VM sur le réseau : c'est par elle qu'on l'atteint
    except OSError:
        pass
    return noms


def certificat(cfg: Config) -> tuple[Path, Path]:
    """(certificat, clé). Ceux de la configuration s'ils sont donnés ; sinon un couple auto-signé, créé une fois."""
    if cfg.service.certificat and cfg.service.cle:
        return Path(cfg.service.certificat).expanduser(), Path(cfg.service.cle).expanduser()
    dossier = cfg.donnees / "tls"
    cert, cle = dossier / "pilote.crt", dossier / "pilote.key"
    if not (cert.exists() and cle.exists()):
        if not shutil.which("openssl"):  # image minimale : dit en français, au lieu d'un FileNotFoundError au démarrage
            raise TlsIndisponible(
                "openssl est absent : il sert à créer le certificat du service. Installez-le (« sudo apt-get install openssl »), "
                "ou donnez votre propre certificat dans service.certificat / service.cle, ou mettez service.https à faux."
            )
        dossier.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "825", "-keyout", str(cle),
                 "-out", str(cert), "-subj", "/CN=pilote", "-addext", f"subjectAltName={','.join(_noms_de_la_machine(cfg))}"],
                check=True, capture_output=True,
            )  # fmt: skip
        except subprocess.CalledProcessError as exc:
            raise TlsIndisponible(f"openssl n'a pas pu créer le certificat : {(exc.stderr or b'').decode('utf-8', 'replace').strip()[:200]}") from exc
        cle.chmod(0o600)
    return cert, cle
