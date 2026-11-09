# Note pour momo — où est quoi

Mise à jour le 02/11/2026. La version précédente de cette note demandait d'importer `pilote/` dans
GAPPES-FINAL : **c'est fait** (ton commit `4ea310e`, 412 fichiers), vérifié, moteur intact. Cette note
ne sert plus qu'à dire où travailler.

## Le partage des dépôts

| Dépôt | Rôle | Qui y écrit |
| :-- | :-- | :-- |
| **NALSED/GRAPPES** | **les specs** | Sednal et Claude |
| **NALSED/GAPPES-FINAL** | **le code** | toi |

**Tu ne codes pas dans GRAPPES.** Tu y lis les specs, tu codes dans GAPPES-FINAL, tu pousses dessus.
Sednal regarde le résultat depuis la VM de test (.115).

## Les specs

Dans [`specs/`](specs/) : **un document par spec**, numéroté comme le pavé de retours de Sednal du
02/11/2026, pour qu'aucun point ne se perde.

* [`specs/000-INDEX.md`](specs/000-INDEX.md) — tous les points, leur état, et quel document les traite.
  **Commence par là.**
* Les documents `T*` traitent les remarques qui revenaient à l'identique sur les dix outils : elles
  sont spécifiées une fois, pas dix.

## La règle de travail

* On avance **point par point, dans l'ordre**. Un point non réglé bloque la suite.
* **Une spec ne part au code que lorsque Sednal l'a validée.** Tant que `000-INDEX.md` la donne en
  « à valider » ou « à traiter », c'est une note de travail : ne l'implémente pas.
* Sednal décide, Claude rédige, tu codes. Pour toute question d'orientation : Sednal, pas de décision
  seul.
* **Instruction transverse, permanente (09/11/2026) :** à la fin de CHAQUE tâche, avant de passer à la
  suivante, relis `specs/000-INDEX.md` et les specs modifiées depuis ta dernière lecture. De nouvelles
  instructions peuvent sortir à tout moment — pas seulement groupées en séance de revue avec Sednal.

## Ce qui reste provisoirement dans GRAPPES

Le code de `grappes/` et `pilote/` est encore là parce que .115 tourne dessus et que GAPPES-FINAL n'a
pas encore d'outillage d'installation (`installer_grappes.sh`, `installer.sh`, `lancer.sh`,
`INSTALLATION.md` n'existent qu'ici, et ils supposent la forme de ce dépôt : `grappes/` et `pilote/`
côte à côte, pas `src/grappes` à la racine). Ce déménagement est à faire ; d'ici là, ce code est une
**copie de référence**, pas un endroit où travailler.
