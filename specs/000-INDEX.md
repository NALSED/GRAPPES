# Index des specs — retours de Sednal du 02/11/2026

Un document par spec. Chaque numéro reprend **exactement** la numérotation du pavé de retours de
Sednal, pour qu'aucun point ne se perde. Les documents `T*` traitent les remarques qui reviennent à
l'identique sur les dix outils : elles sont spécifiées **une fois**, pas dix.

## Règle de travail

* On avance **point par point, dans l'ordre**. Un point non réglé bloque la suite.
* Sednal décide, Claude rédige la spec, **momo écrit le code** sur `.250` et pousse sur
  `NALSED/GAPPES-FINAL`. Sednal regarde le résultat depuis `.115`.
* Un document passe à l'état **à implémenter** seulement quand Sednal l'a validé. Avant, c'est une
  note de travail : momo n'y touche pas.
* La recherche avancée (duplication des tuiles avec leur préréglage) n'est traitée **qu'après** la fin
  de ce pavé.

## État des points

| Point | Sujet | Document | État |
| :-- | :-- | :-- | :-- |
| **1.1** | Pourquoi le Tableau de bord n'est pas construit | `1.1-tableau-de-bord.md` | **validée** par Sednal, prête pour momo |
| **1.2** | Réglages doit passer avant Recherche | `1.2-ordre-des-onglets.md` | décision prise, spec à valider |
| **1.3** | Page Info : tout ce qui est paramétrable, en clair | `1.3-page-info.md` | à traiter |
| **2.1** | Page Recherche | — | **vide dans le pavé**, Sednal n'a rien écrit |
| **3.1** | Plus de sources qu'avant ? | `3.1-nombre-de-sources.md` | à traiter |
| **3.2** | Pourquoi la plupart sont éteintes | `3.2-sources-eteintes.md` | à traiter |
| **3.3** | Bouton allumer/éteindre + boutons en pictogramme seul | `3.3-boutons-de-ligne-source.md` | à traiter |
| **3.4** | Élargir le panneau de modification en tirant son bord | `3.4-panneau-elargissable.md` | à traiter |
| **3.5** | La page source paraît bien | — | **rien à faire** |
| **3.6** | Changer la clé d'API ou tout prérequis extérieur d'une source | `3.6-changer-la-cle-d-une-source.md` | à traiter |
| **3.7** | Les onglets de modification des outils ne sont pas intuitifs | `3.7-fiche-outil-navigation.md` | à traiter |
| **3.8** | Les choix ne doivent pas être libres — outil par outil | voir les dix documents `3.8-*` | à traiter |
| **3.9** | L'en-tête change dynamiquement au clic sur un modèle | `T1-modele-et-entete.md` | à traiter |

### Les dix outils (point 3.8)

| Outil | Document | État |
| :-- | :-- | :-- |
| 1 — Format JSON / CSV | `3.8.01-format-json-csv.md` | spec écrite, à valider |
| 2 — Traduction | `3.8.02-traduction.md` | à traiter |
| 3 — Condition « si » | `3.8.03-condition-si.md` | à traiter |
| 4 — Boucle | `3.8.04-boucle.md` | à traiter |
| 5 — Fusion / doublons | `3.8.05-fusion-doublons.md` | spec écrite, à valider |
| 6 — Filtre | `3.8.06-filtre.md` | à traiter |
| 7 — Attente (quota) | `3.8.07-attente-quota.md` | à traiter |
| 8 — Compteur budget | `3.8.08-compteur-budget.md` | à traiter |
| 9 — Assistant IA | `3.8.09-assistant-ia.md` | à traiter |
| 10 — RSSHub | `3.8.10-rsshub.md` | à traiter |

### Les quatre remarques transverses aux dix outils

Sednal les a écrites dix fois, une par outil. Elles sont spécifiées une seule fois ici.

| Remarque de Sednal | Document | État |
| :-- | :-- | :-- |
| « Modèle => les autres modèles ne doivent pas apparaître, uniquement celui actuellement utilisé ou si un autre sauvegardé » + point 3.9 | `T1-modele-et-entete.md` | à traiter |
| « Ce qu'il fait => OK SI c'est seulement une description, si c'est le cas changer le titre avec Description » | `T2-description.md` | à traiter |
| « Rôles ET Effet => dans le Tableau de bord pas clair du tout » | traité dans `1.1-tableau-de-bord.md` §5 et §6 | dépend de 1.1 |
| « Clé d'API => Pertinent ??? » | `T4-cle-api-des-outils.md` | à traiter |

## Hors du pavé — infrastructure

| Sujet | Document | État |
| :-- | :-- | :-- |
| Déménager l'outillage d'installation vers GAPPES-FINAL, pour que .115 tourne depuis le dépôt de momo | `900-demenagement-du-code.md` | à valider — doit se faire **avant** que GRAPPES soit vidé de `grappes/` et `pilote/` |

## Après le pavé

| Sujet | État |
| :-- | :-- |
| Recherche avancée : les tuiles doivent pouvoir être dupliquées avec leur préréglage | en attente, après le pavé |
