# 909 — Vérifier et enrichir : correctifs, puis comparaison ancienne UI / `/suite`

État : en cours de rédaction, point par point avec Sednal (09/11/2026).

Hors du pavé du 02/11, suite à une question de Sednal le 09/11/2026 (« est-ce que vérifier et enrichir
pourraient être améliorées ? »). Deux volets, dans cet ordre :

1. Corriger les défauts trouvés en relisant le code de vérifier et d'enrichir (ci-dessous, vérifier
   d'abord, enrichir ensuite).
2. **Comparer systématiquement l'ancienne UI et `/suite`**, fonctionnalité par fonctionnalité — pas
   seulement vérifier/enrichir — et mettre `/suite` à jour partout où elle est en retard. Ce volet
   élargit 905 (qui ne traitait que l'ajout de source et les menus fermés) à l'ensemble des deux UIs.

## 1 — Vérifier

### 1.1 — Trois correctifs décidés le 09/11/2026

**a) Réglage global absent de `/suite`.** « Vérification active » et le mode (« memes » / « plus »,
`reg["verification"]`) ne se règlent aujourd'hui qu'à l'installation de première fois (assistant,
`installation.js` étape 2), ou via l'ancienne UI (`PUT /reglages/verification`). Décision : ajouter
cette case dans Réglages transverse de `/suite`, même traitement que toute autre case fermée (règle
d'affichage 3.10 de 908 si le choix dépasse 4 options).

**b) La fiche source de `/suite` n'affiche qu'un seul rôle.** 36 sources sur 79 sont déclarées
`chercher` + `verifier` (ou `chercher` + `enrichir`) à la fois — voir liste en annexe du point 2. Le
calcul qui affiche le rôle (`suite_reel.py` ligne 125 : `role = sur.get("role") or ("CHERCHER" if
"chercher" in d.roles else "VERIFIER" if "verifier" in d.roles else "ENRICHIR")`) ne garde que le
premier trouvé, toujours CHERCHER pour ces sources — leur vérification/enrichissement est active mais
invisible dans leur fiche. Décision : le champ « Rôle » de la fiche devient **à choix multiples** (une
case par rôle déclaré : CHERCHER, VERIFIER, ENRICHIR), reflétant la liste réelle de `Declaration.roles`
au lieu d'un seul choix qui en masque les autres.

**c) Le bouton marche/arrêt casse la vérification des sources à double rôle — bug.**
`suite_reel.allumer()` pose `"verifier": allumee and "verifier" in d.roles and "chercher" not in
d.roles` : pour une source `chercher`+`verifier`, ce booléen est toujours faux, quel que soit
`allumee`. Éteindre puis rallumer wikidata ou ror depuis le bouton marche/arrêt de `/suite` remet donc
`verifier` à faux et ne le remet **jamais** à vrai — perte silencieuse et permanente de la vérification,
jusqu'à correction manuelle du fichier de réglages. Décision : corriger `allumer()` pour qu'il pose
chaque rôle déclaré indépendamment (`chercher` et `verifier` suivent chacun `allumee`, sans condition
d'exclusion mutuelle).

### 1.2 — Amélioration décidée le 09/11/2026

Rappel du rôle de la fonction (clarifié avec Sednal) : vérifier n'apporte jamais de nouveau nom, elle
apporte de la **fiabilité** à ce qui a déjà été trouvé, en repassant chaque fiche par une autre source
de la liste des 79. Les cinq pistes ci-dessous sont retenues.

**a) Rendre visible le signal « alerte ».** Une alerte (ex. liste de sanctions) n'apparaît aujourd'hui
que dans la fiche du candidat en Tri. À faire apparaître aussi dans le Tableau de bord (rejoint le
trou d'affichage déjà noté en 908 point 2).

**b) Montrer le coût réel d'une source de vérification payante avant usage.** Le mécanisme « test
réel, prix annoncé avant clic » (`tests_source.py`) existe mais seulement côté ancienne UI
(`api_reglages.py`) : à brancher aussi dans `/suite` (`api_suite.py`) pour les sources utilisées en
vérification.

**c) Permettre de restreindre « qui vérifie quoi » en recherche simple.** `en_amont` (ne vérifier que
les candidats trouvés par telle source) n'existe aujourd'hui que dans le plan avancé
(`suite_plan.py`). À exposer aussi en simple, pour économiser des appels coûteux sur une partie
seulement des résultats.

