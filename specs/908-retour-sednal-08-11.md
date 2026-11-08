# 908 — Retour de Sednal du 08/11/2026 (grappes + pilote `/suite`)

Hors du pavé. Retour écrit par Sednal après usage réel de `/suite` sur `.60`, repris **point par point** avec
Claude. Chaque point est écrit ici au fur et à mesure qu'il est traité : ce fichier se remplit en plusieurs
fois, il n'est pas complet tant que la dernière section ne le dit pas.

Ordre du retour : Transverse → Tableau de bord → Réglages (Sources, puis Outils 2.1 à 2.10) → Tri.

**État : en cours de rédaction.** Points traités : 1, 2, 3, 4, 5, 6 (outil 2.1), 7 (outil 2.2, partiel).

---

## 1 — Transverse : faire disparaître complètement l'ancienne UI

Demande de Sednal : `/suite` est la charte, l'ancienne UI (`/`) doit disparaître entièrement, câblage adapté
si besoin.

### Constat (vérifié dans le code le 08/11/2026)

La parité **pour l'ajout de source** est faite (905 §2 : les 6 types, plus les flux RSS sur une fiche à
part). Ce n'est pas elle qui bloque. Ce qui bloque, ce sont **deux pages de l'ancienne UI que `/suite` ne
remplace pas encore** :

| | Ancienne UI | `/suite` |
|---|---|---|
| **Tri** | `static/tri.js`, 585 lignes — paquets, 5 vues, classements, motifs de rejet, décisions annulables, export, liste virtuelle | `static/suite/js/tri.js`, **59 lignes** — seulement les rapprochements Splink à confirmer ou séparer |
| **Lancement** | `static/lancement.js`, 229 lignes — profondeur, limites (temps, appels), **pause et reprise** d'une recherche en cours, sources mises en pause avec leur raison | `static/suite/js/recherche.js`, 204 lignes — **aucun de ces réglages** : ni profondeur, ni limites, ni pause/reprise |

C'est exactement ce que le lien lui-même annonce : « Ancienne interface (**Lancement, Tri**) ». Supprimer `/`
aujourd'hui ferait perdre le seul Tri complet qui existe, et la pause/reprise d'une recherche en cours.

### Décision de Sednal (08/11/2026)

**La nouvelle UI reprend les fonctionnalités de l'ancienne, et l'ancienne ne disparaît qu'une fois tout
porté.** Pas de suppression partielle, pas d'attente passive : on porte, puis on supprime.

Ordre de travail qui en découle :

1. **Porter les réglages de Lancement dans `/suite`** (page Recherche) : profondeur, limites de temps et
   d'appels, **pause et reprise** d'une recherche en cours, affichage des sources mises en pause avec leur
   raison. Reprendre ce qui est déjà écrit dans `static/lancement.js` et les routes `/api/recherches/
   <id>/pause` et `/reprise` qui existent déjà — ne rien réécrire depuis zéro.
2. **Tri** : **adapter** l'ancien Tri (`static/tri.js`, 585 lignes) à la charte de `/suite`, pas le
   réécrire. Les fonctionnalités à garder, à changer ou à abandonner se discutent avec Sednal **avant** que
   momo commence — ce point sera traité dans la section Tri de cette même spec.
3. **Alors seulement**, supprimer l'ancienne UI entièrement : route `/`, fichiers statiques devenus
   inutiles, et le lien « Ancienne interface (Lancement, Tri) » dans `/suite`. C'est la 905 §3, qui reste
   suspendue jusque-là.

La vérification des 6 types d'ajout de source sur `.60` (905 §2) reste à faire par Sednal, en parallèle.

Précision utile pour la suppression : le lien se trouve en **pied de page**, `static/suite/js/main.js`
ligne 79 — pas dans la barre de navigation.

---

## 2 — Tableau de bord

Retour de Sednal : « pour l'instant OK » ; le lien vers l'ancienne interface n'a pas disparu ; « il manque
des parties ?? Alerte Journal ??? des outils ont des renvois vers tableau de bord qui n'existe pas ».

### 2.1 — Le lien vers l'ancienne interface

Couvert par le point 1 : il tombe avec elle. Rien de particulier ici.

