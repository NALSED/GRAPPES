#!/bin/bash
# Outil de TEST seulement (jamais dans l'application) : un navigateur sans tête pour vérifier les pages à l'œil (captures, niveaux de gris,
# gestes au clavier). Rien n'est installé dans le système : les bibliothèques manquantes sont extraites dans ~/.cache/pilote-libs sans droits
# particuliers, le navigateur est téléchargé par Playwright dans ~/.cache/ms-playwright. Les tests qui en ont besoin sont sautés s'il est absent.
set -e
RACINE="$(cd "$(dirname "$0")/.." && pwd)"
"$RACINE/.venv/bin/python" -m pip install playwright
"$RACINE/.venv/bin/python" -m playwright install chromium
TMP="$(mktemp -d)"
cd "$TMP"
apt-get download libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libxdamage1 libxkbcommon0 libasound2t64 libatspi2.0-0t64
mkdir -p ~/.cache/pilote-libs
for f in *.deb; do dpkg -x "$f" ~/.cache/pilote-libs; done
rm -rf "$TMP"
echo "Navigateur de test prêt."
