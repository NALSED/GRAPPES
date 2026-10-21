#!/usr/bin/env bash
# Démarre l'interface web (pilote) au-dessus de grappes : `./lancer.sh`.
# Adresse par défaut : https://127.0.0.1:8443 (certificat auto-signé ; réglable dans pilote/config/pilote.yaml).
racine="$(cd "$(dirname "$0")" && pwd)"
[ -x "$racine/pilote/.venv/bin/python" ] || { echo "Lancer d'abord ./installer.sh" >&2; exit 1; }
cd "$racine/pilote" && exec .venv/bin/python -m pilote
