# Les mots de grappes

La liste close des mots de l'interface. Un mot par action, un mot par état, un mot par objet. Si un écran
a besoin d'un mot qui n'est pas ici, c'est cette page qu'on modifie d'abord, pas l'écran.

## Les verbes d'action

| Verbe | Ce qu'il fait | Où | Ce qu'il remplace |
| :-- | :-- | :-- | :-- |
| **Ajouter** | Crée un objet qui n'existait pas | Ajouter une source, Ajouter un outil | — |
| **Modifier** | Ouvre un objet pour le changer | Sources, outils, tuiles | « Régler », qui servait aux outils |
| **Enregistrer** | Valide ce qui est ouvert et referme | Panneaux et fenêtres | — |
| **Annuler** | Referme sans rien garder | Panneaux et fenêtres | — |
| **Fermer** | Referme ce qu'on ne faisait que lire | Fenêtre d'une tuile | « Terminé » |
| **Allumer** / **Éteindre** | Change l'état d'une source ou d'un outil | Listes et panneaux | « Allumé », employé comme étiquette |
| **Retirer** | Sort de la liste, sans rien effacer, réversible | Retirer la source, Retirer la tuile, Retirer le lien | « Délier », « Supprimer le lien », « Retirer cette tuile » |
| **Supprimer** | Efface pour de bon, avec une confirmation | Recherches sauvegardées | — |
| **Lancer** | Démarre un traitement | Lancer la recherche, Lancer le test | — |
| **Réutiliser** | Recharge une recherche sauvegardée | Recherches sauvegardées | — |
| **Remettre par défaut** | Annule les changements d'un préréglage | Recherche simple | — |
| **Ranger** | Replace les tuiles en colonnes | Plan de travail | — |
| **Filtrer** | Réduit une liste affichée | En-tête de Réglages | — |
| **Replier** / **Déplier** | Range la fenêtre Aide sur sa barre de titre, ou la rouvre | Fenêtre Aide | « Réduire », qui dit la même chose que *Filtrer* |
| **Confirmer** | Accepte un rapprochement proposé : les fiches fusionnent dans la grappe | Onglet Tri | — |
| **Séparer** | Refuse un rapprochement proposé : les fiches restent distinctes | Onglet Tri | « Rejeter », plus dur que ce que fait réellement l'action |

**Confirmer** et **Séparer** ne sont pas non plus un seul et même geste : *Confirmer* avance la grappe,
*Séparer* n'efface rien — la fiche écartée reste une fiche normale, cherchable, juste pas fondue avec
l'autre. Aucun des deux ne supprime quoi que ce soit : voir la distinction retirer/supprimer ci-dessous.

Retirer et supprimer ne sont pas synonymes, et c'est la distinction la plus importante de cette page.
**Retirer** cache une source de la liste et ne touche à aucun fichier : on peut la remettre. **Supprimer**
est définitif. Un seul objet se supprime aujourd'hui dans grappes, la recherche sauvegardée, et il demande
une confirmation — c'est la règle du GOV.UK Design System sur les actions difficiles à défaire.

La fenêtre Aide ne se ferme pas, elle se replie — donc pas de `fermer` dessus, un chevron `deplier`
avec `aria-label="Replier"`. C'est aussi pour ça que **Replier** ne dit pas « réduire » : *Filtrer*
réduit déjà une liste, et deux verbes pour deux choses différentes ne peuvent pas se ressembler.

## Ce qui vient d'une IA

Un mot réservé : **IA**. Tout ce qu'un modèle écrit porte cette marque, en toutes lettres, du moment où
il le produit jusqu'à la grappe finale. La marque ne se retire jamais en chemin, et un contenu marqué IA
n'est jamais compté comme un fait vérifié ni fondu dans un résultat sourcé.

L'outil s'appelle **Assistant IA** et il est **éteint** à la livraison. L'allumer passe par un
avertissement que l'utilisateur doit lire — voir le composant *Avertissement*. La fenêtre d'aide, elle,
s'appelle **Aide** et jamais « assistant » : deux objets différents, deux noms différents.

## Les trois états

