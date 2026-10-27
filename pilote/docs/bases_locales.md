# Bases locales : brancher une base téléchargée comme une API

Document 22 de la suite. Une source de type `fichier_local` lit une copie locale (SQLite indexée) au lieu d'appeler le réseau : **pas de quota, pas de jetons, pas d'appel croisé**. Elle apparaît dans Réglages comme les autres sources, avec sa fiabilité (A–F), sa langue et son rôle, et affiche « illimité » à la colonne Quota.

## Ajouter une base

1. Déclarer la source dans `config/sources/<id>.yaml` : `famille: fichier`, `mode: {en_ligne: false, local: true}`, `moteur: {adaptateur: fichier_local, parametres: {base: <nom>, installation: {...}}}`.
2. `installation` dit où télécharger (`telechargements` : `url` + `fichier`, ou une requête `sparql` paginée) et comment lire le fichier (`import`).
3. `.venv/bin/python outils/importer_base_locale.py <id>` télécharge (reprise possible), verse en base, enregistre `donnees/bases_locales.json` et supprime l'archive (sauf `--garder`).

Formats lus : CSV, TSV, JSONL, GeoJSON, SQLite déjà constitué ; en clair ou dans un zip. `import` accepte : `colonnes` (nom, alias, ville, numero, pays, genre, site, themes, detail ; « a|b » = la première colonne non vide ; `{premier: [...], motif: regex}`), `defauts`, `garder` / `exclure` (colonne → expression régulière), `jointures` (compléter une colonne depuis un second fichier), `poids` (classer les homonymes), `separateur_alias`.

## Noms partagés et ENRICHIR

* **Désambiguïser** : la recherche accepte un lieu (ville, département ou code postal) ; sans lieu, une source qui voit plus de trois entités de même nom le dit dans chaque résultat. SIRENE porte le code postal du siège et le code d'activité pour cela.
* **ENRICHIR** : une copie locale peut aussi enrichir une fiche déjà trouvée (`enrichit_par: ville | nom`, `classes`) : elle ajoute, à côté de la fiche et avec sa source, par exemple les coordonnées de sa ville (GeoNames).

## Règles

* Une base locale apporte des **données**, jamais un juge : le rapprochement reste dans Fusion/doublons.
* La fiabilité se note sur l'origine, pas sur le moyen d'accès (SIRENE et RNA : A ; OpenSanctions : B, agrégateur ; GeoNames : B ; Wikidata : C).
* **Personnes morales seulement** (règle 8) : le filtre est posé À L'IMPORT, par classe (SIRENE : catégories juridiques « 1… » = entrepreneurs individuels, et unités non diffusibles ; OpenSanctions : schémas Organization / Company / PublicBody ; Wikidata : classes d'organisation ; RNA : jamais les colonnes de dirigeants).
* Une source en copie locale n'est **pas comptée dans la limite d'appels** : la vérification contre OpenSanctions local couvre tous les noms d'une recherche. BODACC reste une API : « X sur Y noms vérifiés » reste affiché pour elle.
* Une copie absente est dite (« non installée sur cette machine »), la source reste « à vérifier ».
* Les mentions obligatoires (`attribution`) vont au `SOURCES.txt` de la recherche, comme pour GDELT.

## Installé le 27/10/2026

| Source | Contenu | Lignes | Sur disque |
| :-- | :-- | --: | --: |
| `sirene-local` | unités légales (hors personnes physiques), ville du siège | 13,1 M | ≈ 2,8 Go |
| `rna-local` | associations (fichiers import et Waldec) | 3,5 M | ≈ 1,9 Go |
| `opensanctions-local` | cibles de type organisation | 72 189 | ≈ 0,06 Go |
| `wikidata-fr` | organisations de France (pays, siège ou SIREN) | 592 508 | ≈ 0,19 Go |
| `geonames-fr` | lieux de France | 174 784 | < 0,1 Go |
| `geoboundaries-fr` | régions | 13 | < 0,01 Go |
| `gdelt-local` | organisations citées dans la presse française des 90 derniers jours | voir ci-dessous | ≈ 1 Go |

Non fait : le géocodeur OSM France complet (cadrage à part, document 22).

## GDELT : fenêtre de 90 jours, France

`.venv/bin/python outils/gdelt_local.py` télécharge les fichiers GKG de 15 minutes de la fenêtre (presse en anglais et presse traduite, où se trouve le français), garde les articles de sites en « .fr » ou en français, et verse UNE ligne par organisation citée (jamais les personnes). Il est reprenable, supprime ce qui sort de la fenêtre et se relance pour mettre à jour. 90 jours = 8 640 quarts d'heure, ≈ 1 h de téléchargement ici. Les fichiers des trois dernières heures arrivent en retard chez GDELT : ils sont repris à la fois suivante.

## Traduction : LibreTranslate auto-hébergé

Voir `outils/libretranslate/LISEZMOI.md`. Local seulement (127.0.0.1:5000), modèles fr, es, de, it, ar, ru, zh ↔ en, réglage `suite.traduction_url` de `config/pilote.yaml`. Une source en copie locale (adaptateur) reçoit la requête traduite ; une source « prise » de grappes (Wikipédia, Wikidata…) ne le peut pas, le plan le dit.
