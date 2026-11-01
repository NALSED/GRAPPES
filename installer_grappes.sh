#!/usr/bin/env bash
# Installation COMPLÈTE de grappes sur une machine neuve, du système jusqu'au lancement.
# Par défaut, TOUT s'installe sans aucune question. « --questions » rend la main étape par étape.
#
#   ./installer_grappes.sh                  INSTALLE TOUT, sans poser une seule question (le cas normal)
#   ./installer_grappes.sh --questions      choisit étape par étape, avec une réponse par défaut entre crochets
#   ./installer_grappes.sh --minimal        paquets système + environnements Python + lancement, rien d'autre
#
# Sans « --donnees », le disque des données est CHERCHÉ : un système de fichiers monté, inscriptible, d'au moins
# 200 Go, qui n'est pas celui du dépôt. S'il n'y en a pas un seul évident, le script s'arrête et dit quoi faire :
# il ne remplit jamais le disque système par défaut.
#
# Pour ne pas répondre aux questions, chaque étape a son option (utile pour rejouer une installation à l'identique) :
#   --systeme / --sans-systeme             paquets système (apt ou dnf ; demande sudo)
#   --bases "sirene-local rna-local"       seulement ces bases ; --sans-bases pour aucune
#   --gdelt-jours 90 / --sans-gdelt        fenêtre de presse GDELT (France)
#   --mesure / --sans-mesure               outils de mesure de la qualité (extra autocal, ≈ 500 Mo)
#   --searxng / --sans-searxng             méta-moteur de recherche web, auto-hébergé, local
#   --libretranslate / --sans-libretranslate   traduction hors ligne (≈ 2–3 Go de modèles)
#   --overpass /point/de/montage           géocodage OpenStreetMap local (exige un disque de 100 Go déjà monté)
#   --donnees /point/de/montage            disque des données (250 Go et plus) : base, copies, modèles, traduction
#   --sans-autre-disque                    tout garder dans le dépôt (déconseillé si le disque système est petit)
#   --sans-overpass                        ne pas proposer Overpass
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
systeme=-1; gdelt=-1; searxng=-1; libretranslate=-1; service=-1; lancer=-1; bases_choisies=""; sans_bases=-1; mesure=-1
jours=90; garder=""; overpass_dir=""; overpass=-1; tout=0; minimal=0; questions=0; donnees_mp=""; donnees_demande=-1
BASES_PAR_DEFAUT="geoboundaries-fr geonames-fr opensanctions-local rna-local wikidata-fr sirene-local"

while [ $# -gt 0 ]; do
  case "$1" in
    --tout) tout=1 ;;
    --questions) questions=1 ;;
    --minimal) minimal=1 ;;
    --systeme) systeme=1 ;;         --sans-systeme) systeme=0 ;;
    --bases) bases_choisies="${2:?}"; sans_bases=0; shift ;;
    --sans-bases) sans_bases=1 ;;
    --gdelt-jours) jours="${2:?}"; gdelt=1; shift ;;
    --sans-gdelt) gdelt=0 ;;
    --searxng) searxng=1 ;;         --sans-searxng) searxng=0 ;;
    --mesure) mesure=1 ;;           --sans-mesure) mesure=0 ;;
    --libretranslate) libretranslate=1 ;; --sans-libretranslate) libretranslate=0 ;;
    --overpass) overpass_dir="${2:?}"; shift ;;
    --sans-overpass) overpass=0 ;;
    --donnees) donnees_mp="${2:?}"; shift ;;
    --sans-autre-disque) donnees_demande=0 ;;
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
# /dev/tty peut exister sans être ouvrable (service, tâche planifiée, conteneur sans terminal) : on essaie vraiment
# de l'ouvrir, sinon chaque question affichait une erreur avant de prendre la réponse par défaut.
[ -z "$_tty" ] && { : < /dev/tty; } 2>/dev/null && _tty="/dev/tty"

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
# Lancer le script SANS rien préciser installe TOUT, sans poser une seule question : c'est le cas normal.
# `--questions` repasse en mode question par question, `--minimal` ne pose que le socle.
if [ "$tout" = 0 ] && [ "$minimal" = 0 ] && [ "$questions" = 0 ]; then
  tout=1
  note "mode par défaut : tout est installé, aucune question posée (« --questions » pour choisir étape par étape)"