### 2.2 — « Il manque des parties ? » : non, c'est l'état vide (aucune action)

Vérifié dans le code, puis confirmé par une capture de Sednal le 08/11/2026. La page a deux moitiés :

* **Moitié haute — la recherche en cours** (alertes, plan qui tourne, sources au travail, résultats, coût).
  Tout y est conditionné à l'existence d'une recherche : sans aucune recherche, la moitié entière est
  remplacée par la phrase « Aucune recherche à montrer pour l'instant. »
* **Moitié basse — l'état du système** : Budget du mois, Sources, Recherches programmées (cachée quand rien
  n'est programmé), Journal (toujours affiché, « Rien pour l'instant. » quand il est vide).

Aucune partie ne manque : Sednal regardait un tableau de bord vide parce qu'**aucune vraie recherche n'avait
encore tourné sur `.60`**. La moitié haute se remplira à la première. **Rien à faire pour momo.**

### 2.3 — Effet « alerte » des outils : aucun chemin d'affichage (à corriger)

Le constat de Sednal (« des outils renvoient vers un tableau de bord qui n'existe pas ») est juste sur un
point précis. Chaque outil déclare un *Effet dans le Tableau de bord* parmi rien / compteur / journal /
alerte. Trois sur quatre aboutissent, le quatrième non :

| Effet déclaré | Rendu réel |
|---|---|
| `rien` | ✅ par définition |
| `compteur` | ✅ section « Le plan en train de tourner » : N entrés → N sortis, par tuile |
| `journal` | ✅ ligne « *outil* : N fiches traversées, N modifiées » dans la carte Journal (`tuile_passee`) |
| `alerte` | ❌ **rien** |

`sectionAlertes()` (`static/suite/js/tableau.js`, ligne 149) ne construit ses alertes qu'à partir de quatre
situations système : budget mensuel au-delà du seuil, quota d'une source au-delà du seuil, source mise en
pause, plafond du mois atteint. Aucune alerte levée par un outil n'a de chemin pour y arriver — or `alerte`
est précisément l'effet déclaré par le **Compteur budget** (3.8.08), dont le seuil « À partir de … % » et
l'action « Prévenir » ne mènent donc nulle part aujourd'hui.

**À faire (momo)** : brancher l'effet `alerte` d'un outil sur la section Alertes du Tableau de bord, en
traitant d'abord le Compteur budget, seul outil livré à le déclarer — son seuil et son action « Prévenir »
doivent produire une vraie ligne d'alerte. Ne pas toucher aux trois autres effets, ils fonctionnent.

---

## 3 — Réglages, partie transverse

Huit remarques de Sednal. Reprises une par une, avec ce qui est vérifié dans le code.

### 3.1 — Le lien vers l'ancienne interface (rien à faire ici)

Point 1.

### 3.2 — « Comment fonctionnent les tests ET pourquoi en local ? » (rien à faire)

C'est la décision du 13/10/2026 : le test d'activation ne doit **rien** consommer, ni crédit ni argent.
Quatre niveaux, arrêt au premier échec (`src/pilote/tests_source.py`) : configuration valide ; convention de
sortie vérifiée sur un **exemple de réponse enregistré**, la source n'étant jamais appelée ; connexion et clé
seulement si le fournisseur offre un point d'accès gratuit pour ça, sinon « non vérifié » ; pour un programme
local, exécution sur l'exemple dans un processus séparé avec limite de temps. Si tout passe, la source est
« vérifiée hors ligne ». Comportement voulu, pas un manque.

### 3.3 — « TOUS les tests doivent être fonctionnels » : le test réel existe mais pas dans `/suite`

Le **test réel** demandé existe **et est entièrement codé** : une vraie requête, **le prix dit avant le
clic**, refusé si le plafond mensuel ne le permet pas (`tests_source.test_reel` + `tests_source.prix_du_test`,
routes `GET` et `POST /api/sources/{id}/test-reel`).

**Mais ces routes ne sont déclarées que dans `api_reglages.py`, l'API de l'ancienne UI.** `api_suite.py`
n'expose que le test local (`POST /sources/{ident}/test`). Depuis `/suite`, le test réel est donc
inatteignable — d'où le constat de Sednal.

**À faire (momo)** : exposer le test réel dans `/suite` — la route de prix et la route d'exécution, avec la
confirmation du prix avant le clic, exactement comme l'ancienne page. C'est un portage, pas une écriture :
la logique existe, seule l'exposition manque. Ce point rejoint la liste de portage du point 1 (même nature
que Tri et Lancement).

