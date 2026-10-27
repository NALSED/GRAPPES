# L'ordre des résultats : ce qui est mesuré, ce qui ne l'est pas

Spécification 24 § 5, 27/10/2026. L'indice de vraisemblance du moteur sert à **deux choses** : estimer une probabilité (jamais montrée à l'utilisateur) et **ordonner la liste** (`production.classer` trie par log-LR décroissant, le pont parcourt la liste dans cet ordre et coupe à `combien`). Ce qui apparaît à l'écran, et ce qui est coupé, dépend de cet ordre.

## Le chiffre publié, tel quel

Test du 12/10/2026 (jeu test ouvert une seule fois, verdict **NON CERTIFIÉ**, `docs/CERTIFICATION.md` de grappes) :

| Mesure | Valeur |
|---|---|
| R-précision stricte, moyenne des 6 sujets positifs (critère 1, cible ≥ 0,90) | **0,0178** |
| bpref | **0,0184** |
| Validation | 0,0768 (écart d'optimisme +0,059) |

## Pourquoi ce chiffre ne dit rien de l'ordre

Sur les six sujets, **11 acteurs de la référence sur 356 (3,1 %)** figurent parmi les candidats. Même un classement parfait ne dépasserait pas une R-précision d'environ 0,03 : la mesure est plafonnée par le **rappel de la collecte**, pas par l'ordre. Le bpref l'est aussi (il se rapporte au même R).

## Ce qui mesure l'ordre sans dépendre du rappel

La probabilité qu'un résultat **juste** soit placé avant un résultat **faux** (AUC), sur les seuls résultats jugés (les non vérifiables sont écartés : on ne sait pas ce qu'ils valent). `outils/mesurer_classement.py`, en lecture seule sur les rejeux déjà produits (le jeu test n'est pas rouvert) :

| Jeu | Justes | Faux | AUC | Marge (95 %, approchée) |
|---|---|---|---|---|
| dev (réglage) | 13 | 462 | 0,72 | ± 0,16 |
| validation | 62 | 447 | 0,56 | ± 0,08 |
| **test (12/10)** | **8** | 493 | **0,73** | **± 0,20** |

(0,5 = le hasard.) Les justes sont rendus avant les faux un peu plus souvent que par hasard, mais **les marges sont grandes** : 8 justes au test, 62 en validation dont 45 pour un seul sujet (cac40, AUC 0,53 : une liste fermée de noms connus, ordonnée comme au hasard). `rang` ne garde que les 200 premiers candidats rendus, et deux candidats peuvent y désigner la même entité : à lire comme un ordre de grandeur.

## Ce que cela autorise à dire, et ne pas dire

* On **ne peut pas** écrire « l'ordre des résultats est bon » : au mieux « un peu meilleur que le hasard, sur très peu de justes ».
* On **ne peut pas** non plus écrire « l'indice n'a pas de pouvoir discriminant » comme verdict sur l'ordre : ce constat de la calibration concerne la **probabilité** (Brier 0,0234 contre 0,0229 pour le prédicteur constant, soit 0,36 % de la variance), pas le classement.
* Le défaut mesuré est celui de la **collecte** (rappel 3,1 %), pas du tri.

C'est la question à poser à Sednal : améliorer la portée de la collecte (le levier que `CERTIFICATION.md` § 2.4 désigne) avant de toucher au tri.

## Remesurer à volonté

`autocal_classement_fr/` : jeu français rejouable, **vide aujourd'hui** (une référence indépendante et jugée à la main n'existe pas encore ; l'inventer fausserait la mesure). Format et règle de croissance dans son `LISEZMOI.md` ; mesure :

````
/opt/grappes/.venv/bin/python outils/mesurer_classement.py --cas autocal_classement_fr/cas.jsonl
/opt/grappes/.venv/bin/python outils/mesurer_classement.py --rejeu /opt/grappes/donnees/autocal/test_rejeu1.json
````