**d) Faire que la fiabilité apportée par vérifier compte réellement — le point le plus important.**
Constat en lisant le code : une fois qu'une vérification renvoie confirmation ou alerte
(`faits.verifications`), **rien ne l'utilise automatiquement**. Le filtre « Fiabilité minimale »
(`suite_plan.py` ligne 523, commentaire : « la meilleure fiabilité parmi les sources qui ont trouvé
ce nom ») ne regarde que la fiabilité déclarée des sources de RECHERCHE, jamais un résultat de
vérification. Aucun tri, aucun classement ne la lit non plus : cette fiabilité n'existe que si une
personne ouvre la fiche du candidat en Tri. Décidé : la vérification doit avoir un effet réel, pas
seulement un affichage —
  - une confirmation par une source première main peut faire remonter la fiabilité effective du
    candidat au-dessus de celle de sa seule source de recherche ;
  - une alerte doit faire ressortir le candidat (visuellement, ou en le remontant) sans attendre
    qu'une personne l'ouvre.
  Détail d'implémentation (calcul exact de la fiabilité effective, seuils) laissé à momo ; ce qui est
  tranché ici, c'est que le résultat de vérifier doit avoir une conséquence automatique, pas seulement
  apparaître dans une fiche.

**e) Nouveau mécanisme de vérification : confirmation par présence de texte sur une page.**
Les registres fixes (sanctions, registres d'entreprises) ne couvrent que le formel. Pour une entité
informelle, rien ne vérifie rien aujourd'hui. Décidé :

- **Le mécanisme** : au lieu d'interroger un registre, on prend une page web et on regarde si
  **plusieurs champs déjà connus de la fiche** (nom ET ville, ou nom ET numéro — pas le nom seul, trop
  d'homonymes) apparaissent ensemble dans son texte. Trouvés → on extrait l'extrait qui les entoure
  comme preuve citée. Pas trouvés → on passe, aucun verdict. Généraliser avec Scrapling (déjà décidé
  le 08/11, 908 §5.2) plutôt que créer un outil à part.
- **Compter l'indépendance, pas juste « trouvé »** : réutiliser le principe déjà dans le moteur pour
  compter les sources indépendantes qui trouvent un candidat (même logique que `nb_endroits` et que
  les seuils de Fusion, `SEUILS_FUSION`) — une seule page qui matche est un signal faible, plusieurs
  pages de domaines différents sont un signal fort. Le mécanisme rend un nombre de pages confirmantes
  indépendantes, comparé à un seuil, pas un simple binaire.
- **Deux façons de lui fournir une page** : (1) les pages déjà trouvées par les sources de recherche
  pour ce candidat — gratuit, immédiat, aucun appel de plus ; (2) une recherche web dynamique scopée
  au nom exact, via un moteur déjà dans la liste (searxng — self-hébergé, sans quota — ou
  brave/tavily/serper en vérifier), pour aller chercher au-delà de ce qu'on a déjà trouvé.
- **Garde-fou obligatoire, à ne jamais oublier à l'implémentation** : ce signal est **faible**, bien
  plus faible qu'un hit de registre. Il doit être marqué `seconde main`, fiabilité basse, et ne
  **jamais** pouvoir servir de source première main pour le garde-fou de l'IA niveau 4 (908 §13 — un
  nom proposé par l'IA ne sort de sa zone que confirmé par une source première main). Sans ce
  garde-fou explicite dans le code, ce mécanisme recréerait exactement le risque que 908 avait bloqué.
- **Mis de côté pour l'instant, pas prioritaire** : générer un flux RSS éphémère à la volée par
  recherche (réutiliserait `definition_flux`, déjà dans le moteur, avec une URL construite au moment
  de la recherche plutôt que la liste fixe de l'utilisateur) — gain réel limité par rapport à
  simplement interroger searxng/brave en vérifier ; à reprendre seulement si (1) et (2) montrent une
  vraie limite.

## 2 — Enrichir

*(à traiter après le point 1, voir 908 point 13-14 pour le lien avec les niveaux d'IA et l'inventaire)*

## 3 — Évolution future identifiée : tuiles câblables sur 4 faces

Idée de Sednal (09/11/2026), transverse à vérifier ET enrichir. Aujourd'hui, cibler précisément « qui
vérifie/enrichit quoi » n'existe qu'en plan avancé, en calculant les ancêtres du graphe (`en_amont`,
`suite_plan.py`) — pas intuitif. Idée : chaque tuile devient câblable sur **4 faces** — gauche/droite
pour le flux normal (chercher, comme aujourd'hui), haut pour y accrocher un VÉRIFIER, bas pour y
accrocher un ENRICHIR, chacun avec ses propres réglages — applicable soit sur une tuile précise, soit
sur tout le flux.

Identifiée comme une bonne idée, mais c'est une évolution du modèle même du plan (comment un chemin
est validé, comment les ancêtres sont calculés dans `suite_plan.py`), pas un correctif — même famille
que « la recherche avancée n'est traitée qu'après la fin du pavé » (règle de `000-INDEX.md`).
**Décidé : mise en attente, à traiter plus tard, une fois que vérifier et enrichir sont
opérationnels** (correctifs et améliorations des points 1 et 2 ci-dessus livrés) — pas avant.

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
