# Rapport de test du 26/10/2026 (`test.md`) — livré tel quel

Trois parties, avec les « pas rempli » et les anomalies. Les chiffres viennent de requêtes réelles (clés de `config/secrets.env`, jamais affichées).

## 1. Review totale

### Les 8 règles non négociables de `00-MAIN.md`

| # | Règle | Verdict | Exemple concret |
|---|-------|---------|-----------------|
| 1 | L'original est toujours gardé | **partiellement** | La traduction garde l'original dans le journal. Les noms retirés par un Filtre ne sont que dans le journal (30 par tuile au plus). Confirmer/Séparer ne suppriment rien. |
| 2 | Ce qui vient de l'IA est marqué | **pas rempli** | L'Assistant IA ne s'exécute pas : rien n'entre dans une grappe. Le marquage n'existe donc pas dans le modèle de données. |
| 3 | Aucun style ni nom de source en dur | **rempli** (pour `/suite`) | Un test balaie le CSS et le JS. L'ancienne interface (`/`) n'est pas couverte. |
| 4 | « Retirer » et « Supprimer » sont distincts | **rempli** | Testés (API et navigateur). |
| 5 | Vocabulaire fermé | **partiellement** | Écarts connus : « Ouvrir », « Ajouter un lien depuis… », « Chargement… » (QUESTIONS F22 / suite-5). |
| 6 | L'Aide ne fait que proposer | **rempli** | État identique après 6 appels d'Aide. 300 appels aléatoires : 0 erreur 5xx. |
| 7 | Fonctionne sans modèle | **rempli** | Aide, vérification du plan et préréglages marchent sans modèle. |
| 8 | Personnes morales seulement | **partiellement** | Genre « personne » retiré, export FtM sans fiches de personne. Le fichier `config/personnes.yaml` de grappes (préparé, non activé) est laissé tel quel. |

### Points précis

- **Clé d'API jamais en clair : rempli.** Balayage de 25 319 fichiers (base, journaux, exports, historique git) : aucune valeur de clé. Fausses clés de test absentes de l'API, du journal et des fichiers de travail.
- **Fiabilité A–F et Langue sur chaque source : rempli.** 64 sources, aucune sans note ni langue. Fiabilité : B 23, D 40, C 1, aucune en A par défaut. Aucun registre de première main noté C/D/E/F, aucune source web ou presse notée A/B. Remarque : OpenSanctions est notée B alors que c'est de la seconde main.
- **Langue :** l'implémentation donnait « en » à 49 sources sur 64, y compris Mondial. Corrigé (vide = inconnue).
- **Tri (ordre, Confirmer, Séparer, Déjà tranchés) : rempli**, testé en API et en navigateur.
- **Assistant IA éteint par défaut + avertissement en quatre points : rempli**, mais l'Assistant ne s'exécute pas encore.
- **Sources P1 de `17-sources-a-implementer.md` : partiellement.**
  - Vérifiées par appel réel (plus de vingt) : Linkup, Firecrawl, Serper, Guardian, NYT, ProPublica, NZ Charities, ACNC, BODACC, AMF, PRH Finlande, Mobilizon, Bluesky, Mastodon, Lemmy, SepiaSearch, Photon, universités, Media Cloud, registre des associations, Wikidata, Wikipedia, GDELT. Radio-Browser est intermittent.
  - **Ne répondent pas ou non branchées :** Exa (HTTP 402, crédits épuisés), catalogue data.gouv MCP (« ne répond pas »), Charity Commission (clé absente), Nominatim/Overpass (0 résultat sur le cas de test), Parallel Search MCP, Fetch MCP, Memento, OCDS, TED, data.europa.eu, org-id, IRS, CRA, Irlande, GrantNav (anti-robot), CompanyScope, MatrixRooms, Jetstream, OpenAddresses, geoBoundaries, GeoNames (identifiant absent), trafilatura, news-please, RSSHub, changedetection.

