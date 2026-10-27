#!/bin/bash
# LibreTranslate auto-hébergé : écoute en local seulement, rien ne sort sur le réseau (les modèles sont déjà installés).
D="$(cd "$(dirname "$0")" && pwd)"
export XDG_DATA_HOME="$D/donnees" XDG_CACHE_HOME="$D/cache"
exec "$D/venv/bin/libretranslate" --host 127.0.0.1 --port 5000 --load-only fr,en,es,de,it,ar,ru,zh --disable-web-ui --disable-files-translation --threads 2 --req-limit 100000
