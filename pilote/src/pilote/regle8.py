"""Règle 8 à la couture : un compte est une personne tant que son nom ne porte pas d'indice institutionnel.

Le moteur tient cette règle (`grappes/personnes.py` : « en cas de doute, ou sans nom, on le traite comme une personne »). Côté pilote, le genre
d'un résultat de réseau social est « compte », et le filtre de `rapprochements.py` n'écarte que « personne » : sans cette conversion, le nom d'un
compte de personne physique devenait une clé de rapprochement (NIST SP 800-188 : un quasi-identifiant ne sert jamais de clé de liaison).
La fiche reste affichée (règle 1) ; elle n'est simplement jamais candidate à un rapprochement. La liste d'indices est celle du moteur, pas une copie."""

from __future__ import annotations


def genre_retenu(genre: str, nom: str) -> str:
    """Le genre que reçoit la fiche : « compte » sans indice institutionnel dans le nom devient « personne », le reste passe tel quel."""
    if (genre or "").strip().lower() != "compte":
        return genre
    # import tardif : le moteur n'est sur le chemin d'import qu'une fois la copie branchée
    from grappes.personnes import is_institution

    return genre if is_institution(nom) else "personne"
