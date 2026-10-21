#!/usr/bin/env bash
# Serveur Overpass AUTO-HÉBERGÉ, France seule (décision de Sednal du 17/10/2026, REPONSES.md §2) : image Docker éprouvée `wiktorn/overpass-api`,
# mode `init`, extrait Geofabrik de la France (en .osm.pbf : le .osm.bz2 demandé n'existe plus chez Geofabrik, c'est le même extrait), OVERPASS_META=no (les métadonnées dépasseraient les 100 Go). N'écoute que sur 127.0.0.1.
# Usage : OVERPASS_DIR=/point/de/montage outils/installer_overpass.sh   (le disque doit être partitionné, formaté et MONTÉ avant : rien n'est
# formaté ici). Idempotent : si la base existe déjà, le conteneur est seulement (re)démarré.
set -euo pipefail
DIR="${OVERPASS_DIR:?indiquez OVERPASS_DIR, le point de montage du disque de 100 Go}"
PORT="${OVERPASS_PORT:-12345}"
mountpoint -q "${OVERPASS_MONTAGE:-$DIR}" || { echo "« $DIR » n'est pas un point de montage : montez d'abord le disque." >&2; exit 1; }
mkdir -p "$DIR/db"
if docker ps -a --format '{{.Names}}' | grep -qx overpass; then docker start overpass >/dev/null; echo "Conteneur overpass démarré."; exit 0; fi
docker run -d --name overpass --restart unless-stopped \
  -e OVERPASS_META=no -e OVERPASS_MODE=init \
  -e OVERPASS_PLANET_URL=https://download.geofabrik.de/europe/france-latest.osm.pbf \
  -e OVERPASS_DIFF_URL=https://download.geofabrik.de/europe/france-updates/ \
  -e OVERPASS_PLANET_PREPROCESS='mv /db/planet.osm.bz2 /db/planet.osm.pbf && osmium cat -o /db/planet.osm.bz2 /db/planet.osm.pbf && rm /db/planet.osm.pbf' \
  -e OVERPASS_UPDATE_SLEEP=3600 -e OVERPASS_USE_AREAS=true -e OVERPASS_RATE_LIMIT=0 \
  -v "$DIR/db:/db" -p "127.0.0.1:$PORT:80" wiktorn/overpass-api
echo "Import lancé (long) : suivre avec « docker logs -f overpass ». Prêt quand http://127.0.0.1:$PORT/api/status répond."
