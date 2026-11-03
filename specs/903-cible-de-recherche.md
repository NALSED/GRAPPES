# 903 — Cible de recherche (champ « Ce que je recherche »)

Hors du pavé, décidé avec Sednal le 2026-11-03 dans le prolongement de la revue 902 (Q26, Q30). Devient le
**mécanisme prioritaire** : robuste, opérationnel, chaque valeur doit avoir un vrai effet — rien de
cosmétique.

## Le principe : un vrai filtre, séparé des sources

Deux choses bien distinctes, à ne jamais mélanger :

* **Les sources/presets** (Web, Associations, Entreprises, Lieux, Réseaux sociaux...) décident **où
  chercher** — inchangé, cochables plusieurs à la fois comme aujourd'hui.
* **La cible de recherche** décide **ce qui est gardé dans le résultat**, d'après le **type réel** de
  chaque candidat trouvé — jamais d'après la source qui l'a trouvé.

Exemple qui doit marcher : presets Association + Entreprise + Lieux activés, cible = organisation. Un
club de foot trouvé via le preset Lieux (une adresse OpenStreetMap taguée club sportif) doit être gardé
si son type réel est une organisation — peu importe que ce soit le preset Lieux qui l'ait trouvé.

## Le champ

Nouveau menu déroulant **multi-sélection** dans Recherche (simple et avancée), à côté des champs
existants (mot-clé, lieu, presets...). Nom : **« Ce que je recherche »**. Même mécanisme d'interface que
« Traduire vers » de la tuile Traduction (plusieurs valeurs à la fois).

**Liste fermée, complète dès maintenant** (décision explicite de Sednal — pas de liste minimale à
compléter plus tard) :

site, compte, organisation, association, entreprise, lieu, personne, média/presse, mouvement/groupe
informel, événement.

Chaque export (`resultat.csv` et les autres formats) porte la cible retenue pour chaque ligne (quelle
valeur de la liste ce résultat satisfait).

## Mécanisme par cible — rien d'inventé, de l'existant étendu ou réutilisé

### Organisation, association, entreprise — le vérificateur de type existant

`src/grappes/decouverte/verification_type.py` (déjà réel, mesuré D69, Q27) compare le type déclaré d'un
candidat (code NAF via `type_candidat`, `nature`) à un type demandé, et écarte ce qui ne correspond pas.
Aujourd'hui `demande_type()` fige `TypeDemande.nature` à `"organisation"`, toujours la même valeur.

**À changer** : `TypeDemande` doit accepter **plusieurs natures en même temps** (celles cochées dans
« Ce que je recherche »), pas une seule figée. `verifier()`/`filtrer()` restent les mêmes fonctions,
simplement appelées avec la liste de natures demandées. Association/entreprise se distinguent entre elles
par la table NAF déjà chargée (`charger_naf`) — pas de nouveau mécanisme, le rattachement NAF déjà décidé
en Q27 fait le travail.

### Personne, lieu — le NER déjà branché, juste élargi

Les modèles déjà actifs pour l'extraction d'entités (Q26, D63-D65) — `Jean-Baptiste/camembert-ner` et
`Babelscape/wikineural-multilingual-ner` — reconnaissent nativement **PER** (personne), **ORG**
(organisation), **LOC** (lieu), **MISC** (divers). Aujourd'hui `config/ner/*.yaml` ne garde que `ORG`
(`categories: {ORG: [ORG]}`), volontairement limité quand le projet ne visait que les organisations.

**À changer** : élargir cette ligne de config à `{ORG: [ORG], PER: [PER], LOC: [LOC]}` — exactement le
principe déjà écrit dans le fichier (« changer de modèle = changer cette liste, jamais le code »). Pas de
nouveau modèle, pas de nouveau code d'extraction.

* **Personne** : un candidat étiqueté PER passe ensuite par la règle Q21 (match direct / bruit / doute) —
  les deux mécanismes s'enchaînent, pas de doublon.
