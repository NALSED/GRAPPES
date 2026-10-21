"""`python -m pilote` (ou la commande `pilote`) : démarre le service avec la configuration."""

from __future__ import annotations

import argparse

import uvicorn

from pilote.app import creer_app
from pilote.config import charger
from pilote.tls import certificat


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pilote")
    p.add_argument("--config", help="fichier de configuration (défaut : PILOTE_CONFIG ou config/pilote.yaml)")
    args = p.parse_args(argv)
    cfg = charger(args.config)
    ssl: dict[str, str] = {}
    if cfg.service.https:
        cert, cle = certificat(cfg)
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(cle)}
    uvicorn.run(creer_app(cfg), host=cfg.service.hote, port=cfg.service.port, log_level="info", **ssl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
