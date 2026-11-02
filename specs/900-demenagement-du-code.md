# 900 — Déménager l'outillage d'installation vers GAPPES-FINAL

Hors du pavé de retours : c'est de l'infrastructure, décidée par Sednal le 02/11/2026 en même temps
que le partage **GRAPPES = specs / GAPPES-FINAL = code**.

## Pourquoi

GRAPPES devient le dépôt des specs, GAPPES-FINAL celui du code. Donc la VM de test (**.115**) doit
tirer son code de GAPPES-FINAL, et non plus de GRAPPES.

**Mais GAPPES-FINAL n'a aucun outillage d'installation** : `installer.sh`, `installer_grappes.sh`,
`lancer.sh` et `INSTALLATION.md` n'existent qu'à la racine de GRAPPES. En l'état, GAPPES-FINAL
n'est pas installable sur une machine neuve.

C'est pour ça que **GRAPPES ne sera vidé de son code qu'après** que .115 tourne depuis GAPPES-FINAL
(voir §5). Tant que ce n'est pas fait, le code de GRAPPES reste la seule copie installable, et c'est
ce qui fait tourner la machine de test de Sednal.

## 1. La seule difficulté : les deux dépôts n'ont pas la même forme

| | **GRAPPES** | **GAPPES-FINAL** |
| :-- | :-- | :-- |
| Le moteur | dans `grappes/` | **à la racine du dépôt** (`src/grappes`, `pyproject.toml` à la racine) |
| Environnement du moteur | `grappes/.venv` | `.venv` (racine) |
| Configuration du moteur | `grappes/config/` | `config/` |
| Clés du moteur | `grappes/config/secrets.env` | `config/secrets.env` |
| pilote | `pilote/` | `pilote/` — **identique** |

L'outillage de GRAPPES suppose partout la première forme. Il faut l'adapter à la seconde.

**Ce qu'on ne fait pas :** on ne restructure **pas** GAPPES-FINAL pour qu'il ressemble à GRAPPES. Le
moteur de momo est la version de référence et il ne bouge pas — décision de Sednal du 02/11. C'est
l'outillage qui s'adapte au dépôt, jamais l'inverse. Un déplacement de `src/grappes` casserait trente
commits d'historique, les chemins des tests, `CLAUDE.md`, `MISSION.md` et la mission
d'autocalibration, pour ne gagner que la commodité d'un script.

Bonne nouvelle : **les deux conventions nécessaires existent déjà** dans GAPPES-FINAL. Son
`.gitignore` ignore déjà `.venv/` et `config/secrets.env`. Il n'y a donc rien à inventer, juste à
poser les scripts et à corriger leurs chemins.

## 2. Les quatre fichiers à porter, et ce qui change dans chacun

À copier depuis `NALSED/GRAPPES` (dernier commit) vers la racine de GAPPES-FINAL, puis à corriger.

### 2.1 `installer.sh`

Crée un environnement Python par application. Trois endroits à changer :

| Ligne d'origine | Devient |
| :-- | :-- |
| `[ -x "$racine/grappes/.venv/bin/python" ] \|\| python3 -m venv "$racine/grappes/.venv"` | `.venv` à la **racine** : `"$racine/.venv"` |
| `"$racine/grappes/.venv/bin/pip" … install torch …` | `"$racine/.venv/bin/pip" … install torch …` |
| la boucle `for app in grappes pilote; do … -e "$racine/$app"; done` | **ne peut plus être une boucle sur deux sous-dossiers** : le moteur s'installe par `-e "$racine"` dans `"$racine/.venv"`, pilote par `-e "$racine/pilote"` dans `"$racine/pilote/.venv"` |
| `"$racine/grappes/.venv/bin/pip" -q install pg8000 pymysql` | `"$racine/.venv/bin/pip" …` |
| `[ -f "$racine/grappes/config/secrets.env" ]` et son `printf` | `"$racine/config/secrets.env"` |

Les messages d'aide affichés à l'utilisateur citent des chemins (`grappes/.venv/bin/pip install
torch…`) : les corriger aussi, sinon ils envoient l'utilisateur sur un dossier qui n'existe pas.

Le reste du script — contrôle de Python 3.11, détection des paquets système manquants (`pkg-config`,
`build-essential`, `libicu-dev`, `python3-dev`), torch en version processeur avant tout le reste — ne
change pas. **Garder ces garde-fous tels quels** : ce sont eux qui évitent le premier mur d'une
machine neuve (la compilation de `pyicu`) et le téléchargement inutile de plusieurs gigaoctets de
CUDA.

### 2.2 `installer_grappes.sh`

Le script d'installation complet, en 8 étapes. Deux motifs à remplacer partout :

* `$racine/grappes/` → `$racine/` (le moteur **est** la racine)
* `$racine/pilote/` → **inchangé**

Les occurrences repérées à la lecture : les deux contrôles de `.venv` de l'étape 2, le
`pip install -e "$racine/grappes[autocal]"` de l'autocalibration, et le chemin de
`grappes/config/secrets.env`. Momo relit le script en entier : la liste ci-dessus est un repère, pas
un inventaire garanti.

