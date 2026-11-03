# 901 — Réponses aux questions ouvertes du moteur (QUESTIONS.md de momo)

Hors du pavé UI. Répond aux points ouverts du `QUESTIONS.md` de momo (dépôt `NALSED/GAPPES-FINAL`) :
Q3, Q10, Q11, Q20, Q21, Q26, Q27. À reporter par momo dans **son propre** `QUESTIONS.md`/`DECISIONS.md`
— Claude ne modifie plus directement ces fichiers dans `GAPPES-FINAL` (ce dépôt est réservé au code de
momo, voir § Règle de dépôts).

## Q3 — Langues des corpus

Réglée : normalisation multilingue reste le défaut. Pas de changement tant qu'aucun cas réel multilingue
ne le justifie.

## Q10 — Client MCP visé et lieu d'exécution

Réglée : le client visé est l'agent Claude (abonnement Pro/Max), sur la **même machine** que grappes —
.115 en production, .250 possible pour test. Client et serveur locaux : stdio/lecture seule confirmés,
pas d'exposition réseau nécessaire.

## Q11 — Scoring par embeddings

Réglée : défaut gardé (non, lexique et recoupement). Un score de similarité par embeddings serait moins
vérifiable à l'œil qu'une correspondance de mots — ça irait contre la priorité fiabilité du projet, et
rien aujourd'hui ne montre que le lexique rate des recoupements. À revoir seulement si un cas réel
le montre.

## Q20 — Garde-fou de la boucle d'apprentissage

Réglée : le garde-fou reste actif par défaut (`apprentissage.exiger_racine_de_confiance: true`), mais
doit rester un **réglage réel**, configurable — jamais figé en dur dans le code.

## Q21 — Personnes physiques : critère de correspondance plutôt qu'exclusion de principe

Affine D32. Exemple de Sednal : une recherche sur le football doit pouvoir ramener le compte Instagram
public de Messi ou Ronaldo — personnes physiques, mais le profil est public, répond directement au critère
de recherche, et ce n'est pas un ciblage par leak ou un autre moyen. L'ancienne règle (« en cas de doute,
une personne » → exclue) perdait ce genre de résultat utile.

**Nouvelle règle, trois cas** pour un compte de réseau social trouvé (personne physique ou pas) :

1. **Matche directement la recherche** (nom, mot-clé, critère explicite) → gardé dans `resultat.csv`,
   personne physique ou pas.
