#!/usr/bin/env bash
# Installe SearXNG (méta-moteur libre, auto-hébergé) pour le preset Web : dépôt + environnement + réglages + service systemd UTILISATEUR.
# Idempotent. Aucun droit root. Écoute sur 127.0.0.1 seulement. Port : variable SEARXNG_PORT (défaut 8888).
set -euo pipefail
racine="$(cd "$(dirname "$0")/.." && pwd)"
cible="$racine/outils/searxng"
port="${SEARXNG_PORT:-8888}"
if curl -fs "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then echo "SearXNG répond déjà sur le port $port : rien à installer."; exit 0; fi
mkdir -p "$cible"
[ -d "$cible/src/.git" ] || git clone --depth 1 https://github.com/searxng/searxng.git "$cible/src"
[ -x "$cible/venv/bin/python" ] || python3 -m venv "$cible/venv"
"$cible/venv/bin/pip" -q install -U pip setuptools wheel
"$cible/venv/bin/pip" -q install -r "$cible/src/requirements.txt" -r "$cible/src/requirements-server.txt"
"$cible/venv/bin/pip" -q install --use-pep517 --no-build-isolation -e "$cible/src"
if [ ! -f "$cible/settings.yml" ]; then
  cle="$("$cible/venv/bin/python" -c 'import secrets;print(secrets.token_hex(32))')"
  sed -e "s|__CLE__|$cle|" -e "s|__PORT__|$port|" "$racine/outils/searxng.settings.modele.yml" > "$cible/settings.yml"
  chmod 600 "$cible/settings.yml"
fi
unite="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$unite"
sed -e "s|%CIBLE%|$cible|g" "$racine/outils/searxng.service" > "$unite/searxng.service"
systemctl --user daemon-reload
systemctl --user enable --now searxng.service
echo "SearXNG installé : http://127.0.0.1:$port/"