| Mot | Couleur | Ce qu'il dit |
| :-- | :-- | :-- |
| **opérationnelle** | `etat-ok` | Testée avec succès, elle répond |
| **à vérifier** | `etat-attention` | Jamais testée, ou son dernier test a échoué |
| **éteinte** | `etat-eteint` | Volontairement mise de côté, elle n'est pas interrogée |

Au féminin pour une source, au masculin pour un outil : « source opérationnelle », « outil opérationnel ».
Jamais « actif », « inactif », « OK », « KO », « en ligne » ni « hors ligne ».

## La fiabilité d'une source : A à F

Code Admiralty (norme OTAN). Remplace « première main / seconde main », qui confondait la fiabilité de la
source avec la crédibilité d'un fait précis — deux choses que ce code sépare.

| Lettre | Sens |
| :-- | :-- |
| **A** | Entièrement fiable |
| **B** | Fiable d'habitude |
| **C** | Assez fiable |
| **D** | Pas toujours fiable |
| **E** | Non fiable |
| **F** | Fiabilité indéterminée |

Toujours une seule lettre majuscule, jamais un chiffre à côté sur la fiche source : le chiffre (1–6, la
crédibilité d'un fait) est un champ distinct, pas encore maquetté, qui vivra sur la fiche de résultat.
Détail dans `pilote/15-mecanismes-et-references.md` §2.

## Les six rôles

| Rôle | Ce qu'il fait | Qui le porte |
| :-- | :-- | :-- |
| **CHERCHER** | Trouve des fiches à partir de ce qu'on saisit | Une source |
| **VÉRIFIER** | Confirme ou infirme une fiche déjà trouvée | Une source |
| **ENRICHIR** | Ajoute des informations à une fiche | Une source |
| **CATALOGUE** | Fournit une liste d'autres sources | Une source ou un outil |
| **OUTIL** | Traite ce qui passe, sans rien chercher | Un outil |
| **RAPPROCHER** | Réunit les fiches qui parlent de la même entité | Une source ou un outil |

**RAPPROCHER** remplace **LIEN**, qui était ambigu depuis que le plan de travail relie des tuiles par des
liens. Désormais un « lien » dans grappes est toujours la flèche entre deux tuiles, et jamais un rôle.

Les rôles s'écrivent en capitales parce qu'ils sont des étiquettes, pas des phrases. C'est la seule
exception à la règle sur les capitales.

## Les objets

| Mot | Ce qu'il désigne |
| :-- | :-- |
| **source** | Un endroit où grappes va chercher : registre, API, base, flux, script |
| **outil** | Une brique qui traite ce qui passe, sans rien chercher |
| **brique** | Une source ou un outil, quand on parle de ce qu'on pose sur le plan de travail |
| **tuile** | La brique telle qu'elle apparaît sur le plan de travail |
| **lien** | La flèche qui relie la sortie d'une tuile à l'entrée d'une autre |
| **plan de travail** | La zone de la recherche avancée où l'on pose les tuiles et tire les liens |
| **préréglage** | Un ensemble de sources d'une catégorie, prêt pour la recherche simple |
| **grappe** | Le résultat : les fiches rassemblées qui parlent de la même entité |
| **fiche** | Ce qu'une source renvoie pour une entité : nom, identifiant, adresse, et le reste de ses propriétés |
| **rapprochement** | Deux ou plusieurs fiches que Fusion/doublons soupçonne de parler de la même entité, en attente de validation dans l'onglet Tri |
| **quota** | Ce qu'il reste d'appels autorisés sur une source, sur une période |

Dis « source » et jamais « base », « connecteur » ou « fournisseur ». Dis « grappe » et jamais
« cluster », « groupe » ou « regroupement ». Dis « rapprochement » et jamais « doublon », « match » ou
« correspondance » — une fiche seule qu'on hésite à fusionner n'est pas encore un doublon, c'est une
hypothèse qu'on vérifie.

## Les titres des onglets

**Tableau de bord**, **Recherche**, **Réglages**, **Tri**. Dans cet ordre, au singulier quand c'est
possible, et sans sous-titre dans la barre. Les deux sous-parties de Réglages sont **Sources** et
**Outils** ; celles de Recherche sont **Recherche simple**, **Recherche avancée** et **Recherches
sauvegardées**.
