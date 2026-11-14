# 912 — Plan d'amélioration : fiabilité et couverture (14/11/2026)

**État : note de travail, à valider point par point par Sednal.** Rien n'est à coder tant qu'un
point n'est pas marqué validé ici. Ce plan découle des audits `910` et `911`.

Principe : **collecter large, sortir strict.** La couverture se gagne à la collecte, la fiabilité à
la sortie. Aujourd'hui le programme collecte étroit (3 % des acteurs attendus trouvés en octobre)
et sort large (200 noms sans seuil).

Règle de méthode, valable pour tout le plan : aucun mécanisme nouveau quand un existant fait le
travail. Chaque point nomme ce qu'il réutilise.

## A — Fiabilité

### A1 — Appliquer le plan avant la coupe, et dire ce qui est coupé

`pilote/src/pilote/pont/executer.py` garde les `combien` premiers candidats, puis applique le plan.

* Appliquer `suite_plan.appliquer()` sur **tous** les candidats classés, puis couper à `combien`.
* Quand la coupe retire des noms, l'écrire au journal (nombre, et les trente premiers noms), sur le
  modèle de `plan_noms_retires`.
* La vérification reste après la coupe (inutile de payer pour vérifier ce qui ne sort pas).

### A2 — Une confirmation exige un second champ concordant

`pilote/src/pilote/pont/verification.py` écrit « confirmation » dès qu'une source rend le nom.

* Deux signaux distincts dans `faits.verifications` : `meme_nom` (le nom existe dans la source,
  rien d'autre ne concorde) et `confirmation` (le nom **et** au moins un autre champ concordent :
  ville, numéro officiel ou site).
* La comparaison champ par champ existe déjà : `rapprochements.comparer()` (accord / désaccord /
  absence). La réutiliser, ne pas en écrire une autre.
* Seule une `confirmation` relève `faits.fiabilite_effective` (909 § 1.2.d). Un `meme_nom` s'affiche
  dans la fiche, sans effet.
* Un désaccord (même nom, autre ville) s'affiche aussi : c'est une information utile en Tri.

### A3 — Deux niveaux de sortie : « sûr » et « à vérifier »

* Un nom est **sûr** s'il remplit au moins une condition : présent dans un registre de première
  main ; trouvé à deux endroits indépendants au moins (`nb_endroits`, déjà calculé par
  `pont/faits.py` sans double compte) ; porteur d'une `confirmation` au sens de A2.
* Tout le reste est **à vérifier**.
* Dans pilote : un fait de plus sur la fiche (`niveau`), utilisable par Filtre et par les
  classements de Tri comme les autres faits. Aucun score.
* Dans le moteur, mode `extraction` : `resultat.csv` ne contient que les sûrs ; les autres vont
  dans `resultat_a_verifier.csv`, sur le modèle de `resultat_a_trancher.csv`.
* Conséquence annoncée : des listes plus courtes dans `resultat.csv`.

### A4 — Montrer les faits, pas un chiffre non mesuré

* Retirer le chiffre `score` de `resultat_brut.csv` tant que `config/calibration.json` est à
  `valide: false` ; garder la colonne `bande` (restitution verbale, déjà calculée).
* L'indice continue d'ordonner les candidats. Il ne se présente plus comme une probabilité.

### A5 — Remettre l'indice en ordre

* `config/lr.yaml` : revenir aux valeurs d'expert d'origine et écrire dans le fichier qu'elles ne
  sont pas mesurées (`910` § 5.1).
* Signal « écosystèmes » : compter les écosystèmes des **citants**, pas celui de l'entité
  (`910` § 3.1).
* Poids des citations : pondérer par la fiabilité de celui qui cite, comme pour les noms lus.

### A6 — Brancher les registres de première main sur la vérification

Sur 48 sources déclarées vérifier ou enrichir, 15 le font réellement (`911` § 4.1). À doter d'une
clé de vérification (`verifie_sur`) et du contrôle A2, par ordre d'intérêt :
`recherche-entreprises`, `registre-associations`, `pappers`, `companies-house`, `gleif`,
`opencorporates`, `ror`. Une source à la fois, chacune avec son test sur exemple archivé.
Les sources payantes de la liste restent soumises au plafond et au test réel de 909 § 1.2.b.

### A7 — Compter une seule fois deux écritures du même acteur

