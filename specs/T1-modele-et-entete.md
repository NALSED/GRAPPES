# T1 — L'en-tête change avec le modèle, et les presets personnalisés apparaissent

Transverse aux dix fiches outils (point **3.8**), et au point **3.9** (« l'en-tête change
dynamiquement quand on clique sur un modèle »). Reprend la résolution que Sednal a écrite lui-même à
la fin du pavé :

> « Pour régler le problème récurrent *"Modèle => les autres modèles ne doivent pas apparaître,
> uniquement celui actuellement utilisé ou si un autre sauvegardé"* : l'en-tête change dynamiquement
> quand on clique sur un modèle. On garde la présentation actuelle, avec l'en-tête qui change ET
> les presets aussi si script ou modèle sauvegardé précédemment. »

Donc **pas de retrait** des autres modèles de la liste — c'est la lecture correcte de cette phrase,
tranchée par Sednal lui-même en fin de pavé : la liste reste visible comme aujourd'hui, mais deux
choses la rendent enfin claire.

## 1. Le titre du panneau suit le modèle choisi

Aujourd'hui (`ficheOutil`, `reglages.js`, dernière ligne) :

````js
titre: edition ? o.nom : "Nouvel outil"
````

Pour un outil **existant**, le titre est déjà son nom — correct. Pour un **nouvel** outil, le titre
reste figé sur « Nouvel outil », même après avoir choisi un modèle. C'est le trou : rien ne confirme
quel modèle est sélectionné au moment où on le choisit.

Le titre devient réactif : au clic sur un modèle, il prend son nom. Le panneau se referme et se
rouvre normalement pour afficher un titre dynamique dans `ouvrirCouche` (déjà posé une fois à la
création) ; pour le mettre à jour en cours de vie sans refermer la fenêtre, `ouvrirCouche` doit
exposer un moyen de changer son titre après coup (ajouter une méthode, ex. `couche.titre(texte)`, ou
reconstruire seulement le nœud du titre si `ouvrirCouche` le garde accessible).

````js
zones.modele.replaceChildren(..., groupePuces(choix, val.modele, (v) => {
  const m = outilParId(v);
  val.modele = v; /* … */
  couche.titre(m.nom); // nouveau
  dessiner();
}));
````

## 2. Les variantes déjà personnalisées apparaissent dans la liste

Aujourd'hui, la liste de choix ne montre que les dix modèles livrés :

````js
app.data.outils.filter((m) => m.livre).map((m) => [m.id, m.nom])
````

Un outil que l'utilisateur a déjà personnalisé et enregistré (`livre: false`, basé sur l'un des dix
modèles — champ `o.modele` encore à exposer côté backend s'il ne l'est pas déjà) devient un
**preset** dans la même liste, à la suite des modèles livrés, visuellement distingué (une légère
séparation, ou une mention `legende pale` « personnalisé » après le nom) :

````js
const livres = app.data.outils.filter((m) => m.livre);
const presets = app.data.outils.filter((m) => !m.livre && m.modele_base);
groupePuces([...livres.map((m) => [m.id, m.nom]), ...presets.map((m) => [m.id, `${m.nom} (personnalisé)`])], val.modele, ...)
````

Choisir un preset personnalisé charge ses réglages enregistrés, exactement comme choisir un modèle
livré charge ses réglages par défaut (même bloc `onclick`, qui lit déjà `m.options`, `m.fait`,
`m.recoit`… peu importe que `m` soit livré ou personnalisé).

**Prérequis côté moteur** : qu'un outil personnalisé garde la trace du modèle livré dont il dérive
(`modele_base`, à ajouter à la déclaration si absent) — sans cette trace, impossible de regrouper
« les variantes de Traduction » séparément des variantes de Filtre dans la liste.

## Comment momo vérifie

* Créer un nouvel outil, cliquer sur « Traduction » : le titre du panneau devient « Traduction »
  immédiatement, sans fermer le panneau.
* Enregistrer une Traduction personnalisée (ex. langue cible fixée), rouvrir « Ajouter un outil » :
  elle apparaît dans la liste de choix, à la suite des dix modèles livrés, marquée « personnalisé ».
* La cliquer charge ses réglages enregistrés, pas les réglages par défaut du modèle Traduction.
