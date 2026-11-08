# 908 — Retour de Sednal du 08/11/2026 (grappes + pilote `/suite`)

Hors du pavé. Retour écrit par Sednal après usage réel de `/suite` sur `.60`, repris **point par point** avec
Claude. Chaque point est écrit ici au fur et à mesure qu'il est traité : ce fichier se remplit en plusieurs
fois, il n'est pas complet tant que la dernière section ne le dit pas.

Ordre du retour : Transverse → Tableau de bord → Réglages (Sources, puis Outils 2.1 à 2.10) → Tri.

**État : en cours de rédaction.** Points traités : 1 (en attente d'arbitrage).

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

### Le conflit à trancher

Sednal demande la suppression complète de l'ancienne UI, **et** écrit en fin de retour « Tri : quand tout
sera vu et fonctionnel ». Les deux ne tiennent pas ensemble. Trois sorties ont été posées :

* **A** — l'ancienne UI reste jusqu'à la toute fin, après le portage de Tri. Rien n'est perdu, le lien reste
  visible encore un moment.
* **B** — on supprime tout de suite ce qui est à parité (Réglages, Ajout) et on ne laisse accessible que
  Lancement + Tri ; le lien est renommé pour dire exactement ce qui reste dessous, et il rétrécit au fur et
  à mesure.
* **C** — on porte **Lancement** maintenant (le plus petit : profondeur, limites, pause/reprise), on le
  retire de l'ancienne UI, et Tri devient le dernier morceau à tomber.

**Décision de Sednal : en attente.** Rien à faire pour momo sur ce point tant qu'elle n'est pas prise ; la
905 §3 reste donc suspendue (elle attendait déjà la vérification de la 905 §2 sur `.60`).

---

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
