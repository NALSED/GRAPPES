#!/usr/bin/env bash
# Installation COMPLÈTE de grappes sur une machine neuve, du système jusqu'au lancement.
# Chaque prérequis est PROPOSÉ, jamais imposé : le script pose la question, avec une réponse par défaut entre crochets.
#
#   ./installer_grappes.sh                  pose les questions une par une (c'est le mode normal)
#   ./installer_grappes.sh --tout           répond oui à tout, sans rien demander
#   ./installer_grappes.sh --minimal        paquets système + environnements Python + lancement, rien d'autre
#
# Pour ne pas répondre aux questions, chaque étape a son option (utile pour rejouer une installation à l'identique) :
#   --systeme / --sans-systeme             paquets système (apt ou dnf ; demande sudo)
#   --bases "sirene-local rna-local"       seulement ces bases ; --sans-bases pour aucune
#   --gdelt-jours 90 / --sans-gdelt        fenêtre de presse GDELT (France)
#   --searxng / --sans-searxng             méta-moteur de recherche web, auto-hébergé, local
#   --libretranslate / --sans-libretranslate   traduction hors ligne (≈ 2–3 Go de modèles)
#   --overpass /point/de/montage           géocodage OpenStreetMap local (exige un disque de 100 Go déjà monté)
#   --service / --sans-service             démarrage automatique de pilote (service systemd utilisateur)
#   --lancer / --sans-lancer               lancer l'interface à la fin
#   --garder                               garde les archives téléchargées (par défaut : effacées après import)
#
# Reprenable : une base déjà importée est sautée, un téléchargement coupé reprend où il en était. Un prérequis qui
# échoue n'arrête pas les autres ; la liste de ce qui reste à faire est donnée à la fin, avec le journal.
#
# N'INVENTE AUCUN IMPORT ni AUCUN SERVICE : il appelle les outils du dépôt (installer.sh, outils/importer_base_locale.py,
# outils/gdelt_local.py, outils/installer_searxng.sh, outils/installer_overpass.sh, outils/libretranslate,
# outils/installer_service.sh). Ce script ne fait que l'ordre, les questions, la place disque et les adresses datées.
set -uo pipefail

racine="$(cd "$(dirname "$0")" && pwd)"
journal="$racine/installation.log"
: > "$journal"

# -1 = pas encore décidé (on demandera), 0 = non, 1 = oui
systeme=-1; gdelt=-1; searxng=-1; libretranslate=-1; service=-1; lancer=-1; bases_choisies=""; sans_bases=-1
jours=90; garder=""; overpass_dir=""; tout=0; minimal=0
BASES_PAR_DEFAUT="geoboundaries-fr geonames-fr opensanctions-local rna-local wikidata-fr sirene-local"

while [ $# -gt 0 ]; do
  case "$1" in
    --tout) tout=1 ;;
    --minimal) minimal=1 ;;
    --systeme) systeme=1 ;;         --sans-systeme) systeme=0 ;;
    --bases) bases_choisies="${2:?}"; sans_bases=0; shift ;;
    --sans-bases) sans_bases=1 ;;
    --gdelt-jours) jours="${2:?}"; gdelt=1; shift ;;
    --sans-gdelt) gdelt=0 ;;
    --searxng) searxng=1 ;;         --sans-searxng) searxng=0 ;;
    --libretranslate) libretranslate=1 ;; --sans-libretranslate) libretranslate=0 ;;
    --overpass) overpass_dir="${2:?}"; shift ;;
    --service) service=1 ;;         --sans-service) service=0 ;;
    --lancer) lancer=1 ;;           --sans-lancer) lancer=0 ;;
    --garder) garder="--garder" ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1 (voir --help)" >&2; exit 2 ;;
  esac
  shift
done

dire() { printf '\n== %s\n' "$*" | tee -a "$journal"; }
note() { printf '   %s\n' "$*" | tee -a "$journal"; }
echecs=""
rate() { echecs="$echecs
   - $*"; note "ÉCHEC : $*"; }

# Les questions passent par le terminal, même si l'entrée standard est un tuyau. Sans terminal du tout, on prend la réponse par défaut.
_tty=""
[ -t 0 ] && _tty="/dev/stdin"
[ -z "$_tty" ] && [ -r /dev/tty ] && _tty="/dev/tty"

demander() {  # demander "question" "o" -> 0 si oui ; la réponse par défaut est le 2e argument
  local q="$1" defaut="$2" rep=""
  if [ "$tout" = 1 ] || [ -z "$_tty" ]; then
    [ "$defaut" = "o" ] && return 0 || return 1
  fi
  if [ "$defaut" = "o" ]; then printf '   %s [O/n] ' "$q"; else printf '   %s [o/N] ' "$q"; fi
  read -r rep < "$_tty" || rep=""
  rep="${rep:-$defaut}"
  case "$rep" in o|O|y|Y|oui|OUI) return 0 ;; *) return 1 ;; esac
}

