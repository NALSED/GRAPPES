"""Configuration de pilote : un fichier YAML, aucun chemin en dur (fondation 4 de D70)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parents[2]  # le dossier qui contient `config/` (sert de base aux chemins relatifs)


@dataclass(frozen=True, slots=True)
class Service:
    hote: str = "127.0.0.1"
    port: int = 8443
    https: bool = True
    certificat: str = ""
    cle: str = ""
    hotes_autorises: tuple[str, ...] = ()  # noms d'hôte acceptés en plus de la boucle locale (voir `app.creer_app`)


@dataclass(frozen=True, slots=True)
class Config:
    racine: Path = RACINE
    service: Service = field(default_factory=Service)
    grappes_racine: Path = Path("grappes")  # aucun chemin en dur : la vraie valeur vient de config/pilote.yaml (grappes.racine)
    grappes_config: str = "config"
    grappes_python: str = ".venv/bin/python"
    donnees: Path = RACINE / "donnees"
    copies: Path | None = None  # où vont les copies locales (gros fichiers) : un autre disque que le système ; vide = <donnees>/copies
    base: str = "sqlite:///{dossier}/pilote.db"
    fils: int = 2
    qui_par_defaut: str = "sednal"
    familles: tuple[dict, ...] = ()
    ordre_familles: tuple[str, ...] = ()
    quotas: dict = field(default_factory=dict)
    profondeurs: tuple[dict, ...] = ()
    origines: dict = field(default_factory=dict)
    catalogue_mcp: str = "https://mcp.data.gouv.fr/mcp"
    catalogue_delai_s: float = 60.0
    classements_livres: str = "classements"
    classements_perso: str = "{donnees}/classements"
    profondeur_par_defaut: str = "normal"
    limites_par_defaut: dict = field(default_factory=dict)
    dossier_config: Path = RACINE / "config"  # le dossier qui contient pilote.yaml : tout le reste de la configuration s'y trouve
    chemins: dict = field(default_factory=dict)  # sources, reglages, presets, presets_perso, secrets (relatifs au dossier de configuration)
    genres: tuple[str, ...] = ()  # genres génériques que les sources font correspondre à leur vocabulaire propre
    pays_proposes: dict = field(default_factory=dict)
    secrets_grappes: str = ""  # fichier de clés de grappes (lecture seule, relatif à sa racine) ; vide = aucun

    def _rel(self, cle: str, defaut: str) -> Path:
        return _chemin(str(self.chemins.get(cle, defaut)), self.dossier_config)

    @property
    def dossier_sources(self) -> Path:
        return self._rel("sources", "sources")

    @property
    def fichier_reglages(self) -> Path:
        return self._rel("reglages", "reglages.yaml")

    @property
    def fichier_flux_rss(self) -> Path:
        return self._rel("flux_rss", "flux_rss.yaml")

    @property
    def dossier_presets(self) -> Path:
        return self._rel("presets", "presets")

    @property
    def dossier_formats_perso(self) -> Path:
        return self._rel("formats_perso", "formats_perso")

    @property
    def dossier_presets_perso(self) -> Path:
        return self._rel("presets_perso", "presets_perso")

    @property
    def fichiers_secrets(self) -> list[Path]:
        """Fichiers de clés, dans l'ordre de lecture : celui de pilote d'abord, puis (lecture seule) celui de grappes."""
        out = [_chemin(str(x), self.dossier_config) for x in (self.chemins.get("secrets") or ["secrets.env"])]
        if self.secrets_grappes:
            out.append(self.grappes_racine / self.secrets_grappes)
        return out

    @property
    def fichier_etat_sources(self) -> Path:
        return self.donnees / "etat_sources.json"

    @property
    def journal_actions(self) -> Path:
        return self.donnees / "actions.log"

    @property
    def url_base(self) -> str:
        return self.base.format(dossier=self.donnees)

    @property
    def dossier_classements_livres(self) -> Path:
        return _chemin(self.classements_livres, self.racine)

    @property
    def dossier_classements_perso(self) -> Path:
        return _chemin(self.classements_perso.format(donnees=self.donnees), self.racine)

    @property
    def python_grappes(self) -> Path:
        return self.grappes_racine / self.grappes_python

    @property
    def dossier_grappes_config(self) -> Path:
        return self.grappes_racine / self.grappes_config

    @property
    def dossier_copies(self) -> Path:
        return self.copies or self.donnees / "copies"

    def dossier_recherche(self, recherche_id: str) -> Path:
        """Dossier de travail d'une recherche : nommé d'après son identifiant, jamais d'après le sujet."""
        return self.donnees / "recherches" / recherche_id


def _chemin(valeur: str, base: Path) -> Path:
    p = Path(valeur).expanduser()
    return p if p.is_absolute() else base / p


def charger(fichier: str | Path | None = None) -> Config:
    """Lit `PILOTE_CONFIG` ou `config/pilote.yaml`. Un fichier absent donne les valeurs par défaut."""
    f = Path(fichier or os.environ.get("PILOTE_CONFIG") or RACINE / "config" / "pilote.yaml")
    y = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    y = y or {}
    base = f.parent.parent if f.exists() else RACINE
    s, g, d, t = (y.get(k) or {} for k in ("service", "grappes", "donnees", "travail"))
    return Config(
        racine=base,
        service=Service(
            str(s.get("hote", "127.0.0.1")), int(s.get("port", 8443)), bool(s.get("https", True)),
            str(s.get("certificat", "")), str(s.get("cle", "")), tuple(str(x) for x in (s.get("hotes_autorises") or [])),
        ),
        grappes_racine=_chemin(str(g.get("racine", "grappes")), base),
        grappes_config=str(g.get("config", "config")),
        grappes_python=str(g.get("python", ".venv/bin/python")),
        donnees=_chemin(str(d.get("dossier", "donnees")), base),
        copies=_chemin(str(d["copies"]), base) if d.get("copies") else None,
        base=str(d.get("base", "sqlite:///{dossier}/pilote.db")),
        fils=int(t.get("fils", 2)),
        qui_par_defaut=str(y.get("qui_par_defaut", "sednal")),
        familles=tuple(y.get("familles") or ()),
        ordre_familles=tuple(y.get("ordre_familles") or ()),
        quotas=dict(y.get("quotas") or {}),
        profondeurs=tuple(y.get("profondeurs") or ()),
        origines=dict(y.get("origines") or {}),
        catalogue_mcp=str((y.get("catalogue") or {}).get("mcp", "https://mcp.data.gouv.fr/mcp")),
        catalogue_delai_s=float((y.get("catalogue") or {}).get("delai_s", 60)),
        classements_livres=str((y.get("classements") or {}).get("livres", "classements")),
        classements_perso=str((y.get("classements") or {}).get("perso", "{donnees}/classements")),
        profondeur_par_defaut=str(y.get("profondeur_par_defaut", "normal")),
        limites_par_defaut=dict(y.get("limites_par_defaut") or {}),
        dossier_config=f.parent if f.exists() else RACINE / "config",
        chemins=dict(y.get("chemins") or {}),
        genres=tuple(y.get("genres") or ()),
        secrets_grappes=str(g.get("secrets", "")),
        pays_proposes=dict(y.get("pays_proposes") or {}),
    )
