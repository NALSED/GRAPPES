# GRAPPES — les specs

> ## Qui travaille où (02/11/2026)
>
> | Dépôt | Rôle | Qui y écrit |
> | :-- | :-- | :-- |
> | **NALSED/GRAPPES** (ici) | **les specs** | Sednal et Claude |
> | **NALSED/GAPPES-FINAL** | **le code** | momo |
>
> **momo : tu ne codes pas ici.** Les specs à implémenter sont dans [`specs/`](specs/), une par
> point, avec leur état dans [`specs/000-INDEX.md`](specs/000-INDEX.md). Une spec ne part au code que
> lorsque Sednal l'a validée.
>
> Le code présent dans `grappes/` et `pilote/` ci-dessous **reste provisoirement** : la VM de test
> (.115) tourne encore sur ce dépôt, et GAPPES-FINAL n'a pas encore son outillage d'installation. Il
> part dès que ce déménagement est fait.

Entités (organisations, groupes, sites) rangées en **grappes** par proximité sémantique et validation par recoupement de sources.

Ce dépôt contient deux applications qui marchent ensemble :

* **`grappes/`** — le moteur : collecte, recoupement, classement, export CSV, serveur MCP en lecture seule.
* **`pilote/`** — l'interface web : lancer une recherche, la suivre, trier les résultats, décider, exporter.

## Installation

Prérequis : Linux (Debian 13 ou Ubuntu 24.04 conseillés), Python 3.11 ou plus, git.

**Sur une machine ou une VM neuve**, un seul script fait tout sans rien demander — paquets système,
environnements Python, bases locales, services, lancement :

````bash
git clone https://github.com/NALSED/GRAPPES.git grappes
cd grappes
./installer_grappes.sh
````

**Taille de la VM, découpage des disques et installation pas à pas : voir [`INSTALLATION.md`](INSTALLATION.md).**
À retenir : 16 Go de mémoire, 8 processeurs, **un disque de 20 Go pour le système et grappes, un second de
250 Go pour les données**, et sur Proxmox le **type de processeur `host`** (avec `kvm64`, DuckDB s'arrête en
« instruction illégale »).

Pour n'installer que le code, sans les bases ni les services : `./installer.sh` puis `./lancer.sh`.

Ouvrir ensuite <https://127.0.0.1:8443> (certificat auto-signé : accepter l'avertissement du navigateur une fois).

## Clés d'API (facultatives)

Les sources gratuites marchent sans clé. Pour les autres, écrire les clés dans `pilote/config/secrets.env` ou `grappes/config/secrets.env` (une par ligne, `NOM=valeur`). Ces fichiers ne sont jamais versionnés.

## Utilisation

* **Interface web** : pages Réglages (sources), Ajout (nouvelle source), Lancement (sujet, profondeur), Tri (décisions) ; voir `pilote/README.md`.
* **Ligne de commande** : voir `grappes/README.md` et `grappes/docs/utilisateur.md`.

## Service en arrière-plan (facultatif)

````bash
pilote/outils/installer_service.sh
````

Installe pilote comme service systemd utilisateur. Le cycle automatique de grappes (`grappes/outils/systemd/`) se planifie de la même façon, après avoir adapté les chemins.

## Tests

````bash
cd grappes && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
cd ../pilote && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
````

Certains tests de grappes (autocalibration) demandent les extras `autocal` ; voir `grappes/pyproject.toml`.

## Licence

MIT (`LICENSE`).

## Première utilisation

Au premier lancement, grappes télécharge des données publiques (liste Tranco, modèles de reconnaissance de noms) : la première recherche est plus lente, et en profondeur « Strict » elle peut y consacrer une partie de son budget d'appels. Préférer « Normal » pour la première recherche.
