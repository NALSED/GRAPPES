# Jeu rejouable du classement (ordre des résultats)

Même forme que `autocal_rapprochement_fr/` : un jeu qui grossit à chaque erreur rencontrée, rejouable à volonté, **séparé** du jeu test de l'autocalibrage de grappes (ouvert et consommé le 12/10/2026, jamais à rouvrir).

Une ligne de `cas.jsonl` = un sujet :

````json
{"id": "...", "phrase": "...", "attendus": 40, "rendus": [{"nom": "...", "verdict": "juste"}, {"nom": "...", "verdict": "faux"}, {"nom": "...", "verdict": "non_verifiable"}]}
````

* `rendus` : les résultats **dans l'ordre où le programme les a rendus** (celui qui décide de ce qui s'affiche et de ce qui est coupé) ;
* `attendus` : le nombre d'entités de la référence (R) ; la référence vient d'une autorité **indépendante** des sources interrogées (jamais de la mémoire de l'agent, jamais du service qui a servi à chercher) ;
* un résultat **non vérifiable ne compte jamais comme juste**.

Mesure (interpréteur de grappes, qui porte `pytrec_eval`) :

````
/opt/grappes/.venv/bin/python outils/mesurer_classement.py --cas autocal_classement_fr/cas.jsonl
````

L'outil rend, par sujet puis en moyenne, la R-précision et le bpref, et à côté la probabilité qu'un résultat juste soit placé avant un résultat faux (AUC) avec sa marge. Il lit aussi les rejeux de l'autocalibrage en lecture seule (`--rejeu`).

**État : vide.** Aucun cas français n'est versé : une référence indépendante et jugée à la main pour un sujet français n'existe pas encore, et l'inventer fausserait la mesure. Le premier cas arrive avec la première recherche réelle dont la liste attendue est établie par une autorité (registre officiel, liste d'agrément). Règle : tout ordre manifestement faux rencontré en usage rejoint le jeu, on ne règle jamais le classement sur un seul exemple.
