#!/usr/bin/env bash
# Installe grappes (moteur) et pilote (interface web) : `./installer.sh`.
# Crée un environnement Python par application, sans droit root.
set -euo pipefail
racine="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null || { echo "python3 (>= 3.11) est requis" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11 ou plus est requis" >&2; exit 1; }

# torch en version processeur (léger) avant le reste : évite le téléchargement des bibliothèques GPU.
[ -x "$racine/grappes/.venv/bin/python" ] || python3 -m venv "$racine/grappes/.venv"
"$racine/grappes/.venv/bin/pip" -q install torch --index-url https://download.pytorch.org/whl/cpu || true
for app in grappes pilote; do
  [ -x "$racine/$app/.venv/bin/python" ] || python3 -m venv "$racine/$app/.venv"
  "$racine/$app/.venv/bin/pip" -q install --upgrade pip
  "$racine/$app/.venv/bin/pip" -q install -e "$racine/$app"
done

# Fichiers de clés d'API : créés vides, à remplir (jamais versionnés).
[ -f "$racine/grappes/config/secrets.env" ] || {
  printf '# Clés d API de grappes, une par ligne : TAVILY_API_KEY=...\n' > "$racine/grappes/config/secrets.env"
  chmod 600 "$racine/grappes/config/secrets.env"
}
[ -f "$racine/pilote/config/secrets.env" ] || {
  : > "$racine/pilote/config/secrets.env"; chmod 600 "$racine/pilote/config/secrets.env"
}
echo "Installation terminée. Lancer l'interface web : ./lancer.sh"
