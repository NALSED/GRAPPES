# GRAPPES

Entités (organisations, groupes, sites) rangées en **grappes** par proximité sémantique et validation par recoupement de sources.

Ce dépôt contient deux applications qui marchent ensemble :

* **`grappes/`** — le moteur : collecte, recoupement, classement, export CSV, serveur MCP en lecture seule.
* **`pilote/`** — l'interface web : lancer une recherche, la suivre, trier les résultats, décider, exporter.

## Installation

Prérequis : Linux ou macOS, Python 3.11 ou plus, git.

````bash
git clone https://github.com/NALSED/GRAPPES.git
cd GRAPPES
./installer.sh
./lancer.sh
````

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
