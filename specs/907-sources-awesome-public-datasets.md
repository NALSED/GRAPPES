# 907 — Trois sources trouvées dans awesome-public-datasets

Hors du pavé. Demande de Sednal le 08/11/2026 : évaluer `awesomedata/awesome-public-datasets` (liste
communautaire de jeux de données publics, ~240 Ko de README, une quinzaine de catégories pertinentes
passées en revue — Economics, Finance, GIS, Government, Healthcare, Museums, SocialNetworks,
SocialSciences, Sports, Transportation). La quasi-totalité de la liste est hors sujet pour grappes (crypto,
immobilier, jeux de données ML/image/biologie…) ou déjà couverte (GDELT, OpenSanctions). Trois retenus par
Sednal.

## 1 — Company Registry Atlas (lance le catalogue de bases officielles par pays)

<https://github.com/aunikolskii-bit/company-registry-atlas> — atlas de 761 registres officiels
(entreprises, fiscal, douanes, permis) classés par pays.

C'est le point de départ tout fait pour l'idée validée le 13/10/2026 et mise de côté pour après les presets :
un **catalogue de bases officielles par pays**, proposé selon le pays choisi, avec téléchargement total ou
partiel par zone/grand type de base. Ne pas reconstruire cette liste à la main — partir de cet atlas, vérifier
pays par pays ce qui est effectivement exploitable (accès libre, format exploitable, pas de clé payante
cachée) avant de l'intégrer au catalogue.

## 2 — UN Civil Society Database

<http://esango.un.org/civilsociety/> — annuaire des organisations de la société civile accréditées auprès de
l'ONU (ECOSOC). À ajouter comme source du preset **Organisations officielles** / **Associations**, selon le
même protocole que toute source existante (4 niveaux de test avant activation, rôle chercher/vérifier,
première ou seconde main à préciser).

## 3 — Humanitarian Data Exchange (HDX)

<https://data.humdata.org/> — portail de données humanitaires d'UN OCHA et de ses partenaires (ONG,
organisations humanitaires). À ajouter comme source du preset **Organisations officielles** / **Associations**,
même protocole que le point 2.

## Écartés (pour mémoire, pas à spécifier)

* **Universities Worldwide** : redondant avec ROR, déjà en place.
* **World Company Database** / **Registry Lookup** : statut gratuit pas clair (ressemble à un produit
  commercial), à vérifier séparément si Sednal veut creuser — rien à faire pour l'instant.
* **EveryPolitician** : personne physique nommée — exclu d'office par la règle 8.

## Règle de dépôts (rappel)

`NALSED/GAPPES-FINAL` est réservé au **code** de momo. Cette instruction s'écrit dans `NALSED/GRAPPES`
(`specs/`) — jamais directement dans `GAPPES-FINAL`.
