# 906 — Deux outils externes à intégrer : Scrapling et api-anything

Hors du pavé. Demande de Sednal le 08/11/2026 : évaluer trois outils trouvés sur GitHub pour grappes
(`d4vinci/Scrapling`, `blacklanternsecurity/bbot`, `goodnight000/api-anything`). Décision : **bbot écarté**
(scanner de reconnaissance sécurité — sous-domaines, surface d'attaque, bug bounty — hors sujet pour
trouver des organisations/personnes, contredit la décision du 19/10/2026 d'écarter le registre domaine/IP
de cybersécurité ; licence AGPL-3.0 plus contraignante que le MIT de grappes). **Scrapling et api-anything
retenus**, à intégrer. Principe « ne rien réinventer » : utiliser ces projets tels quels (dépendance, pas de
réimplémentation de leur logique interne).

## 1 — Scrapling (scraping auto-hébergé, licence BSD-3)

Framework Python de scraping : requêtes HTTP qui imitent une empreinte TLS de navigateur, navigateur furtif
(Playwright/Chromium) pour le JS et les protections Cloudflare (Turnstile, Interstitial), sessions avec
cookies persistants, rotation de proxy, export JSON/JSONL/CSV/XML.

C'est la « solution maison » gratuite dont la construction avait été mise de côté le 13/10/2026 (décision :
d'abord tester les prestataires payants éprouvés — Apify, Bright Data, ZenRows —, la solution maison
venant après). Scrapling n'est pas une solution maison à construire : c'est un outil déjà écrit, documenté,
éprouvé — donc rien n'empêche de le brancher maintenant plutôt que d'attendre.

**Où le brancher** : comme nouveau membre de la famille **prestataire de collecte** (`config/sources/`,
même famille qu'Apify/Bright Data/ZenRows), mais gratuit et auto-hébergé — pas de clé ni de coût, donc pas
soumis au plafond de budget. Avertissement à l'activation identique aux autres prestataires de collecte
(compte/empreinte dédiés recommandés), et mêmes 4 niveaux de test obligatoires avant activation
(configuration, connexion, mini-requête factice, respect de la convention de sortie) que toute source.

## 2 — api-anything (adaptateur site-sans-API → MCP, licence MIT)

Apprend les requêtes qu'envoie le frontend d'un site (sur deux exemples, sans IA dans cette étape), puis les
rejoue en HTTP simple ; s'expose en serveur MCP local, utilisable directement par un agent. Catalogue partagé
de sites déjà appris (114 sites, 323 opérations en lecture) réutilisable tel quel. Écritures désactivées par
défaut, secrets gardés en local, option `--local-only` pour ne rien partager.

**Où le brancher** : c'est un cas d'usage direct du type de source **serveur MCP** que le spec 905 §2 demande
déjà de porter dans `/suite` (aujourd'hui seules les sources API sont ajoutables). Une fois ce type porté,
ajouter une source « serveur MCP » pointant vers une instance locale d'api-anything doit fonctionner sans
code spécifique à api-anything — c'est un serveur MCP comme un autre pour pilote. Pas de travail séparé :
à vérifier une fois 905 §2 fait, en ajoutant api-anything comme premier cas réel de test du type MCP.

## Ordre

Scrapling : indépendant, peut être ajouté dès maintenant (famille prestataire de collecte déjà existante).
api-anything : attend 905 §2 (port du type de source « serveur MCP ») — sert alors de premier test réel de
ce type, pas une fonctionnalité à part.

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
