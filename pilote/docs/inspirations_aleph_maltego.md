# Ce que pilote retient d'Aleph et de Maltego

Lecture de `inspi/sources.md` (notes de travail sur la documentation publique d'Aleph/OCCRP et de Maltego), le 26/10/2026. Règle de ce document : on
reprend des **idées**, jamais du code ni une interface, et on ne retient que ce qui sert la priorité de grappes — un résultat sûr, dont on sait
toujours d'où vient chaque information.

## Retenu et fait

* **Un format d'échange du même écosystème** (`formats/ftm.py`, `.ftm`, NDJSON, une entité par ligne : `id`, `schema`, `properties` à valeurs en liste).
  Les entités sont validées par la bibliothèque officielle `followthemoney` dans les tests (dépendance de développement seulement : le format
  lui-même n'importe rien). Trois idées d'Aleph y sont appliquées :
  * **identifiant stable** (nom normalisé + numéro officiel + pays) : réimporter le même résultat ne crée pas de doublon ;
  * **un schéma par genre** (entreprise → `Company`, association/club/administration → `Organization`, …), sans rien deviner
    quand le genre est inconnu (`LegalEntity`) ;
  * **provenance dans l'entité** : une note par source qui a trouvé le nom, la date et la recherche de collecte, la décision de l'utilisateur.
  Limite dite : la provenance est **par entité**, pas par valeur (pilote ne garde pas quelle source a donné la ville ou le numéro).

## Déjà en place (rien à faire)

* Deux étages de recoupement avec décision humaine (grappes regroupe, la page Tri garde / rejette / met de côté, annulable) ; la décision n'est
  jamais prise par le programme.
* Contrat de source déclaré, réglages séparés du code, limites d'appels respectées, journal, disjoncteur, budget et quotas autour de chaque appel
  (l'équivalent des « middlewares » de Maltego).
* Playbooks déclaratifs : les recherches avancées sauvegardées gardent leurs tuiles, leurs coordonnées et leurs liens.
* Séparation vérité / vue : la base de pilote est la vérité, les exports et la page Tri en sont des vues reconstructibles.
* Catalogue de types : les genres de `pilote.yaml` jouent le rôle de la liste d'entités standard.

## Non retenu, et pourquoi

* **Intégrer du code AGPL** (ingest-file, openaleph-search) : décision réservée à Sednal ; rien n'en est repris. `followthemoney` (MIT) n'est
  utilisé que pour valider les tests.
* **Moteur de recherche séparé, file de tâches distribuée, Elasticsearch** : disproportionné pour un programme local à un utilisateur ; SQLite
  reste le choix (F11-3).
* **Permissions par collection, multi-utilisateurs** : pilote n'écoute que cette machine, sans comptes.
* **Rétro-ingénierie de Maltego** : exclue (EULA). Rien dans ce dépôt n'y touche et rien n'y touchera.
* **Mode « seed-then-expand »** (élargir une grappe en appelant d'autres sources à partir d'un nom) : idée utile, mais c'est une fonction nouvelle
  du moteur, pas une retouche. Notée dans QUESTIONS (F21-1).
* **Connecteurs distants en HTTP** : les sources déclaratives (api, mcp, fichier, base) couvrent déjà l'isolation des sources instables.

## Les cinq points ouverts du document, avec la réponse du projet

1. Stockage : SQLite seul (F11-3, décidé).
2. AGPL : inspiration seulement, tant que Sednal n'a pas décidé autrement.
3. Connecteurs : en processus (adaptateurs et déclarations) ; pas de mode distant.
4. Provenance : par entité aujourd'hui (voir plus haut) ; par valeur demanderait de changer le pont, à décider.
5. Interface : web, comme Aleph.
