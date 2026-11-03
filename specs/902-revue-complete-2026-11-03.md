# 902 — Revue complète et test en profondeur (demandé par Sednal, 2026-11-03)

Hors du pavé. À ce stade, tout le pavé de retours (1.1-3.9, 3.8.01-10) et le lot de questions moteur
(901, D82-D84) sont implémentés et poussés sur `NALSED/GAPPES-FINAL`. Avant d'avancer (1.3, « après le
pavé »), Sednal demande une revue complète, comme celle déjà faite le 20/10/2026 (D76 : « review complète
et test en profondeur »).

## Ce que momo fait

1. **Suite de tests complète**, pas seulement les tests touchés par les derniers commits : `pytest` sur
   `grappes/` et `pilote/` en entier. Détail de chaque échec, pas seulement le compte.
2. **Revue de code** sur l'ensemble des changements de cette session (3.8.01 à 3.8.10, 1.1, 1.2, 3.3, 3.4,
   3.6, 3.7, T1/T2/T4, 901/D82-D84) :
   * chaque tuile fait bien ce que sa spec décrit, rien d'oublié ni d'ajouté au-delà ;
   * pas de régression sur ce qui marchait avant (sources, recoupement, export, apprentissage) ;
   * les mécanismes réutilisés (registre de formats, `anchors:`, `flux_rss.py`, etc.) le sont vraiment,
     rien de dupliqué en silence ;
   * cohérence de la charte graphique sur les nouveaux éléments d'interface (mode de recherche, fichier
     « à trancher », fiche outil en 3 blocs).
3. **Test en conditions réelles** sur au moins un sujet réel (pas seulement le corpus synthétique) pour
   vérifier que les tuiles nouvellement câblées (Assistant IA, mode de recherche, Q21) produisent un
   résultat exploitable, pas seulement des tests unitaires verts.
4. Rapporter les défauts trouvés, classés par gravité, dans `QUESTIONS.md`/`ETAT.md` (comme pour les
   revues précédentes, D75/D76/D79) — correction de ce qui est routinier et déjà spécifié, liste de ce qui
   demande une décision de Sednal pour le reste.

## Ce que momo ne fait pas

* Ne pas commencer 1.3 (page Info, reportée) ni les sujets « après le pavé » pendant cette revue.
* Ne pas changer de spec de son propre chef sur un point déjà validé — un défaut trouvé devient une
  question dans `QUESTIONS.md`, pas une réinterprétation silencieuse.
