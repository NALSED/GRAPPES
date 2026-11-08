# 908 — Retour de Sednal du 08/11/2026 (grappes + pilote `/suite`)

Hors du pavé. Retour écrit par Sednal après usage réel de `/suite` sur `.60`, repris **point par point** avec
Claude. Chaque point est écrit ici au fur et à mesure qu'il est traité : ce fichier se remplit en plusieurs
fois, il n'est pas complet tant que la dernière section ne le dit pas.

Ordre du retour : Transverse → Tableau de bord → Réglages (Sources, puis Outils 2.1 à 2.10) → Tri.

**État : en cours de rédaction.** Points traités : 1 (tranché).

---

## 1 — Transverse : faire disparaître complètement l'ancienne UI

Demande de Sednal : `/suite` est la charte, l'ancienne UI (`/`) doit disparaître entièrement, câblage adapté
si besoin.

### Constat (vérifié dans le code le 08/11/2026)

La parité **pour l'ajout de source** est faite (905 §2 : les 6 types, plus les flux RSS sur une fiche à
part). Ce n'est pas elle qui bloque. Ce qui bloque, ce sont **deux pages de l'ancienne UI que `/suite` ne
remplace pas encore** :

| | Ancienne UI | `/suite` |
|---|---|---|
| **Tri** | `static/tri.js`, 585 lignes — paquets, 5 vues, classements, motifs de rejet, décisions annulables, export, liste virtuelle | `static/suite/js/tri.js`, **59 lignes** — seulement les rapprochements Splink à confirmer ou séparer |
| **Lancement** | `static/lancement.js`, 229 lignes — profondeur, limites (temps, appels), **pause et reprise** d'une recherche en cours, sources mises en pause avec leur raison | `static/suite/js/recherche.js`, 204 lignes — **aucun de ces réglages** : ni profondeur, ni limites, ni pause/reprise |

C'est exactement ce que le lien lui-même annonce : « Ancienne interface (**Lancement, Tri**) ». Supprimer `/`
aujourd'hui ferait perdre le seul Tri complet qui existe, et la pause/reprise d'une recherche en cours.

### Décision de Sednal (08/11/2026)

**La nouvelle UI reprend les fonctionnalités de l'ancienne, et l'ancienne ne disparaît qu'une fois tout
porté.** Pas de suppression partielle, pas d'attente passive : on porte, puis on supprime.

Ordre de travail qui en découle :

1. **Porter les réglages de Lancement dans `/suite`** (page Recherche) : profondeur, limites de temps et
   d'appels, **pause et reprise** d'une recherche en cours, affichage des sources mises en pause avec leur
   raison. Reprendre ce qui est déjà écrit dans `static/lancement.js` et les routes `/api/recherches/
   <id>/pause` et `/reprise` qui existent déjà — ne rien réécrire depuis zéro.
2. **Tri** : **adapter** l'ancien Tri (`static/tri.js`, 585 lignes) à la charte de `/suite`, pas le
   réécrire. Les fonctionnalités à garder, à changer ou à abandonner se discutent avec Sednal **avant** que
   momo commence — ce point sera traité dans la section Tri de cette même spec.
3. **Alors seulement**, supprimer l'ancienne UI entièrement : route `/`, fichiers statiques devenus
   inutiles, et le lien « Ancienne interface (Lancement, Tri) » dans `/suite`. C'est la 905 §3, qui reste
   suspendue jusque-là.

La vérification des 6 types d'ajout de source sur `.60` (905 §2) reste à faire par Sednal, en parallèle.

---

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