veut() {  # veut <variable> "question" "defaut" : respecte l'option si elle a été donnée, sinon demande
  local valeur="$1"
  [ "$valeur" = "1" ] && return 0
  [ "$valeur" = "0" ] && return 1
  demander "$2" "$3"
}

dire "grappes — installation, $(date '+%d/%m/%Y %H:%M')"
note "journal : $journal"
if [ "$minimal" = 1 ]; then
  [ "$sans_bases" = "-1" ] && sans_bases=1
  [ "$gdelt" = "-1" ] && gdelt=0; [ "$searxng" = "-1" ] && searxng=0
  [ "$libretranslate" = "-1" ] && libretranslate=0; [ "$service" = "-1" ] && service=0
fi

# ---------------------------------------------------------------- 1. paquets système
# libicu-dev + pkg-config : sans eux, `pip install -e grappes` échoue sur pyicu (dépendance de followthemoney) avec un
# message illisible. C'est le premier mur d'une machine neuve, et la seule étape qui demande sudo.
PAQ_APT="python3 python3-venv python3-dev build-essential pkg-config libicu-dev openssl unzip curl ca-certificates git"
PAQ_DNF="python3 python3-devel gcc gcc-c++ make pkgconf-pkg-config libicu-devel openssl unzip curl ca-certificates git"
dire "1/8 — Paquets système"
note "nécessaires pour compiler les dépendances de grappes (pyicu) et pour le certificat du service"
if veut "$systeme" "Installer les paquets système maintenant (demande sudo) ?" "o"; then
  if command -v apt-get >/dev/null; then
    (sudo apt-get update -qq && sudo apt-get install -y -qq $PAQ_APT) >>"$journal" 2>&1 && note "installés" || rate "paquets système (voir le journal ; sans eux l'étape 2 échouera)"
  elif command -v dnf >/dev/null; then
    sudo dnf install -y -q $PAQ_DNF >>"$journal" 2>&1 && note "installés" || rate "paquets système (voir le journal)"
  else
    note "ni apt-get ni dnf : installez à la main — $PAQ_APT"
  fi
else
  note "sauté"
fi

# ---------------------------------------------------------------- 2. environnements Python (obligatoire)
dire "2/8 — Environnements Python de grappes et de pilote"
if [ -x "$racine/pilote/.venv/bin/python" ] && [ -x "$racine/grappes/.venv/bin/python" ]; then
  note "déjà installés"
else
  note "torch en version processeur, puis les deux applications — quelques minutes"
  if ! "$racine/installer.sh" >>"$journal" 2>&1; then
    note "ÉCHEC de installer.sh. Extrait :"
    tail -12 "$journal" | sed 's/^/      /'
    if grep -qiE "pyicu|ICU_VERSION|pkg-config" "$journal"; then
      note ""
      note "Cause : pyicu (dépendance de followthemoney, elle-même dépendance de grappes) se compile et exige des paquets système."
      note "Corriger puis relancer ce script :   sudo apt-get install -y pkg-config libicu-dev python3-dev build-essential"
    fi
    exit 1
  fi
  note "installés"
fi
PY="$racine/pilote/.venv/bin/python"
[ -x "$PY" ] || { echo "L'environnement de pilote est introuvable : voir $journal" >&2; exit 1; }

# ---------------------------------------------------------------- 3. bases locales
dire "3/8 — Bases locales (copies interrogées sans appel réseau)"
BASES=""
if [ "$sans_bases" = "1" ]; then
  note "sautées"
else
  [ -n "$bases_choisies" ] && BASES="$bases_choisies" || BASES="$BASES_PAR_DEFAUT"
  if [ -z "$bases_choisies" ]; then
    note "proposées : $BASES"
    note "SIRENE est la plus lourde : ≈ 4 Go d'archives, ≈ 20 Go indexés, plusieurs heures d'import."
    if ! veut "-1" "Installer toutes ces bases ?" "o"; then
      retenues=""
      for id in $BASES; do demander "  $id ?" "o" && retenues="$retenues $id"; done
      BASES="$retenues"
    fi
  fi
fi

# Adresses datées : SIRENE est republié chaque mois sous une adresse horodatée, et celle de la déclaration finit par
# disparaître. On demande l'adresse du jour à l'API de data.gouv.fr. (Le RNA, lui, garde ses anciens fichiers en ligne.)
if echo " $BASES " | grep -q " sirene-local "; then
  note "vérification de l'adresse de téléchargement de SIRENE…"
  "$PY" - "$racine" >>"$journal" 2>&1 <<'PYEOF'