**Attention au bloc qui place les données sur le second disque.** Il écrit `donnees.dossier`,
`donnees.copies` dans `pilote/config/pilote.yaml` et `modeles_dir` dans `config/ner.yaml` du moteur.
Ce bloc vient d'être corrigé dans GRAPPES (commit `0d2669e`, 02/11/2026) : il faisait un aller-retour
`yaml.safe_load` / `yaml.safe_dump` qui **effaçait tous les commentaires** des fichiers de
configuration et faisait passer les clés par le résolveur booléen de PyYAML — c'est comme ça que la
Norvège (`NO`) est devenue `False` en production sur .115. **Porter la version corrigée**, celle qui
remplace la valeur ligne par ligne avec `remplacer_valeur()`, jamais l'ancienne.

### 2.3 `lancer.sh`

Lance l'interface web. Vérifier et corriger les chemins qu'il suppose.

### 2.4 `INSTALLATION.md`

Le mode d'emploi : taille de la VM (16 Go de mémoire, 8 processeurs, un disque de 20 Go pour le
système et un de 250 Go pour les données), type de processeur `host` sur Proxmox — sans quoi DuckDB
s'arrête en « instruction illégale ». **Le contenu matériel ne change pas**, seuls les chemins et le
nom du dépôt dans les commandes de clonage.

### 2.5 Et le `README.md` de GAPPES-FINAL

Y ajouter la section d'installation : cloner, lancer `./installer_grappes.sh`, ouvrir
`https://127.0.0.1:8443`. GAPPES-FINAL devient le dépôt depuis lequel on installe — son README doit
le dire.

## 3. Le fichier de configuration à corriger

Dans `pilote/config/pilote.yaml` de GAPPES-FINAL, une seule ligne :

````yaml
grappes:
  racine: ../grappes     # devient :  racine: ..
````

Le moteur n'est plus le dossier voisin, c'est le dossier **parent** de `pilote/`. Corriger le
commentaire de la ligne en même temps, sinon il décrit une structure qui n'existe plus.

Vérifier aussi `grappes.python` (`.venv/bin/python`, relatif à la racine du moteur) et
`grappes.secrets` (`config/secrets.env`) : ces deux-là restent justes, puisqu'ils sont relatifs à la
racine du moteur, qui est maintenant la racine du dépôt.

## 4. Comment momo vérifie que c'est bon

Dans l'ordre, et **sans sauter la dernière** :

1. `./installer.sh` passe sur GAPPES-FINAL, et crée bien `.venv` à la racine **et**
   `pilote/.venv`.
2. Les deux suites de tests passent :
   * le moteur, depuis la racine ;
   * pilote : `cd pilote && .venv/bin/python -m pytest -m "not reseau"` (505 tests qui ne dépendent
     d'aucun service extérieur, et qui ne se sautent jamais).
3. `./lancer.sh` démarre, et `https://127.0.0.1:8443/` **et** `/suite` répondent.
4. **Le vrai test** : une installation depuis zéro, sur une machine ou un conteneur neuf, par un
   simple `git clone` de GAPPES-FINAL puis `./installer_grappes.sh`, sans rien corriger à la main. Si
   une seule commande doit être rattrapée au clavier, le déménagement n'est pas fini.

## 5. L'ordre des opérations, et ce qui ne doit pas être fait avant

| # | Qui | Quoi |
| :-- | :-- | :-- |
| 1 | **momo** | Porte et adapte les quatre fichiers (§2), corrige `pilote.yaml` (§3), vérifie (§4), pousse sur GAPPES-FINAL |
| 2 | **Sednal** | Réinstalle .115 depuis GAPPES-FINAL et vérifie que tout tourne |
| 3 | **Claude** | **Seulement là**, vide GRAPPES de `grappes/` et `pilote/` : il ne reste que les specs |

**Rien de l'étape 3 ne se fait avant que l'étape 2 soit confirmée par Sednal.** Vider GRAPHES avant
laisserait .115 sans aucune source de code installable.

Pour l'étape 2, un point qui demande une décision de Sednal, à lui poser **avant** de toucher à .115 :
sa configuration actuelle n'est pas dans le dépôt (clés d'API dans `secrets.env`, chemins
`/srv/grappes`, `reglages.yaml`, préréglages personnalisés, et la base SQLite avec ses recherches).
Une réinstallation depuis un autre dépôt ne doit pas les perdre — il faut décider si on les reprend
depuis l'installation actuelle, et lesquels.

## 6. Ce que ce déménagement ne change pas

* **Le moteur de momo.** Il ne bouge pas, ni de place ni de contenu.
* **La structure de GAPPES-FINAL.** On adapte les scripts à elle.
* **Les garde-fous de l'installeur** : paquets système, torch processeur, pilotes de base de données,
  création des `secrets.env` vides en `chmod 600`. Tout ça reste, à l'identique.
