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
# Sans « linger », un service UTILISATEUR s'arrête à la déconnexion : sur un serveur ou une VM qu'on quitte en fermant
# le SSH, pilote mourait avec la session. On le demande ici (seul endroit qui a besoin de root, et il peut être refusé).
if ! loginctl show-user "$(id -un)" 2>/dev/null | grep -q "Linger=yes"; then
  if sudo -n true 2>/dev/null || [ -t 0 ]; then
    sudo loginctl enable-linger "$(id -un)" && echo "« linger » activé : le service survit à la déconnexion." \
      || echo "ATTENTION : « linger » n'a pas pu être activé ; pilote s'arrêtera à la déconnexion (sudo loginctl enable-linger $(id -un))." >&2
  else
    echo "ATTENTION : activez « linger » pour que pilote survive à la déconnexion : sudo loginctl enable-linger $(id -un)" >&2
  fi
fi
systemctl --user --no-pager status pilote.service | head -5
