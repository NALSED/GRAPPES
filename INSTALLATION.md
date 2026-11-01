# Installer grappes sur une VM neuve

Pour une VM Proxmox sous Debian 13 (ou Ubuntu 24.04). Tout passe par `./installer_grappes.sh`, qui propose
chaque prérequis sans l'imposer.

## 1. La VM

| | Minimum | Conseillé | Ce qui commande |
| :-- | :-- | :-- | :-- |
| Mémoire | 8 Go | **16 Go** | le modèle de lecture de noms (CamemBERT, ≈ 1,5 Go résident), le moteur de rapprochement (DuckDB, 0,5–2 Go), le pic d'indexation de SIRENE (≈ 1 Go) |
| Processeurs | 4 | **8** | le modèle de lecture de noms utilise tous les cœurs ; GDELT télécharge sur 6 fils ; `travail.fils: 2` = deux recherches en même temps |
| Disque | 70 Go | **120 Go** | voir le découpage ci-dessous |

**Type de processeur : `host`.** C'est le réglage le plus important de la création de la VM. Avec le `kvm64`
par défaut de Proxmox, les extensions AVX2 sont masquées, et DuckDB s'arrête en « instruction illégale »
(c'est la raison pour laquelle `duckdb` est épinglé en version 1 dans `pilote/pyproject.toml`). PyTorch est
sensible de la même façon.

Autres réglages : BIOS OVMF ou SeaBIOS indifférent, disque en VirtIO SCSI avec `discard` activé si le stockage
est en thin-provisioning, agent QEMU installé (`qemu-guest-agent`).

## 2. Le découpage du disque

Deux choses très différentes vivent sur ce disque : le **code et les environnements Python**, qui ne bougent
presque pas, et les **copies locales de bases**, qui pèsent et qui grossissent. Les séparer évite qu'un import
de SIRENE qui déborde remplisse la partition système.

### Option simple — un seul disque de 120 Go

| Partition / volume | Taille | Montage | Contenu |
| :-- | :-- | :-- | :-- |
| EFI | 512 Mo | `/boot/efi` | — |
| `/` | 30 Go | `/` | Debian, le dépôt, les deux environnements Python (≈ 4 Go avec PyTorch processeur), les modèles de lecture de noms (≈ 0,5 Go), LibreTranslate si installé (≈ 3 Go) |
| swap | 4 Go | — | — |
| `donnees` | 80 Go | `/srv/grappes` | base SQLite de pilote, dossiers de travail des recherches, **copies locales des bases** |

Avec LVM, un seul VG et deux LV (`racine`, `donnees`) : l'intérêt est de pouvoir étendre `donnees` plus tard
sans toucher au reste.

### Option propre — deux disques

Disque 1 de 32 Go pour `/` (+ swap), disque 2 de 100 Go pour `/srv/grappes`. C'est la même chose, mais la
sauvegarde et l'agrandissement du disque de données sont indépendants du système.

### Pourquoi 80 Go de données

| Poste | Taille |
| :-- | :-- |
| SIRENE indexé (27 M unités légales + jointure des sièges) | ≈ 20 Go |
| Archives SIRENE pendant l'import (0,98 + 2,88 Go, effacées après) | ≈ 4 Go |
| RNA, OpenSanctions, Wikidata France, GeoNames France, geoBoundaries | ≈ 4 Go |
| Fenêtre GDELT de 90 jours, filtrée France | 1 à 3 Go, à mesurer |
| Dossiers de travail des recherches, base de pilote, journaux | ≈ 2 Go |
| Marge (un import demande de la place pour l'archive **et** la base en même temps) | le reste |

Le minimum réel pour tout installer est de **45 Go**. 80 Go laisse de quoi réimporter SIRENE sans faire de
place à la main, et de quoi grossir.

### Si tu veux Overpass (géocodage OpenStreetMap local)

**Un disque de plus, 100 Go, formaté et monté avant l'installation.** C'est la seule exigence de
`outils/installer_overpass.sh`, et rien n'est formaté par les scripts. Sans Overpass, le géocodage passe par
le service public : c'est fonctionnel, juste bridé en débit.

## 3. Mettre les données sur la partition de données

Par défaut, tout vit dans `pilote/donnees/`, donc sur la partition du dépôt. Deux lignes de
`pilote/config/pilote.yaml` déplacent ce qui pèse :

````yaml
donnees:
  dossier: /srv/grappes/donnees    # base SQLite, travail des recherches, certificat
  copies: /srv/grappes/copies      # copies locales des bases (les gros fichiers)
````

À faire **avant** de lancer l'installation des bases : le script lit ces chemins dans la configuration, c'est
sur eux qu'il vérifie la place disque, et c'est là qu'il versera les bases.

````bash
sudo mkdir -p /srv/grappes/{donnees,copies}
sudo chown -R "$USER:$USER" /srv/grappes
````

## 4. L'installation

````bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/NALSED/GRAPPES.git grappes
cd grappes
# déplacer les données maintenant (étape 3) si tu as une partition dédiée
./installer_grappes.sh
````

Le script pose huit questions, dans cet ordre, avec une réponse par défaut entre crochets :

| Étape | Défaut | Ce que ça change |
| :-- | :-- | :-- |
| 1. Paquets système | oui | la seule étape qui demande `sudo`. Sans `libicu-dev` et `pkg-config`, l'étape 2 échoue sur `pyicu` |
| 2. Environnements Python | — | obligatoire, quelques minutes (PyTorch en version processeur) |
| 2 bis. Outils de mesure | non | ≈ 500 Mo, servent seulement à mesurer la qualité du classement |
| 3. Bases locales | oui | les six, ou une par une si tu réponds non au groupe. **SIRENE prend plusieurs heures** |
| 4. Fenêtre GDELT | oui | des milliers de fichiers de 15 minutes ; long, et reprenable |
| 5. SearXNG | oui | recherche web auto-hébergée, évite une API payante |
| 6. LibreTranslate | non | ≈ 2–3 Go de modèles de traduction hors ligne |
| 7. Overpass | non | demande le point de montage du disque de 100 Go |
| 8. Service systemd puis lancement | oui | démarrage automatique, et survit à la déconnexion SSH |

Pour ne rien demander : `--tout`. Pour le strict nécessaire : `--minimal`. Chaque étape a son option
(`--sans-gdelt`, `--bases "rna-local geonames-fr"`, `--overpass /mnt/osm`…), ce qui permet de rejouer une
installation à l'identique. `./installer_grappes.sh --help` les liste.

**C'est reprenable.** Une base déjà importée est sautée, un téléchargement coupé reprend où il en était, et un
prérequis qui échoue n'arrête pas les autres : la liste de ce qui reste à faire est donnée à la fin, avec le
journal (`installation.log`).

### Faire l'installation en plusieurs fois

C'est recommandé, parce que SIRENE et GDELT sont longs :

````bash
./installer_grappes.sh --minimal                 # le socle, puis l'interface répond
./installer_grappes.sh --sans-systeme --bases "geoboundaries-fr geonames-fr opensanctions-local rna-local wikidata-fr" --sans-gdelt
./installer_grappes.sh --sans-systeme --bases "sirene-local" --sans-gdelt   # la grosse, à lancer le soir
./installer_grappes.sh --sans-systeme --sans-bases --gdelt-jours 90
````

## 5. Atteindre l'interface depuis ton poste

Par défaut le service n'écoute que la VM elle-même. Dans `pilote/config/pilote.yaml` :

````yaml
service:
  hote: 0.0.0.0                       # écoute sur le réseau
  hotes_autorises: [grappes.local]    # le nom par lequel tu y accèdes, en plus de la boucle locale
````

Puis `systemctl --user restart pilote.service`. Le certificat est auto-signé et porte le nom de la machine, son
adresse et les hôtes autorisés : le navigateur prévient à la première visite, c'est normal.

## 6. Vérifier que tout est en place

````bash
curl -sk https://127.0.0.1:8443/api/sante            # {"ok":true,"grappes_present":true}
cat pilote/donnees/bases_locales.json                 # une ligne par base importée, avec son nombre de lignes
systemctl --user status pilote.service
cd pilote && .venv/bin/python -m pytest -q -k "not reseau and not chromium"
````

La suite de tests demande que les deux environnements existent ; trois tests de mesure se sautent d'eux-mêmes
si tu n'as pas installé les outils de mesure (étape 2 bis), en disant la commande qui les activerait.
