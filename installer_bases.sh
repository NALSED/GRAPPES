#!/usr/bin/env bash
# Installe, sur une VM nue, tout ce dont grappes a besoin pour tourner hors ligne :
# les paquets système, les deux environnements Python, puis TOUTES les copies locales (bases) déclarées
# dans pilote/config/sources/*.yaml, plus la fenêtre GDELT.
#
#   ./installer_bases.sh                      tout (système + venvs + bases + GDELT 90 jours)
#   ./installer_bases.sh --sans-systeme       sans apt/dnf (si les paquets sont déjà là)
#   ./installer_bases.sh --bases "rna-local geonames-fr"   seulement celles-là
#   ./installer_bases.sh --sans-gdelt         sans la fenêtre GDELT (c'est elle qui télécharge le plus)
#   ./installer_bases.sh --gdelt-jours 30     fenêtre GDELT plus courte
#   ./installer_bases.sh --garder             garde les archives téléchargées (par défaut : effacées après import)
#   ./installer_bases.sh --oui                ne pose aucune question (installation sans surveillance)
#
# Reprenable : une base déjà importée est sautée (relancer ne refait rien d'inutile). Les téléchargements
# coupés reprennent où ils en étaient. Chaque import est journalisé dans installer_bases.log.
#
# N'INVENTE AUCUN IMPORT : il appelle les outils du dépôt (outils/importer_base_locale.py, outils/gdelt_local.py),
# qui portent les filtres de la règle n° 8. Ce script ne fait que l'ordre, les paquets système et les URL.
set -euo pipefail

racine="$(cd "$(dirname "$0")" && pwd)"
journal="$racine/installer_bases.log"
systeme=1; gdelt=1; jours=90; garder=""; bases=""; oui=0

while [ $# -gt 0 ]; do
  case "$1" in
    --sans-systeme) systeme=0 ;;
    --sans-gdelt) gdelt=0 ;;
    --gdelt-jours) jours="${2:?}"; shift ;;
    --bases) bases="${2:?}"; shift ;;
    --garder) garder="--garder" ;;
    --oui) oui=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1 (voir --help)" >&2; exit 2 ;;
  esac
  shift
done

dire() { printf '\n== %s\n' "$*" | tee -a "$journal"; }
note() { printf '   %s\n' "$*" | tee -a "$journal"; }

: > "$journal"
dire "grappes — installation des bases locales, $(date '+%d/%m/%Y %H:%M')"

# ---------------------------------------------------------------- 1. paquets système
# libicu-dev + pkg-config : sans eux, `pip install -e grappes` échoue sur pyicu (dépendance de
# followthemoney/nomenklatura) avec un message illisible. C'est le premier mur d'une VM nue.
PAQUETS="python3 python3-venv python3-dev build-essential pkg-config libicu-dev openssl unzip curl ca-certificates git"
if [ "$systeme" = 1 ]; then
  dire "Paquets système"
  if command -v apt-get >/dev/null; then
    sudo apt-get update -qq
    # shellcheck disable=SC2086
    sudo apt-get install -y -qq $PAQUETS 2>&1 | tail -2 | tee -a "$journal"
  elif command -v dnf >/dev/null; then
    sudo dnf install -y -q python3 python3-devel gcc gcc-c++ make pkgconf-pkg-config libicu-devel openssl unzip curl ca-certificates git 2>&1 | tail -2 | tee -a "$journal"
  else
    note "Ni apt-get ni dnf : installez à la main $PAQUETS"
  fi
else
  note "paquets système : sautés (--sans-systeme)"
fi

