"""Règle 8 à la couture : un compte est une personne tant que son nom ne porte pas d'indice institutionnel.

Le moteur tient cette règle (`grappes/personnes.py` : « en cas de doute, ou sans nom, on le traite comme une personne »). Côté pilote, le genre
d'un résultat de réseau social est « compte », et le filtre de `rapprochements.py` n'écarte que « personne » : sans cette conversion, le nom d'un
compte de personne physique devenait une clé de rapprochement (NIST SP 800-188 : un quasi-identifiant ne sert jamais de clé de liaison).
La fiche reste affichée (règle 1) ; elle n'est simplement jamais candidate à un rapprochement.

Les indices institutionnels ne sont PAS dupliqués ici : ce sont ceux du moteur (`DEFAULT_INSTITUTION_HINTS`), complétés par la liste que Sednal
tient lui-même dans `config/scoring.yaml` (`resultat.indices_institution` — déjà lue par le moteur à l'affectation des entités, voir
`clustering/assign.py`). Pilote et moteur lisent donc la même liste, modifiable sans toucher au code (27-leviers-regle8-a-faire-par-sednal.md §1).

Deux leviers supplémentaires, documentés dans le même fichier : lever la règle sur UNE fiche précise après coup (`tri.marquer_personne_morale`),
ou pour UNE recherche entière au moment de la lancer (`hints=None` ci-dessous, piloté par `lancement.py`/`executer.py`). Aucun des deux ne
touche à la règle par défaut ni au moteur : voir ce fichier pour le détail."""

from __future__ import annotations


def genre_retenu(genre: str, nom: str, hints: tuple[str, ...] | None = None) -> str:
    """Le genre que reçoit la fiche : « compte » sans indice institutionnel dans le nom devient « personne », le reste passe tel quel.

    `hints`, quand fourni, remplace la liste par défaut du moteur (c'est `executer.py` qui y met celle de `config/scoring.yaml`, déjà
    étendue par le moteur avec `DEFAULT_INSTITUTION_HINTS`). `hints=None` garde le comportement du moteur tel quel."""
    if (genre or "").strip().lower() != "compte":
        return genre
    # import tardif : le moteur n'est sur le chemin d'import qu'une fois la copie branchée
    from grappes.personnes import is_institution

    institution = is_institution(nom, hints) if hints is not None else is_institution(nom)
    return genre if institution else "personne"