import json, re, sys, urllib.request
from pathlib import Path
decl = Path(sys.argv[1]) / "pilote/config/sources/sirene-local.yaml"
if not decl.exists():
    print(f"déclaration SIRENE introuvable ({decl})"); sys.exit(0)
API = "https://www.data.gouv.fr/api/1/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/"
VOULUS = ("stock-stockunitelegale-csv.zip", "stock-stocketablissement-csv.zip")
try:
    with urllib.request.urlopen(urllib.request.Request(API, headers={"User-Agent": "pilote/0.1"}), timeout=60) as r:
        jeu = json.load(r)
except OSError as exc:
    print(f"API data.gouv.fr injoignable ({exc}) : on garde les adresses de la déclaration"); sys.exit(0)
actuelles = {}
for res in jeu.get("resources", []):
    u = res.get("url") or ""
    for v in VOULUS:
        if u.endswith(v) and v not in actuelles:
            actuelles[v] = u
texte = ancien = decl.read_text(encoding="utf-8")
for v, u in actuelles.items():
    m = re.search(rf"https://\S*{re.escape(v)}", texte)
    if m and m.group() != u:
        texte = texte.replace(m.group(), u)
        print(f"adresse mise à jour : {v}")
if texte != ancien:
    decl.with_suffix(".yaml.avant").write_text(ancien, encoding="utf-8")
    decl.write_text(texte, encoding="utf-8")
    print("déclaration SIRENE corrigée (ancienne version : sirene-local.yaml.avant)")
else:
    print("adresses SIRENE à jour")
PYEOF
  tail -2 "$journal" | sed 's/^/      /'
fi

place_de() { case "$1" in
    sirene-local) echo 30 ;; rna-local|wikidata-fr) echo 4 ;; opensanctions-local) echo 3 ;; *) echo 1 ;;
  esac; }
deja() { "$PY" - "$racine" "$1" <<'PYEOF'
import json, sys
from pathlib import Path
reg = Path(sys.argv[1]) / "pilote/donnees/bases_locales.json"
liste = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else []
sys.exit(0 if any(x.get("source") == sys.argv[2] for x in liste) else 1)
PYEOF
}

if [ -n "$BASES" ]; then
  copies="$racine/pilote/donnees/copies"; mkdir -p "$copies"
  libre_go=$(df -BG --output=avail "$copies" 2>/dev/null | tail -1 | tr -dc '0-9')
  besoin=0; for id in $BASES; do besoin=$((besoin + $(place_de "$id"))); done
  note "${libre_go:-?} Go libres ; ~$besoin Go nécessaires pour les bases demandées"
  if [ "${libre_go:-0}" -lt "$besoin" ]; then
    note "Place insuffisante. Chaque import vérifie lui-même la place et s'arrête avant de remplir le disque."
    veut "-1" "Continuer quand même ?" "n" || BASES=""
  fi
fi
for id in $BASES; do
  dire "    base « $id »"
  if deja "$id"; then note "déjà importée (pour la refaire : la retirer de pilote/donnees/bases_locales.json)"; continue; fi
  if (cd "$racine/pilote" && "$PY" outils/importer_base_locale.py "$id" $garder) 2>&1 | tee -a "$journal" | tail -3 | sed 's/^/      /'; then
    note "fait"
  else
    rate "base « $id » — relancer : cd pilote && .venv/bin/python outils/importer_base_locale.py $id"
  fi
done

# ---------------------------------------------------------------- 4. GDELT
dire "4/8 — Presse : fenêtre GDELT (France)"
note "des milliers de fichiers de 15 minutes, filtrés France : c'est long, et reprenable"
if veut "$gdelt" "Constituer la fenêtre GDELT de $jours jours ?" "o"; then
  if (cd "$racine/pilote" && "$PY" outils/gdelt_local.py --jours "$jours") 2>&1 | tee -a "$journal" | tail -3 | sed 's/^/      /'; then
    note "fait"
  else
    rate "GDELT — relancer : cd pilote && .venv/bin/python outils/gdelt_local.py --jours $jours"
  fi
else
  note "sauté"
fi

# ---------------------------------------------------------------- 5. SearXNG
dire "5/8 — SearXNG (recherche web auto-hébergée, locale)"
note "évite de dépendre d'une API payante pour le preset Web ; écoute sur 127.0.0.1 seulement"
if veut "$searxng" "Installer SearXNG ?" "o"; then
  if "$racine/pilote/outils/installer_searxng.sh" >>"$journal" 2>&1; then note "installé"; else rate "SearXNG (voir le journal)"; fi
else
  note "sauté"
fi

