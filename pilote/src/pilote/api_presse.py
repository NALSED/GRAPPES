"""Routes de la presse (fiche 09) : la liste des flux RSS de l'utilisateur (ajout à la main, import OPML, suppression) et l'encadré Contexte."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from pilote import actions, contexte, flux_rss
from pilote.base import Recherche
from pilote.config import Config
from pilote.refus import ConfigRefusee


class CorpsFlux(BaseModel):
    url: str
    nom: str = ""
    pays: str = ""
    qui: str | None = None


def construire(cfg: Config, fabrique: sessionmaker[Session]) -> APIRouter:
    r = APIRouter(prefix="/api")

    @r.get("/flux-rss")
    def liste() -> dict[str, Any]:
        try:
            return {"flux": flux_rss.charger(cfg)}
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc

    @r.post("/flux-rss", status_code=201)
    def ajouter(corps: CorpsFlux) -> dict[str, Any]:
        """Ajoute un flux et le LIT une fois pour vérifier qu'il rend bien des articles (refusé sinon, rien n'est écrit)."""
        try:
            res = flux_rss.ajouter(cfg, corps.url, corps.nom, corps.pays)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, corps.qui or cfg.qui_par_defaut, "flux_rss_ajoute", res["id"])
        return res

    @r.delete("/flux-rss/{ident}")
    def supprimer(ident: str, qui: str | None = None) -> dict[str, Any]:
        try:
            flux_rss.supprimer(cfg, ident)
        except ConfigRefusee as exc:
            raise HTTPException(404, str(exc)) from exc
        actions.noter(cfg, qui or cfg.qui_par_defaut, "flux_rss_supprime", ident)
        return {"ok": True}

    @r.post("/flux-rss/opml", status_code=201)
    async def importer(requete: Request, qui: str | None = None) -> dict[str, Any]:
        """Corps de la requête = le fichier OPML tel quel (export d'un lecteur de flux)."""
        octets = (await requete.body())[: flux_rss.MAX_OCTETS]
        try:
            res = flux_rss.importer_opml(cfg, octets)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, qui or cfg.qui_par_defaut, "flux_rss_import_opml", f"{res['ajoutes']} ajoutés")
        return res

    @r.get("/recherches/{rid}/contexte")
    def contexte_de(rid: str) -> dict[str, Any]:
        """Les titres déjà collectés par la recherche. LIT seulement la base de la recherche : aucune collecte, aucun appel réseau."""
        with fabrique() as s:
            if s.get(Recherche, rid) is None:
                raise HTTPException(404, "Cette recherche n'existe pas.")
        return contexte.lire(cfg.dossier_recherche(rid))

    return r
