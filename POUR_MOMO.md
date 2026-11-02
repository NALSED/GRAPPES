# Note pour momo — récupérer la nouvelle UI dans GAPPES-FINAL

Écrit le 02/11/2026, à la demande de Sednal. Corrige et remplace la version précédente de cette note (elle se
trompait sur la relation entre les dépôts — voir plus bas).

## Qui travaille où

* **NALSED/GRAPPES** (ce dépôt) : Sednal + Claude. C'est ici que l'interface (`pilote/`) est développée.
* **NALSED/GAPPES-FINAL** : Sednal + toi. C'est ton dépôt, ton moteur (`src/grappes`) y reste la version de
  référence, personne n'y touche.

Les deux dépôts ne sont **pas** indépendants : `pilote/grappes` (le moteur synchronisé dans ce dépôt) est une copie
de ton `src/grappes` — vérifié fichier par fichier, identique. Et la charte visuelle de `/suite` est générée (par
`pilote/outils/generer_suite.py`) à partir de `suite/pilote/charte/` dans GAPPES-FINAL — vérifié aussi, le résultat
généré ici est identique à ta source. Donc ton travail de moteur et de charte alimente déjà ce dépôt. Ce qui manque
encore dans GAPPES-FINAL, c'est l'application elle-même : le dossier `pilote/` (serveur FastAPI + interface web)
n'existe pas chez toi aujourd'hui.

## Ce qu'il faut faire

1. **Le moteur ne bouge pas.** `src/grappes` reste tel quel dans GAPPES-FINAL.
2. **Récupérer le dossier `pilote/` de ce dépôt** (NALSED/GRAPPES, dernier commit) et l'ajouter dans GAPPES-FINAL,
   à côté de `src/grappes` (même logique que ce dépôt : deux applications côte à côte).
3. Ça apporte, en plus de l'interface elle-même : les corrections de bugs de ce matin, la règle 8, et surtout la
   nouvelle charte graphique avec `/suite` et son assistant de première installation.
4. **Si tu as de ton côté une ancienne version de l'interface** (locale, pas forcément commitée) : elle disparaît,
   remplacée par ce `pilote/`. Il ne doit plus en rester de trace.
5. **`/suite` est désormais la seule UI qui compte.** Pas d'interface à toi en parallèle.

## Pour le faire proprement

```bash
# dans ton répertoire de travail GAPPES-FINAL
git status                      # si tu as du travail non commité, le mettre de côté avant (git stash, ou une branche)

# récupérer pilote/ depuis NALSED/GRAPPES
git clone --depth 1 https://github.com/NALSED/GRAPPES.git /tmp/grappes-source
rm -rf pilote                   # ou le dossier où vivait ton ancienne interface, si ce n'est pas "pilote"
cp -r /tmp/grappes-source/pilote ./pilote
rm -rf /tmp/grappes-source

git add -A
git status                      # relire ce qui va être commité avant de commiter
git commit -m "Import de pilote/ depuis NALSED/GRAPPES : nouvelle charte, /suite, corrections de ce matin"
git push
```

Avant de pousser, dis à Sednal où ça en est (git status + un mot sur le moteur) — pas d'enchaînement automatique sur
autre chose derrière.

## Pour travailler sur l'interface une fois importée

* Tests : `cd pilote && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest` (`-m "not reseau"` pour la
  partie qui ne dépend d'aucun service extérieur).
* Toute nouvelle valeur de style dans `/suite` passe par les jetons (`charte/jetons.css`/`typo.css`), jamais en dur
  — vérifié par `tests/test_suite_navigateur.py::test_aucune_valeur_de_style_en_dur`.

Pour toute question d'orientation : voir avec Sednal, pas de décision à prendre seul.
