# pilote

Application locale pour lancer, trier et décider les recherches de **grappes** (décision D70, `DECISION_PILOTE.md`).
Une application = une fonction : grappes reste la multiprise et garde sa ligne de commande ; pilote l'utilise comme bibliothèque.

* **Technique** : FastAPI, HTML/JS simple (aucune chaîne de build, pas de npm), SQLAlchemy + SQLite, un service systemd utilisateur.
* **Configuration** : `config/pilote.yaml` (port, HTTPS, racine de grappes, crans de profondeur, familles de prises). Aucun chemin en dur.
* **Installer et démarrer** : `./installer.sh` puis `./lancer.sh` à la racine du dépôt (ou `outils/installer_service.sh` pour un service systemd) (crée l'environnement, installe, active le service). Adresse : `https://127.0.0.1:8443`
  (certificat auto-signé créé au premier lancement ; `service.https: false` pour du HTTP simple ; `service.hote: 0.0.0.0` pour
  l'ouvrir au réseau, sans comptes : à ne faire que sur un réseau de confiance).
* **Tests** : `.venv/bin/python -m pytest` (les pages sont testées sous Node, il n'y a pas de navigateur).
* **Pages** : Réglages (état matériel des prises), Ajout (nouvelle prise), Lancement (sujet, profondeur, suivi), Tri (paquets, décisions).


## Sources et mentions obligatoires

Certaines sources n'autorisent leur usage libre qu'à condition d'être citées. Elles le déclarent (champ `attribution` de leur fichier dans `config/sources/`),
et leur mention est ajoutée à `SOURCES.txt` à côté des fichiers de sortie de toute recherche qui s'en est servie.

* **GDELT** — *Données de presse : GDELT Project* — <https://www.gdeltproject.org>. Usage libre, y compris commercial, à condition de citer le GDELT Project
  et de mettre un lien vers gdeltproject.org.

## Licence

MIT (fichier `LICENSE`). Les bibliothèques copiées dans `static/vendor/` (Tabulator, Cytoscape.js) gardent leur propre licence MIT.

## Nouvelle interface (`/suite`)

En plus des pages ci-dessus, l'interface décrite par la spécification `suite/pilote` est servie sur `/suite` : Réglages (sources et outils), Recherche (simple, plan de travail libre appliqué par le moteur, recherches sauvegardées), Tri (rapprochements proposés par Splink, à confirmer ou séparer) et l'Aide. Les sources y sont les déclarations de `config/sources`. Voir `docs/inspirations_aleph_maltego.md` pour l'export FollowTheMoney (`.ftm`).
