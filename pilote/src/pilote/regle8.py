"""Règle 8 à la couture : un compte est une personne tant que son nom ne porte pas d'indice institutionnel.

Le moteur tient cette règle (`grappes/personnes.py` : « en cas de doute, ou sans nom, on le traite comme une personne »). Côté pilote, le genre
d'un résultat de réseau social est « compte », et le filtre de `rapprochements.py` n'écarte que « personne » : sans cette conversion, le nom d'un
compte de personne physique devenait une clé de rapprochement (NIST SP 800-188 : un quasi-identifiant ne sert jamais de clé de liaison).
La fiche reste affichée (règle 1) ; elle n'est simplement jamais candidate à un rapprochement.

Les indices institutionnels ne sont PAS dupliqués ici : ce sont ceux du moteur (`DEFAULT_INSTITUTION_HINTS`), que `config/scoring.yaml`
(`resultat.indices_institution`) remplace quand Sednal le renseigne — la même liste que le moteur lit à l'affectation des entités
(`clustering/assign.py`). Pilote et moteur restent donc sur une seule liste, modifiable sans toucher au code.

DEUX SORTIES, et c'est le point important : `est_personne` dit CE QUI A ÉTÉ CONSTATÉ (ce nom est celui d'une personne physique), `genre_retenu`
dit CE QUI EST ÉCRIT sur la fiche. Les deux sont séparés parce que les leviers (lever la règle sur une fiche, ou pour une recherche) changent le
second sans effacer le premier : le constat est tracé dans les faits de la fiche (`faits.regle8_personne`), et c'est lui — jamais le genre seul —
que lisent les garde-fous qui n'ont pas à être ouverts par un levier, comme la sortie FollowTheMoney."""

from __future__ import annotations


def est_personne(genre: str, nom: str, hints: tuple[str, ...] | None = None) -> bool:
    """Vrai si ce résultat est celui d'une personne physique au sens de la règle 8 : un « compte » dont le nom ne porte aucun indice
    institutionnel (sans nom, ou dans le doute : vrai, comme le moteur). Ne dépend d'aucun levier : c'est le constat, pas la décision."""
    if (genre or "").strip().lower() != "compte":
        return False
    # import tardif : le moteur n'est sur le chemin d'import qu'une fois la copie branchée
    from grappes.personnes import is_institution

    return not (is_institution(nom, hints) if hints is not None else is_institution(nom))


def genre_retenu(genre: str, nom: str, hints: tuple[str, ...] | None = None) -> str:
    """Le genre que reçoit la fiche : « compte » sans indice institutionnel dans le nom devient « personne », le reste passe tel quel."""
    return "personne" if est_personne(genre, nom, hints) else genre