2. **Hors sujet / bruit** (apparaît sans répondre au critère, ex. quelqu'un qui a juste commenté) → exclu,
   comme avant.
3. **Doute** (le programme ne peut pas trancher) → part dans un fichier séparé — proposition de nom
   `resultat_a_trancher.csv`, à confirmer par momo selon ce qui s'intègre le mieux — où Sednal décide
   au cas par cas.

`redact_persons` reste le réglage qui protège contre le ramassage de personnes non visées par la
recherche ; il ne doit plus retirer un résultat qui répond réellement au critère.

**Boucle d'apprentissage** : la décision de Sednal sur un cas du fichier « à trancher » (garder/exclure)
compte comme une ancre de confiance pour l'apprentissage (garde-fou de Q20) — au même titre qu'une entité
confirmée descendant d'une ancre existante.

## Q26 — Plafond de rappel (0 à 17 %) : mode de recherche et extraction d'entités nommées

Mesuré le 2026-10-12 : au plus 17 % de la référence Wikidata existe comme candidat, parce que grappes
compare la **source** (site, compte) à la référence, alors que la référence attend souvent l'**acteur
nommé dans le texte** (ex. une organisation citée dans un article, pas le site qui en parle). Plus de
crawl ou d'autonomie d'apprentissage ne change rien (déjà mesuré, sans effet). Sans extraction de noms
dans les textes lus, le verdict restera « non certifié ».

Sednal autorise cette extraction (méthode hors de la liste de `MISSION.md`, donc décision explicite), en
observant qu'elle n'est utile que pour un usage précis : une recherche qui cible directement des
sites/comptes n'a rien à en extraire.

**Décision** : nouveau réglage **mode de recherche**, fermé à deux valeurs :

* **Trouver des sites/comptes qui correspondent aux critères** — défaut, comportement actuel, aucune
  extraction.
* **Lire le contenu pour en extraire les acteurs** — nouveau, active l'extraction d'entités nommées dans
  les textes lus par les sources de cette recherche ; les entités extraites deviennent candidates pour le
  recoupement, comme les sources le sont aujourd'hui.

L'extraction ne tourne **jamais** en dehors du second mode.

## Q27 — D69 : trois décisions

* **Thésaurus de types** : pas de liste de synonymes inventée — rattachement au code NAF officiel (INSEE)
  ↔ classe, nomenclature déjà existante et autoritaire, cohérent avec « ne rien réinventer ».
* **Amorces par requêtes web** : mesure du mécanisme TREC autorisée (~3 crédits Tavily/sujet) — décision
  d'implémentation seulement après ce chiffrage, pas avant.
* **Nouveau jeu test** : confirmé nécessaire avant toute certification (sinon on certifierait sur le jeu
  qui a servi à ajuster) ; à geler juste avant la prochaine tentative, pas avant si aucune n'est encore
  visée.

## Q28 — Mécanisme d'ancrage d'une décision de Sednal sur un cas « à trancher » (soulevée par momo, 2026-11-03)

En implémentant Q21, momo relève que la boucle « décision de Sednal sur un cas à trancher → ancre de
confiance » n'avait pas de mécanisme d'enregistrement/relecture précisé. Réponse : **réutiliser le
mécanisme d'ancre déjà existant**, rien de nouveau à construire.

`anchors` (champ du YAML de chaque grappe, lu par `config.py: load_grappe`) est déjà exactement ça — une
liste de références que `cycle/learn.py` traite comme racines de confiance, et que l'apprentissage ne
réécrit jamais (« les ancres écrites par Sednal ne sont jamais lues en écriture »).

* **Garder** un cas de `resultat_a_trancher.csv` → sa référence s'ajoute à `anchors:` dans le YAML de la
  grappe concernée, dédoublonné — exactement comme toute autre ancre posée par Sednal à la main.
* **Exclure** → rien à écrire ; la ligne reste hors de `resultat.csv`, aucune ancre créée. Si le besoin de
  ne plus jamais reproposer un cas exclu se confirme plus tard, ce sera mesuré et construit à ce moment-là
  — pas anticipé maintenant.

Ce que momo construit : un petit outil (script ou route) qui lit les décisions marquées dans
`resultat_a_trancher.csv` et les ajoute à la bonne liste `anchors:` — pas de nouveau système de stockage.

## 3.8.09 — Séparer le coût de l'appel IA des crédits (2026-11-03)

Déjà tranché par la spec 3.8.09 : l'appel à l'agent IA (facturé par l'abonnement Pro/Max, pas par appel)
**ne compte jamais** dans le compteur crédits (3.8.08). Ce qui restait ouvert — comment le suivre quand
même — est tranché :

* Un simple **compteur** (« n appels IA ») dans le journal de la recherche, à côté du compteur crédits,
  sans plafond : l'abonnement Pro/Max a déjà ses propres limites, pas la peine d'en ajouter un côté
  grappes.

**Précisé par Sednal (03/11/2026)** : pas la peine d'attendre l'installation sur .115 pour avancer. Momo
continue et termine le câblage réel (`NON_APPLIQUES["ia"]` disparaît) en testant sur **.250**, où l'agent
est déjà installé et connecté (vérifié par le commit `0780fe1`) — ça suffit pour développer et valider le
mécanisme. L'installation sur .115 (la machine de production) reste une tâche de Sednal, mais devient un
déploiement séparé, plus tard, pas un blocage pour momo aujourd'hui.

## Consigne d'interface (mode de recherche, fichier « à trancher »)

Lisibilité d'abord, en suivant la charte déjà en place (`pilote/static/suite/charte/` dans GAPPES-FINAL),
pas une interface improvisée :

* **Jamais de couleur seule** pour porter une information (règle déjà appliquée par le composant Pastille,
  WCAG 1.4.1) : toujours la couleur ET le mot.
* **Vocabulaire fermé**, pas de reformulation libre — les deux valeurs du mode de recherche et les trois
  issues des personnes physiques sont des mots fixes, comme les rôles ou les états de source le sont déjà.
* Réutiliser les jetons de couleur et composants existants (`charte/jetons.css`, `charte/composants/`)
  plutôt qu'en inventer de nouveaux ; si aucun composant existant ne convient, en proposer un nouveau dans
  `charte/composants/` en suivant le même gabarit (README + preview.html) que les composants actuels.

## Ce que momo change

* Reporter chacune des sept clôtures ci-dessus dans **son propre** `QUESTIONS.md`/`DECISIONS.md` (dépôt
  `GAPPES-FINAL`), avec son propre numéro de décision (D82 et suivants, selon ce qui existe déjà chez lui).
* Implémenter Q20, Q21, Q26 (réglage réel + mécanisme) ; Q3/Q10/Q11/Q27 sont des clarifications de défaut
  déjà en place, rien à coder sauf Q27-amorces (mesure TREC autorisée, à chiffrer avant toute décision
  d'implémentation).

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Toute instruction/spec/décision destinée à momo
s'écrit dans `NALSED/GRAPPES` (`specs/`) — jamais directement dans `GAPPES-FINAL`.