fi
if [ "$minimal" = 1 ]; then
  [ "$sans_bases" = "-1" ] && sans_bases=1
  [ "$gdelt" = "-1" ] && gdelt=0; [ "$searxng" = "-1" ] && searxng=0
  [ "$libretranslate" = "-1" ] && libretranslate=0; [ "$service" = "-1" ] && service=0; [ "$mesure" = "-1" ] && mesure=0; overpass=0
fi
# `--tout` dit OUI à chaque étape, et ne se contente pas de prendre les réponses par défaut : sans ça, LibreTranslate
# et les outils de mesure (dont la réponse par défaut est non, parce qu'ils sont lourds) étaient sautés en silence,
# alors que « tout » veut dire tout. Seul Overpass reste à part : il exige un point de montage qui ne se devine pas,
# donc il faut l'écrire (`--overpass /mnt/osm`) même avec `--tout`.
if [ "$tout" = 1 ]; then
  [ "$systeme" = "-1" ] && systeme=1
  [ "$mesure" = "-1" ] && mesure=1
  [ "$sans_bases" = "-1" ] && sans_bases=0
  [ "$gdelt" = "-1" ] && gdelt=1
  [ "$searxng" = "-1" ] && searxng=1
  [ "$libretranslate" = "-1" ] && libretranslate=1
  [ "$service" = "-1" ] && service=1
  [ "$lancer" = "-1" ] && lancer=1
  [ "$overpass" = "-1" ] && overpass=1   # Overpass compris : son dossier se déduit du disque des données
fi

# ---------------------------------------------------------------- 1. paquets système
# libicu-dev + pkg-config : sans eux, `pip install -e grappes` échoue sur pyicu (dépendance de followthemoney) avec un
# message illisible. C'est le premier mur d'une machine neuve, et la seule étape qui demande sudo.
PAQ_APT="python3 python3-venv python3-dev build-essential pkg-config libicu-dev openssl unzip curl ca-certificates git"
PAQ_DNF_SUP=""
[ "$overpass" != 0 ] && { PAQ_APT="$PAQ_APT docker.io"; PAQ_DNF_SUP="docker"; }  # Overpass tourne dans un conteneur
PAQ_DNF="python3 python3-devel gcc gcc-c++ make pkgconf-pkg-config libicu-devel openssl unzip curl ca-certificates git"
dire "1/8 — Paquets système"
note "nécessaires pour compiler les dépendances de grappes (pyicu) et pour le certificat du service"
if veut "$systeme" "Installer les paquets système maintenant (demande sudo) ?" "o"; then
  if command -v apt-get >/dev/null; then
    (sudo apt-get update -qq && sudo apt-get install -y -qq $PAQ_APT) >>"$journal" 2>&1 && note "installés" || rate "paquets système (voir le journal ; sans eux l'étape 2 échouera)"
  elif command -v dnf >/dev/null; then
    sudo dnf install -y -q $PAQ_DNF $PAQ_DNF_SUP >>"$journal" 2>&1 && note "installés" || rate "paquets système (voir le journal)"
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

# ---------------------------------------------------------------- 2 ter. placer les données sur l'autre disque
# Deux disques, deux rôles : un petit pour grappes (le dépôt et les deux environnements Python, ≈ 8 Go), un grand pour
# TOUT ce qui pèse et qui grossit. Le script place lui-même les quatre postes lourds, au lieu de laisser éditer le YAML :
#   <disque>/donnees        base SQLite de pilote, dossiers de travail des recherches, certificat
#   <disque>/copies         copies locales des bases (SIRENE à lui seul ≈ 20 Go indexés)
#   <disque>/modeles        modèles de lecture de noms (HF_HOME de grappes)
#   <disque>/libretranslate environnement et modèles de traduction (≈ 8 Go, mesuré sur la VM de momo)
#   <disque>/overpass       base OpenStreetMap, si Overpass est demandé (≈ 100 Go)
dire "2 ter/8 — Emplacement des données"

