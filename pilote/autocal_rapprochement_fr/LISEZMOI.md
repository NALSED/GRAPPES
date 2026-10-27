# Jeu de cas difficiles du rapprochement français

Jeu **séparé** de FEBRL (anglophone, synthétique) et de `autocal/jeux.json` de grappes, qui reste intouché. Il est **répétable à volonté** : on le rejoue après chaque réglage de Fusion/doublons (document 20 de la suite).

Une ligne de `cas.jsonl` = une paire de fiches (`a`, `b`), le verdict correct (`meme` ou `differentes`) et une courte raison.

Mesure :

````
.venv/bin/python outils/mesurer_rapprochement_fr.py
````

Règle : tout faux positif ou faux négatif trouvé en usage réel (sessions de test ou usage normal) **rejoint ce jeu** au lieu d'être traité isolément. On n'ajuste jamais un seuil sur un seul exemple.
