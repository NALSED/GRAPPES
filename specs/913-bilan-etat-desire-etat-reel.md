# 913 — Bilan : état désiré, état réel, défauts trouvés (23/11/2026)

**État : N1 à N5 corrigés le 23/11/2026 sur demande de Sednal (D137 à D139 de GAPPES-FINAL) ; G1 non touché ; B1 validé, relevé bloqué dans cette session (D140).** Relecture de `NALSED/GAPPES-FINAL` au commit `380f1a4`
(dernier envoi le 16/11/2026, rien de nouveau depuis), des specs de ce dépôt et des fichiers de suivi
(`FINAL.md`, `ETAT.md`, `QUESTIONS.md`, `DECISIONS.md`, `pilote/QUESTIONS.md`). Aucune ligne de code
modifiée. Les défauts nouveaux N1 à N3 ont été reproduits par un essai ; N4 et N5 sont établis par lecture du code.

## 0 — En une page

* **La construction est presque finie.** Tout ce que `FINAL.md` demande existe : multiprise, amorçage
  depuis une phrase, récupérateur de pages, ingestion, boucle `grappes cycle`, sortie `resultat.csv`.
  Le pavé du 02/11, les specs 901 à 909 et 10 points sur 13 du plan 912 sont codés.
* **La fiabilité n'est toujours pas prouvée.** Aucune mesure depuis celle d'octobre, dont le verdict
  était négatif. Le plan 912 a rendu les résultats honnêtes (« sûr » / « à vérifier »), il ne les a pas
  mesurés. Tant que B1 n'est pas lancé, on ne sait pas si c'est mieux.
* **Cinq défauts nouveaux** trouvés aujourd'hui, dont un qui touche directement la fiabilité : le
  propre flux RSS d'un site peut voter pour ce site et le faire passer « confirmé ».
* **Le point grave n° 1 de la note 911 est toujours ouvert** : la levée automatique de la règle 8
  joue pour tous les comptes. Il n'a pas été touché, par consigne.

## 1 — État désiré

Trois sources, par ordre de priorité :

1. `FINAL.md` : un système ouvert et autonome qui part d'une phrase, sans liste de sites fournie, et
   sort une liste de noms fiable (`resultat.csv`).
2. Les specs validées de ce dépôt (`000-INDEX.md`) : l'application `/suite`, ses sources et ses
   outils, Tri.
3. Ta priorité constante : un résultat sûr et vérifiable avant le volume.

## 2 — État réel, chantier par chantier

| Chantier | Désiré | Réel | Écart |
| :-- | :-- | :-- | :-- |
| Moteur (`FINAL.md` § 3 à § 12) | tout | fait | `autonome: true` livré, `FINAL.md` dit faux par défaut (pilote en a besoin) |
| Pavé du 02/11 (1.1 à 3.9, T1 à T4) | validé | codé par momo | 1.3 « Page Info » jamais rédigée ; 2.1 vide |
| 900 Déménagement de l'outillage | à valider | non tranché | à confirmer par toi |
| 901, 902, 904 Questions et revue | validé | codé | — |
| 903 Cible de recherche | validé | pièce 1/2 faite, pièce 2/2 non commencée | bloque aussi C1 (912) |
| 905 Menus fermés, parité `/suite` | validé | § 1 et § 2 faits | § 3 (retirer l'ancienne interface) : fin de projet, voulu |
| 906 Scrapling, 907 sources | validé | fait | — |
| 908 Retour du 08/11 | validé | fait | — |
| 909 Vérifier et enrichir | § 1 à 3 | faits | 1.2.e et 1.2.f non câblés (raisons tracées) ; volet comparaison des deux interfaces non fait |
| 910 / 911 Points graves | — | G2, G3, G4 corrigés par 912 | **G1 ouvert** (règle 8), **G5 ouvert** (pas de compte) |
| 912 Plan fiabilité | point par point | 10 sur 13 codés | B1 attend ta validation ; C1, C3, C4 non codés |
| Mesure de fiabilité | un chiffre avant/après | **aucun** | le jeu d'octobre est usé, B1 en remplace la référence |
| Tri (charte `/suite`) | après la tuyauterie | non commencé | voulu (décision du 09/11) |
| Recherche avancée (tuiles dupliquées) | après le pavé | non commencé | voulu |

## 3 — Défauts nouveaux trouvés le 23/11

Classés du plus grave au moins grave. Aucun n'est corrigé : ils changent des résultats, la décision te
revient.

### N1 — Un site se confirme lui-même par son propre flux RSS (grave, fiabilité)

`src/grappes/ecosystem/crossref.py`. Le texte d'une page ne peut pas citer son propre site (contrôle
`_same_site`). Un **lien**, lui, n'est écarté que s'il pointe vers exactement la même clé. Or le flux
`rss:zorbel.fr` et le site `web:zorbel.fr` ont deux clés différentes, et chaque article d'un flux
pointe vers son site. Le flux devient donc une voix de plus **et** un écosystème de plus pour son
propre site. Essai, deux sites extérieurs citent `zorbel.fr` :

````text
sans son flux : écosystèmes ('web',)        confirmé : False
avec son flux : écosystèmes ('rss', 'web')  confirmé : True
````

Même effet pour un sous-domaine (`blog.zorbel.fr` qui pointe vers `zorbel.fr`). Le compte d'éditeurs
de A3 (« sûr ») est touché de la même façon. Correctif proposé : écarter aussi les liens dont le
citant est le même éditeur que le cité, avec la règle qui existe déjà pour le texte (`_same_site`).

### N2 — Une ville avec accent est vue « en désaccord » avec elle-même (moyen)