### 3.4 — Une source payante ne doit jamais afficher « illimité » (vrai défaut)

Couvre aussi le point 1.1 du retour (« si le coût est payant pourquoi le quota est illimité ? ») : c'est la
même chose, vue à deux endroits.

`suite_reel._quota()` ne renvoie un quota que dans deux cas : le fournisseur en a rendu un au dernier test,
ou la déclaration annonce un palier gratuit mensuel (`cout.gratuit_par_mois > 0`). Sinon il renvoie `None`,
et la fiche affiche **« illimité »**.

Or **14 sources sont réellement payantes** (`cout.vers_dollar > 0`) et **12 d'entre elles n'ont aucun palier
gratuit** — elles affichent donc « illimité » alors que chaque appel coûte et que rien ne les borne sauf le
budget mensuel global. Les plus chères : OpenCorporates (0,58 $/appel), NewsAPI.ai (0,045 $), Google Places
(0,035 $, mais 1 000 gratuits/mois), Pappers (0,01 $).

**À faire (momo)** : pour une source payante sans palier gratuit, ne plus écrire « illimité ». Dire qu'elle
est payante et bornée par le budget du mois (formulation à poser avec Sednal si besoin), et garder
« illimité » pour ce qui l'est vraiment — une source gratuite sans quota.

### 3.5 — Plusieurs tuiles du même outil : déjà possible (à rendre visible)

Déjà implémenté. Dans la palette (`static/suite/js/plan.js`), une entrée d'outil est posée avec
`posee: false` en dur : un outil n'est **jamais** grisé, chaque clic pose une tuile indépendante, avec son
identifiant propre (`${o.id}:${horodatage}${aléa}`) et **sa propre copie des options**
(`opts: o.options.map((p) => [...p])`). Trois tuiles « Filtre » avec trois réglages différents fonctionnent
déjà. Les sources, elles, se grisent une fois posées (`posee: surPlan.has(s.id)`) — volontaire, une source ne
se pose qu'une fois.

**À faire (momo)** : rien sur le fond. Seulement le rendre lisible dans la palette — Sednal ne savait pas que
c'était possible, donc la palette ne le dit pas assez.

### 3.6 — « Ce qu'il reçoit » / « Ce qu'il renvoie » : texte tronqué

Ces deux champs portent des phrases longues (ex. Traduction : « Le même contenu, avec sa traduction ajoutée à
côté — l'original n'est jamais remplacé ») affichées dans deux colonnes étroites, qui les coupent en plein
milieu — sur la capture de Sednal : « Le texte de la recherche, ou les r… ». Le texte est juste, c'est
l'affichage qui le rend incompréhensible.

**À faire (momo)** : afficher ces deux phrases en entier (pleine largeur, retour à la ligne, ou tout autre
rendu qui ne tronque pas), au lieu de les serrer dans deux colonnes.

### 3.7 — « LES CHOIX DOIVENT ÊTRE FIXE » (rien à faire)

C'est ce que la 905 §1 a corrigé. Sednal avait écrit son retour en regardant une version antérieure du code ;
une fois à jour, il confirme le 08/11/2026 : « menu fermé pour l'instant ». Point clos.

### 3.8 — « Le design doit être propre à chaque outil »

Traité **outil par outil** dans les sections 2.1 à 2.10 du retour (accord de Sednal le 08/11/2026), plutôt
que comme une règle générale : il a déjà détaillé ce qui cloche pour chacun.

### 3.9 — « Tester tous les outils »

Campagne de test à mener **une fois** les corrections par outil faites (sections 2.1 à 2.10) et le test réel
exposé dans `/suite` (3.3). À reprendre en fin de spec, pas avant.

---

## 4 — Réglages / Sources

### 4.1 — « Si le coût est payant, pourquoi le quota est illimité ? »

