# 910 — Audit du moteur de confiance et de son calibrage (14/11/2026)

> **Complément du 14/11/2026 :** cet audit a été fait sur une copie en retard de quelques commits
> (`8d5c0bd`) ; relu sur `b4ab69e`, aucun de ses constats ne change. L'indice ne sert pas qu'au mode
> `extraction` : pilote s'en sert à chaque recherche pour choisir et ordonner les noms, et pour lever
> la règle 8. Voir `911-etat-des-lieux-complet.md`, points G1 et G2.

**État : note de travail, rien à coder.** Audit en lecture seule demandé par Sednal, fait sur
`NALSED/GAPPES-FINAL` au commit `8d5c0bd`. Aucune ligne de code n'a été modifiée. Chaque point
« à décider » attend la décision de Sednal avant de devenir une instruction pour momo.

Fichiers lus : `DECISION_AUTOCAL.md`, `FINAL.md`, `docs/CERTIFICATION.md`,
`docs/conception/calibration.md`, `config/lr.yaml`, `config/calibration.json`,
`config/classement.yaml`, `src/grappes/vraisemblance.py`, `classement/` (indice, fusion, candidats,
production), `clustering/assign.py`, `ecosystem/crossref.py`, `variantes.py`, `fiabilite.py`,
`autocal/` (optimiser, etape3, evaluation, protocole, controles, metriques, jeux, test_final).

Limite de l'audit : les archives de mesure (`donnees/autocal/`) ne sont pas dans le dépôt, elles
sont sur la machine de momo. Les défauts ci-dessous sont établis par lecture du code et par deux
petits essais sans données ; leur effet chiffré sur les mesures n'a pas pu être recalculé.

## 1 — Le constat qui commande tout le reste

Le projet a deux moteurs de score, et aucun des deux n'est prouvé fiable :

* **Le moteur historique** (`assign.py`, formule `S + (100 − S)·(0,6·E + 0,4·A)/100`) est celui qui
  tourne par défaut (mode `sites`). Ses constantes (0,6 / 0,4, plancher 60, seuils 40 et 70) n'ont
  jamais été réglées sur des données. La mission d'octobre l'a mesuré : il ne fait pas mieux qu'un
  simple vote majoritaire (0,0146 pour les deux sur le jeu de test).
* **Le moteur « rapport de vraisemblance »** (`indice.py` + `config/lr.yaml`) est celui du mode
  `extraction`. Il a été **non certifié** le 12/10 : 0,018 pour une cible de 0,90, et sa conversion
  en probabilité est déclarée non valide dans `config/calibration.json`.

La cause mesurée par momo est juste et je la confirme à la lecture : **seuls 11 acteurs attendus
sur 356 (3 %) figuraient parmi les candidats**. Le classement ne peut pas faire remonter ce que la
collecte n'a pas trouvé. Conséquence directe : régler les poids du score ne sert à rien tant que ce
taux n'a pas monté. Le levier de fiabilité est dans les sources et la collecte (le travail des
specs 906, 907, 909), pas dans la formule.

## 2 — Ce qui est solide

* **La méthode de mesure est honnête.** Critères fixés avant les résultats, jeu de test ouvert une
  seule fois, trois comptes (juste / faux / non vérifiable), témoin sans acteur réel, test de
  permutation, comparaison au système d'avant et au vote. Le verdict « non certifié » est écrit
  noir sur blanc avec sa cause. C'est le point fort du projet.
* **Pas de fuite entre réglage et test.** Le réglage n'a vu que le jeu de mise au point ; le test
  n'a servi qu'une fois, après figement des paramètres.
* **Rien d'inventé** : découverte de vérité, métriques TREC (`pytrec_eval`), Optuna, Platt et
  isotone (scikit-learn), nomenklatura, échelle Admiralty. Conforme à la règle de la mission.
* **Le calcul est déterministe** (ex æquo départagés par ordre fixe, deux rejeux identiques octet
  pour octet) et la boucle d'`assign.py` ne peut pas osciller (les membres ne font que s'ajouter).
* **Chaque élément du score est borné** (±3 par élément, ±6 au total) : aucun signal isolé ne peut
  emporter la décision.

## 3 — Défauts confirmés dans le code

### 3.1 Le signal « plusieurs écosystèmes » ne compte jamais dans l'indice

`indice.py` ajoute un élément quand `len(c.ecosystemes) > 1`. Or `candidats.py` remplit ce champ
avec `st.ecosystems`, et `assign.py` n'y met que l'écosystème **de l'entité elle-même** :

````python
st.ecosystems.add(ref.split(":", 1)[0])          # son propre écosystème
st.ecosystems.add(c.cited.split(":", 1)[0])      # encore le sien, pas celui du citant
````