Aujourd'hui seuls les noms strictement identiques sont réunis ; le reste attend une décision en
Tri. Proposition limitée : réunir d'office deux fiches qui portent le **même numéro officiel**
(SIREN, ou SIRET du même SIREN). Tout autre rapprochement reste une proposition Splink qu'une
personne tranche. Un rapprochement confirmé en Tri met à jour `nb_endroits` de la fiche gardée.

## B — Mesure (ce qui rend le reste vérifiable)

### B1 — Une référence indépendante de Wikidata

* Vingt à trente sujets dont la liste officielle existe et est publiée par une autorité :
  annuaire d'une fédération, liste d'un label d'État, liste préfectorale.
* Même format que l'existant (`autocal/references/`, jugements qrels, trois comptes : juste, faux,
  non vérifiable). Rien de nouveau à inventer.
* Deux chiffres suivis après chaque changement du plan :
  1. **part des acteurs attendus présents parmi les candidats** (aujourd'hui 3 %) ;
  2. **part de faux dans la sortie « sûr »**.
* Sednal valide la liste des sujets avant toute collecte. Les collectes consomment des crédits :
  le chiffre est donné avant de lancer.

### B2 — Corriger l'outil de mesure avant de s'en resservir

Copie partagée entre configurations, nombre d'attendus variable, en-têtes qui annoncent une
validation imbriquée absente, phrase de D82 (`910` § 3.3, § 3.4, § 4). Corriger aussi la date du
corpus de `tests/test_cycle.py`, qui fera tomber ces tests à partir du 29/12/2026.

### B3 — Un test de bout en bout sur la configuration livrée

Une recherche complète, faux serveurs locaux, avec les fichiers de `config/` tels qu'ils sont
livrés. Aucun test ne le fait aujourd'hui.

## C — Couverture

Chaque point de C se mesure sur B1 avant d'être gardé.

### C1 — Les registres fournissent d'abord les candidats

* Interroger en premier SIRENE par code d'activité, le RNA et data.gouv.fr, puis chercher sur le
  web de quoi les confirmer. Le mécanisme existe (`decouverte/registres.py`, `traduction.py`).
* Dépend du rattachement NAF de la spec 903 (partie gratuite : `config/naf_rev2.csv`, aucun appel).
* Wikidata en découverte : possible, mais ses résultats ne comptent pas dans la mesure quand la
  référence en vient.

### C2 — Lire les pages-annuaires en entier

`fetch/pages.py` coupe le texte d'une page à 20 000 caractères et garde 100 liens. Une page « liste
des clubs » de deux cents entrées est donc lue en partie.

* Pour une page dont l'essentiel est une liste (beaucoup d'entrées de même forme), relever ces deux
  limites, dans un plafond écrit en configuration.
* Les noms y sont lus par l'extraction déjà en place (`ner/extraire.py`). Ils entrent « à
  vérifier » (A3), jamais « sûrs » sur cette seule page.

### C3 — Décliner les requêtes

Le moteur envoie la phrase plus deux paires de mots-clés (`cycle/collect.py::search_queries`).

* Décliner par lieu quand la phrase couvre un territoire (départements ou villes, à partir de la
  source `geonames-fr` déjà présente).
* Décliner par langue avec l'outil Traduction existant, pour les sources par adaptateur.
* Borné par le budget d'appels de la recherche ; le nombre de requêtes prévu est affiché avant le
  lancement, comme l'estimation actuelle.

### C4 — Donner un effet réel à la Requête avancée

Aucune source ne déclare d'opérateur, la tuile ne change rien (`911` § 4.2). Déclarer les
opérateurs compris par `serper`, `brave` et `searxng`, chacun vérifié par un test réel.

## D — Ordre proposé

| Rang | Point | Change les résultats ? |
| :-- | :-- | :-- |
| 1 | A1, A2 | oui : listes complètes après filtre, fiabilités affichées plus justes |
| 2 | A3, A4 | oui : sortie en deux niveaux, plus de chiffre trompeur |
| 3 | B2, B3 | non |
| 4 | B1 | non (donne les deux chiffres de départ) |
| 5 | A5, A6, A7 | oui, mesuré sur B1 |
| 6 | C1, C2, C3, C4 | oui, mesuré sur B1, un levier à la fois |

## Hors de ce plan

À la demande de Sednal, la règle 8 ne figure pas dans ce plan.