Même défaut que **3.4**, vu à un deuxième endroit. Rien de plus à faire que ce qui y est écrit.

### 4.2 — « À quoi correspond *adresse* ? » : mapper les serveurs, et réclamer ceux qui manquent

Le champ « Adresse » de la fiche d'une source affiche `presets.domaine_source(d)` : le nom de machine du
serveur contacté, **lu uniquement dans la déclaration** (`moteur.parametres.url` pour une API,
`moteur.parametres.mcp` pour un MCP). Quand l'adresse est dans le code de l'adaptateur, la fonction rend
`""` plutôt que de deviner — bon réflexe en soi, mais la fiche affiche alors un « — » muet.

Chiffré sur les 79 sources livrées :

| Ce que la déclaration permet déjà de savoir | Nb | Une adresse a-t-elle un sens ? |
|---|---|---|
| Hors ligne (`mode.en_ligne: false`) — copie locale, fichier | 7 | **Non** : aucun serveur contacté |
| En ligne, adresse écrite dans la déclaration | 22 | **Oui**, déjà lisible aujourd'hui |
| En ligne, adresse dans le code de l'adaptateur | 50 | **Oui**, mais affichée « — » aujourd'hui |
| Base extérieure (`adaptateur: base_exterieure`) | 0 livrée | **Non** : déjà affichée comme « Machine » |

**Décision de Sednal (08/11/2026)** : pas de champ générique affiché partout — du cas par cas, décidé par le
programme à partir de ce qu'il sait déjà. On **mappe** les adresses serveur ; si une adresse existe elle est
affichée ; si elle manque là où elle est nécessaire, on la réclame par un message **en rouge**
(« Veuillez entrer une URL serveur »).

Trois cas à distinguer à l'implémentation, sinon la règle se retourne contre son but :

1. **Adresse fixée par l'adaptateur** (Brave Search, CourtListener, Bluesky… — les 50) : à remonter depuis
   l'adaptateur et à afficher **en lecture seule**. Laisser l'utilisateur en saisir une autre ne changerait
   rien à ce que la source appelle réellement : l'affichage deviendrait faux.
2. **Adresse qui appartient à l'utilisateur** (services auto-hébergés : SearXNG, Overpass, RSSHub,
   LibreTranslate, et toute source dont l'URL est un paramètre) : champ **modifiable**, et **message rouge
   « Veuillez entrer une URL serveur » quand il est vide** — sans elle la source ne peut pas fonctionner.
   C'est le seul cas où le message rouge a un sens.
3. **Source hors ligne** (copie locale, fichier local, programme local) : **aucun champ**, aucun message.

**Manque révélé par ce point** : rien dans les déclarations ne distingue un serveur **tiers** d'un serveur
**auto-hébergé par Sednal**. SearXNG porte `mode.local: false` alors qu'il tourne sur sa machine. Or c'est
exactement la distinction qui donne son sens au champ — savoir où partent les mots cherchés, sa propre
machine n'étant pas une fuite. **À ajouter dans la déclaration** d'une source, et c'est aussi ce qui permet
de classer automatiquement une source dans le cas 1 ou le cas 2.

**Nouvelle source** : le formulaire d'ajout fait déjà le cas par cas (API → adresse, MCP → adresse du
serveur, base extérieure → machine et port, fichier / base SQLite / programme → chemin, sans serveur). Ce
qui manque, c'est de le **dire** : en choisissant le type, on doit savoir si une adresse serveur sera
demandée, et pourquoi.

**Le mécanisme du cas 2 existe déjà — ne pas en inventer un autre.** Une déclaration peut porter un bloc
`parametres` (rendu comme `parametres_attendus`, posé le 02/11/2026 après le retour « je mets ça où ? ») :
libellé, `type: url`, `requis: true`, exemple. **CKAN est la seule des 79 sources à s'en servir** — et c'est
aussi, confirme Sednal le 08/11/2026, la seule adresse qu'il ait eu à saisir jusqu'ici :

````yaml
parametres:
  portail:
    libelle: Adresse du portail de données ouvertes de ton pays
    type: url
    requis: true
    exemple: https://open.canada.ca/data
note: Éteinte tant que l'adresse du portail n'est pas donnée.
````

