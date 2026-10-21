"""Base de données : SQLAlchemy entre le code et la base (fondation 5 de D70).

Objets : une `Recherche` a un identifiant ; ses `Candidat`, `Decision` et `Journal` s'y rattachent. Chaque action
porte un champ `qui` (fondation 3), même s'il vaut toujours « sednal » aujourd'hui. Les champs structurés sont du JSON
portable (SQLite aujourd'hui, PostgreSQL plus tard).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

ETATS = ("en_attente", "en_cours", "terminee", "arretee", "echec", "interrompue")
ETATS_FINAUX = ("terminee", "arretee", "echec", "interrompue")
ORIGINES = ("registre", "presse", "encyclo", "web", "texte")  # d'où vient un nom (fait, jamais un avis)
DECISIONS = ("garder", "rejeter", "plus_tard")  # réservées à l'utilisateur


def maintenant() -> datetime:
    return datetime.now(UTC)


def nouvel_id() -> str:
    return uuid.uuid4().hex[:16]


class Base(DeclarativeBase):
    pass


class Recherche(Base):
    __tablename__ = "recherche"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=nouvel_id)
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=maintenant)
    qui: Mapped[str] = mapped_column(String(64))
    sujet: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # champs séparés (quoi, genre, lieu, langue...)
    parametres: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # profondeur, limites, planning
    etat: Mapped[str] = mapped_column(String(16), default="en_attente", index=True)
    avancement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # rapport de grappes en cours de route
    couts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # dépense de cette recherche : {source: {"unites": n, "dollars": x}}
    message: Mapped[str] = mapped_column(Text, default="")  # phrase en français courant sur l'état
    debut: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    candidats: Mapped[list[Candidat]] = relationship(back_populates="recherche", cascade="all, delete-orphan")
    journaux: Mapped[list[Journal]] = relationship(back_populates="recherche", cascade="all, delete-orphan")


class Candidat(Base):
    """Un nom trouvé. Que des FAITS : d'où il vient, combien d'endroits, genre de source, lieu, numéro officiel."""

    __tablename__ = "candidat"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recherche_id: Mapped[str] = mapped_column(ForeignKey("recherche.id"), index=True)
    nom: Mapped[str] = mapped_column(String(512))
    genre_source: Mapped[str] = mapped_column(String(16), default="")  # origine : registre|presse|encyclo|web|texte
    trouve_par: Mapped[list[str]] = mapped_column(JSON, default=list)  # prises qui l'ont trouvé
    nb_endroits: Mapped[int] = mapped_column(Integer, default=1)
    genre_de_chose: Mapped[str] = mapped_column(String(128), default="")
    ville: Mapped[str] = mapped_column(String(128), default="")
    pays: Mapped[str] = mapped_column(String(64), default="")
    site: Mapped[str] = mapped_column(String(512), default="")
    numero_officiel: Mapped[str] = mapped_column(String(64), default="")
    faits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Place réservée (fiche 15, vue « carte de liens ») : relations enregistrées dès la collecte, sinon il n'y aurait rien à tracer plus tard.
    # Chaque relation : {"type": "maison_mere|siege|trouve_via|meme_adresse", "vers": "nom ou identifiant", "source": "id de la source"}.
    relations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    recherche: Mapped[Recherche] = relationship(back_populates="candidats")


class Decision(Base):
    """Décision de l'utilisateur sur un nom (garder / rejeter / plus tard). Jamais prise par le programme. `lot` regroupe une action
    groupée pour pouvoir l'annuler d'un coup."""

    __tablename__ = "decision"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recherche_id: Mapped[str] = mapped_column(ForeignKey("recherche.id"), index=True)
    candidat_id: Mapped[int] = mapped_column(ForeignKey("candidat.id"), index=True)
    valeur: Mapped[str] = mapped_column(String(16))  # garder|rejeter|plus_tard
    qui: Mapped[str] = mapped_column(String(64))
    le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=maintenant)
    lot: Mapped[str] = mapped_column(String(32), default="", index=True)
    annulee: Mapped[bool] = mapped_column(Boolean, default=False)
    motif: Mapped[str] = mapped_column(String(32), default="")  # pour un rejet : pourquoi (mauvais_type, hors_zone, doublon...), choisi par l'utilisateur


class Journal(Base):
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recherche_id: Mapped[str | None] = mapped_column(ForeignKey("recherche.id"), index=True, nullable=True)
    le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=maintenant)
    qui: Mapped[str] = mapped_column(String(64))
    evenement: Mapped[str] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    recherche: Mapped[Recherche | None] = relationship(back_populates="journaux")


def creer_moteur(url: str) -> Engine:
    if url.startswith("sqlite"):
        from pathlib import Path

        chemin = url.split("///", 1)[-1]
        if chemin and chemin != ":memory:":
            Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


def _migrer(moteur: Engine) -> None:
    """Ajoute les colonnes apparues depuis la création de la base (jamais de suppression, jamais de perte de données)."""
    from sqlalchemy import inspect, text

    insp = inspect(moteur)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existantes = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existantes:
                type_sql = col.type.compile(moteur.dialect)
                with moteur.begin() as cx:
                    cx.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {type_sql}'))


def creer_fabrique(url: str) -> sessionmaker[Session]:
    moteur = creer_moteur(url)
    Base.metadata.create_all(moteur)
    _migrer(moteur)
    return sessionmaker(moteur, expire_on_commit=False)


class Programme(Base):
    """Lancement daté ou récurrent d'une recherche. Chaque déclenchement crée une NOUVELLE recherche (avec son identifiant)."""

    __tablename__ = "programme"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=nouvel_id)
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=maintenant)
    qui: Mapped[str] = mapped_column(String(64))
    libelle: Mapped[str] = mapped_column(String(256), default="")  # phrase lisible : « clubs de handball — tous les jours 10 h 00 »
    sujet: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parametres: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quand: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"date": ISO local} ou {"jours": [0..6]|[], "heure": "10:00"}
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    prochaine: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    derniere_recherche_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
