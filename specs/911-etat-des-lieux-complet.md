# 911 — État des lieux complet du programme (14/11/2026)

**État : note de travail, rien à coder.** Audit en lecture seule de `NALSED/GAPPES-FINAL` au commit
`b4ab69e` (après la revue totale de momo, D112 à D116). Aucune ligne de code modifiée. Ce document
reprend et replace l'audit du score (`910`) dans l'ensemble.

## 0 — En une page

Le programme est **bien construit et honnête sur ce qu'il fait** : il dit ce qu'il n'a pas pu faire,
ne perd pas les résultats en cas de panne, respecte les sites qu'il visite et garde les clés à
l'abri. La revue de momo a déjà corrigé une cinquantaine de défauts.

Sa faiblesse est ailleurs, et elle touche ta priorité : **ce qui décide quels noms sortent, dans
quel ordre et avec quelle confiance n'est pas prouvé fiable**, et plusieurs garde-fous annoncés ne
jouent pas en pratique. Cinq points à traiter avant tout le reste :

| N° | Constat | Gravité |
| :-- | :-- | :-- |
| G1 | La règle 8 (comptes de personnes physiques masqués) est levée automatiquement pour **tous** les comptes, à chaque recherche | grave, vie privée |
| G2 | L'indice non certifié décide quels noms entrent dans les résultats, et la coupe se fait **avant** les filtres et la vérification | grave, fiabilité |
| G3 | Une « confirmation » repose sur le nom seul : un homonyme dans un registre donne la fiabilité A | grave, fiabilité |
| G4 | En mode `extraction`, `resultat.csv` sort 200 noms sans aucun seuil ; le score affiché surestime d'un facteur dix | grave, fiabilité |
| G5 | Sur une machine ouverte au réseau, quiconque atteint le port peut faire exécuter un programme | grave si exposé, connu et documenté |

## 1 — Ce qu'est réellement le programme aujourd'hui

Deux étages, écrits à deux époques.

**Le moteur `grappes`** (`src/grappes`, environ 13 000 lignes, outillage de mesure compris). À partir d'une phrase : il interroge
des moteurs de recherche, tire des mots-clés des extraits reçus, visite les pages, note chaque
source selon le nombre de ces mots-clés qu'elle contient, puis regarde qui cite qui. Une entité
citée par des sources déjà retenues, venant d'au moins deux écosystèmes, est « confirmée ».