Il manque seulement à ce mécanisme le **message rouge quand un paramètre requis est vide**, et son extension
aux services auto-hébergés (SearXNG, Overpass, RSSHub, LibreTranslate), dont l'URL est aujourd'hui enfouie
dans la configuration du moteur au lieu d'être demandée dans la fiche de la source.

**À faire (momo)** : le mappage des adresses depuis les adaptateurs ; l'affichage en lecture seule ou
modifiable selon le cas 1 / 2 / 3 ; le message rouge sur un paramètre `requis` vide, en réutilisant
`parametres_attendus` (modèle : CKAN) et sans créer de second mécanisme ; l'extension de ce bloc
`parametres` aux services auto-hébergés ; le marqueur tiers / auto-hébergé dans la déclaration ; le libellé
du champ, qui doit dire qu'il s'agit du serveur contacté (« Adresse » seul n'apprend rien).

---

## 5 — Réglages / Outils, partie transverse

### 5.1 — « La section Modèle doit disparaître » : oui, mais seulement en modification

`ficheOutil()` affiche deux blocs identiques à la création et à la modification :

* **« Comment il travaille »** (À partir d'un modèle / Script collé) ;
* **« Modèle »** : la liste de tous les outils en pastilles.

À la **création**, les deux sont indispensables — choisir un modèle est ce qui débloque le bouton
(« Choisis un modèle. »). À la **modification**, ils ne servent à rien et sont dangereux : cliquer une autre
pastille de « Modèle » écrase d'un coup le rôle, l'effet, les options, la description et les exemples de
test de l'outil qu'on était en train de régler. Sur un outil livré (Traduction, Filtre…), basculer en
« Script collé » n'a pas davantage de sens.

**À faire (momo)** : masquer « Comment il travaille » **et** « Modèle » en modification ; les garder à la
création.

### 5.2 — Scrapling : brancher la version complète, en secours et en outil

**Décision de Sednal (08/11/2026) : on branche Scrapling complet, et on l'implémente à deux endroits.**

Aujourd'hui, la 906 n'a câblé que le **client HTTP** de Scrapling (empreinte TLS de navigateur). Son
**navigateur furtif** (Chromium, pages en JavaScript, protections Cloudflare) n'est pas branché, et une
seule source l'utilise (`un-civil-society.yaml`).

Rappel de la contrainte, qui façonne les deux usages : l'adaptateur a besoin, **par site**, d'une adresse,
d'un sélecteur de résultat et de sélecteurs de champs. Scrapling n'est pas un moteur de recherche, c'est un
**lecteur de pages** : il ne peut pas « prendre le relais » d'une recherche, il n'aurait rien à chercher.

**(a) Brancher le navigateur furtif.** Ajouter au-delà du client HTTP le fetcher navigateur de Scrapling,
pour les sites dont les résultats n'arrivent qu'en JavaScript, ou protégés. Choix du mode par source
(HTTP simple par défaut, navigateur si la source le demande) : le navigateur est beaucoup plus lourd, il ne
doit pas devenir le cas général.

**(b) Recherche simple — une notion de « source de secours ».** Une source marquée *secours* n'est appelée
que si les sources principales n'ont rien rendu ou ont échoué. Mécanisme **général**, pas réservé à
Scrapling : les sources Scrapling s'y rangent naturellement. Le précédent existe déjà, mais enfermé dans une
seule source — `osm-overpass.yaml` essaie le serveur auto-hébergé puis des serveurs publics « en secours ».
Il s'agit de sortir cette idée de la source et d'en faire un réglage partagé.

**(c) Recherche avancée — une tuile Outil, en rôle ENRICHIR.** Elle prend les candidats déjà trouvés (qui
portent leur `site`), va lire **leur propre page**, et ramène ce qu'il y a dessus (ville, contact, nom
exact, description). **Cette fonction n'existe nulle part aujourd'hui** : aucun outil livré ne va chercher
une page. Elle complète une fiche sans jamais l'écraser, comme tout ENRICHIR (voir `pont/verification.py`,
`fonction: enrichir`).

### 5.3 — api-anything : écarté pour l'instant (corrige la 906)

