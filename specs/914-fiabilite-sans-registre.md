# 914 — Fiabiliser les sources sans registre officiel

**État : proposée le 23/11/2026, à valider par Sednal. Rien n'est codé.** Suite du bilan 913.
Deux volets, dans cet ordre : A (ce que le site dit de lui-même), B (les pages qui se recopient).
G1 et la règle 8 ne sont pas touchés.

## 0 — En une page

* **Le problème.** Sans registre officiel, un nom est « sûr » s'il est trouvé à deux endroits
  indépendants. Or deux endroits ne sont pas toujours indépendants : un annuaire recopie un autre
  annuaire, un blog recopie un communiqué. Aujourd'hui, deux sites qui recopient le même texte
  comptent comme deux preuves. Et ce que le site d'un acteur dit de lui-même (son numéro officiel,
  sa ville) est jeté au téléchargement de la page.
* **Volet A — le site se déclare.** On garde, au téléchargement, ce que la page déclare d'elle-même :
  numéro SIREN, SIRET ou RNA dans les mentions légales, nom, ville, téléphone, et les données
  structurées que les sites mettent pour les moteurs de recherche (schema.org). Ces informations
  sont **affichées** et servent à **proposer** de réunir des fiches. Elles ne rendent jamais un nom
  « sûr » à elles seules : c'est l'acteur qui parle de lui.
* **Volet B — les copies.** Deux pages dont le passage autour du nom est quasi identique comptent
  pour **un seul endroit**. Effet : moins de noms « sûrs » à tort.
* **Coût.** Aucun crédit, aucune requête en plus : tout se fait sur les pages déjà téléchargées.
* **Effet attendu.** Moins de noms « sûrs », mais ceux qui restent le sont pour de bon. Plus de
  numéros officiels connus, donc plus de doublons repérés.

## 1 — Volet A : ce que le site déclare de lui-même

### A.1 Ce qui est relevé

Sur chaque page téléchargée, avant que le code HTML ne soit jeté (`fetch/pages.py`, `_normalize`) :

1. **Données structurées** (schema.org en JSON-LD, microdonnées, RDFa), lues avec la bibliothèque
   `extruct` (Zyte, éprouvée, sous licence BSD). Seuls les objets de type organisation sont gardés
   (`Organization` et ses sous-types : `LocalBusiness`, `SportsOrganization`, `NGO`…). Champs
   gardés : `name`, `legalName`, `taxID`, `vatID`, `identifier`, `address.addressLocality`,
   `address.postalCode`, `telephone`, `sameAs`.