# ---------------------------------------------------------------- 6. LibreTranslate
dire "6/8 — LibreTranslate (traduction hors ligne)"
note "≈ 2–3 Go de modèles (fr, en, es, de, it, ar, ru, zh) ; sans lui, la tuile Traduction reste éteinte"
if veut "$libretranslate" "Installer LibreTranslate et ses modèles ?" "n"; then
  if [ -x "$racine/pilote/outils/libretranslate/installer_modeles.py" ] || [ -f "$racine/pilote/outils/libretranslate/installer_modeles.py" ]; then
    if "$PY" "$racine/pilote/outils/libretranslate/installer_modeles.py" >>"$journal" 2>&1; then
      note "installé — voir outils/libretranslate/LISEZMOI.md pour le service"
    else
      rate "LibreTranslate (voir le journal et outils/libretranslate/LISEZMOI.md)"
    fi
  else
    rate "LibreTranslate : outils/libretranslate/installer_modeles.py est introuvable"
  fi
else
  note "sauté"
fi

# ---------------------------------------------------------------- 7. Overpass
dire "7/8 — Overpass (géocodage OpenStreetMap local, France)"
note "exige Docker et un disque de 100 Go DÉJÀ monté ; sans lui, le géocodage passe par le service public"
if [ -z "$overpass_dir" ] && [ "$tout" != 1 ] && veut "-1" "Installer Overpass ?" "n"; then
  if [ -n "$_tty" ]; then printf '   Point de montage du disque de 100 Go : '; read -r overpass_dir < "$_tty" || overpass_dir=""; fi
fi
if [ -n "$overpass_dir" ]; then
  if [ ! -d "$overpass_dir" ]; then
    rate "Overpass : « $overpass_dir » n'est pas un dossier monté"
  elif ! command -v docker >/dev/null; then
    rate "Overpass : Docker est absent (sudo apt-get install docker.io, puis relancer avec --overpass $overpass_dir)"
  elif OVERPASS_DIR="$overpass_dir" "$racine/pilote/outils/installer_overpass.sh" >>"$journal" 2>&1; then
    note "installé (l'import de la France prend plusieurs heures, en tâche de fond)"
  else
    rate "Overpass (voir le journal)"
  fi
else
  note "sauté"
fi

# ---------------------------------------------------------------- 8. service et lancement
dire "8/8 — Démarrage"
if veut "$service" "Installer le service systemd (pilote démarre tout seul, et survit à la déconnexion) ?" "o"; then
  if "$racine/pilote/outils/installer_service.sh" >>"$journal" 2>&1; then
    note "service installé et démarré"
    service=1
  else
    rate "service systemd (voir le journal) — l'interface reste lançable à la main par ./lancer.sh"
    service=0
  fi
else
  note "pas de service : l'interface se lance à la main par ./lancer.sh"
  service=0
fi

# ---------------------------------------------------------------- bilan
dire "Bilan"
(cd "$racine/pilote" && "$PY" - <<'PYEOF') 2>&1 | tee -a "$journal"
import json
from pathlib import Path
reg = Path("donnees/bases_locales.json")
if not reg.exists():
    print("   aucune base locale installée")
else:
    for x in json.loads(reg.read_text(encoding="utf-8")):
        print(f"   {x['base']:<18} {x.get('lignes', 0):>12,} lignes  {x.get('octets', 0)/1e9:>6.2f} Go  importée le {x.get('date')}".replace(",", " "))
PYEOF
du -sh "$racine/pilote/donnees" 2>/dev/null | awk '{print "   données sur le disque : "$1}' | tee -a "$journal"

port=$("$PY" -c "import sys; sys.path.insert(0,'$racine/pilote/src'); from pilote.config import charger; c=charger('$racine/pilote/config/pilote.yaml'); print(c.service.port)" 2>/dev/null || echo 8443)
hote=$("$PY" -c "import sys; sys.path.insert(0,'$racine/pilote/src'); from pilote.config import charger; c=charger('$racine/pilote/config/pilote.yaml'); print(c.service.hote)" 2>/dev/null || echo 127.0.0.1)
if [ -n "$echecs" ]; then
  dire "À reprendre"
  printf '%s\n' "$echecs" | tee -a "$journal"
fi
dire "Terminé"
note "Interface : https://$hote:$port  (certificat auto-signé : le navigateur prévient la première fois)"
if [ "$hote" = "127.0.0.1" ]; then
  note "Le service n'écoute que cette machine. Pour l'atteindre depuis un autre poste : mettre « hote: 0.0.0.0 »"
  note "et renseigner « hotes_autorises » dans pilote/config/pilote.yaml, puis relancer le service."
fi
note "Clés d'API à remplir si besoin : pilote/config/secrets.env et grappes/config/secrets.env"

if [ "$service" = "1" ]; then
  note "Le service tourne déjà : systemctl --user status pilote.service"
elif veut "$lancer" "Lancer l'interface maintenant (au premier plan, Ctrl-C pour arrêter) ?" "o"; then
  dire "Lancement"
  exec "$racine/lancer.sh"
fi
[ -n "$echecs" ] && exit 1
exit 0