Contraintes relevées le 08/11/2026 sur le dépôt : **Node 22.13+** et un **navigateur sans fenêtre** ;
apprentissage par une commande à trois exemples (déterministe, sans IA) **mais** pages à clics apprises par
un **agent** avec validation humaine, et **réapprentissage par un agent** quand le site change ; ne marche
pas sur les sites à protection anti-robot (leur propre exemple : Reddit), pas de résolution de CAPTCHA ; et
surtout **les opérations apprises sont partagées par défaut** avec les autres installations (mode
`--local-only` disponible) — pour un outil d'OSINT, publier la liste des sites qu'on a appris à interroger
revient à publier ce qu'on cherche.

Son seul cas d'usage solide pour grappes — un annuaire dont les résultats arrivent en JavaScript depuis une
API interne — est **couvert par le navigateur furtif de Scrapling** (point 5.2 a), sans nouvelle dépendance
ni partage.

**Décision : on ne prend pas api-anything maintenant.** À ressortir seulement si un site concret résiste au
Scrapling complet ; le besoin sera alors réel et mesurable. **Cette décision remplace ce qu'annonçait la
906**, qui prévoyait de le brancher comme première source de type « serveur MCP ».

### 5.4 — « Description doit être une vraie description »

Le champ attend littéralement « Une phrase » (placeholder de `f.fait`), et les dix outils livrés n'en ont
qu'une (Traduction : « Traduit la requête ou les résultats, et garde toujours l'original à côté. »).

**À faire (momo)** : développer la description des dix outils livrés — ce que fait l'outil, quand s'en
servir, ce qu'il ne fait pas. Outil par outil, en suivant les sections 2.1 à 2.10 du retour.

### 5.5 — Une explication au survol dans « Réglages du modèle »

Aucune aide au survol sur les options d'un outil aujourd'hui. **À faire (momo)** : une courte explication au
survol de chaque case / pastille des réglages d'un outil, comme il en existe déjà sous « Effet dans le
Tableau de bord ».

---

## 6 — Outil 2.1 : Format de sortie

Constaté sur `.60` le 08/11/2026, captures à l'appui.

### 6.1 — Les dix outils livrés n'ont aucun test réel (dépasse 2.1)

C'est le fond des remarques 2.1.2, 2.1.5 et du « TOUS les tests doivent être fonctionnels » du point 3.

`suite.tester_outil()` n'exécute quelque chose que pour un outil de nature **script** (`suite_script.executer`
sur l'exemple d'entrée, comparé à la sortie attendue). Pour un outil de nature **modèle** — c'est-à-dire les
dix outils livrés — le test ne lance rien : il vérifie seulement que l'exemple d'entrée et la sortie attendue
**ne sont pas vides**, puis met l'outil à « opérationnel ».

L'interface l'avoue à moitié (« Fiche vérifiée — l'outil ne s'exécute pas encore sur de vraies données »),
mais la pastille passe quand même au vert, et `suite_graine` livre les dix avec `test_reussi: True` d'office.
Un test qui réussit ne dit donc rien du fonctionnement de l'outil.

**À faire (momo)** : donner un vrai test aux dix outils livrés — l'outil tourne sur son exemple d'entrée, la
sortie obtenue est comparée à la sortie attendue, et « opérationnel » ne s'obtient que comme ça. Tant qu'un
outil n'est pas exécutable, il ne doit pas afficher « opérationnel » mais un état qui dit la vérité.

### 6.2 — Un menu déroulant par format de sortie (2.1.3)

Les réglages propres à chaque format **existent** (cocher CSV fait apparaître « Contenu » et « Séparateur »),
mais ils sont présentés en une **liste de neuf cases à cocher** suivie de sections empilées dessous.

**Demande de Sednal** : **un menu déroulant par format**, chacun portant ses propres options à l'intérieur —
sur le modèle des blocs repliables de Réglages / Sources. La liste reste courte quand tout est fermé, et les
spécificités d'un format se lisent en l'ouvrant, au lieu de s'empiler en bas de la page.

### 6.3 — Le chemin du fichier de sortie n'existe nulle part (2.1.1)