# ---------------------------------------------------------------- 2. environnements Python
dire "Environnements Python (grappes + pilote)"
if [ ! -x "$racine/pilote/.venv/bin/python" ] || [ ! -x "$racine/grappes/.venv/bin/python" ]; then
  if ! "$racine/installer.sh" >>"$journal" 2>&1; then
    note "ÉCHEC de installer.sh. Extrait :"
    tail -12 "$journal" | sed 's/^/      /'
    if grep -qiE "pyicu|ICU_VERSION|pkg-config" "$journal"; then
      note ""
      note "Cause : pyicu (dépendance de followthemoney, elle-même dépendance de grappes) se compile et"
      note "exige des paquets système. Corriger puis relancer ce script :"
      note "   sudo apt-get install -y pkg-config libicu-dev python3-dev build-essential"
    fi
    exit 1
  fi
  note "installés"
else
  note "déjà installés"
fi
PY="$racine/pilote/.venv/bin/python"
[ -x "$PY" ] || { echo "L'environnement de pilote n'a pas pu être créé : voir $journal" >&2; exit 1; }

# ---------------------------------------------------------------- 3. URL datées : vérifier avant de télécharger
# SIRENE est publié tous les mois sous une adresse horodatée (…/20261001-072119/…) : celle qui est écrite dans
# sirene-local.yaml finit par disparaître. On demande l'adresse du jour à l'API de data.gouv.fr et on corrige
# la déclaration si elle a changé. Le RNA, lui, garde ses anciens fichiers en ligne : rien à faire.
dire "Adresses de téléchargement"
"$PY" - "$racine" <<'PYEOF' 2>&1 | tee -a "$journal"
import json, re, sys, urllib.request
from pathlib import Path

decl = Path(sys.argv[1]) / "pilote/config/sources/sirene-local.yaml"
if not decl.exists():
    print(f"   déclaration SIRENE introuvable ({decl}) — rien à vérifier")
    sys.exit(0)
API = "https://www.data.gouv.fr/api/1/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/"
VOULUS = ("stock-stockunitelegale-csv.zip", "stock-stocketablissement-csv.zip")
try:
    with urllib.request.urlopen(urllib.request.Request(API, headers={"User-Agent": "pilote/0.1"}), timeout=60) as r:
        jeu = json.load(r)
except OSError as exc:
    print(f"   adresses SIRENE : API injoignable ({exc}) — on garde celles de la déclaration")
    sys.exit(0)
actuelles = {}
for res in jeu.get("resources", []):
    u = res.get("url") or ""
    for v in VOULUS:
        if u.endswith(v) and v not in actuelles:
            actuelles[v] = u
texte = decl.read_text(encoding="utf-8")
change = 0
for v, u in actuelles.items():
    ancienne = re.search(rf"https://\S*{re.escape(v)}", texte)
    if ancienne and ancienne.group() != u:
        texte = texte.replace(ancienne.group(), u)
        change += 1
        print(f"   SIRENE : adresse mise à jour ({v})")
if change:
    decl.with_suffix(".yaml.avant").write_text(decl.read_text(encoding="utf-8"), encoding="utf-8")
    decl.write_text(texte, encoding="utf-8")
    print(f"   {change} adresse(s) corrigée(s) ; l'ancienne déclaration est dans sirene-local.yaml.avant")
else:
    print("   adresses SIRENE : à jour")
PYEOF

# ---------------------------------------------------------------- 4. place disque
# ---------------------------------------------------------------- 5. les bases, de la plus petite à la plus grosse
# Ordre voulu : les petites d'abord, pour qu'une erreur de configuration se voie en deux minutes et non en trois heures.
TOUTES="geoboundaries-fr geonames-fr opensanctions-local rna-local wikidata-fr sirene-local"
[ -n "$bases" ] && TOUTES="$bases"

# Place nécessaire, en Go, par base (archives + base indexée + marge d'import) : mesures du 27/10/2026
# (SIRENE : 0,98 + 2,88 Go d'archives ; RNA : 0,10 + 0,41 ; les autres sont petites).
place_de() { case "$1" in
    sirene-local) echo 30 ;;
    rna-local) echo 4 ;;
    wikidata-fr) echo 4 ;;
    opensanctions-local) echo 3 ;;
    geonames-fr) echo 1 ;;
    *) echo 1 ;;
  esac; }