**`pilote`** (`pilote/`, environ 15 500 lignes plus l'interface). C'est l'application que tu
utilises : les 80 sources, les 11 outils, le plan de travail, Tri, les exports. Pour chaque
recherche, il copie la configuration du moteur dans un dossier à part, y lance le moteur, puis
appelle lui-même les sources « par adaptateur », la vérification et l'enrichissement.

**Le chemin d'une recherche lancée depuis `/suite`**, dans l'ordre réel du code
(`pont/executer.py`) :

1. Amorçage des mots-clés, collecte web du moteur, recoupement.
2. Appel des registres et des sources par adaptateur ; lecture des noms dans les textes.
3. **Classement de tous les candidats par l'indice de vraisemblance**, puis on garde les
   `combien` premiers (200 par défaut).
4. Application du plan (filtres, conditions, scripts) sur ces 200.
5. Assistant IA, puis vérification et enrichissement.
6. Écriture des candidats, proposition des rapprochements (Splink), Tri.

Conséquence peu visible : même si Tri n'affiche « que des faits, jamais un avis du programme »
(c'est écrit dans `classements.py` et c'est le bon principe), **un avis du programme a déjà choisi
quels noms arrivent jusqu'à Tri**.

## 2 — Ce qui est solide

* **Rien ne se perd en silence.** Source en panne, vérification coupée, traduction non appliquée,
  noms retirés par un filtre, plafond atteint : tout est écrit au journal et montré. Les noms sont
  enregistrés avant le compte rendu, une panne du compte rendu ne les fait pas perdre.
* **Chaque source tourne isolée** : son erreur ou sa lenteur n'arrête que elle. Un disjoncteur met
  en pause une source qui échoue plusieurs fois.
* **Les clés** restent dans un fichier à droits restreints, ne partent jamais vers le navigateur,
  et chaque recherche ne reçoit que les clés des sources qu'elle utilise.
* **Les visites de pages respectent les règles** : robots.txt, délai par site, arrêt sur refus,
  pas de connexion, pas de captcha contourné, adresses internes refusées.
* **Tout ce qui vient de l'extérieur est traité comme une donnée** : textes bornés et nettoyés,
  agent IA lancé sans outil et hors du dossier des clés, scripts du plan lancés sans variables
  d'environnement, et sans réseau quand le système le permet.
* **Les décisions de Tri sont celles d'une personne**, annulables, journalisées. Un rapprochement
  n'efface jamais une fiche.
* **La méthode de mesure d'octobre** (voir `910` § 2) est exemplaire, y compris son verdict négatif.
* **Tests** : moteur 603 réussis ici (les échecs restants viennent de bibliothèques de mesure non
  installées dans mon environnement, plus le défaut de date ci-dessous). Pilote : voir § 6.

## 3 — Les cinq points graves

### G1 — La règle 8 est levée pour tout le monde

`pont/executer.py` appelle `lever_automatiquement(…, cc.p_min, p)` : un compte de personne voit
son masquage levé si sa probabilité atteint le seuil `p_min`. Or `config/classement.yaml` livre
`p_min: 0.0`, et `executeur_grappes.preparer()` ne le change pas. Essai fait sur la configuration
livrée :

````text
log10 LR=-6  p=0.002 -> levée automatique : True, genre affiché : compte
log10 LR=-1  p=0.269 -> levée automatique : True
log10 LR=+0  p=0.500 -> levée automatique : True
````

Même avec le plus mauvais score possible, la levée a lieu. Effets : le compte entre dans les
rapprochements (`rapprochements.py` laisse passer toute fiche portant `regle8_leve`), et l'export
FollowTheMoney s'ouvre pour lui, alors que `formats/ftm.py` écrit « un interrupteur ne suffit
jamais ; une décision humaine, fiche par fiche, oui ». La levée automatique porte la même marque
qu'une décision humaine. Les tests ne le voient pas : ils essaient la fonction avec un seuil de
0,5, jamais avec la configuration réelle.

Origine : la décision 904/Q31 supposait une probabilité mesurée et un seuil réel. Ni l'un ni
l'autre n'existent (voir `910`).

### G2 — L'indice non certifié choisit les noms, et coupe avant les filtres

Étape 3 du chemin ci-dessus. L'ordre vient de `classer()`, donc des poids de `config/lr.yaml`
réglés sur du bruit (`910` § 5.1). Deux effets :

* Si plus de `combien` candidats existent, ceux qui sont écartés le sont sur ce classement, sans
  trace dans le journal.
* Les filtres du plan s'appliquent **après** la coupe. Demander 200 noms et filtrer « France
  seulement » rend moins de 200, même si des noms français existaient au rang 201 et au-delà.

### G3 — Une confirmation par le nom seul

`pont/verification.py` : dès qu'une source de vérification rend quelque chose pour le nom, c'est
une « confirmation ». Les sources locales (`sirene-local`, `rna-local`, `bodacc`) comparent le nom
exact, rien d'autre. Depuis 909 § 1.2.d, une confirmation de première main fait monter la
« fiabilité effective » de la fiche à la lettre du registre. Un nom courant trouvé sur le web
(« Club Avenir ») qui existe à l'identique dans SIRENE, dans une autre ville, devient donc
fiabilité A. La confirmation dit « un organisme porte ce nom », pas « c'est celui-là ».

### G4 — Mode `extraction` sans seuil, score trompeur

Détail dans `910` § 3.2 et § 5.2. Rappel : 200 lignes sortent quel que soit leur score, et le
chiffre affiché ne correspond ni à la formule annoncée ni à une mesure.

### G5 — Pas de compte

Connu et écrit en toutes lettres dans `config/pilote.yaml`. Sur la machine seule (127.0.0.1) le
contrôle du nom d'hôte protège correctement. Dès que le service écoute le réseau (ce qui est
nécessaire pour l'ouvrir depuis un autre poste, comme tu le fais sur `.60`), toute personne du
réseau peut : ajouter un « programme local » qui s'exécute sur le serveur, faire lire un fichier
de la machine, dépenser le budget. À garder sur un réseau où tu es seul, ou derrière une
authentification.

## 4 — Défauts de logique, moins graves

### 4.1 Vérifier et enrichir couvrent peu

Sur 80 sources, 48 déclarent un rôle vérifier ou enrichir. **15 seulement peuvent réellement être
appelées** pour vérifier ou enrichir un nom. Les 33 autres n'ont pas ce qu'il faut (pas de clé de
vérification déclarée) : cocher leur case ne fait rien. Parmi elles, les registres de première main
les plus utiles : `companies-house`, `pappers`, `recherche-entreprises`, `registre-associations`,
`gleif`, `opencorporates`, `ror`. momo l'a signalé pour neuf d'entre elles
(`pilote/QUESTIONS.md`) ; le compte complet est 33.

### 4.2 Des outils posables qui n'agissent pas

* **Requête avancée** (909 § 3) : aucune des 80 sources ne déclare d'opérateur. La tuile se pose,
  ne change aucune requête. momo l'a rectifié lui-même dans D112.
* **Boucle** : la relance par élément n'est pas branchée. C'est dit à l'écran.
* **Compteur budget** : le plafond propre à une recherche n'est pas appliqué, seule l'alerte l'est.
* **Traduction** : sans effet sur les sources qui passent par le moteur de collecte. C'est dit.
* **Chaîne de repli entre prestataires** et **vérification par texte de page** (909 § 1.2.e/f) :
  non commencées, raisons tracées par momo.

### 4.3 La « proximité sémantique » est un comptage de mots-clés

`semantic/scoring.py` compte les mots d'un lexique dans le texte. Ce lexique vient des extraits
rendus par la recherche sur ta phrase. Conséquences : un sujet dont les acteurs n'emploient pas
ces mots est mal vu ; les mots vides ne sont gérés que pour le français et l'anglais ; un gros site
a plus de chances qu'un petit. Ce n'est pas un défaut de code, c'est une limite de méthode à
connaître : le mot « sémantique » promet plus que ce qui est fait.

### 4.4 Quatre mécanismes de rapprochement de noms

| Où | Méthode | État |
| :-- | :-- | :-- |
| moteur, `variantes.py` | nomenklatura | **éteint** (enchaîne des noms sans rapport) |
| pilote, Tri | Splink, probabilités écrites à la main, une personne tranche | actif |
| pilote, fiche 06 | cleanco + ressemblance de texte | actif |
| pont, sortie du moteur | égalité du nom mis à plat | actif |

Ils ne se contredisent pas, mais deux écritures d'un même acteur traversent tout le circuit comme
deux lignes jusqu'à Tri. La confiance affichée par Splink n'est pas mesurée non plus ; comme une
personne tranche, le risque est faible.

**Rectification de ce que je t'ai dit le 14/11** : j'ai affirmé que Tri devait s'appuyer sur
nomenklatura. C'est faux pour l'application que tu utilises : le Tri de pilote s'appuie déjà sur
Splink, et nomenklatura est éteint dans le moteur. La bonne base pour Tri est Splink.

### 4.5 Mécanismes qui ne jouent pas

* **Signal « écosystèmes » de l'indice** : jamais déclenché (`910` § 3.1).
* **Recalibrage automatique des seuils** (`cycle/learn.py`) : il ne peut que relâcher le seuil, et
  avec les réglages livrés sa cible est toujours au-dessus du seuil actuel (plancher 60 contre
  seuil 40) : le seuil ne bouge jamais. Seule la marge d'ambiguïté peut bouger, et seulement
  avec plusieurs sujets.
* **Rétention de 90 jours** : calculée sur la date de publication, pas sur la date de collecte. En
  mode cycle, un article ancien est effacé au cycle suivant puis recollecté. Sans effet dans
  pilote, où chaque recherche a sa propre base.

### 4.6 Écarts entre les documents et le programme

* `FINAL.md` § 2 : `autonome` faux par défaut. `config/autonomie.yaml` du dépôt est à `true`
  (pilote en a besoin).
* D82 : extraction « mesurée et calibrée ». Mesurée, non certifiée, calibration non valide.
* En-têtes d'`autocal` : « validation imbriquée », absente du code (`910` § 4).

## 5 — Ce que momo a signalé et qui reste ouvert (D115, D116)

À trancher par toi :

* `inclure_personnes: non` est lu comme « oui » dans `config.py` : des noms de personnes
  sortiraient en clair. Vérifié : `bool("non")` vaut vrai. À corriger comme `autonome` l'a été.
* Deux recherches en même temps peuvent dépenser le même reste du plafond.
* Un dossier d'export commun écrase `resultat.csv` d'une recherche à l'autre.
* `grappes export` lance des appels sans vérifier `autonome` ni le fichier STOP.
* `Crawl-delay` sans plafond : un site peut faire dormir un cycle 24 heures.
* `rel=canonical` d'un autre domaine décide de la source d'une observation, sans contrôle.
* `min_ecosystemes` accepte 1 alors que `FINAL.md` exige 2.
* Le serveur MCP permet de confirmer une personne masquée par son identifiant.

## 6 — Tests

* **Moteur** : 603 réussis dans mon environnement. `tests/test_cycle.py` échoue en partie parce
  que la purge ignore la date injectée et que le corpus de test est daté du 30/09/2026 : **à
  partir du 29/12/2026 ces tests tomberont en masse**, sans qu'aucun code n'ait changé.
* **Pilote** (hors réseau) : 647 réussis dans mon environnement. Les 33 autres sont des tests de
  bout en bout qui exigent l'interpréteur du moteur installé à côté, absent chez moi : ce n'est
  pas un défaut du code. momo compte 639 réussis et 1 échec connu sur sa machine.
* Les corrections de D114 (interface) et de D115 (moteur) n'ont pas de test de non-régression.
* Aucun test ne lance une recherche avec la configuration livrée de bout en bout : c'est ce qui a
  laissé passer G1.

## 7 — Ce que je n'ai pas vérifié

* Les 55 adaptateurs de sources un par un (seulement leur cadre commun et quelques-uns).
* Le détail de l'interface (`static/`), déjà revue deux fois par momo.
* Aucune recherche réelle : pas de clés, pas de réseau, pas d'accès à `.60` ni aux archives de
  mesure. Les constats G1 à G4 sont établis par lecture et par essais sans données.

## 8 — Ordre proposé (rien n'est décidé)

| Rang | Quoi | Pourquoi d'abord |
| :-- | :-- | :-- |
| 1 | G1 : couper la levée automatique de la règle 8 tant qu'aucun seuil mesuré n'existe ; la levée manuelle reste | vie privée, correctif court |
| 2 | `inclure_personnes: non` lu comme oui | même famille, une ligne |
| 3 | G3 : une confirmation exige un second champ concordant (ville, numéro ou site) ; sinon elle est notée « même nom » sans effet sur la fiabilité | fausse confiance |
| 4 | G2 : appliquer filtres et plan avant la coupe ; journaliser les noms coupés | résultats incomplets en silence |
| 5 | G4 et décisions 1 à 4 de `910` § 6 | fiabilité de l'affichage |
| 6 | 4.1 : donner une vraie clé de vérification aux registres de première main | c'est là que vérifier gagne le plus |
| 7 | Test de bout en bout sur la configuration livrée ; corriger la date du corpus de test | pour que ces défauts ne reviennent pas |
| 8 | Le reste du § 5, puis Tri | |

Les rangs 1 et 2 ne changent aucun résultat de recherche. Les rangs 3 à 5 en changent : listes
parfois plus courtes, fiabilités affichées plus basses, mais justes.