## 2. Partie 1 — sorties connues

### 2.1 Fusion / doublons (Splink) contre la vérité

FEBRL1 (1 000 fiches, 500 paires vraies). **Mesure du 26/10 (moteur d'alors)** puis **remesure du 27/10 avant la v1 (moteur actuel)** :

````
            26/10 (moteur d'alors)          27/10 (moteur actuel, v1)
seuil  proposées  FP   FN  rappel     proposées  FP   FN  rappel   précision
  0.2        471   0   29   0.942          450   0   50   0.900     1.000
  0.3        456   0   44   0.912          435   0   65   0.870     1.000
  0.5        450   0   50   0.900          435   0   65   0.870     1.000
  0.8        434   0   66   0.868          434   0   66   0.868     1.000
  0.9        375   0  125   0.750          375   0  125   0.750     1.000
````

**Le rappel a baissé de 0,942 à 0,900 au seuil 0,2 entre les deux mesures.** Cause connue : le 27/10, un numéro officiel différent est devenu presque décisif (deux entités distinctes, pas une faute de saisie) et un même nom n'est plus compté deux fois ; c'est ce qui règle les cas français (Club Alpin, deux boulangeries Martin) mais FEBRL, jeu de personnes dont les identifiants sont corrompus dans les doublons, y perd des paires. Compromis assumé : la précision reste 1,000, et le jeu français (25 cas) donne au seuil 0,2 une précision de 0,923 et un rappel de 1,000 (un seul faux positif connu : « Croix-Rouge française » et sa délégation de Paris).

Lecture des faux négatifs un par un : noms écorchés ou champs inversés, ou identifiants changés dans le doublon. Aucun faux positif. FEBRL est un jeu de **personnes** : il sert ici à mesurer le moteur, pas à traiter des personnes.

Cas piégés (personnes morales), après correction :

| Cas | Attendu | Obtenu | Conforme |
|-----|---------|--------|----------|
| Club Alpin Lyon / Club Alpin Paris | non proposé | 13 % (masqué) | oui |
| Boulangerie Martin, deux numéros officiels différents | non proposé | 1 % | oui |
| SAS Dupont Sports / Dupont Sports, Grenoble | proposé | 87 % | oui |
| Danone : SIRET différents du même SIREN | pas de paire entre établissements | corrigé (avant : 100 % de fausses paires) | oui |

Défauts trouvés et corrigés pendant la mesure : bruit du Tri (69 paires, ramenées à 15 sur « association sportive » / « club de judo »), double comptage du nom (Club Alpin montait à 70 %), numéros différents trop peu pénalisants.
**Limite :** les probabilités m/u sont fixées a priori, pas entraînées.

### 2.2 Requêtes à réponse connue (35 cas)

Résultat final : environ 30 conformes, 3 partiels, 2 à 5 échecs selon l'intermittence. Détail en annexe A.

- **Partiels :** Renault SA hors du top 10 (l'API rend de petits homonymes) ; Ligue contre le cancer au rang 2 ; CNRS au rang 5 dans ROR.
- **Échecs :** CEA (acronyme dans ROR) ; RFI, France Inter, FIP (Radio-Browser intermittent).
- **Faux « oui » :** Fondation Abbé Pierre (absente du RNA) a été rapprochée d'une entité Emmaüs.
- **ENRICHIR :** n'existe pas côté moteur (rôle d'affichage seulement).

Vérifications (annexe B) : BODACC confirme DUPONT & DUPONT et DANONE, rien pour une société inexistante. OpenSanctions : Rosneft et Gazprom en alerte. Danone était en « alerte » à tort (liste de risque d'un registre) ; corrigé en « information ». Wayback confirme grenoble.fr. CourtListener ne trouve pas « Tesla, Inc. ».

### 2.3 Honnêteté de la fiabilité et copies

Le SIREN de Danone (552032534) vient du registre (première main). Les copies Wikipedia n'ajoutent pas d'endroits : `nb_endroits` reste à 1.

### 2.4 L'Assistant IA et l'Aide ne se confirment jamais eux-mêmes

L'Aide ne modifie pas l'état (6 appels, état identique ; 300 appels aléatoires). L'outil Assistant IA est compilé « non appliqué ». Rien ne vient de l'IA dans une grappe, donc rien ne peut se confirmer lui-même. La règle n'est pas mise à l'épreuve tant que l'IA ne s'exécute pas.

## 3. Partie 2 — grandeur réelle

| Session | Charte | Constat |
|---------|--------|---------|
| S1 | Plan d'entreprises vérifiées : Annuaire + GLEIF, vérifiées par BODACC et OpenSanctions | 127 noms en 23 s. La vérification n'a examiné que 4 noms sur 127 (BODACC) et 0 sur 61 (OpenSanctions) : le plafond d'appels est partagé. Dit dans le journal (`verification_incomplete`). |
| S2 | Plan chargé de 17 sources, Traduction, IA, Filtre, Condition, script, fusion, 2 vérificateurs | 9 sources écartées car éteintes dans Réglages, avec la raison. Traduction et Assistant IA « non appliqués », dits. Limite d'appels atteinte, 185 noms, 3 noms vérifiés sur 185. |
| S3 | Noms ambigus | Bruit dans le Tri, corrigé (voir 2.1). |
| S4 | Aide : fuzz et injection | Robuste, aucune invention, `definir` refuse les mots inconnus. La remarque de langue (contrôle 6) se déclenche pour une saisie anglaise face à une source française. |
| S5 | Pannes injectées | Voir ci-dessous. |

Pannes (S5) :

- **Source qui plante :** signalée (« code 3 »), les autres continuent.
- **Limite d'appels à 3 :** fin en 5 s, sources « non appelée » dites, pas de boucle.
- **Mauvaise clé :** Guardian et Serper signalés comme échec avec un message en français ; la clé n'apparaît nulle part.
- **Arrêt demandé à 8 s avec une source lente (45 s) :** voir A1.
- **Langue non couverte sans Traduction :** Traduction non appliquée (aucun moteur réglé), dit.

### Liste séparée des anomalies

| # | Anomalie | Reproduction | État |
|---|----------|--------------|------|
| A1 | Arrêt non prompt : 58 s au lieu de 8 s | Lancer avec un programme local qui dort 45 s, demander l'arrêt à 8 s | **corrigé** (14 s), sans test de non-régression |
| A2 | Clé refusée (403) comptée comme « a répondu » | Serper avec une fausse clé | **corrigé** (test) |
| A3 | Message « guardian : HTTP 401 » peu lisible | Guardian avec une fausse clé | **corrigé** |
| A4 | `secrets.env` jamais chargé dans le pont : les sources web à clé ne marchaient pas | Source web « prise » avec clé | **corrigé** |
| A5 | Vérification BODACC plantait (`cleanco` absent de l'interpréteur de grappes) | Lancer une vérification BODACC | **corrigé** |
| A6 | Budget d'appels : la collecte privait les sources par adaptateur et la vérification | S1, S2 | **atténué** (réserves) ; la vérification reste partielle sur de gros volumes, dite |
| A7 | Langue « en » par défaut pour 49 sources | Lire la liste des sources | **corrigé** |
| A8 | Mots de moins de 4 lettres perdus (« Air France » → « France », WWF, CEA, RFI) | Recherche par nom court | **corrigé** |
| A9 | Pas de gestion du 429 | Associations sous charge | **corrigé** (attente selon `Retry-After`, 3 essais) |
| A10 | OpenSanctions disait « sanctions » pour toute liste | Danone | **corrigé** |
| A11 | « Tri » refusé à l'ouverture (« pas encore conçu ») | Ouvrir l'écran Tri | **corrigé** |
| A12 | Journal : noms retirés surcomptés ; événement `rapprochements_proposes` en double | Plan avec deux branches | **corrigé** |
| A13 | Échecs de tests attribués au « réseau » alors que le conteneur Overpass local était dégradé | Test Bristol | **correction de mon affirmation** : `docker restart overpass` l'a réglé. Les échecs Wayback viennent d'archive.org (429). |
| A14 | Splink : plantage « Illegal instruction » avec DuckDB 2.0 sur le CPU de la VM | Lancer le Tri | contourné : DuckDB `>=1.4,<2` |
| A15 | Fondation Abbé Pierre : faux « oui » | Chercher la fondation au registre des associations | **ouvert** — le défaut est dans la requête par nom du registre, pas dans Splink (voir `autocal_rapprochement_fr/`, 27/10) |
| A16 | Exa HTTP 402 ; Radio-Browser intermittent ; data.gouv MCP muet | Voir section 1 | **ouvert**, hors de notre contrôle |
| A17 | La marque « IA » n'existe pas dans les données | Voir règle 2 | **ouvert** |
| A18 | Plusieurs sources P1, Traduction, GLiNER, crédibilité 1–6 : non faits | Voir section 1 | **ouvert** |

## Annexe A — requêtes à réponse connue

````
catégorie                         source                  requête                             résultat  détail / conforme
Entreprises                       recherche-entreprises   Danone                              rang 1    top1: DANONE | autres noms: 3/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   Air France                          rang 1    top1: SOCIETE AIR FRANCE | autres noms: 9/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   Orange                              rang 1    top1: ORANGE | autres noms: 0/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   Carrefour                           rang 1    top1: CARREFOUR | autres noms: 0/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   L'Oréal                             rang 1    top1: L'OREAL (KERASTASE ; MIZANI ; L'OREAL PR | autres noms: 0/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   Renault                             rang 1    top1: RENAULT | autres noms: 0/10 | SIREN ✘  => partiel
Entreprises                       recherche-entreprises   Société Générale                    rang 1    top1: SOCIETE GENERALE (SG) | autres noms: 0/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   BNP Paribas                         rang 1    top1: BNP PARIBAS (HELLO BANK!) | autres noms: 1/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   Michelin                            rang 1    top1: MICHELIN | autres noms: 1/10 | SIREN ✔  => oui
Entreprises                       recherche-entreprises   LVMH Moët Hennessy Louis Vuitton    rang 1    top1: LVMH MOET HENNESSY LOUIS VUITTON | autres noms: 9/10 | SIREN ✔  => oui
Associations                      registre-associations   Médecins du Monde                   rang 1    top1: MEDECINS DU MONDE ASSOCIATION | autres noms: 8/10  => oui
Associations                      registre-associations   Secours populaire français          rang 1    top1: SECOURS POPULAIRE FRANCAIS (SPF) | autres noms: 0/10  => oui
Associations                      registre-associations   Croix-Rouge française               rang 1    top1: CROIX ROUGE FRANCAISE (CRF) | autres noms: 0/10  => oui
Associations                      registre-associations   Emmaüs France                       rang 1    top1: EMMAUS FRANCE | autres noms: 8/10  => oui
Associations                      registre-associations   Fondation Abbé Pierre               rang 1    top1: ASSOCIATION COMMUNAUTE EMMAUS DU CLERMON | autres noms: 1/2  => oui
Associations                      registre-associations   Ligue contre le cancer              rang 2    top1: LIGUE NATIONALE CONTRE LE CANCER (LNCC) | autres noms: 7/10  => partiel
Associations                      registre-associations   Greenpeace France                   rang 1    top1: GREENPEACE FRANCE | autres noms: 0/1  => oui
Associations                      registre-associations   Amnesty International France        rang 1    top1: AMNESTY INTERNATIONAL FRANCE | autres noms: 1/3  => oui
Associations                      registre-associations   Handicap International              rang 1    top1: HANDICAP INTERNATIONAL FRANCE (HI) | autres noms: 6/10  => oui
Associations                      registre-associations   WWF France                          rang 1    top1: ASS BIENS GRANDS FAITEURS DU WWF FRANCE | autres noms: 1/2  => oui
Organisations officielles (ROR)   ror                     Université Grenoble Alpes           rang 1    top1: Université Grenoble Alpes | autres noms: 7/10  => oui
Organisations officielles (ROR)   ror                     CNRS                                rang 5    top1: Canadian Nautical Research Society | autres noms: 6/10  => partiel
Organisations officielles (ROR)   ror                     Sorbonne                            rang 1    top1: PRISM Sorbonne | autres noms: 0/10  => oui
Organisations officielles (ROR)   ror                     INSERM                              rang 1    top1: Inserm | autres noms: 8/10  => oui
Organisations officielles (ROR)   ror                     CEA                                 ABSENT    top1: Canadian Economics Association | autres noms: 10/10  => non
Lieux                             photon                  Grenoble                            rang 1    top1: Grenoble | autres noms: 0/10  => oui
Lieux                             photon                  Tour Eiffel                         rang 1    top1: Tour Eiffel | autres noms: 0/10  => oui
Lieux                             photon                  Vieux-Port                          rang 1    top1: Vieux-Port | autres noms: 1/10  => oui
Lieux                             photon                  Mont Blanc                          rang 1    top1: Mont Blanc / Monte Bianco | autres noms: 1/7  => oui
Lieux                             photon                  Gare de Lyon                        rang 1    top1: Gare de Lyon | autres noms: 3/10  => oui
Presse (radios)                   radio-browser           France Inter                        rang 1    top1: Écoutez Mon petit France Inter | autres noms: 0/10  => oui
Presse (radios)                   radio-browser           FIP                                 rang 1    top1: FIP | autres noms: 0/10  => oui
Presse (radios)                   radio-browser           RFI                                 ERREUR    La source ne répond pas.  => non
Presse (radios)                   radio-browser           Radio Nova                          rang 1    top1: Radio Nova | autres noms: 0/10  => oui
Presse (radios)                   radio-browser           RTL                                 rang 1    top1: * COUNTRY || Country Pop, Country Rock,  | autres noms: 0/10  => oui
conformes 30/35, partiels 3
````

## Annexe B — vérifications

(Mesure faite avant la correction A10 : Danone y figure encore en « alerte » ; il est maintenant en « information ».)

````
== bodacc  bilan: examinés 4/4 complète=True 
   DUPONT & DUPONT                  -> signal=confirmation | C202002241440 | BODACC (annonces légales)
   Dupont & Dupont                  -> signal=confirmation | C202002241440 | BODACC (annonces légales)
   SOCIETE INEXISTANTE ZZZ          -> aucune vérification trouvée
   DANONE                           -> signal=confirmation | B201001141874 | BODACC (annonces légales)
== opensanctions  bilan: examinés 4/4 complète=True 
   Rosneft                          -> signal=alerte | https://www.opensanctions.org/entities/NK-nq68oAyh | OpenSanctions : ce nom figure sur une li
   Gazprom                          -> signal=alerte | https://www.opensanctions.org/entities/NK-N7dfJjNt | OpenSanctions : ce nom figure sur une li
   Danone                           -> signal=alerte | https://www.opensanctions.org/entities/NK-2Hjn4eHA | OpenSanctions : ce nom figure sur une li
   Croix-Rouge française            -> aucune vérification trouvée
== wayback  bilan: examinés 2/2 complète=True 
   Mairie de Grenoble               -> signal=confirmation | http://web.archive.org/web/20261017143535/https:// | Wayback Machine (capture du 17/10/2026)
   Site inexistant                  -> aucune vérification trouvée
== courtlistener  bilan: examinés 2/2 complète=True 
   Tesla, Inc.                      -> aucune vérification trouvée
   Entreprise Fantôme ZZZ           -> aucune vérification trouvée
````
