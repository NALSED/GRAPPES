#!/usr/bin/env bash
# Installe grappes (moteur) et pilote (interface web) : `./installer.sh`.
# Crée un environnement Python par application, sans droit root. Les PAQUETS SYSTÈME, eux, en demandent :
# ce script les vérifie et s'arrête en disant lesquels manquent, plutôt que d'échouer au milieu de pip.
# Pour tout faire d'un coup, paquets système compris : `./installer_grappes.sh`.
set -euo pipefail
racine="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null || { echo "python3 (>= 3.11) est requis" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11 ou plus est requis" >&2; exit 1; }
python3 -c 'import venv' 2>/dev/null || { echo "Le module venv est absent : sudo apt-get install python3-venv" >&2; exit 1; }

# `followthemoney` (dépendance de grappes) tire `pyicu`, qui se COMPILE : sans ces paquets, pip s'arrête sur une erreur
# illisible (« Please install pkg-config… ICU_VERSION »). C'est le premier mur d'une machine neuve : on le dit avant.
manquants=""
command -v pkg-config >/dev/null || manquants="$manquants pkg-config"
command -v cc >/dev/null || command -v gcc >/dev/null || manquants="$manquants build-essential"
if command -v pkg-config >/dev/null && ! pkg-config --exists icu-i18n 2>/dev/null; then manquants="$manquants libicu-dev"; fi
python3 -c 'import sysconfig, pathlib, sys; sys.exit(0 if pathlib.Path(sysconfig.get_paths()["include"], "Python.h").exists() else 1)' || manquants="$manquants python3-dev"
if [ -n "$manquants" ]; then
  echo "Il manque des paquets système pour compiler les dépendances de grappes :$manquants" >&2
  echo "  sudo apt-get install -y$manquants        (Debian, Ubuntu)" >&2
  echo "  sudo dnf install -y pkgconf-pkg-config gcc gcc-c++ make libicu-devel python3-devel   (Fedora, RHEL)" >&2
  echo "Puis relancez ./installer.sh — ou lancez ./installer_grappes.sh, qui les installe lui-même." >&2
  exit 1
fi

# torch en version processeur (léger) avant le reste : sans lui, `pip install -e grappes` prend le torch par défaut,
# c'est-à-dire les bibliothèques GPU (plusieurs gigaoctets de CUDA, inutiles ici). Un échec ici s'arrête : il ne se
# rattrape pas en silence par un téléchargement dix fois plus gros.
[ -x "$racine/grappes/.venv/bin/python" ] || python3 -m venv "$racine/grappes/.venv"
"$racine/grappes/.venv/bin/pip" -q install --upgrade pip
if ! "$racine/grappes/.venv/bin/pip" -q install torch --index-url https://download.pytorch.org/whl/cpu; then
  echo "L'index processeur de PyTorch n'a pas répondu : torch n'est pas installé." >&2
  echo "Relancez plus tard, ou installez-le à la main :" >&2
  echo "  grappes/.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu" >&2
  echo "Sans cette étape, la suite prendrait la version GPU de torch (plusieurs Go de CUDA pour rien)." >&2
  exit 1
fi

for app in grappes pilote; do
  [ -x "$racine/$app/.venv/bin/python" ] || python3 -m venv "$racine/$app/.venv"
  "$racine/$app/.venv/bin/pip" -q install --upgrade pip
  "$racine/$app/.venv/bin/pip" -q install -e "$racine/$app"
done

# Pilotes de base de données (PostgreSQL, MySQL, MariaDB) : le pont de pilote tourne dans l'interpréteur de grappes et en a besoin
# pour la source « base extérieure ». Un échec est dit : sinon la source tombait à l'usage, loin de sa cause.
"$racine/grappes/.venv/bin/pip" -q install pg8000 pymysql || {
  echo "Les pilotes de base de données (pg8000, pymysql) n'ont pas pu être installés : la source « base extérieure » ne marchera pas." >&2
  echo "  grappes/.venv/bin/pip install pg8000 pymysql" >&2
  exit 1
}

# Fichiers de clés d'API : créés vides, à remplir (jamais versionnés).
[ -f "$racine/grappes/config/secrets.env" ] || {
  printf '# Clés d API de grappes, une par ligne : TAVILY_API_KEY=...\n' > "$racine/grappes/config/secrets.env"
  chmod 600 "$racine/grappes/config/secrets.env"
}
[ -f "$racine/pilote/config/secrets.env" ] || {
  : > "$racine/pilote/config/secrets.env"; chmod 600 "$racine/pilote/config/secrets.env"
}
echo "Installation terminée. Lancer l'interface web : ./lancer.sh"
