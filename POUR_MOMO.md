# Note pour momo — ce dépôt (GRAPPES) est la source

Écrit le 02/11/2026, à la demande de Sednal. But : repartir d'un état commun avant de continuer à coder dessus.

## Ce qui compte

**NALSED/GRAPPES est désormais le dépôt de référence.** Toute reprise de travail sur `pilote` (l'interface) repart
d'ici, pas d'une copie antérieure. Dernier commit à la date de cette note : `aa63075`.

## Ce qu'il y a dans ce dépôt

Deux applications, comme déjà documenté dans `README.md` :

* **`grappes/`** — le moteur (collecte, recoupement, classement, export).
* **`pilote/`** — l'interface web qui pilote le moteur.

`pilote` sert actuellement **deux interfaces en parallèle**, sur le même serveur :

* `/` — l'interface classique (HTML/JS simple, sans build).
* `/suite` — la nouvelle interface, construite sur une charte visuelle et une bibliothèque de composants propres
  (`pilote/static/suite/`, jetons dans `charte/jetons.css` et `charte/typo.css`), avec son propre assistant de
  première installation depuis ce dernier commit.

**`/` reste la page servie par défaut.** Basculer `/suite` comme interface par défaut à l'installation n'est **pas
encore fait** — Sednal fait d'abord une revue complète de l'interface avant de trancher. Ne pas partir du principe
que `/suite` remplace `/` tant que ça n'a pas été dit explicitement.

## Ce que ce dépôt n'est PAS

Ce dépôt ne contient pas ton moteur `grappes` (NER, rapprochement Splink, scoring, fiabilité, registres,
autonomie...). Ce travail reste dans GRAPPES2, séparément — aucun fichier en commun avec ce dépôt en dehors de noms
génériques. Le dépôt `GAPPES-FINAL` existe comme cible de fusion éventuelle mais cette fusion est **en attente** :
ni le périmètre ni le calendrier ne sont décidés. N'en tiens pas compte pour l'instant.

## Pour travailler dessus

* Tests : `cd pilote && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest` (`-m "not reseau"` pour la
  partie qui ne dépend d'aucun service extérieur).
* Toute nouvelle valeur de style dans `/suite` passe par les jetons (`charte/jetons.css`/`typo.css`), jamais en dur
  — vérifié par `tests/test_suite_navigateur.py::test_aucune_valeur_de_style_en_dur`.
* La suite pour la prochaine étape : Sednal fait sa revue de l'interface, puis la transmet.

Pour toute question sur l'orientation (bascule `/suite`, fusion avec GRAPPES2, etc.) : voir avec Sednal, pas de
décision à prendre seul sur ces points.