Le champ vaut donc toujours un seul écosystème (zéro pour un nom lu dans un texte), et l'élément
ne se déclenche que si la fusion de variantes est active — elle est désactivée. Les mesures de momo
le confirment : retirer « écosystèmes » donne exactement le même résultat sur les trois jeux.
Le recoupement entre écosystèmes, principe central du projet, est absent de l'indice. Et la valeur
`ecosysteme: 1.149` de `config/lr.yaml` est le réglage d'un paramètre qui n'agit pas : du hasard.

### 3.2 Le score affiché n'est pas celui que la documentation annonce

`config/calibration.json` et `calibration.md` § 10 annoncent `p = LR/(1+LR)`. Le code fait autre
chose : `charger_calibreur()` prend `a = 1.0` par défaut quand le fichier ne donne pas `a` (la
valeur correcte, `ln 10`, n'est que le défaut de la classe, écrasé au chargement).

| log10 LR | score affiché par le code | score annoncé par la doc | seul ajustement jamais mesuré (Platt, non valide) |
| :-- | :-- | :-- | :-- |
| 0,19 (présent dans SIRENE) | 55 | 61 | 2 |
| 1,0 | 73 | 91 | 4 |
| 2,0 (membre de la classe Wikidata) | 88 | 99 | 11 |

Les deux premières colonnes supposent qu'un candidat a une chance sur deux d'être bon au départ.
La mesure dit 1 à 2 %. Le chiffre de la colonne `score` de `resultat_brut.csv` surestime donc d'un
ordre de grandeur. L'étiquette « estimation étendue » est bien écrite à côté, mais un 88 se lit
comme 88 % de chances.

### 3.3 Les comparaisons « avec / sans » peuvent se contaminer

`fusion.ajouter()` écrit dans `c.ner_sites` des candidats existants, et `fusionner()` copie les
candidats par `copy.copy`, qui **partage** ce dictionnaire avec l'original (vérifié par essai).
Dans `autocal`, toutes les configurations d'un sujet sont calculées sur le même contexte, dans cet
ordre (`test_final.comparaisons`) : « complet » d'abord, puis « sans noms lus », puis « web seul ».
Les candidats du web dont le nom a été lu dans un texte gardent donc cette trace dans les
configurations censées ne pas l'avoir. Effet attendu : l'apport des noms lus est sous-estimé.
Ampleur non mesurée (archives absentes). En production, un seul calcul par cycle : sans effet.

### 3.4 Le nombre d'attendus change selon la configuration mesurée

`evaluation.qrels_de()` ajoute à la référence tout résultat jugé juste hors de la liste initiale,
puis `mesurer()` recalcule R sur ce total. Deux configurations d'un même sujet sont donc notées
sur des dénominateurs différents. L'écart est petit, mais la comparaison n'est pas à base égale.

## 4 — Écarts entre `DECISION_AUTOCAL.md` et le code

| Ce que demande la décision | Ce que fait le code |
| :-- | :-- |
| Méthode 6 : validation croisée imbriquée | Annoncée dans les en-têtes d'`optimiser.py` et `protocole.py`, **absente du code**. Seul un découpage simple mise au point / validation / test existe. Avec six sujets par jeu, le résultat n'aurait pas changé, mais les en-têtes affirment une chose fausse. |
| Méthode 4 : un score de 90 veut dire 90 % | Non atteint et dit honnêtement (calibration non valide). Mais voir 3.2 : le chiffre affiché reste trompeur. |
| Méthode 5 : régler les paramètres | Fait (108 essais), gain de +0,003, soit rien. Pourtant ces valeurs sont devenues la configuration de production, à trois décimales. |
| D82 (DECISIONS.md) : l'extraction est « mesurée et calibrée (D63-D65) » | Mesurée oui, calibrée non : `docs/CERTIFICATION.md` dit le contraire. Formulation à corriger, elle donne une confiance que la mesure n'autorise pas. |

## 5 — Fragilités de fond

### 5.1 Les poids de production sont un réglage sur du bruit

Le réglage a porté sur 13 bons résultats parmi 2 060 candidats, 11 paramètres, pour un gain dans
le bruit. Deux conséquences contraires au bon sens sont passées en production :

* **Un registre officiel pèse dix fois moins qu'une page web qui cite un nom** : `registre_sirene_naf`
  0,19 contre `nom_dans_texte` 1,9. La raison n'est pas que SIRENE soit peu fiable : la référence
  (Wikidata) est incapable de lui donner raison, `calibration.md` le dit lui-même (« ce qui ne
  prouve pas qu'ils n'apportent rien »). Le réglage a puni ce qu'il ne savait pas mesurer.
  `registre_source` (data.gouv.fr) a été aligné sur cette valeur sans aucune mesure.
* **Un site lu et moyennement dans le sujet passe derrière un nom simplement cité** (calcul sur
  les valeurs de `lr.yaml`) : un site lu avec une proximité de 40 reçoit −0,56 ; un nom cité une
  fois par une page web ordinaire reçoit +0,45 ; il faut une proximité de 70 pour égaler cette
  seule citation. Ne pas avoir été lu protège de la pénalité.

### 5.2 En mode `extraction`, `resultat.csv` n'a aucun seuil de fiabilité

`cc_pour_mode()` rend le classement autoritaire sur `resultat.csv`, avec `p_min: 0.0` et
`n_max: 200` : les 200 premiers sortent, quel que soit leur score. La certification le notait déjà
(« 70 à 90 % de ce qui est servi est faux ou non vérifiable ») et la mesure des noms lus donne au
moins 36 % de faux vérifiés. C'est le risque pratique le plus élevé pour la priorité du projet :
une liste d'une seule colonne `NOM`, sans rien qui distingue le sûr du douteux.

### 5.3 Formule historique (`assign.py`)

* **Marche d'escalier** : sous le seuil de recoupement, E vaut 0 ; au seuil, E vaut 50 et le
  plancher 60 s'applique. Une voix de plus ou de moins fait passer une entité de « rien » à
  « probable ». Voulu (D19), mais rend le résultat instable près du seuil.
* **Propagation** : le plancher (60) dépasse le seuil pour devenir citant (50). Une entité validée
  valide donc à son tour, sur trois tours, y compris sans aucun texte propre lu. À surveiller sur
  des données réelles (dérive hors sujet par chaîne de citations). Non mesuré.
* **Avantage aux gros sites** : S est la moyenne des 5 meilleures observations. Un site de 200
  pages a mécaniquement de meilleures « 5 meilleures » qu'un site de 5 pages.
* **Poids des citations dans l'indice** : multiplié par la fiabilité de l'entité **citée**, alors
  que les noms lus sont pondérés par la fiabilité de celui qui **cite**. Incohérent ; sans effet
  mesurable aujourd'hui (retirer les citations ne change rien).

### 5.4 Fusion de variantes

Désactivée à raison : nomenklatura en lien « simple » enchaîne des noms sans rapport (groupe de 37
noms). Le lien « complet » existe et a été mesuré meilleur, mais reste éteint. Tant qu'elle est
éteinte, un même acteur peut occuper plusieurs lignes.

## 6 — À décider par Sednal (rien n'est appliqué)

| N° | Sujet | Options | Mon avis |
| :-- | :-- | :-- | :-- |
| 1 | Score affiché (3.2) | (a) remplacer le chiffre par la seule bande verbale (« soutien faible / modéré / fort »), déjà calculée ; (b) garder le chiffre et corriger le code pour qu'il suive la doc ; (c) ne rien changer | **(a)**. Un chiffre non mesuré est pire que pas de chiffre. Le classement reste intact. |
| 2 | Seuil en mode `extraction` (5.2) | (a) ne sortir dans `resultat.csv` que les entités appuyées par au moins deux éditeurs distincts ou un registre, le reste dans un second fichier « à vérifier » ; (b) garder les 200 premiers | **(a)**. Même logique que `resultat_a_trancher.csv`, déjà en place pour les personnes. Coût : listes plus courtes. |
| 3 | Poids de `lr.yaml` (5.1) | (a) revenir aux valeurs d'expert d'origine et écrire dans le fichier qu'elles ne sont pas mesurées ; (b) garder les valeurs réglées | **(a)**. Le gain du réglage est nul et deux de ses effets sont contraires à la logique du projet. |
| 4 | Signal « écosystèmes » (3.1) | (a) le corriger pour compter les écosystèmes des **citants** ; (b) le retirer de l'indice | **(a)**, c'est le principe du projet. À faire avant toute nouvelle mesure. |
| 5 | Défauts de mesure (3.3, 3.4, § 4) | corriger la copie partagée, fixer R par sujet, corriger les en-têtes et la phrase de D82 | À faire, sans débat : petits correctifs. À poser avant la prochaine campagne de mesure, pas après. |
| 6 | Prochaine mesure | Le jeu de test est brûlé. Une nouvelle certification demande un nouveau jeu, fixé avant tout changement, et une référence qui ne vienne pas seulement de Wikidata | À lancer seulement quand le taux de candidats trouvés aura monté (après 906, 907, 909). Mesurer ce taux d'abord : c'est lui le vrai indicateur. |
| 7 | Fusion de variantes (5.4) | rallumer en lien « complet » après une mesure dédiée | À traiter avec Tri, pas avant. |

## 7 — Conséquence pour Tri

Tri ne doit pas afficher le score chiffré actuel comme une fiabilité. Ce qui est sûr et affichable
aujourd'hui : les **faits** derrière chaque ligne (quels registres, combien d'éditeurs distincts,
quels écosystèmes, quelles vérifications et alertes de 909), et la bande verbale. Les décisions 1
et 2 ci-dessus conditionnent donc directement la conception de Tri.
