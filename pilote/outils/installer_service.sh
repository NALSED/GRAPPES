#!/usr/bin/env bash
# Installe le service systemd UTILISATEUR de pilote (aucun droit root) : `outils/installer_service.sh`.
# La racine est celle de ce dépôt ; rien n'est écrit en dur dans pilote.service.
set -euo pipefail
racine="$(cd "$(dirname "$0")/.." && pwd)"
cible="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
[ -x "$racine/.venv/bin/python" ] || python3 -m venv "$racine/.venv"
"$racine/.venv/bin/pip" -q install -e "$racine"
mkdir -p "$cible"
sed "s|%PILOTE_RACINE%|$racine|g" "$racine/pilote.service" > "$cible/pilote.service"
systemctl --user daemon-reload
systemctl --user enable --now pilote.service
systemctl --user --no-pager status pilote.service | head -5
