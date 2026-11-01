# Installer grappes sur une VM neuve

Pour une VM Proxmox sous Debian 13 (ou Ubuntu 24.04). Tout passe par `./installer_grappes.sh`, qui propose
chaque prérequis sans l'imposer et qui place lui-même les données sur le second disque.

## 1. La VM

| | Minimum | Conseillé | Ce qui commande |
| :-- | :-- | :-- | :-- |
| Mémoire | 8 Go | **16 Go** | le modèle de lecture de noms (CamemBERT, ≈ 1,5 Go résident), le moteur de rapprochement (DuckDB, 0,5–2 Go), le pic d'indexation de SIRENE (≈ 1 Go) |
| Processeurs | 4 | **8** | le modèle de lecture de noms utilise tous les cœurs ; GDELT télécharge sur 6 fils ; `travail.fils: 2` = deux recherches en même temps |
| Disque système | 20 Go | **20 Go** | Debian, le dépôt, les deux environnements Python |
| Disque de données | 250 Go | **250 Go et plus** | tout ce qui pèse et qui grossit (voir § 2) |

**Type de processeur : `host`.** C'est le réglage le plus important de la création de la VM. Avec le `kvm64`
par défaut de Proxmox, les extensions AVX2 sont masquées, et DuckDB s'arrête en « instruction illégale »
(c'est pour cette raison que `duckdb` est épinglé en version 1 dans `pilote/pyproject.toml`). PyTorch est
sensible de la même façon.

Autres réglages : disque en VirtIO SCSI, `discard` activé si le stockage est en thin-provisioning, agent
QEMU (`qemu-guest-agent`) installé.

## 2. Les deux disques

Deux choses très différentes : le **code**, qui ne bouge presque pas et tient dans 20 Go, et les **données**,
qui pèsent et qui grossissent. Les séparer évite qu'un import de SIRENE qui déborde remplisse la partition
système, et permet d'agrandir les données sans toucher au reste.

### Disque 1 — 20 Go, le système et grappes

| Partition | Taille | Montage |
| :-- | :-- | :-- |
| EFI | 512 Mo | `/boot/efi` |
| swap | 2 Go | — |
| `/` | le reste (≈ 17 Go) | `/` |

Ce qui y vit : Debian (≈ 2,5 Go), le dépôt, l'environnement Python de grappes avec PyTorch processeur
(≈ 3,5 Go), celui de pilote (≈ 0,7 Go), SearXNG si installé (≈ 0,4 Go). Soit **≈ 8 Go utilisés**, le reste
en marge pour les mises à jour et le cache d'apt.

### Disque 2 — 250 Go minimum, toutes les données

Un seul système de fichiers, monté par exemple sur `/srv/grappes`. Le script y crée cinq dossiers :

| Dossier | Contenu | Taille |
| :-- | :-- | :-- |
| `donnees/` | base SQLite de pilote, dossiers de travail des recherches, certificat | ≈ 2 Go, grossit avec l'usage |
| `copies/` | copies locales des bases **et** leurs archives pendant l'import | ≈ 30 Go (SIRENE indexé ≈ 20 Go, + 4 Go d'archives pendant son import) |
| `modeles/` | modèles de lecture de noms (sert de `HF_HOME` à grappes) | ≈ 1 Go |
| `libretranslate/` | environnement et modèles de traduction hors ligne | ≈ 8 Go |
| `overpass/` | base OpenStreetMap France, si Overpass est demandé | ≈ 100 Go |

Total si tu installes tout, Overpass compris : **≈ 140 Go**. Les 250 Go laissent de quoi réimporter sans
faire de place à la main, allonger la fenêtre GDELT, et ajouter des bases.

Avec LVM, un VG sur le disque 2 et un LV `donnees` : tu pourras l'étendre plus tard sans rien démonter.

### Préparer le disque 2

````bash
sudo mkfs.ext4 -L grappes /dev/sdb1
echo 'LABEL=grappes /srv/grappes ext4 defaults,noatime 0 2' | sudo tee -a /etc/fstab
sudo mkdir -p /srv/grappes && sudo mount /srv/grappes
sudo chown -R "$USER:$USER" /srv/grappes
````

Le script ne formate rien et ne monte rien : il refuse un dossier absent ou non accessible en écriture, et le
dit. Il prévient aussi si le dossier donné se trouve en réalité sur le même système de fichiers que le dépôt.

## 3. L'installation, d'un seul coup

````bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/NALSED/GRAPPES.git grappes
cd grappes
./installer_grappes.sh --tout --donnees /srv/grappes --overpass /srv/grappes/overpass
````

`--tout` installe **chaque** étape sans poser de question : paquets système, environnements Python, outils de
mesure, les six bases locales, la fenêtre GDELT de 90 jours, SearXNG, LibreTranslate, le service systemd, puis
le lancement. `--donnees` place tout ce qui pèse sur le disque 2 (il écrit `pilote/config/pilote.yaml` et
`grappes/config/ner.yaml`, en gardant les versions précédentes en `.yaml.avant`).

Overpass reste à part même avec `--tout`, parce qu'il demande un dossier qui ne se devine pas : sans
`--overpass`, il est simplement sauté.

**Compte plusieurs heures**, et tu peux fermer ta session SSH en route si tu lances sous `tmux` ou `screen` :

````bash
tmux new -s grappes
./installer_grappes.sh --tout --donnees /srv/grappes --overpass /srv/grappes/overpass
# Ctrl-B puis D pour détacher ; tmux attach -t grappes pour revenir
````

C'est **reprenable** : une base déjà importée est sautée, un téléchargement coupé reprend où il en était, un
prérequis qui échoue n'arrête pas les autres. La liste de ce qui reste à faire est donnée à la fin, avec le
journal (`installation.log`).

### Si tu préfères étaler

````bash
./installer_grappes.sh --donnees /srv/grappes                 # pose les questions une par une
./installer_grappes.sh --minimal --donnees /srv/grappes       # le socle seul : l'interface répond déjà
./installer_grappes.sh --sans-systeme --bases "sirene-local" --sans-gdelt   # la grosse base, le soir
````

`./installer_grappes.sh --help` liste toutes les options.

## 4. Atteindre l'interface depuis ton poste

Par défaut le service n'écoute que la VM elle-même. Dans `pilote/config/pilote.yaml` :

````yaml
service:
  hote: 0.0.0.0                       # écoute sur le réseau
  hotes_autorises: [grappes.local]    # le nom par lequel tu y accèdes, en plus de la boucle locale
````

Puis `systemctl --user restart pilote.service`. Le certificat est auto-signé et porte le nom de la machine,
son adresse et les hôtes autorisés : le navigateur prévient à la première visite, c'est normal.

## 5. Vérifier que tout est en place

````bash
curl -sk https://127.0.0.1:8443/api/sante            # {"ok":true,"grappes_present":true}
cat /srv/grappes/donnees/bases_locales.json          # une ligne par base, avec son nombre de lignes
df -h / /srv/grappes                                 # la place prise de chaque côté
systemctl --user status pilote.service
cd pilote && .venv/bin/python -m pytest -q -k "not reseau and not chromium"
````

La suite de tests demande que les deux environnements existent. Trois tests de mesure se sautent d'eux-mêmes
si les outils de mesure ne sont pas installés, en disant la commande qui les activerait.
