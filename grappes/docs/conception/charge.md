# Test de charge

Commande : `.venv/bin/python outils/charge.py 100000 <dossier>` (observations synthétiques, thèmes neutres, 5 000 sources, 3 écosystèmes, 0 à 2 citations par observation).

Mesure du 2026-10-06 (VM de développement, Python 3.13) :

| Étape | Durée |
| --- | --- |
| Insertion SQLite | 1,3 s |
| Chargement | 0,6 s |
| Scoring + recoupement + affectation (2 itérations) | 2,7 s |
| Sauvegarde du run | 0,3 s |
| Export CSV | < 0,1 s |
| **Total** | **5,0 s** |

Pic mémoire : environ 200 Mo ; base SQLite : 33 Mo. 6 666 entités, 100 246 citations, 10 000 enregistrements de validation.

Ces chiffres valent pour les lexiques de démonstration (2 grappes, quelques termes) ; le coût croît avec le nombre de grappes et de termes.

## Gros fichier : lecture en flux (2026-10-11)

Commande : `.venv/bin/python outils/charge.py --ingestion 500000 <dossier>` (un fichier `.jsonl` de 500 000 enregistrements X au format plat, soit 32 Mo, puis `ingest`, `run` et `export` avec `resultat.csv`).

| Étape | Durée |
| --- | --- |
| Ingestion par lots de 5 000 (lecture en flux, normalisation, écriture) | 9,5 s |
| `run` (500 000 observations) | 8,3 s |
| `export` (relance le `run`, puis CSV et `resultat.csv`) | 8,9 s |

Pic mémoire du processus entier : 606 Mo (l'ingestion seule reste bornée par la taille du lot ; le pic vient de `run`, qui charge toutes les observations pour le recoupement). Base : 98 Mo ; 25 000 entités.

Règles de robustesse : un `.jsonl` est lu ligne à ligne sans limite de taille ; une ligne de plus de 10 Mo est rejetée sans être chargée ; un octet invalide ne rejette que sa ligne ; un `.json` monolithique au-delà de `max_fichier_mo` (200 par défaut) est rejeté (le convertir en `.jsonl`) ; le détail des rejets est limité à 1 000 entrées, le compte reste exact. Chiffres valables pour la machine de développement ; ils ne sont pas une garantie.