2. **Numéros officiels dans le texte**, repérés seulement près des mots qui les annoncent (« SIREN »,
   « SIRET », « RCS », « RNA », « n° d'association ») :
   * SIREN (9 chiffres) et SIRET (14 chiffres) : gardés seulement si leur clé de contrôle est juste
     (algorithme de Luhn, celui que l'INSEE utilise). Un numéro à la clé fausse est jeté. Seule
     exception connue : les SIRET de La Poste (SIREN 356 000 000), dont le contrôle est différent.
   * RNA : la lettre W suivie de 9 chiffres.
   * Numéro de TVA français (FR + 2 chiffres + SIREN) : ramené au SIREN, clé vérifiée.

Le tout est rangé dans un champ typé `declare` de l'enregistrement de la page, avec la méthode de
relevé (« schema.org » ou « texte »). Rien d'autre du HTML n'est gardé.

### A.2 Ce qu'on en fait

* **Affichage.** Sur la fiche : « le site déclare : SIREN …, ville … ». Visible dans `/suite` et dans
  `resultat.csv` (colonne `declare_par_le_site`).
* **Réunir des fiches.** Deux fiches qui ont le même numéro déclaré par leurs sites sont **proposées**
  au rapprochement (une personne tranche). Elles ne sont **pas** réunies d'office, contrairement à
  A7 (spec 912) qui réunit d'office quand le numéro vient d'un registre : un site peut se tromper
  ou recopier le numéro d'un autre.
* **Contrôle de cohérence.** Si un registre donne plus tard un numéro différent de celui que le site
  déclare, la fiche porte une alerte « numéro du site différent du registre ». Le niveau n'est pas
  changé.
* **Jamais une preuve.** La déclaration ne compte pas comme un endroit (même règle que N5 : le site
  de l'acteur est affiché, pas compté).

## 2 — Volet B : les pages qui se recopient

### B.1 Méthode

Méthode standard de repérage des quasi-doublons (Broder, 1997, utilisée par les moteurs de
recherche), avec la bibliothèque `datasketch` (licence MIT) :

1. Pour chaque page qui cite le nom, on prend **le passage autour du nom** : 40 mots avant, 40 mots
   après, à chaque endroit où le nom apparaît. On ne compare pas la page entière : deux sites faits
   avec le même modèle (menus, pied de page) se ressembleraient à tort.
2. Le passage est découpé en suites de 5 mots, et on mesure la part de suites communes entre deux
   passages (similarité de Jaccard, estimée par MinHash).
3. Deux passages sont des **copies** si cette part atteint **80 %**.
4. Passage de moins de 30 mots (nom seul dans une liste courte) : pas jugé, rien ne change.

### B.2 Ce qu'on en fait

* Les pages de sites différents qui se recopient forment **un groupe** et comptent pour **un seul
  endroit** dans `endroits_comptes` (pilote) et une seule voix dans `validate_crossref` (moteur).
* Le groupe garde toutes les preuves affichées, avec la mention « copie de … ».
* Une source de première main (registre) n'est jamais regroupée : elle reste ce qu'elle est.

## 3 — Choix à valider par Sednal

Chaque point porte ma proposition. Rien n'est codé avant ta réponse.

1. **Ce que le site dit de lui-même** est affiché et sert à proposer des rapprochements, sans
   jamais rendre un nom « sûr ». *Proposition : oui.*
2. **Même numéro déclaré par deux sites** : proposé à une personne, pas réuni d'office.
   *Proposition : oui (prudence).*
3. **Numéro du site différent du registre** : alerte affichée, niveau inchangé.
   *Proposition : oui.* Autre choix possible : passer la fiche « à vérifier ».
4. **Seuil de copie** : 80 % de texte commun autour du nom. *Proposition : 80 %.* Plus bas, on
   regroupe des pages qui se ressemblent sans se copier ; plus haut, on laisse passer des copies
   légèrement retouchées.
5. **Profils de l'acteur sur les réseaux** : si le site déclare lui-même ses comptes (`sameAs`, liens
   `rel="me"`) et que le compte renvoie au site, faut-il traiter ce compte comme le site lui-même
   (affiché, pas compté), comme N5 ? *Proposition : oui, mais dans un second temps, après A et B.*

## 4 — Tests (sans réseau, thèmes inventés)

* A : pages HTML synthétiques avec JSON-LD, microdonnées, mentions légales ; SIREN à clé juste et
  fausse ; RNA ; TVA ; numéro sans mot annonciateur (ignoré) ; deux sites au même numéro (proposition,
  pas fusion) ; numéro différent du registre (alerte).
* B : deux passages recopiés mot pour mot (un endroit) ; recopiés avec trois mots changés (un
  endroit) ; deux textes différents sur le même acteur (deux endroits) ; même modèle de site, textes
  différents (deux endroits) ; passage trop court (inchangé) ; registre + copie (registre intact).
* Non-régression : suites moteur et pilote vertes, hors échecs connus d'environnement.

## 5 — Ordre de travail

1. Validation de cette spec par Sednal.
2. Volet A : relevé (moteur), puis affichage et propositions (pilote). Un commit par étape.
3. Volet B : groupes de copies, puis comptage. Un commit par étape.
4. Mise à jour de `ETAT.md`, `DECISIONS.md`, de cette spec et de l'index.

La mesure de l'effet réel attend B1 (sur momo).
