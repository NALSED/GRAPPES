# T4 — Le champ Clé d'API, seulement quand un outil en a besoin

Transverse aux dix fiches outils (point **3.8**). Sednal l'a écrit dix fois, en question : « Clé
d'API => Pertinent ??? »

## Le problème

`ficheOutil` affiche le champ clé **sans condition**, pour les dix outils :

````js
f.cle.el,  // reglages.js, dans `contenu`, toujours présent
````

Sur les documents de spec, **seuls deux outils sur dix** parlent d'une clé :

| Outil | Besoin réel d'une clé |
| :-- | :-- |
| **Traduction** | Seulement si on choisit un service externe (ex. DeepL) plutôt que LibreTranslate auto-hébergé, qui n'en demande aucune (`09-tuile-traduction.md`) |
| **Assistant IA** | Pour les modèles distants (Claude, ChatGPT, Gemini…) ; aucune pour un modèle local (`10-tuile-assistant-ia.md`) |
| Les huit autres (Format JSON/CSV, Condition, Boucle, Fusion/doublons, Filtre, Attente, Compteur budget, RSSHub) | **Aucune** — ils ne parlent à aucun service externe authentifié |

Le champ est donc une question sans objet pour huit outils sur dix. C'est ce que Sednal relevait.

## Ce que momo change

Chaque modèle livré déclare s'il peut avoir besoin d'une clé, comme une source :

````js
{ id: "traduction", cle_requise: true, /* … */ }
{ id: "assistant-ia", cle_requise: true, /* … */ }
{ id: "format", cle_requise: false, /* … */ }
// … les sept autres : cle_requise: false
```` 

`ficheOutil` n'affiche `f.cle.el` que si le modèle choisi le demande :

````js
... val.modele && outilParId(val.modele)?.cle_requise ? f.cle.el : null,
```` 

Pour **Traduction**, la clé ne devient visible que si le service choisi en §3.8.02 (menu déroulant)
n'est pas LibreTranslate — voir la spec `3.8.02-traduction.md`.

Pour **Assistant IA**, le besoin dépend du modèle choisi (local vs distant) et se règle dans sa
propre spec (`3.8.09-assistant-ia.md`), qui prévoit plusieurs fournisseurs — potentiellement
plusieurs clés, pas une seule : ce document T4 ne fixe que la règle générale (afficher seulement si
pertinent), le détail multi-fournisseur est traité à part.

## Comment momo vérifie

* Créer un outil Filtre : aucun champ clé visible.
* Créer un outil Traduction avec LibreTranslate : aucun champ clé visible.
* Créer un outil Traduction avec un service externe (une fois §3.8.02 fait) : le champ apparaît.
