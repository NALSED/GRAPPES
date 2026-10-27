# La recherche par emoji

Spécification 26 § 4, faite le 27/10/2026. Ce que le programme fait d'un emoji tapé dans la recherche, ce qui a été **mesuré** contre les services réels, et ce qui ne l'a pas été.

## Ce qui se passait avant

`mots_significatifs` n'extrayait jamais l'emoji (le motif exigeait trois caractères de mot) et `nom_normalise` l'effaçait (`[^a-z0-9]`) : un emoji tapé disparaissait avant qu'aucune source ne le voie, et rien ne le disait. C'était aussi un manquement à la règle n° 1 (« un retrait se voit »).

## Les quatre règles de traitement (norme UTS #51, Unicode Emoji)

Un emoji n'est pas un caractère : « ✊🏽 » est un poing et une teinte de peau, « 🏳️‍🌈 » est un drapeau, un sélecteur U+FE0F, un liant U+200D et un arc-en-ciel.

1. **Jamais jeté** : `mots_significatifs("collectif ♻️ Isère")` rend `['collectif', '♻️', 'Isère']`, la séquence entière d'un seul morceau. Un emoji seul est une requête valable. La limite de mots ne les coupe jamais au profit des mots.
2. **À une source, la forme tapée** (U+FE0F compris).
3. **Comparer sur la forme réduite, en interne seulement** : sans U+FE0F ni teinte de peau, séquence ZWJ conservée (`reduit`). « ✊🏽 » et « ✊🏿 » se comparent égaux ; cette forme ne sort jamais vers une source. `nom_normalise` garde l'emoji sous cette forme : « Club ⚽ » et « Club 🏀 » ne sont plus le même nom.
4. **Dans une adresse, encodé** (`%E2%9C%8A`) : le client HTTP des adaptateurs encode tout caractère non ASCII d'une adresse (accents compris).

La reconnaissance (`src/pilote/emoji_texte.py`) n'utilise que la bibliothèque standard, parce que les adaptateurs tournent aussi dans l'interpréteur de grappes. Ses points de code sont **générés** (`outils/generer_emoji.py`, à relancer quand Unicode évolue) depuis le paquet `emoji` ; les tests prennent ce paquet et `regex` (`\X`) comme **oracle** : les 3 963 emoji complètement qualifiés sont reconnus d'un seul tenant. Choix assumé : `©`, `™`, `✓` (texte par défaut, sans U+FE0F) ne sont pas des emoji, pour qu'un nom d'entreprise ne le devienne pas ; `♻` nu non plus, `♻️` oui.

## Qui reçoit l'emoji : `consomme: emoji`, déclaré après mesure

Une recherche plein texte qui découpe en mots perd l'emoji à l'indexation et rend zéro résultat sans le dire. Chaque source ne reçoit donc l'emoji que si sa déclaration porte `emoji` dans `consomme`, **essayé contre le service réel**, avec sa date dans `verifie_le`. Les autres reçoivent la requête sans lui. Si la saisie n'est faite que d'emoji qu'une source ne cherche pas, elle n'est pas appelée (statut « non appelée », ni succès ni panne : le disjoncteur ne la pénalise pas).

Mesures du 27/10/2026 (4 emoji essayés : ♻️, 🏳️‍🌈, ✊🏽, ⚽) :

| Source | Résultat | Déclarée |
|---|---|---|
| **Bluesky** (`searchActors`) | 4 sur 4 : des comptes dont le nom ou la présentation contient l'emoji. Joint à des mots (« collectif ♻️ »), il ne contraint pas | **oui** |
| **Bluesky Jetstream** | filtre fait ici, sur le texte des messages : ♻️ → 5 comptes sur la fenêtre | **oui** |
| Arctic Shift | 0 sur 4 (recherche par préfixe de nom de communauté : un nom n'a pas d'emoji) | non |
| Lemmy | 2 sur 4, incohérent | non |
| Mastodon | 1 sur 4, incohérent | non |
| SepiaSearch | 2 sur 4, incohérent | non |
| Serper, Brave, Apify, Bright Data, moteurs généraux | **non mesuré** (clé ou crédits : pas dépensés sans demande) | non |

`searchPosts` de Bluesky répond 403 sans authentification : la source utilise `searchActors`.

## Ce que l'utilisateur voit

* **Aide** (contrôle n° 6, remarque) : « ta saisie contient un emoji, et aucune source allumée de ce plan ne déclare le chercher ». Elle signale, elle n'éteint ni n'allume rien.
* **Bilan de la recherche sauvegardée** : « emoji non transmis à n sources : … » (journal : `emoji_non_transmis`).

## Limites connues

* Le moteur de collecte de grappes (prises web, Wikidata, SIRENE en ligne) n'a qu'une phrase et aucune de ses prises ne déclare l'emoji : il ne le reçoit pas, et le bilan les compte.
* Le regroupement dur du moteur (`fusion.norm_name`) efface encore l'emoji d'un nom : deux noms qui ne diffèrent que par un emoji y sont un seul nom. Le rapprochement de pilote (Splink) les distingue.
* Une saisie en `♻` nu (sans sélecteur) n'est pas reconnue comme emoji.
