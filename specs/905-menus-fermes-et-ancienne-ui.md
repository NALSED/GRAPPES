# 905 — Menus fermés dans la fiche outil, parité `/suite`, puis suppression de l'ancienne UI

Hors du pavé. Deux défauts trouvés le 08/11/2026 en relisant le code depuis Réglages > Outils sur `/suite`
(.60), plus la condition pour supprimer l'ancienne interface (`/`) que Sednal demande.

## 1 — `ficheOutil()` : menus encore libres (régression de câblage, pas de spec)

`pilote/static/suite/js/reglages.js`, fonction `ficheOutil()` (ouverte par **Modifier** sur n'importe quel
outil dans Réglages > Outils, y compris les 10 outils livrés) : chaque option du modèle est affichée en
champ texte libre —

```js
const reconstruireOptions = () => { champsOptions = val.options.map(([lib, v]) => champ({ libelle: lib, valeur: v })); };
```

Les vocabulaires fermés (séparateur CSV, comparateurs ET/OU, « Quand le quota est atteint », Opération/
Effort/Marquer de l'IA, etc.) **ont bien été câblés**, mais seulement dans l'éditeur de tuile posée dans un
plan (`pilote/static/suite/js/plan.js`, `RENDUS_OPTIONS` + les fonctions `rendreOptions*`) — jamais dans
cette fiche de réglage par défaut de l'outil.

**À corriger** : `ficheOutil()` doit utiliser les **mêmes** rendus de champs que `plan.js` pour les mêmes
genres d'outil (format, traduction, si/filtre, boucle, attente, budget, ia — rsshub n'a qu'un champ libre,
l'adresse, donc rien à fermer). Exporter les fonctions `rendreOptions*` et le registre `RENDUS_OPTIONS` de
`plan.js` (ou les déplacer dans un module commun, ex. `options_outils.js`, importé par les deux), pour que
les deux écrans restent la même source de vérité et ne divergent plus jamais. Ne pas dupliquer les listes
fermées (`COMPARATEURS`, `CHOIX_ATTENTE`, `EFFORTS_IA`, etc.) : un seul endroit les déclare.

## 2 — Parité `/suite` pour l'ajout de source (condition à la suppression de l'ancienne UI)

Sednal veut que l'ancienne interface (`/`, onglets Réglages/Ajout/Recherches/Tri) disparaisse
complètement, et que `/suite` devienne la seule UI. Aujourd'hui ce n'est pas possible sans perte de
fonctionnalité :

`pilote/static/suite/js/reglages.js`, écran d'ajout de source, le dit explicitement à l'écran : *« Une
source de type API : le service est interrogé en GET. Les autres types (serveur MCP, fichier, base,
programme local, flux RSS) s'ajoutent dans l'ancienne page Ajout. »* Et côté moteur, `suite.ajouter_source()`
n'appelle que `suite_reel.ajouter_api()` — rien d'équivalent pour les cinq autres types.

**À porter dans `/suite` avant toute suppression** (réutiliser les fonctions déjà écrites pour l'ancienne
page, ne rien réécrire depuis zéro) :

* Backend (`pilote/src/pilote/suite.py`, `suite_reel.py`) : une fonction `ajouter_<type>` par type manquant
  (mcp, fichier, base SQLite, base extérieure PostgreSQL/MySQL, programme/script local, flux RSS/OPML),
  construite sur le même modèle qu'`ajouter_api` — en s'appuyant sur ce qui existe déjà dans
  `sources_ajout.py` et `ajout.py` (l'ancienne page), pas une réimplémentation.
* Frontend (`pilote/static/suite/js/reglages.js`) : les formulaires manquants pour ces types, avec les
  composants déjà en place (`champ`, `groupePuces`, etc.), sur le modèle de `ajout.js`/`ajout_types.js`
  (l'ancienne page) pour les champs à reprendre.
* Chaque type porté est vérifié par Sednal sur .60 avant de passer au suivant (test réel d'ajout d'une
  source de ce type depuis `/suite`), pour ne rien casser d'un coup sur un système qu'il utilise déjà.

## 3 — Suppression de l'ancienne UI — **revu le 09/11/2026, ne plus suivre tel quel**

> **Décision de Sednal (09/11/2026) : on ne supprime rien.** On adapte l'ancienne UI à la nouvelle
> (câblage, fonctionnalités) au fur et à mesure, et la suppression n'a lieu **qu'à la toute fin du
> projet**, pas dès que le point 2 et le portage de Tri/Lancement sont finis comme prévu ici à
> l'origine. Le texte ci-dessous garde la liste technique de ce qu'il faudra retirer le jour venu,
> mais sa condition de déclenchement (« une fois le point 2 complet ») ne s'applique plus — voir 908
> point 1 et `000-INDEX.md` pour l'état à jour de cette décision.

Une fois le point 2 complet et vérifié (tous les types de source ajoutables depuis `/suite`), **et une
fois le reste du projet terminé** (plus seulement Tri/Lancement portés) :

* Retirer la route `/` (classique) de `pilote/src/pilote/app.py`, et les fichiers statiques qui ne servent
  plus qu'à elle (`pilote.html` racine, `reglages.js`, `ajout.js`, `ajout_types.js`, `lancement.js`,
  `presse.js`, `tri.js`, `assistant.js` à la racine de `static/` — à vérifier un par un qu'aucun n'est
  encore importé par `/suite`).
* Retirer le lien « Ancienne interface (Lancement, Tri) » visible dans `/suite`.
* `/suite` devient la seule UI de référence du projet — décision déjà actée le 02/11/2026, ce point la
  termine enfin.

## Ordre

1 (rapide, sans risque) → 2 (par type, vérifié un par un par Sednal) → **adapter** l'ancienne UI au fur
et à mesure du reste du projet → 3 (seulement une fois **tout le projet** terminé, pas seulement 2).
Ne pas supprimer l'ancienne UI avant la fin du projet : elle reste utilisable et à jour en parallèle de
`/suite`, pas un palier intermédiaire qu'on retire dès que `/suite` rattrape son retard.

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