Le moteur sait le gérer — `sortie.py` : « le dossier est choisi par l'utilisateur (Réglages, ou pour cette
recherche) ; sinon celui de la recherche » — mais **aucun champ ne le propose dans Réglages sur `/suite`**.

**À faire (momo)** : une section où donner la destination des fichiers de sortie, en **chemin absolu**, avec
**vérification** (le dossier existe, il est accessible en écriture). Linux uniquement, c'est le seul système
visé.

### 6.4 — « Effet dans le Tableau de bord » pas clair (2.1.4)

Le bloc affiche quatre pastilles et une phrase sous la pastille choisie (« À la fin de son passage, cet outil
écrit une ligne de bilan dans le journal du Tableau de bord »). Deux raisons au flou :

* le mot « effet » ne dit pas **ce qu'on verra**, ni où ;
* l'un des quatre choix, `alerte`, **ne produit rien du tout** aujourd'hui (point 2.3).

**À faire (momo)** : dire concrètement ce que chaque effet produit et à quel endroit du Tableau de bord il
apparaît, plutôt qu'un mot abstrait ; et brancher `alerte` (point 2.3), sans quoi un des quatre choix reste
un leurre.

### 6.5 — Rappel : la rangée « Modèle » est bien affichée en modification

Confirmé par capture : en modifiant **Format de sortie**, la rangée « Modèle » liste les dix outils et
« Format de sortie » y est sélectionné. Cliquer « Boucle » écraserait rôle, effet, options, description et
exemples de test. Correction déjà écrite au point 5.1.

---

## 7 — Outil 2.2 : Traduction

### 7.1 — Le test échouait parce que le service n'était pas là (résolu le 08/11/2026)

Message vu par Sednal : `le moteur de traduction ne répond pas (<urlopen error [Errno 111] Connection
refused>)`. Ce n'était pas un défaut de l'outil : **LibreTranslate ne tournait pas sur `.60`**.

Diagnostic : le fichier `libretranslate-pilote.service` livré dans le dépôt lance
`/mnt/carte/pilote-copies/libretranslate/lancer.sh` — le chemin de la machine d'avant. Sur `.60`, le disque
de données (260 Go) est monté sur **`/srv/grappes`**, et LibreTranslate y était déjà installé. Le service
échouait donc en `203/EXEC` (fichier introuvable), en boucle, sans que rien ne le dise côté interface.

Résolu en corrigeant le chemin du service et en réinstallant les modèles interrompus ; le service répond
maintenant (anglais, arabe, chinois, allemand, espagnol, français, italien, russe).

**Deux défauts pour momo :**

1. **Chemin en dur dans un fichier livré.** `pilote/outils/libretranslate/libretranslate-pilote.service` et
   `LISEZMOI.md` écrivent `/mnt/carte/pilote-copies/…`, alors que le README de pilote pose « aucun chemin en
   dur » et que la machine réelle utilise `/srv/grappes`. À dériver de la configuration, comme le reste.
   (`lancer.sh`, lui, est déjà correct : il déduit son dossier de sa propre position.)
2. **Erreur brute affichée à l'utilisateur.** L'interface a montré `<urlopen error [Errno 111] Connection
   refused>`. Elle doit dire ce qui se passe et quoi faire — « le service de traduction n'est pas démarré
   sur cette machine », avec le renvoi vers son fichier d'installation — jamais le texte d'exception Python.
   À traiter comme une règle générale, pas seulement pour la traduction : aucun message d'erreur technique
   brut ne doit arriver jusqu'à l'écran.

### 7.2 — Plusieurs langues d'entrée (2.2.1) et même rendu pour « Traduire vers » (2.2.2)

**En attente de confirmation de Sednal.** Aujourd'hui « Traduire vers » accepte déjà plusieurs langues,
« Langue d'entrée » une seule (ou « détecter »).

Contrainte du moteur : `suite_traduction.traduire_protege()` traduit **depuis une** langue par appel.
« Plusieurs langues d'entrée » ne peut donc pas vouloir dire traduire depuis trois langues à la fois ; cela
veut dire **« détecte, mais seulement parmi ces langues-là »** — utile (évite qu'un texte français soit pris
pour du portugais), mais ce n'est pas la même chose. À confirmer avant d'écrire la consigne.

---

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
