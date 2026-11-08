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
| **1.2** | Réglages doit passer avant Recherche | `1.2-ordre-des-onglets.md` | **validée** par Sednal, prête pour momo |
| **1.3** | Page Info : tout ce qui est paramétrable, en clair | `1.3-page-info.md` | à traiter — reporté à une session dédiée |
| **2.1** | Page Recherche | — | **vide dans le pavé**, Sednal n'a rien écrit |
| **3.1 / 3.2** | Plus de sources qu'avant ? Pourquoi la plupart sont éteintes | `3.1-3.2-sources-eteintes.md` | spec écrite (réponse factuelle, rien à coder) |
| **3.3** | Bouton allumer/éteindre + boutons en pictogramme seul | `3.3-boutons-de-ligne-source.md` | **validée** par Sednal, prête pour momo |
| **3.4** | Élargir le panneau de modification en tirant son bord | `3.4-panneau-elargissable.md` | **validée** par Sednal, prête pour momo |
| **3.5** | La page source paraît bien | — | **rien à faire** |
| **3.6** | Changer la clé d'API ou tout prérequis extérieur d'une source | `3.6-changer-la-cle-d-une-source.md` | **validée** par Sednal, prête pour momo |
| **3.7** | Les onglets de modification des outils ne sont pas intuitifs | `3.7-fiche-outil-navigation.md` | **validée** par Sednal, prête pour momo |
| **3.8** | Les choix ne doivent pas être libres — outil par outil | voir les dix documents `3.8-*` ci-dessous | **les dix tuiles validées**, prêtes pour momo |
| **3.9** | L'en-tête change dynamiquement au clic sur un modèle | `T1-modele-et-entete.md` | **validée** par Sednal, prête pour momo |

### Les dix outils (point 3.8)

| Outil | Document | État |
| :-- | :-- | :-- |
| 1 — Format JSON / CSV | `3.8.01-format-json-csv.md` | **validée** |
| 2 — Traduction | `3.8.02-traduction.md` | **validée** |
| 3 — Condition « si » | `3.8.03-condition-si.md` | **validée** |
| 4 — Boucle | `3.8.04-boucle.md` | **validée** |
| 5 — Fusion / doublons | `3.8.05-fusion-doublons.md` | **validée** |
| 6 — Filtre | `3.8.06-filtre.md` | **validée** |
| 7 — Attente (quota) | `3.8.07-attente-quota.md` | **validée** |
| 8 — Compteur budget | `3.8.08-compteur-budget.md` | **validée** |
| 9 — Assistant IA | `3.8.09-assistant-ia.md` | **validée** |
| 10 — RSSHub | `3.8.10-rsshub.md` | **validée** |

### Les quatre remarques transverses aux dix outils

Sednal les a écrites dix fois, une par outil. Elles sont spécifiées une seule fois ici.

| Remarque de Sednal | Document | État |
| :-- | :-- | :-- |
| « Modèle => les autres modèles ne doivent pas apparaître, uniquement celui actuellement utilisé ou si un autre sauvegardé » + point 3.9 | `T1-modele-et-entete.md` | **validée** |
| « Ce qu'il fait => OK SI c'est seulement une description, si c'est le cas changer le titre avec Description » | `T2-description.md` | **validée** |
| « Rôles ET Effet => dans le Tableau de bord pas clair du tout » | traité dans `1.1-tableau-de-bord.md` §5 et §6 | **validée** (1.1 validée) |
| « Clé d'API => Pertinent ??? » | `T4-cle-api-des-outils.md` | **validée** |

## Hors du pavé — infrastructure

| Sujet | Document | État |
| :-- | :-- | :-- |
| Déménager l'outillage d'installation vers GAPPES-FINAL, pour que .115 tourne depuis le dépôt de momo | `900-demenagement-du-code.md` | à valider — doit se faire **avant** que GRAPPES soit vidé de `grappes/` et `pilote/` |
| Réponses aux questions ouvertes du moteur (`QUESTIONS.md` de momo) : Q3, Q10, Q11, Q20, Q21, Q26, Q27, Q28 | `901-questions-moteur-2026-11-03.md` | **codée et poussée** par momo |
| Revue complète et test en profondeur (tout le pavé + 901) | `902-revue-complete-2026-11-03.md` | **close** — Q29-Q34 toutes répondues (voir 904), rapport reçu |
| Cible de recherche (« Ce que je recherche »), mécanisme prioritaire issu de Q26/Q30 | `903-cible-de-recherche.md` | **validée** par Sednal, prête pour momo |
| Réponses Q29-Q34 (suite de la revue 902) | `904-questions-revue-902-2026-11-03.md` | **validée** par Sednal, prête pour momo |
| Menus fermés de `ficheOutil()` restés en texte libre, parité `/suite` pour l'ajout de source (5 types manquants), puis suppression de l'ancienne UI | `905-menus-fermes-et-ancienne-ui.md` | prête pour momo — à confirmer par Sednal |
| Intégration de Scrapling (scraping auto-hébergé) et api-anything (adaptateur site→MCP) ; bbot écarté | `906-scrapling-et-api-anything.md` | prête pour momo |
| Trois sources trouvées dans awesome-public-datasets : Company Registry Atlas (catalogue de bases par pays), UN Civil Society Database, Humanitarian Data Exchange | `907-sources-awesome-public-datasets.md` | prête pour momo |
| Retour de Sednal du 08/11 repris point par point (transverse, tableau de bord, réglages sources et outils, tri) | `908-retour-sednal-08-11.md` | **en cours de rédaction** — ne pas commencer avant qu'elle soit déclarée complète |

## Après le pavé

| Sujet | État |
| :-- | :-- |
| Recherche avancée : les tuiles doivent pouvoir être dupliquées avec leur préréglage | en attente, après le pavé |