# Les candidats : un système de fichiers monté, inscriptible, d'au moins 200 Go, qui n'est NI celui du dépôt NI un
# pseudo-système. Rien n'est formaté ni monté ici : on choisit parmi ce qui est déjà là.
disques_candidats() {
  local dev_depot
  dev_depot=$(stat -c %d "$racine" 2>/dev/null)
  df -B1000000000 --output=target,size,fstype 2>/dev/null | tail -n +2 | while read -r cible taille fstype _; do
    # Liste BLANCHE de systèmes de fichiers : un disque, pas un partage réseau ni un montage de service. Une base
    # SQLite de 20 Go sur du NFS ou du FUSE serait lente et fragile, et ce n'est pas au script de le découvrir.
    case "$fstype" in ext2 | ext3 | ext4 | xfs | btrfs | zfs | f2fs) ;; *) continue ;; esac
    case "$cible" in / | /boot | /boot/* | /proc* | /sys* | /run* | /dev* | /mnt/pve/*) continue ;; esac
    [ "$(stat -c %d "$cible" 2>/dev/null)" = "$dev_depot" ] && continue
    [ "${taille:-0}" -ge 200 ] || continue
    [ -w "$cible" ] || continue
    printf '%s %s\n' "$cible" "$taille"
  done
}

if [ -z "$donnees_mp" ] && [ "$donnees_demande" != 0 ]; then
  note "grappes tient sur ≈ 8 Go ; les données demandent 250 Go et plus, donc un second disque."
  if [ "$questions" = 1 ] && [ -n "$_tty" ]; then
    if veut "-1" "Mettre les données sur un autre disque (déjà formaté et monté) ?" "o"; then
      printf '   Point de montage du disque de données : '
      read -r donnees_mp < "$_tty" || donnees_mp=""
    fi
  else
    # Mode sans question : on cherche. Un seul candidat évident = on le prend. Zéro ou plusieurs = on s'arrête,
    # parce que verser 30 Go de bases sur un disque système de 20 Go serait une panne, pas un défaut de confort.
    candidats=$(disques_candidats)
    nb=$(printf '%s' "$candidats" | grep -c . || true)
    if [ "$nb" = 1 ]; then
      donnees_mp=$(printf '%s' "$candidats" | awk '{print $1}')
      taille_trouvee=$(printf '%s' "$candidats" | awk '{print $2}')
      note "disque de données trouvé : $donnees_mp (${taille_trouvee} Go)"
      # Un point de montage déjà occupé par autre chose : on se met dans un sous-dossier plutôt qu'en vrac.
      if [ -n "$(ls -A "$donnees_mp" 2>/dev/null | grep -v '^lost+found$' | head -1)" ] \
         && [ ! -d "$donnees_mp/copies" ] && [ ! -d "$donnees_mp/donnees" ]; then
        donnees_mp="$donnees_mp/grappes"
        note "ce disque contient déjà autre chose : les données iront dans $donnees_mp"
      fi
    else
      note ""
      if [ "$nb" = 0 ]; then
        note "AUCUN disque de données trouvé (il faut un système de fichiers monté, inscriptible, d'au moins 200 Go)."
      else
        note "PLUSIEURS disques possibles — je ne choisis pas à ta place :"
        printf '%s\n' "$candidats" | awk '{print "      " $1 "  (" $2 " Go)"}' | tee -a "$journal"
      fi
      note ""
      note "Les bases locales pèsent ≈ 30 Go, Overpass ≈ 100 Go : les verser sur le disque système les ferait"
      note "déborder. Prépare le disque, puis relance en le nommant :"
      note ""
      note "   sudo mkfs.ext4 -L grappes /dev/sdb1"
      note "   echo 'LABEL=grappes /srv/grappes ext4 defaults,noatime 0 2' | sudo tee -a /etc/fstab"
      note "   sudo mkdir -p /srv/grappes && sudo mount /srv/grappes && sudo chown -R \"\$USER\" /srv/grappes"
      note "   ./installer_grappes.sh --donnees /srv/grappes"
      note ""
      note "Ou, pour tout garder dans le dépôt malgré la place :  ./installer_grappes.sh --sans-autre-disque"
      exit 2
    fi
  fi
fi
if [ -n "$donnees_mp" ]; then
  if [ ! -d "$donnees_mp" ]; then
    rate "« $donnees_mp » n'est pas un dossier : montez le disque d'abord (rien n'est formaté ici). Les données restent dans le dépôt."
    donnees_mp=""
  elif ! ( : > "$donnees_mp/.essai_grappes" ) 2>/dev/null; then
    rate "« $donnees_mp » n'est pas accessible en écriture (sudo chown -R \"\$USER\" $donnees_mp). Les données restent dans le dépôt."
    donnees_mp=""
  else
    rm -f "$donnees_mp/.essai_grappes"
    taille_go=$(df -B1000000000 --output=size "$donnees_mp" 2>/dev/null | tail -1 | tr -dc '0-9')
    [ "$(stat -c %d "$donnees_mp" 2>/dev/null)" = "$(stat -c %d "$racine" 2>/dev/null)" ] \
      && note "ATTENTION : $donnees_mp est sur LE MÊME système de fichiers que le dépôt — le but d'un second disque est perdu."
    [ "${taille_go:-0}" -lt 250 ] && note "ATTENTION : ce disque fait ${taille_go:-?} Go ; 250 Go est le minimum conseillé (SIRENE indexé ≈ 20 Go, Overpass ≈ 100 Go, LibreTranslate ≈ 8 Go)."
    mkdir -p "$donnees_mp"/{donnees,copies,modeles,libretranslate}
    if "$PY" - "$racine" "$donnees_mp" >>"$journal" 2>&1 <<'PYEOF'
import sys
from pathlib import Path

import yaml

racine, mp = Path(sys.argv[1]), Path(sys.argv[2])
# pilote : où vont la base, le travail des recherches et les copies
f = racine / "pilote/config/pilote.yaml"
y = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
y.setdefault("donnees", {})
y["donnees"]["dossier"] = str(mp / "donnees")
y["donnees"]["copies"] = str(mp / "copies")
f.with_suffix(".yaml.avant").write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
f.write_text(yaml.safe_dump(y, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(f"pilote.yaml : donnees -> {mp}/donnees, copies -> {mp}/copies")
# grappes : où vont les modèles de lecture de noms (ils servent de HF_HOME)
g = racine / "grappes/config/ner.yaml"
if g.exists():
    yg = yaml.safe_load(g.read_text(encoding="utf-8")) or {}
    yg["modeles_dir"] = str(mp / "modeles")
    g.with_suffix(".yaml.avant").write_text(g.read_text(encoding="utf-8"), encoding="utf-8")
    g.write_text(yaml.safe_dump(yg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"ner.yaml : modeles_dir -> {mp}/modeles")
PYEOF
    then
      tail -2 "$journal" | sed 's/^/      /'
      note "les anciennes configurations sont gardées en .yaml.avant"
    else
      rate "la configuration n'a pas pu être modifiée : voir le journal"
      donnees_mp=""
    fi
  fi
else
  note "les données restent dans le dépôt (pilote/donnees) : à surveiller si le disque système est petit"
fi

# ---------------------------------------------------------------- 2 bis. extra de mesure (autocal)
# `pytrec_eval` et compagnie : ils ne servent QU'À MESURER la qualité du classement et des rapprochements
# (outils/mesurer_classement.py, outils/mesurer_rapprochement_fr.py, et les tests qui les vérifient). Lourds, et
# inutiles pour chercher : c'est pour ça qu'ils ne sont pas dans les dépendances de base.
dire "2 bis/8 — Outils de mesure (facultatif)"
note "≈ 500 Mo (numpy, scipy, scikit-learn, optuna, pytrec_eval) ; sans eux, les outils de mesure et 3 tests se sautent"
if veut "$mesure" "Installer les outils de mesure de la qualité ?" "n"; then
  if "$racine/grappes/.venv/bin/pip" -q install -e "$racine/grappes[autocal]" >>"$journal" 2>&1; then
    note "installés"
  else
    rate "outils de mesure — relancer : grappes/.venv/bin/pip install -e grappes[autocal]"
  fi
else
  note "sauté"
fi

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
  # Le dossier des copies vient de la CONFIGURATION (`donnees.copies`), pas d'un chemin deviné : s'il est sur une autre
  # partition — ce qui est le cas recommandé — c'est sur celle-là qu'il faut mesurer la place, pas sur le disque système.
  copies=$("$PY" -c "import sys; sys.path.insert(0,'$racine/pilote/src'); from pilote.config import charger; print(charger('$racine/pilote/config/pilote.yaml').dossier_copies)" 2>/dev/null || echo "$racine/pilote/donnees/copies")
  mkdir -p "$copies" 2>/dev/null || { note "impossible de créer $copies (droits ? partition non montée ?)"; copies="$racine/pilote/donnees/copies"; mkdir -p "$copies"; }
  note "les copies locales iront dans $copies"
  libre_go=$(df -BG --output=avail "$copies" 2>/dev/null | tail -1 | tr -dc '0-9')
  besoin=0; for id in $BASES; do besoin=$((besoin + $(place_de "$id"))); done
  note "${libre_go:-?} Go libres ; ~$besoin Go nécessaires pour les bases demandées"
  if [ "${libre_go:-0}" -lt "$besoin" ]; then
    note "ATTENTION : place annoncée insuffisante. Chaque import vérifie lui-même la place et s'arrête avant de remplir le disque."
    # Sans terminal, ou en mode « tout », on CONTINUE : abandonner toutes les bases en silence serait pire que de
    # laisser chaque import refuser la sienne, ce qu'il sait faire et dire.
    if [ -t 0 ] && [ "$tout" != 1 ] && [ -n "$_tty" ]; then
      demander "Continuer quand même ?" "n" || BASES=""
    else
      note "on continue : les imports trop gros s'arrêteront d'eux-mêmes, en le disant."
    fi
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
note "≈ 8 Go avec son environnement et ses modèles (fr, es, de, it, ar, ru, zh vers et depuis l'anglais)"
note "sans lui, la tuile Traduction reste éteinte et le plan de travail le dit"
if veut "$libretranslate" "Installer LibreTranslate et ses modèles ?" "n"; then
  # La recette est celle de outils/libretranslate/LISEZMOI.md : un environnement à part (ses dépendances ne sont pas
  # celles de pilote), et XDG_DATA_HOME / XDG_CACHE_HOME pour que les modèles aillent dans CE dossier et pas dans le
  # dossier personnel — c'est ce qui permet de les poser sur le disque des données.
  lt="${donnees_mp:+$donnees_mp/libretranslate}"
  lt="${lt:-$racine/pilote/outils/libretranslate}"
  mkdir -p "$lt"
  cp -n "$racine/pilote/outils/libretranslate/installer_modeles.py" "$racine/pilote/outils/libretranslate/lancer.sh" "$lt/" 2>/dev/null || true
  note "emplacement : $lt"
  if [ ! -x "$lt/venv/bin/python" ]; then
    python3 -m venv "$lt/venv" >>"$journal" 2>&1 && "$lt/venv/bin/pip" -q install argostranslate libretranslate >>"$journal" 2>&1 \
      || rate "LibreTranslate : son environnement n'a pas pu être créé (voir le journal)"
  fi
  if [ -x "$lt/venv/bin/python" ] && XDG_DATA_HOME="$lt/donnees" XDG_CACHE_HOME="$lt/cache" "$lt/venv/bin/python" "$lt/installer_modeles.py" >>"$journal" 2>&1; then
    # La tuile Traduction ne s'allume que si l'adresse du service est dans la configuration (LISEZMOI).
    "$PY" - "$racine" >>"$journal" 2>&1 <<'PYEOF'
import sys
from pathlib import Path

import yaml

f = Path(sys.argv[1]) / "pilote/config/pilote.yaml"
y = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
y.setdefault("suite", {})["traduction_url"] = "http://127.0.0.1:5000"
f.write_text(yaml.safe_dump(y, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("pilote.yaml : suite.traduction_url -> http://127.0.0.1:5000")
PYEOF
    note "installé ; lancer le service : $lt/lancer.sh  (démarrage automatique : voir outils/libretranslate/LISEZMOI.md)"
  else
    rate "LibreTranslate : les modèles ne sont pas installés (voir le journal et outils/libretranslate/LISEZMOI.md)"
  fi
else
  note "sauté"
fi

# ---------------------------------------------------------------- 7. Overpass
dire "7/8 — Overpass (géocodage OpenStreetMap local, France)"
note "exige Docker et ≈ 100 Go ; sans lui, le géocodage passe par le service public (bridé en débit, pas absent)"
if [ -z "$overpass_dir" ] && [ "$overpass" != 0 ]; then
  defaut_over="${donnees_mp:+$donnees_mp/overpass}"
  if [ "$questions" = 1 ] && [ -n "$_tty" ] && veut "-1" "Installer Overpass ?" "n"; then
    printf '   Dossier pour la base OpenStreetMap%s : ' "${defaut_over:+ [$defaut_over]}"
    read -r overpass_dir < "$_tty" || overpass_dir=""
    overpass_dir="${overpass_dir:-$defaut_over}"
  elif [ "$questions" != 1 ]; then
    overpass_dir="$defaut_over"   # mode sans question : sur le disque des données, à côté du reste
    [ -z "$overpass_dir" ] && note "pas de disque de données : Overpass est sauté (ses 100 Go n'iraient pas sur le disque système)"
  fi
fi
if [ -n "$overpass_dir" ]; then
  mkdir -p "$overpass_dir" 2>/dev/null
  note "dossier : $overpass_dir"
  if [ ! -d "$overpass_dir" ]; then
    rate "Overpass : « $overpass_dir » n'a pas pu être créé"
  elif ! command -v docker >/dev/null; then
    rate "Overpass : Docker est absent (sudo apt-get install docker.io, puis relancer avec --overpass $overpass_dir)"
  else
    # Docker demande d'être dans le groupe « docker », et l'appartenance à un groupe ne prend effet qu'à la prochaine
    # session : on ne peut pas se reconnecter au milieu d'une installation. On passe donc par sudo cette fois-ci, et on
    # ajoute au groupe pour les suivantes.
    lanceur=""
    if ! docker info >/dev/null 2>&1; then
      if sudo -n true 2>/dev/null || [ -n "$_tty" ]; then
        lanceur="sudo -E"
        sudo usermod -aG docker "$(id -un)" >>"$journal" 2>&1 \
          && note "ajouté au groupe « docker » : actif à ta prochaine connexion (cette fois-ci, on passe par sudo)"
      else
        rate "Overpass : Docker n'est pas joignable sans droits (sudo usermod -aG docker $(id -un), puis se reconnecter)"
      fi
    fi
    if [ -n "$lanceur" ] || docker info >/dev/null 2>&1; then
      if OVERPASS_DIR="$overpass_dir" $lanceur "$racine/pilote/outils/installer_overpass.sh" >>"$journal" 2>&1; then
        note "lancé : l'import de la France prend plusieurs heures EN TÂCHE DE FOND (docker logs -f overpass)"
        note "prêt quand http://127.0.0.1:12345/api/status répond ; l'installation continue sans l'attendre"
      else
        rate "Overpass (voir le journal)"
      fi
    fi
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
dossier_donnees=$("$PY" -c "import sys; sys.path.insert(0,'$racine/pilote/src'); from pilote.config import charger; c=charger('$racine/pilote/config/pilote.yaml'); print(c.donnees)" 2>/dev/null || echo "$racine/pilote/donnees")
dossier_copies=$("$PY" -c "import sys; sys.path.insert(0,'$racine/pilote/src'); from pilote.config import charger; print(charger('$racine/pilote/config/pilote.yaml').dossier_copies)" 2>/dev/null || echo "$dossier_donnees/copies")
for d in "$dossier_donnees" "$dossier_copies"; do
  [ -d "$d" ] && du -sh "$d" 2>/dev/null | awk '{print "   "$2" : "$1}' | tee -a "$journal"
done

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
