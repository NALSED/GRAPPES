# Boucle automatique `grappes cycle`

Statut : **proposée** (`FINAL.md` § 8 ; D37 à D42). Code : `src/grappes/cycle/`, `src/grappes/fetch/`, `src/grappes/amorcage.py`. Aucune collecte réelle n'a été lancée : les tests n'utilisent que des faux serveurs locaux.

## Déroulement d'un cycle

````text
verrou ─ instantané ─ amorçage des sujets ─ rétention ─ collecte ─ score/recoupement/assignation
   ─ apprentissage ─ recalibrage ─ (nouveau score) ─ indicateurs ─┬─ export CSV ─ rapport ─ journal
                                                                  └─ dépassement : RESTAURATION ─ rapport
````

1. **Verrou** `donnees/cycle.lock` (`flock`, libéré par le système si le processus meurt) : un seul cycle à la fois (code de sortie 3).
2. **Arrêt** : `autonome: false` -> simulation ; fichier `donnees/STOP` -> aucun cycle (code 4) ; s'il apparaît pendant le cycle, restauration.
3. **Instantané** `donnees/instantanes/<cycle>/` : base SQLite (API de sauvegarde), fichiers appris, sorties. Il capture l'état d'AVANT. Les fichiers de Sednal ne sont ni capturés ni restaurés. Seuls les `instantanes_conserves` derniers sont gardés.
4. **Amorçage** des sujets sans lexique (`amorcage.py`), puis **rétention** (`retention_days`, 90).
5. **Collecte** (`cycle/collect.py`) : recherche, filtres, récupération des pages (`fetch/`), ingestion automatique, plafonds.
6. **Score, recoupement, assignation** : le pipeline existant (`run`).
7. **Apprentissage** puis **recalibrage** (`cycle/learn.py`), puis un second `run` si quelque chose a changé (les mots appris entrent dans `config_hash`).
8. **Indicateurs** (`cycle/metrics.py`) comparés au run précédent ; au-delà d'un seuil : retour en arrière.
9. **Export** (`entites.csv`, `appartenances.csv`, `resultat.csv`), **rapport** `rapports/cycle_<date>.md` (+ `dernier_cycle.md`), **journal** `donnees/cycles.jsonl`.

Toute exception restaure aussi l'instantané (statut `erreur`, code 1). Codes de sortie : 0 normal ou simulation, 1 erreur, 3 occupé, 4 arrêt, 5 annulé par la stabilité.

## Apprentissage : garde-fous

* **Uniquement des confirmées** : entité dont le recoupement est validé par des citants d'au moins 2 écosystèmes. Jamais des « probables » seules ni une source mono-écosystème.
* **Termes discriminants** : un mot doit figurer chez au moins 2 confirmées et chez au moins `support_min` (30 %) d'entre elles, et chez au plus `rarete_max` (10 %) des non-membres de la grappe. Mots vides, chiffres, mots courts et mots déjà au lexique (y compris chaque mot d'un terme composé) exclus.
* **Racine de confiance** : une confirmée n'enseigne que si elle descend d'une ancre ou d'une source trouvée par la recherche par des citations fermes, 2 pas au plus. Un cercle de fausses sources qui se citent entre elles et « confirment » de fausses cibles ne remplit pas cette condition : testé avec un corpus piégé, et avec un témoin sans garde-fou qui prouve que le piège fonctionne.
* **Bornes** : poids 0,3 ; 5 mots par cycle et par grappe, 30 au total ; un mot non revu pendant 4 cycles expire.
* **Séparation** : `config/apprentissage/lexique_appris_<grappe>.yaml` ; un terme appris ne remplace jamais un terme de Sednal ; `vu_cycle` n'entre pas dans `config_hash` (revoir un mot ne change pas le `run_id`).
* **Recalibrage** : sur les confirmées seulement, `seuil_min` et `marge_ambiguite` ne sont que RELÂCHÉS s'ils excluent des entités sûres (on n'a aucun exemple négatif pour les durcir), d'au plus `variation_max` (5) par cycle, dans les bornes.

## Stabilité et retour en arrière

| Indicateur | Seuil par défaut |
| --- | --- |
| Entités rangées avant ET après qui changent de grappe | 25 % |
| Entités ambiguës parmi les rangées | 50 % |
| Baisse relative du taux de confirmées | 30 % |
| Lexique appris / lexique de base | 100 % |

En dessous de `min_entites` (10) entités rangées, on ne juge pas. Au-delà d'un seuil : restauration de l'instantané, statut `annule`, mention dans le rapport. `grappes rollback` annule le dernier cycle terminé (non déjà annulé).

## Planification

`outils/cycle.sh` et `outils/systemd/grappes-cycle.{service,timer}` (hebdomadaire par défaut, `Persistent=true`). Rien n'est installé : c'est à Sednal de le faire, et tant que `autonome` est faux, chaque exécution est une simulation.

## Limites connues

* Le texte de recherche d'un candidat est celui que le fournisseur renvoie (titre, description) ; une page n'est ingérée qu'après récupération et seuil de proximité.
* Une source n'est enseignante que si un chemin de confiance existe : sans ancre ni source trouvée par la recherche, rien n'est appris (comportement sûr, à relâcher via `exiger_racine_de_confiance: false`).
* L'identification personne / compte institutionnel repose sur des indices explicites dans le nom (D32).

## Ajouts du 2026-10-11 (D46 à D49)

* **Documents en main** : un résultat de fournisseur peut être le document (flux RSS, article Wikipédia) ; il est ingéré sous son écosystème propre sans récupérer de page (`Candidate.doc`). Les articles de personnes physiques sont écartés (catégories biographiques, texte « né le… », aucune catégorie : en cas de doute, une personne).
* **Partage équitable** du plafond de nouvelles sources entre écosystèmes ; seconde chance pour les documents dont la part est prise.
* **Ingestion** : proximité >= seuil ET au moins `ingestion_termes_min` (2) radicaux distincts du lexique.
* **Seuil d'ingestion auto-ajusté** dans ses bornes d'après la part de sources ingérées ensuite rangées ; raison tracée dans le rapport.
* **Limite constatée (Q24)** : le recoupement exige des citants d'au moins 2 écosystèmes ; un élément RSS ne cite personne et peu de pages web sont ingérées, donc aucune entité n'est encore confirmée.

