"""Service web de pilote (FastAPI). Les requêtes ne font jamais le travail d'une recherche : elles créent l'objet,
le confient au gestionnaire de tâches de fond, et répondent tout de suite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from pilote import (
    ajout,
    api_presse,
    api_reglages,
    carte_liens,
    catalogue,
    copies_locales,
    formats,
    motifs,
    presets,
    tri,
)
from pilote import classements as cls
from pilote import reglages as rg_fichier
from pilote.base import Candidat, Decision, Journal, Programme, Recherche, creer_fabrique, maintenant
from pilote.config import Config, charger
from pilote.executeur_grappes import ExecuteurGrappes
from pilote.lancement import LancementInvalide, valider_options
from pilote.programmation import Planificateur, creer_programme
from pilote.refus import ConfigRefusee
from pilote.taches import Executeur, Gestionnaire

STATIC = Path(__file__).resolve().parents[2] / "static"


class AppelAdresse(BaseModel):
    url: str


class SpecPrise(BaseModel):
    spec: dict[str, Any]
    mot: str = ""
    qui: str | None = None


class SourceAjoutee(BaseModel):
    type: str
    spec: dict[str, Any]
    qui: str | None = None


class Decider(BaseModel):
    valeur: str
    ids: list[int] | None = None
    classement: str | None = None
    cle: str | None = None
    motif: str | None = None
    filtres: list[str] | None = None
    q: str = ""
    nouveaux: bool = False
    qui: str | None = None


class CorpsExport(BaseModel):
    formats: list[dict[str, Any]] | None = None  # [{format, contenus?, options?}] ; vide = ceux de Réglages
    filtre: str | list[str] | None = None  # « gardes » (défaut), « tout », ou une liste de décisions
    dossier: str = ""
    qui: str | None = None


class CorpsMotifs(BaseModel):
    motifs: list[dict[str, Any]]


class NouveauClassement(BaseModel):
    nom: str
    grouper_par: list[str]
    ordre_paquets: str = "solidite"
    ordre_noms: str = "alphabetique"


class NouveauProgramme(BaseModel):
    sujet: dict[str, Any]
    parametres: dict[str, Any] = Field(default_factory=dict)
    quand: dict[str, Any]
    qui: str | None = None


class ChangementProgramme(BaseModel):
    actif: bool
    qui: str | None = None


class NouvelleRecherche(BaseModel):
    sujet: dict[str, Any] = Field(default_factory=dict)
    parametres: dict[str, Any] = Field(default_factory=dict)
    qui: str | None = None


def _iso(d):
    """Date en UTC avec son « Z » (SQLite ne garde pas le fuseau)."""
    return None if d is None else d.replace(tzinfo=None).isoformat() + "Z"


def _recherche_vue(r: Recherche) -> dict[str, Any]:
    return {
        "id": r.id, "cree_le": _iso(r.cree_le), "qui": r.qui, "sujet": r.sujet, "parametres": r.parametres,
        "etat": r.etat, "avancement": r.avancement, "message": r.message,
        "debut": _iso(r.debut), "fin": _iso(r.fin),
    }  # fmt: skip


def creer_app(cfg: Config | None = None, executeur: Executeur | None = None, url_base: str | None = None, pas_planificateur: float = 20.0) -> FastAPI:
    cfg = cfg or charger()
    fabrique: sessionmaker[Session] = creer_fabrique(url_base or cfg.url_base)
    gestionnaire = Gestionnaire(fabrique, cfg.dossier_recherche, executeur or ExecuteurGrappes(cfg), cfg.fils)

    planificateur = Planificateur(fabrique, gestionnaire.lancer, pas_s=pas_planificateur, verification=lambda: bool(rg_fichier.charger_tolerant(cfg)[0]["verification"]["active"]))

    @asynccontextmanager
    async def vie(_: FastAPI):
        gestionnaire.reprendre_apres_arret_du_service()
        planificateur.demarrer()
        yield
        planificateur.arreter()
        gestionnaire.fermer()

    app = FastAPI(title="pilote", lifespan=vie)
    # L'application n'a pas de comptes : elle n'est sûre que parce qu'elle n'écoute que cette machine. On vérifie donc le nom
    # d'hôte demandé : sinon un nom de domaine extérieur pointant sur 127.0.0.1 permettrait à une page web d'atteindre l'API.
    local = cfg.service.hote in ("127.0.0.1", "localhost", "::1", "")
    hotes = ["127.0.0.1", "localhost", "[::1]", "::1", *cfg.service.hotes_autorises] if local else ["*"]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hotes)
    app.state.cfg, app.state.fabrique, app.state.gestionnaire = cfg, fabrique, gestionnaire
    app.include_router(api_reglages.construire(cfg, fabrique))
    app.include_router(api_presse.construire(cfg, fabrique))

    def session():
        with fabrique() as s:
            yield s

    @app.get("/api/sante")
    def sante() -> dict[str, Any]:
        return {"ok": True, "grappes": str(cfg.grappes_racine), "grappes_present": cfg.grappes_racine.exists()}

    @app.post("/api/recherches", status_code=202)
    def creer(corps: NouvelleRecherche) -> dict[str, Any]:
        qui = corps.qui or cfg.qui_par_defaut
        try:
            params = valider_options(cfg, dict(corps.parametres), set(formats.decouvrir(cfg)), presets.ids_connus(cfg))
        except (LancementInvalide, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        with fabrique.begin() as s:
            if params.get("verification") is None:
                params["verification"] = bool(rg_fichier.charger_tolerant(cfg)[0]["verification"]["active"])  # l'interrupteur de Réglages au moment du lancement
            r = Recherche(qui=qui, sujet=corps.sujet, parametres=params)
            s.add(r)
            s.flush()
            s.add(Journal(recherche_id=r.id, qui=qui, evenement="creation", detail={}))
            rid = r.id
        gestionnaire.lancer(rid)  # tâche de fond : la requête répond sans attendre la fin
        return {"id": rid}

    @app.get("/api/recherches")
    def liste(s: Session = Depends(session)) -> list[dict[str, Any]]:
        out = []
        for r in s.scalars(select(Recherche).order_by(Recherche.cree_le.desc())):
            if (r.parametres or {}).get("test_reel"):
                continue  # un test réel de source est une dépense, pas une recherche : il ne figure pas dans la liste
            v = _recherche_vue(r)
            v["noms"] = s.scalar(select(func.count()).select_from(Candidat).where(Candidat.recherche_id == r.id)) or 0
            v["tries"] = s.scalar(select(func.count(func.distinct(Decision.candidat_id))).where(Decision.recherche_id == r.id, Decision.annulee.is_(False))) or 0
            out.append(v)
        return out

    @app.post("/api/lancement/estimation")
    def estimation(corps: NouvelleRecherche) -> dict[str, Any]:
        """La fourchette de temps et de coût, dite avant le lancement. N'appelle aucune source."""
        from pilote.estimation import estimer

        try:
            params = valider_options(cfg, dict(corps.parametres), set(formats.decouvrir(cfg)), presets.ids_connus(cfg))
            res = estimer(cfg, fabrique, params)
            res["copies_locales"] = copies_locales.couverture(cfg, dict(corps.sujet))
            return res
        except (LancementInvalide, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/lancement/options")
    def options() -> dict[str, Any]:
        return {
            "profondeurs": [{"id": p["id"], "nom": p["nom"], "description": p["description"], "appels": p["appels"]} for p in cfg.profondeurs],
            "profondeur_par_defaut": cfg.profondeur_par_defaut,
            "limites_par_defaut": cfg.limites_par_defaut,
        }

    @app.get("/api/programmes")
    def programmes(s: Session = Depends(session)) -> list[dict[str, Any]]:
        return [
            {"id": p.id, "libelle": p.libelle, "actif": p.actif, "quand": p.quand, "qui": p.qui,
             "prochaine": _iso(p.prochaine) if p.prochaine else None, "derniere_recherche_id": p.derniere_recherche_id}
            for p in s.scalars(select(Programme).order_by(Programme.cree_le))
        ]  # fmt: skip

    @app.post("/api/programmes", status_code=201)
    def nouveau_programme(corps: NouveauProgramme) -> dict[str, Any]:
        try:
            params = valider_options(cfg, dict(corps.parametres), set(formats.decouvrir(cfg)), presets.ids_connus(cfg))
            pid = creer_programme(fabrique, corps.sujet, params, corps.quand, corps.qui or cfg.qui_par_defaut)
        except (LancementInvalide, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc
        planificateur.replanifier()
        return {"id": pid}

    @app.put("/api/programmes/{pid}")
    def changer_programme(pid: str, corps: ChangementProgramme) -> dict[str, Any]:
        from pilote.lancement import prochaine_occurrence

        with fabrique.begin() as s:
            p = s.get(Programme, pid)
            if p is None:
                raise HTTPException(404, "Ce lancement programmé n'existe pas.")
            p.actif = corps.actif
            if corps.actif:
                p.prochaine = prochaine_occurrence(p.quand, maintenant())
                p.actif = p.prochaine is not None
            s.add(Journal(recherche_id=None, qui=corps.qui or cfg.qui_par_defaut, evenement="programme_repris" if p.actif else "programme_suspendu", detail={"programme": pid}))
            actif = p.actif
        planificateur.replanifier()
        return {"actif": actif}

    @app.get("/api/recherches/{rid}")
    def une(rid: str, s: Session = Depends(session)) -> dict[str, Any]:
        r = s.get(Recherche, rid)
        if r is None:
            raise HTTPException(404, "Cette recherche n'existe pas.")
        return _recherche_vue(r)

    @app.post("/api/recherches/{rid}/arret")
    def arreter(rid: str, qui: str | None = None, s: Session = Depends(session)) -> dict[str, Any]:
        r = s.get(Recherche, rid)
        if r is None:
            raise HTTPException(404, "Cette recherche n'existe pas.")
        demande = gestionnaire.demander_arret(rid)
        with fabrique.begin() as s2:
            s2.add(Journal(recherche_id=rid, qui=qui or cfg.qui_par_defaut, evenement="arret_demande", detail={"pris_en_compte": demande}))
        return {"arret_demande": demande}

    def _pause(rid: str, mettre: bool, qui: str | None, s: Session) -> dict[str, Any]:
        r = s.get(Recherche, rid)
        if r is None:
            raise HTTPException(404, "Cette recherche n'existe pas.")
        if r.etat != "en_cours":
            raise HTTPException(409, "Cette recherche n'est pas en cours.")
        f = cfg.dossier_recherche(rid) / "PAUSE"
        if mettre:
            f.write_text("pause demandée\n", encoding="utf-8")
        else:
            f.unlink(missing_ok=True)
        with fabrique.begin() as s2:
            r2 = s2.get(Recherche, rid)
            assert r2 is not None
            r2.avancement = {**(r2.avancement or {}), "en_pause": mettre}
            s2.add(Journal(recherche_id=rid, qui=qui or cfg.qui_par_defaut, evenement="pause" if mettre else "reprise", detail={}))
        return {"en_pause": mettre}

    @app.post("/api/recherches/{rid}/pause")
    def pause(rid: str, qui: str | None = None, s: Session = Depends(session)) -> dict[str, Any]:
        """Met la recherche en pause au prochain point d'arrêt de la collecte ; rien n'est perdu et le temps de pause ne compte pas dans la limite de temps."""
        return _pause(rid, True, qui, s)

    @app.post("/api/recherches/{rid}/reprise")
    def reprise(rid: str, qui: str | None = None, s: Session = Depends(session)) -> dict[str, Any]:
        return _pause(rid, False, qui, s)

    @app.get("/api/recherches/{rid}/journal")
    def journal(rid: str, s: Session = Depends(session)) -> list[dict[str, Any]]:
        if s.get(Recherche, rid) is None:
            raise HTTPException(404, "Cette recherche n'existe pas.")
        rows = s.scalars(select(Journal).where(Journal.recherche_id == rid).order_by(Journal.id))
        return [{"le": _iso(j.le), "qui": j.qui, "evenement": j.evenement, "detail": j.detail} for j in rows]

    # ---- Tri ----
    def _tri(f, *a, **k):
        try:
            return f(*a, **k)
        except tri.Introuvable as exc:
            raise HTTPException(404, "Cet élément n'existe pas.") from exc
        except cls.ClassementInvalide as exc:
            raise HTTPException(422, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/recherches/{rid}/tri")
    def tri_page(rid: str, classement: str | None = None, filtre: list[str] | None = Query(default=None), q: str = "", nouveaux: bool = False) -> dict[str, Any]:
        return _tri(tri.tri_vue, cfg, fabrique, rid, classement, filtre, q, nouveaux)

    @app.get("/api/recherches/{rid}/carte")
    def carte(rid: str, centre: int | None = None) -> dict[str, Any]:
        """La carte de liens : les noms gardés, ou le voisinage d'un nom (`centre`). Jamais plus de 60 points."""
        return _tri(lambda _cfg, fab, r, c: carte_liens.construire(fab, r, c), cfg, fabrique, rid, centre)

    @app.get("/api/recherches/{rid}/rejets")
    def rejets(rid: str) -> dict[str, Any]:
        """D'où vient le bruit : par source, combien de noms rejetés et pour quel motif."""
        return _tri(tri.rejets, cfg, fabrique, rid)

    @app.get("/api/motifs-rejet")
    def motifs_lire() -> list[dict[str, str]]:
        return motifs.lire(cfg)

    @app.put("/api/motifs-rejet")
    def motifs_ecrire(corps: CorpsMotifs) -> list[dict[str, str]]:
        try:
            return motifs.ecrire(cfg, corps.motifs)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/recherches/{rid}/decisions")
    def decider(rid: str, corps: Decider) -> dict[str, Any]:
        qui = corps.qui or cfg.qui_par_defaut
        paquet = ({"classement": corps.classement, "cle": corps.cle, "filtres": corps.filtres, "q": corps.q, "nouveaux": corps.nouveaux}
                  if corps.classement and corps.cle is not None else None)
        if not paquet and not corps.ids:
            raise HTTPException(422, "Dites quels noms sont concernés.")
        return _tri(tri.decider, cfg, fabrique, rid, corps.valeur, qui, corps.ids, paquet, True, corps.motif)

    @app.post("/api/recherches/{rid}/annuler")
    def annuler(rid: str, qui: str | None = None) -> dict[str, Any]:
        return _tri(tri.annuler, fabrique, rid, qui or cfg.qui_par_defaut)

    @app.post("/api/recherches/{rid}/noms/{cid}/separer")
    def separer(rid: str, cid: int, qui: str | None = None) -> dict[str, Any]:
        _tri(tri.separer, fabrique, rid, cid, qui or cfg.qui_par_defaut)
        return {"ok": True}

    @app.get("/api/recherches/{rid}/noms/{cid}")
    def fiche(rid: str, cid: int) -> dict[str, Any]:
        return _tri(tri.fiche, cfg, fabrique, rid, cid)

    @app.post("/api/recherches/{rid}/export")
    def exporter(rid: str, corps: CorpsExport | None = None, qui: str | None = None) -> dict[str, Any]:
        """Écrit la sortie d'une recherche déjà faite, dans les formats voulus : AUCUNE requête vers une source, on peut la rejouer à volonté."""
        c = corps or CorpsExport()
        return _tri(tri.exporter, cfg, fabrique, rid, c.qui or qui or cfg.qui_par_defaut, c.formats, c.filtre, c.dossier)

    @app.get("/api/formats")
    def liste_formats() -> list[dict[str, Any]]:
        return formats.vue(cfg)

    @app.get("/api/classements")
    def classements() -> list[dict[str, Any]]:
        return [c.vue() for c in cls.lister(cfg)]

    @app.post("/api/classements", status_code=201)
    def classement_nouveau(corps: NouveauClassement) -> dict[str, Any]:
        return _tri(cls.creer, cfg, corps.nom, corps.grouper_par, corps.ordre_paquets, corps.ordre_noms).vue()

    @app.post("/api/classements/{cid}/dupliquer", status_code=201)
    def classement_dupliquer(cid: str) -> dict[str, Any]:
        try:
            return cls.dupliquer(cfg, cid).vue()
        except KeyError as exc:
            raise HTTPException(404, "Ce classement n'existe pas.") from exc

    @app.get("/api/classements/{cid}/fichier")
    def classement_fichier(cid: str) -> Response:
        try:
            nom, contenu = cls.fichier(cfg, cid)
        except KeyError as exc:
            raise HTTPException(404, "Ce classement n'existe pas.") from exc
        return Response(contenu, media_type="text/yaml; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nom}"'})

    # ---- Ajout ----
    def _ajout(f, *a, **k):
        try:
            return f(*a, **k)
        except ajout.AjoutInvalide as exc:
            raise HTTPException(422, str(exc)) from exc
        except catalogue.CatalogueIndisponible as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/ajout/catalogue")
    def ajout_catalogue(q: str) -> dict[str, Any]:
        if not q.strip():
            raise HTTPException(422, "Tapez quelques mots à chercher.")
        return _ajout(catalogue.chercher, cfg, q.strip())

    @app.get("/api/ajout/catalogue/jeu/{jeu_id}")
    def ajout_jeu(jeu_id: str) -> list[dict[str, Any]]:
        return _ajout(catalogue.ressources, cfg, jeu_id)

    @app.get("/api/ajout/catalogue/api/{api_id}")
    def ajout_api(api_id: str) -> dict[str, Any]:
        return _ajout(catalogue.api, cfg, api_id)

    @app.post("/api/ajout/appeler")
    def ajout_appeler(corps: AppelAdresse) -> dict[str, Any]:
        return _ajout(ajout.appeler, cfg, corps.url)

    @app.post("/api/ajout/tester")
    def ajout_tester(corps: SpecPrise) -> dict[str, Any]:
        return _ajout(ajout.tester, cfg, corps.spec, corps.mot)

    @app.post("/api/ajout/enregistrer", status_code=201)
    def ajout_enregistrer(corps: SpecPrise) -> dict[str, Any]:
        qui = corps.qui or cfg.qui_par_defaut
        r = _ajout(ajout.enregistrer, cfg, corps.spec, qui)
        with fabrique.begin() as s:
            s.add(Journal(recherche_id=None, qui=qui, evenement="prise_ajoutee", detail={"prise": r["id"], "active": False}))
        return r

    @app.post("/api/ajout/source", status_code=201)
    def ajout_source(corps: SourceAjoutee) -> dict[str, Any]:
        """Page Ajout (fiche 11) : écrit la déclaration d'une source (api, mcp, fichier, base), éteinte, puis rend le résultat de son test local."""
        from pilote import sources_ajout
        from pilote.api_reglages import etat_phrase
        from pilote.etat_sources import lire as lire_etat

        qui = corps.qui or cfg.qui_par_defaut
        try:
            d, test = sources_ajout.enregistrer(cfg, corps.type, corps.spec)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        with fabrique.begin() as s:
            s.add(Journal(recherche_id=None, qui=qui, evenement="source_ajoutee", detail={"source": d.id, "type": corps.type, "active": False, "test": test["statut"]}))
        return {"id": d.id, "active": False, "test": test, "etat_phrase": etat_phrase(lire_etat(cfg).get(d.id), d)}

    @app.get("/")
    def accueil() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