dire "Place disque"
copies="$racine/pilote/donnees/copies"
mkdir -p "$copies"
libre_go=$(df -BG --output=avail "$copies" | tail -1 | tr -dc '0-9')
besoin=0
for id in $TOUTES; do besoin=$((besoin + $(place_de "$id"))); done
[ "$gdelt" = 1 ] && besoin=$((besoin + 5))
note "$libre_go Go libres sur $copies ; ~$besoin Go nécessaires pour ce qui est demandé"
if [ "${libre_go:-0}" -lt "$besoin" ]; then
  note "Place insuffisante. Chaque import vérifie lui-même la place avant de télécharger et s'arrête net plutôt que de remplir le disque."
  if [ -t 0 ] && [ "$oui" = 0 ]; then
    printf '   Continuer quand même ? [o/N] '
    read -r rep; [ "$rep" = "o" ] || [ "$rep" = "O" ] || exit 1
  else
    note "Pas de terminal (ou --oui) : on continue, les imports trop gros s'arrêteront d'eux-mêmes."
  fi
fi
deja() { "$PY" - "$racine" "$1" <<'PYEOF'
import json, sys
from pathlib import Path
reg = Path(sys.argv[1]) / "pilote/donnees/bases_locales.json"
liste = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else []
sys.exit(0 if any(x.get("source") == sys.argv[2] for x in liste) else 1)
PYEOF
}

echecs=""
for id in $TOUTES; do
  dire "Base « $id »"
  if deja "$id"; then note "déjà importée (relancer après l'avoir retirée de pilote/donnees/bases_locales.json pour la refaire)"; continue; fi
  if (cd "$racine/pilote" && "$PY" outils/importer_base_locale.py "$id" $garder) 2>&1 | tee -a "$journal"; then
    note "fait"
  else
    note "ÉCHEC — la suite continue"
    echecs="$echecs $id"
  fi
done

# ---------------------------------------------------------------- 6. GDELT (fenêtre glissante)
if [ "$gdelt" = 1 ]; then
  dire "GDELT — fenêtre de $jours jours (France)"
  note "c'est le plus long : des milliers de fichiers de 15 minutes, filtrés France. Reprenable."
  if (cd "$racine/pilote" && "$PY" outils/gdelt_local.py --jours "$jours") 2>&1 | tail -20 | tee -a "$journal"; then
    note "fait"
  else
    note "ÉCHEC — relancer « cd pilote && .venv/bin/python outils/gdelt_local.py --jours $jours » reprend où ça s'est arrêté"
    echecs="$echecs gdelt-local"
  fi
fi

# ---------------------------------------------------------------- 7. bilan
dire "Bilan"
(cd "$racine/pilote" && "$PY" - <<'PYEOF') 2>&1 | tee -a "$journal"
import json
from pathlib import Path
reg = Path("donnees/bases_locales.json")
if not reg.exists():
    print("   aucune base importée")
else:
    for x in json.loads(reg.read_text(encoding="utf-8")):
        print(f"   {x['base']:<18} {x.get('lignes', 0):>12,} lignes  {x.get('octets', 0)/1e9:>6.2f} Go  importée le {x.get('date')}".replace(",", " "))
PYEOF
du -sh "$copies" 2>/dev/null | awk '{print "   total sur le disque : "$1}' | tee -a "$journal"
if [ -n "$echecs" ]; then
  dire "À reprendre :$echecs"
  note "journal complet : $journal"
  exit 1
fi
dire "Terminé. Lancer l'interface : ./lancer.sh"
note "Pour l'atteindre depuis un autre poste : mettre « hote: 0.0.0.0 » et renseigner « hotes_autorises »"
note "dans pilote/config/pilote.yaml (par défaut le service n'écoute que 127.0.0.1)."