* **Lieu** : un candidat étiqueté LOC, recoupé avec OpenStreetMap/Nominatim déjà branché (réglage « type
  de lieu » déjà existant dans Recherches avancées).

### Compte, site, média/presse, mouvement/groupe informel — classification structurelle, pas du NER

Ce ne sont pas des entités nommées à reconnaître dans du texte, mais la **forme du candidat lui-même** :

* **Compte** : le candidat vient d'une source de type réseau social (profil/identifiant de compte),
  reconnaissable à sa structure (déjà typée par la source qui l'a produit — `registre`/`type_candidat`
  côté moteur, le champ équivalent côté pilote).
* **Site** : candidat par défaut, sans classification plus précise (catch-all) — un `domaine`/une adresse
  web sans autre type identifié.
* **Média/presse** : le candidat **est** lui-même un média (un flux RSS identifié comme tel, une entité
  de presse), pas simplement trouvé par le preset Presse — à distinguer par la nature de la source qui le
  déclare, pas par le preset qui l'a trouvée.
* **Mouvement/groupe informel** : une grappe qui correspond sémantiquement au sujet mais dont le type
  NAF/registre reste `inconnu` (aucune preuve de personnalité morale) — c'est déjà le comportement actuel
  par défaut (« un inconnu est gardé, on ne devine pas »), juste étiqueté comme cible à part plutôt que
  confondu avec organisation confirmée.

À momo de préciser le détail d'implémentation de ces quatre-là (quel champ exact du candidat sert de
preuve structurelle), en restant sur le même principe : jamais une devinette sur le nom, toujours une
preuve issue de la structure réelle du candidat.

### Événement — MISC, avec réserve honnête

Le label `MISC` du NER peut approcher « événement », mais c'est un fourre-tout (dates, œuvres, gentilés
selon le modèle) — pas une preuve propre comme PER/ORG/LOC. **Pas de garantie à annoncer tant que ce n'est
pas mesuré** : momo active `MISC` dans la config NER, mesure sur le jeu de développement combien de faux
positifs ça donne (même méthode que D65 pour le seuil de confiance), et rapporte avant qu'on décide si
« événement » reste un vrai filtre ou si ça demande un autre mécanisme (ex. recoupement avec Meetup).

## Ce que momo change

* `verification_type.py` : `TypeDemande.nature` passe d'une valeur unique à un ensemble de natures
  demandées ; `demande_type()` prend la liste de cibles cochées en plus de la phrase du sujet.
* `config/ner/camembert_ner.yaml` et `wikineural.yaml` : `categories` élargi à `ORG`, `PER`, `LOC` (et
  `MISC` à mesurer séparément pour « événement »).
* Nouveau champ fermé multi-sélection dans Recherche (simple et avancée), même composant que « Traduire
  vers » (3.8.02) — vocabulaire fermé, charte respectée (couleur jamais seule).
* Chaque export porte la cible satisfaite par ligne.
* Classification structurelle de compte/site/média/mouvement : détail laissé à momo, sur la base des
  champs déjà présents dans les candidats (`Decouvert`, `Candidat` côté pilote) — pas de nouveau champ
  inventé sans vérifier d'abord ce qui existe déjà.

## Ce que momo vérifie

* Cible « organisation », presets Association + Entreprise + Lieux activés ensemble : un candidat trouvé
  via Lieux mais de type organisation (NAF) est bien gardé — la source qui l'a trouvé n'influence jamais
  la décision.
* Cible « personne » seule : un candidat PER détecté passe par la règle Q21 (3 cas), jamais ajouté
  directement sans ce tri.
* Cible « lieu » : un candidat LOC recoupé avec OpenStreetMap est gardé, un candidat LOC sans recoupement
  reste « inconnu » plutôt que deviné.
* Aucune cible cochée dans « Ce que je recherche » n'est cosmétique : chaque sélection change réellement
  le résultat, ou le dit clairement si elle n'est pas encore mesurée (cas Événement).
