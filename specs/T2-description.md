# T2 — « Ce qu'il fait » devient « Description »

Transverse aux dix fiches outils (point **3.8**). Sednal l'a écrit identiquement dix fois :

> « Ce qu'il fait => OK SI c'est seulement une description, si c'est le cas changer le titre avec
> Description. »

C'est le cas : le champ est une phrase libre affichée sur la carte de l'outil
(`06-reglages-outils.md` : « Ce qu'il fait | une phrase, affichée sur la carte »), rien de plus
qu'une description. Renommage simple, sans changement de comportement.

## Ce que momo change

* `static/suite/js/reglages.js`, champ `fait` : libellé « Ce qu'il fait » → « Description ».
* `suite/pilote/06-reglages-outils.md` : la ligne « Ce qu'il fait | une phrase, affichée sur la
  carte » devient « Description | une phrase, affichée sur la carte ».
* `charte/nommage.md` si le mot y figure littéralement — vérifier et aligner.

Rien d'autre : la donnée elle-même (`o.fait`, le champ API) ne change pas de nom côté backend, par
cohérence avec le principe déjà en place ailleurs dans la suite (le mot affiché à l'écran peut
différer du nom de champ interne — ex. « Retirer » / `retire` côté données).
