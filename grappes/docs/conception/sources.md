# Sources de découverte : prises décrites en YAML (D68, chantier A) et sujets ambigus (chantier B)

Décision de Sednal : `DECISION_SOURCES.md` (enregistrée D68 ; Sednal l'écrit « D67 », numéro déjà pris par le verdict).
Pourquoi : le jeu test a montré que 11 acteurs de la référence sur 356 (3,1 %) sont parmi les candidats ; le goulot est
dans les sources (`docs/CERTIFICATION.md` § 2.3). Mesure sur le **jeu de mise au point seulement** ; le jeu test est
brûlé et n'a servi à rien ici.

## 1. Ce qui a été fait

* Serveur MCP officiel branché : `claude mcp add --transport http datagouv https://mcp.data.gouv.fr/mcp` (11 outils,
  dont `search_dataservices`, `get_dataservice_openapi_spec`, `search_datasets`, `list_dataset_resources`).
* Catalogue exploré avec ces outils (≈ 1 000 APIs tierces ; `search_dataservices` sur : association, annuaire, sport,
  culture, festival, bibliothèque, enseignement supérieur, spectacle, établissement...). **Constat honnête** : le
  catalogue des *APIs* est surtout fait de bouquets d'API d'État (API Entreprise, API Particulier : accès réservé) et
  d'API locales ; peu répondent « quelles organisations font X ? ». Les prises utiles ont été trouvées aussi dans le
  catalogue des *jeux de données* (même serveur, `search_datasets` puis `list_dataset_resources`).
* **Un fichier YAML par prise** dans `config/recherche/` (`type: registre`), lu par un module générique
  `decouverte/sources_yaml.py` : adresse, paramètres, chemins des champs (nom, id, commune, site, SIREN). **Aucun code
  propre à un sujet ni à une source.** Brancher une prise de plus = écrire un YAML.

| prise (fichier) | origine dans le catalogue data.gouv.fr | nature |
|---|---|---|
| `bnf_organisations.yaml` | API « SPARQL de la BnF » (672cfbeff92a8fae20ccf3ea), pas de spécification OpenAPI | notices d'autorité des collectivités (associations, chorales, troupes, clubs, festivals), plein texte `bif:contains` |
| `esr_etablissements.yaml` | jeu 586dae5ea3a7290df6f4be88 (Ministère de l'Enseignement supérieur), API Explore v2.1 | principaux établissements d'enseignement supérieur |
| `culture_festivals.yaml` | jeu 62cf95993d99f22480f49334 (Ministère de la Culture), CSV 7 283 festivals | festivals de France (nom, commune, site) |
| `culture_spectacles_licences.yaml` | jeu 5fc9b4729dbf684fecb13bae (Ministère de la Culture), CSV 27 Mo | entrepreneurs de spectacles vivants déclarés (compagnies, troupes, ensembles, lieux) |

La requête est calculée de la **seule phrase** du sujet (complément du type au singulier : « clubs de handball
professionnels » -> « handball professionnel »), avec relaxation (derniers mots retirés, puis le type) tracée dans
`Decouvert.requete`. Branchement : `decouvrir()` accepte la source `yaml` ; `config/classement.yaml` la liste
(`registres: [wikidata, sirene, yaml]`) ; le classement reste **inactif par défaut**. Poids dans l'indice :
`registre_source: 0,19` dans `config/lr.yaml`, **valeur d'expert non mesurée** (égale à SIRENE par code d'activité).

## 2. Mesure sur le jeu de mise au point (6 sujets positifs, R total = 344)

Même système qu'avant (paramètres Optuna figés, SIRENE + noms lus, sans Wikidata), plus les quatre prises.
Résultats : `autocal/resultats/sources_dev.json`, code `autocal/sources_mesure.py`.

| sujet | R | justes avant | justes avec les prises | en plus | candidats avant -> après |
|---|---|---|---|---|---|
| handball-pro | 17 | 4 | 8 | +4 (BnF) | 217 -> 500 |
| festivals-elec | 7 | 0 | 2 | +2 (festivals du ministère) | 171 -> 1 002 |
| bibliothèque numérique | 45 | 1 | 1 | 0 | 533 -> 932 |
| chorale | 33 | 0 | 1 | +1 (BnF) | 417 -> 738 |
| troupe théâtrale | 142 | 2 | 3 | +1 (BnF) | 275 -> 500 |
| faculté | 100 | 4 | 4 | 0 | 447 -> 451 |
| **total** | **344** | **11 (3,2 %)** | **19 (5,5 %)** | **+8** | **2 060 -> 4 123** |

* **Combien d'acteurs de référence en plus arrivent parmi les candidats : 8** (de 11 à 19 sur 344). Six viennent de la BnF,
  deux des festivals du ministère ; l'ESR et les licences de spectacles n'en apportent aucun sur ces six sujets.
* **À quel coût.** Réseau : 0 à 3 appels par prise et par sujet, 1 à 13 s ; les deux CSV (2,5 Mo et 27 Mo) ne sont
  téléchargés qu'une fois (cache). Bruit : **+2 063 candidats**, dont 8 justes (0,4 %) ; le reste est faux ou non
  vérifiable (la référence est partielle : un non vérifiable n'est pas forcément faux). Le plus gros bruit : 532
  festivals ajoutés pour « festivals de musique électronique » (la relaxation est retombée sur « musique ») et 242
  entrepreneurs de spectacles pour « clubs de handball ». Coût de la mesure elle-même : 80 minutes, presque tout en
  jugements Wikidata des 2 000 nouveaux noms.
* **Le classement n'en profite pas** : R-précision stricte moyenne 0,0197 contre 0,0209 avant (troupe : 0,014 -> 0,007).
  Les acteurs trouvés ne montent pas assez haut parmi le bruit ajouté, avec un poids d'expert non réglé. Le gain est un gain de
  **rappel des candidats**, pas encore de précision.
* **Plafond encore loin** : 5,5 % de rappel, contre 3,2 % ; ce n'est pas un changement d'ordre de grandeur.
* Mesuré sur 6 sujets, **choisi après les avoir vus** (les quatre prises ont été retenues en regardant ces sujets) : un
  sur-ajustement à cette liste est possible ; non confirmé sur la validation (consigne : jeu de mise au point seulement).

## 3. Circularité : ces sources ne dérivent pas de Wikidata, avec une réserve mesurée

Les quatre prises viennent de la BnF et de deux ministères : **aucune ne lit Wikidata**, donc contrairement à
Wikidata elles ne rendent pas la mesure circulaire au sens strict (rien n'est lu dans la source de la référence).
Réserve mesurée : sur les 6 acteurs que la BnF apporte en plus, **3 ont dans Wikidata l'identifiant d'autorité BnF
(P268)** ; les deux jeux de données ne sont donc pas indépendants dans leur *contenu* (Wikidata a repris des notices
BnF). Une partie du gain mesuré avec la BnF est de ce fait optimiste pour un sujet dont les entités n'ont aucun lien avec
Wikidata. L'ESR publie aussi des identifiants Wikidata dans ses fiches (le nom, la commune et le site restent les siens).

## 4. Chantier B : sujets ambigus

`decouverte.traduction.lectures(phrase)` liste toutes les lectures d'un sujet (éléments Wikidata dont le libellé est
identique au segment retenu) ; elle **ne départage pas** et n'invente aucune règle. Le cycle écrit `ambiguite.json`
dans les sorties quand il y en a plusieurs (`classement.production.appliquer`). Cas : « Brasserie » -> Q131734 (entreprise
qui fabrique et vend de la bière, 73 en France) **et** Q1581509 (type de restaurant, 32 en France) ; « Chorale » ->
Q131186 (ensemble vocal), Q5484053 (groupe de musique finlandais), Q724473 (genre musical liturgique). Les cinq autres
sujets de mise au point n'ont qu'une lecture trouvée. Limites : seuls les dix premiers résultats de la recherche
Wikidata sont lus ; la classe Wikidata retenue par `classe_wikidata` reste la première trouvée (comportement d'avant,
**non modifié**, désormais signalé) ; les prises YAML en plein texte couvrent toutes les lectures sans les distinguer.

## 5. Notés, non commencés (consigne)

SearxNG (méta-moteur auto-hébergé : s'installe sur la VM, à voir avec Sednal), OpenStreetMap/Overpass, expansion
d'ensembles d'entités (ProbExpan, SetExpan : code de laboratoire, pensé pour l'anglais).

## 6. Reste à décider (Sednal)

* Régler le poids `registre_source` (et celui de chaque prise) sur la mise au point, ce qui suppose d'accepter qu'il
  s'ajuste à ces six sujets ; ou garder la valeur d'expert.
* Filtrer le bruit des prises en plein texte (ex. rester dans le type du sujet) : aucune règle n'a été inventée.
* Mesurer sur la validation avant d'activer `classement.actif`.
* Un nouveau jeu test (nouvelle graine) pour toute certification ultérieure.