`pilote/src/pilote/rapprochements.py::_norme`. La comparaison met en minuscules mais garde les accents.
Les registres français rendent les villes sans accent (« SAINT-ETIENNE »). Résultat : une vraie
confirmation est rangée en « même nom » (pas de passage en « sûr »), et Tri affiche « désaccord » sur la
même ville.

````text
Saint-Étienne / Saint-Etienne      -> desaccord
Paris / Paris 11e Arrondissement   -> desaccord
````

Correctif proposé : comparer les villes sans accents ni tirets, comme le moteur compare déjà les noms
(`classement/fusion.py::norm_name`). Les arrondissements demandent un choix (les ramener à la ville ?).

### N3 — SIREN et SIRET d'une même entreprise vus « en désaccord » (moyen)

Même fonction. A7 sait qu'un SIRET commence par son SIREN (`cle_numero`) et réunit les deux fiches,
mais la confirmation A2 compare les numéros tels quels :

````text
41234567800012 / 412345678 -> desaccord
````

Correctif proposé : comparer les numéros avec `cle_numero`, déjà écrit.

### N4 — Le niveau n'est pas recalculé après une réunion de fiches (faible)

`rapprochements.py::_recompter`. Quand deux fiches sont réunies (d'office par A7 ou par toi dans Tri),
le nombre d'endroits est recompté, pas le niveau. Deux fiches « à vérifier », trouvées chacune à un
endroit, deviennent une fiche à deux endroits qui reste « à vérifier ». Un filtre sur le niveau et le
nombre affiché se contredisent.

### N5 — Le moteur et pilote ne comptent pas les endroits de la même façon (faible, choix)

Le moteur (`classement/production.py::niveau_de`) dit que le site de l'entité n'est pas un endroit
indépendant. Pilote (`pont/faits.py::preuves`) le compte comme un endroit. Dans pilote, un site trouvé
par la recherche plus **une** mention ailleurs suffit à être « sûr » ; dans le moteur, il en faut deux.
À trancher : quelle règle garder pour les deux ?

### À savoir, sans être un défaut de code

« Sûr » veut dire « cet organisme existe » (registre) ou « il est nommé à deux endroits ». Ça ne veut
pas dire « il fait partie du sujet ». Un registre interrogé avec les mots du sujet ramène aussi des
organismes sans rapport (constat de la revue 902) : ils sortent « sûrs ». C'est la définition écrite
dans 912 A3, appliquée fidèlement.

## 4 — Défauts connus, toujours ouverts

| Défaut | Où c'est écrit | Gravité |
| :-- | :-- | :-- |
| G1 : levée automatique de la règle 8 pour tous les comptes (`p_min: 0.0`, vérifié le 23/11) | 911 | grave, vie privée |
| Le serveur MCP permet de savoir si une personne masquée est dans la base, en cherchant son identifiant | D115 | moyen, vie privée |
| G5 : pas de compte, quiconque atteint le port peut lancer un programme | 911 | grave si exposé |
| Deux recherches en même temps peuvent dépenser le même reste de budget | D116 | moyen |
| Un dossier d'export commun écrase `resultat.csv` d'une recherche à l'autre | D116 | moyen |
| `grappes export` appelle Wikidata et SIRENE sans vérifier `autonome` ni STOP | D115 | faible, dormant |
| `min_ecosystemes` accepte 1, `FINAL.md` exige 2 | D115 | faible |
| Sans la bibliothèque de lecture des textes, toute recherche en mode extraction échoue (message clair depuis D132) | D117 | faible |
| Neuf sources « enrichir » sans effet ; outils Boucle et Compteur budget partiels ; Traduction sans effet sur le moteur | `pilote/QUESTIONS.md`, 911 | faible, affiché à l'écran |
| Source ajoutée depuis `/suite` en Vérifier sans clé de vérification : acceptée puis écartée | Q-D117 | faible |

## 5 — Tests au 23/11

* Moteur : 668 réussis, 4 échecs d'environnement (`followthemoney` absent ici). Identique au 15/11.
* Pilote (hors réseau) : 738 réussis, 2 échecs d'environnement (`test_f14_sortie` en root, `test_f09_presse`
  sans `transformers`). Identique au 16/11, plus les 6 essais du flux RSS.
* Aucun test ne couvrait N1 à N5 : c'est pour ça qu'ils sont passés.

## 6 — Ce qui t'attend

1. **Dire si on corrige N1 à N4.** N1 d'abord : c'est de la fausse confirmation.
2. **G1** : la levée automatique de la règle 8. Proposition de 911 inchangée : la couper tant
   qu'aucun seuil mesuré n'existe, garder la levée manuelle.
3. **B1** : valider les 25 sujets et 200 crédits Tavily au plus, puis lancer depuis momo (la clé est
   là-bas). Sans ça, aucun chiffre de fiabilité.
4. **N5** : quelle règle pour « deux endroits » ?
5. Les questions déjà posées : `QUESTIONS.md` (Q-A5, Q-A6, Q-B3, Q-C1, Q-C3, Q-C4, Q-D117, Q-SECU).
6. **900** : le déménagement de l'outillage est toujours « à valider ».

## 7 — Ordre proposé (rien n'est décidé)

| Rang | Quoi | Change les résultats ? |
| :-- | :-- | :-- |
| 1 | N1 | oui : moins de « confirmés », mais justes |
| 2 | N2, N3 | oui : plus de vraies confirmations |
| 3 | G1 | non (affichage des personnes) |
| 4 | B1, puis la mesure | non, elle donne enfin le chiffre |
| 5 | N4, N5, puis la fiabilité sans registre (site qui se déclare lui-même, copies) | oui |
| 6 | Le reste du § 4, puis Tri | selon le point |
