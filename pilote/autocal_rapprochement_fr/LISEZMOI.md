# Jeu de cas difficiles du rapprochement français

Jeu **séparé** de FEBRL (anglophone, synthétique) et de `autocal/jeux.json` de grappes, qui reste intouché. Il est **répétable à volonté** : on le rejoue après chaque réglage de Fusion/doublons (document 20 de la suite).

Une ligne de `cas.jsonl` = une paire de fiches (`a`, `b`), le verdict correct (`meme` ou `differentes`) et une courte raison.

Mesure :

````
.venv/bin/python outils/mesurer_rapprochement_fr.py
````

Règle : tout faux positif ou faux négatif trouvé en usage réel (sessions de test ou usage normal) **rejoint ce jeu** au lieu d'être traité isolément. On n'ajuste jamais un seuil sur un seul exemple.

## Format d'une fiche et classes de cas

Une fiche porte `{nom, ville, numero}` et, en option, **`alias`** : la liste des autres noms que les sources déclarent pour cette entité (sigle, acronyme, ancien nom). Absent ou vide, il se lit comme `[]` : les anciens cas restent valides. L'outil de mesure passe les alias au rapprochement comme une source les lui passerait.

| Classe | Cas |
| :-- | :-- |
| « même », variantes typographiques | 11 |
| « même », sémantique | 1 |
| « même », **sigle contre nom développé** (document 25) | 6 |
| « différentes », relation mère-fille | 17 |
| « différentes », **sigle qui est le nom d'un tiers** (CEA / société « CEA ») | 1 |
| « différentes », **homonymes exacts départagés par le numéro** | 2 |

**Ne jamais verser un cas indécidable** : deux fiches « École normale supérieure », toutes deux à Paris, sans numéro, ne se départagent par aucune information présente. Les cas d'homonymes portent donc leur numéro officiel exprès ; une paire indécidable est « proposée au Tri avec sa raison », ni « même » ni « différentes ».

Les 6 cas de sigles passent **grâce aux alias** (un registre déclare que « CEA » est un nom du Commissariat), jamais en baissant le seuil. Le cas `cea-contre-societe-cea` est celui à ne jamais perdre : un alias est une preuve, pas une identité.
