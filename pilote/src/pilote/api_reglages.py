"""Routes de la page Réglages (fiche 01). Aucune route d'ici n'appelle un service externe : la page montre le DERNIER ÉTAT CONNU."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from pilote import (
    actions,
    adaptateurs,
    assistant,
    budget,
    catalogue_pays,
    cles,
    copies_locales,
    disjoncteur,
    formats,
    presets,
    programme_local,
    tests_source,
)
from pilote import reglages as rg
from pilote.base import Recherche
from pilote.config import Config
from pilote.etat_sources import lire as lire_etat
from pilote.refus import ConfigRefusee, lire_yaml, verrou
from pilote.sources import Declaration, charger_sources


class CorpsSource(BaseModel):
    chercher: bool | None = None
    verifier: bool | None = None
    confiance: float | None = None
    cout: dict[str, Any] | None = None
    parametres: dict[str, Any] | None = None
    confirme: bool = False
    qui: str | None = None


class CorpsCopie(BaseModel):
    pays: str
    base: str
    confirme: bool = False
    mot_cle: str = ""
    zone: str = ""
    qui: str | None = None


class CorpsBudget(BaseModel):
    plafond_mensuel_usd: float
    qui: str | None = None


class CorpsVerification(BaseModel):
    active: bool
    mode: str | None = None  # « memes » (recoupement entre les sources de recherche) ou « plus » (avec les sources qui ne font que vérifier)
    qui: str | None = None


class CorpsPays(BaseModel):
    pays: str
    qui: str | None = None


class CorpsPresets(BaseModel):
    coches: list[str]
    qui: str | None = None


class CorpsSortie(BaseModel):
    actifs: list[str] | None = None
    contenus: dict[str, list[str]] | None = None
    dossier: str | None = None
    webhook_url: str | None = None
    qui: str | None = None


class CorpsCle(BaseModel):
    valeur: str
    qui: str | None = None


class CorpsPerso(BaseModel):
    depuis: str
    nom: str
    qui: str | None = None


class CorpsPresetNom(BaseModel):
    nom: str
    qui: str | None = None


class CorpsPresetInfos(BaseModel):
    nom: str
    phrase: str = ""
    qui: str | None = None


class CorpsAffichage(BaseModel):
    partie: str  # « recherche » (Sources) ou « verification »
    qui: str | None = None


class CorpsPresetSources(BaseModel):
    sources: list[str]
    qui: str | None = None


class CorpsImport(BaseModel):
    texte: str
    qui: str | None = None


class CorpsProgramme(BaseModel):
    nom: str
    commande: list[str]
    delai_s: float | None = None
    exemple: Any = None
    genres: list[str] | None = None
    pays: list[str] | None = None
    usages: list[str] | None = None
    description: str | None = None
    trouve: str | None = None
    main: str | None = None
    qui: str | None = None


class CorpsTestReel(BaseModel):
    mot: str
    confirme: bool = False
    qui: str | None = None


class CorpsEtape(BaseModel):
    donnees: dict[str, Any]
    confirme: bool = False
    qui: str | None = None


class CorpsTerminer(BaseModel):
    etape1: dict[str, Any]
    etape2: dict[str, Any]
    etape3: dict[str, Any]
    confirme: bool = False
    qui: str | None = None


def portails_ckan(cfg: Config) -> dict[str, dict[str, Any]]:
    """Les portails CKAN contrôlés, par pays (données : config/portails_ckan.yaml)."""
    f = cfg.dossier_config / str(cfg.chemins.get("portails_ckan", "portails_ckan.yaml"))
    try:
        return {str(k).upper(): v for k, v in lire_yaml(f).items() if isinstance(v, dict) and v.get("portail")} if f.exists() else {}
    except ConfigRefusee:
        return {}


def date_fr(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return ""
    return f"{d:%d/%m/%Y à %H:%M}"


def etat_phrase(e: dict[str, Any] | None, d: Declaration) -> str:
    """Le dernier état connu en français courant, avec sa date. Jamais un rafraîchissement : ce qui est écrit sur disque."""
    if not e or not (e.get("teste_le") or e.get("dernier_appel")):
        return "Pas encore testée."
    morceaux = []
    if e.get("teste_le"):
        st = e.get("statut")
        if st == "ok":
            morceaux.append(f"Vérifiée hors ligne le {date_fr(e['teste_le'])}." + (" Connexion non vérifiée (ce fournisseur n'offre pas de point d'accès gratuit pour la tester)." if (e.get("niveaux") or {}).get("3") == "non_verifie" else ""))
        elif st == "echec":
            morceaux.append(f"Test échoué le {date_fr(e['teste_le'])} : {e.get('raison', 'raison inconnue')}.")
        else:
            morceaux.append(f"Testée le {date_fr(e['teste_le'])} (connexion non vérifiée).")
    q = e.get("quota")
    if q and q.get("restant") is not None:
        morceaux.append(f"Quota restant au {date_fr(q.get('le'))} : {q['restant']:g}" + (f" sur {q['total']:g}" if q.get("total") else "") + ".")
    if e.get("derniere_erreur"):
        morceaux.append(f"Dernière erreur le {date_fr(e['derniere_erreur'].get('le'))} : {e['derniere_erreur'].get('raison', '')}.")
    if e.get("disjoncteur"):
        morceaux.append("En pause : " + str(e["disjoncteur"].get("raison", "plusieurs erreurs de suite")) + ". " + phrase_reprise(e["disjoncteur"]))
    return " ".join(morceaux)


def phrase_reprise(dj: dict[str, Any]) -> str:
    """Pour l'affichage seulement (jamais appelé en écartant une source) : dans combien de temps la reprise automatique la retentera."""
    from pilote import disjoncteur

    restant = disjoncteur.reprise_dans_s(dj)
    if restant <= 0:
        return "Reprise automatique à la prochaine recherche."
    minutes = max(1, round(restant / 60))
    return f"Reprise automatique dans environ {minutes} minute{'s' if minutes > 1 else ''} (ou tout de suite, à la main)."


MESSAGE_ADAPTATEUR = "Cette source demande un adaptateur : elle est enregistrée, mais elle ne peut pas servir tant que ce petit programme n'est pas écrit."


def adaptateur_manquant(d: Declaration) -> bool:
    """Vrai si la source s'appuie sur un adaptateur qui n'existe pas (OAuth, curseur, GraphQL… : cas que le déclaratif ne couvre pas)."""
    nom = d.moteur.get("adaptateur")
    if not nom:
        return False
    try:
        adaptateurs.charger(str(nom))
    except adaptateurs.ErreurSource:
        return True
    return False


def voyant(cfg: Config, d: Declaration, e: dict[str, Any] | None, manquant: bool, donnes: dict[str, Any] | None = None) -> tuple[str, str]:
    """Le rond de la ligne : vert = disponible et utilisable, orange = il manque quelque chose (clé, réglage, pause), rouge = inutilisable
    (test échoué, adaptateur à écrire). `donnes` : les réglages propres à la source déjà donnés par l'utilisateur."""
    e = e or {}
    donnes = donnes if isinstance(donnes, dict) else {}
    if manquant:
        return "err", "demande un adaptateur"
    if e.get("statut") == "echec":
        return "err", "test échoué"
    if e.get("disjoncteur"):
        return "warn", "en pause"
    if d.cles and not cles.toutes_presentes(cfg, d.cles):
        return "warn", "clé absente"
    if any(spec.get("requis") and not str(donnes.get(nom, "")).strip() for nom, spec in d.parametres.items()):
        return "warn", "réglage à donner"  # sinon l'activation serait refusée : elle n'est pas « utilisable » telle quelle
    return "ok", "disponible" if e.get("teste_le") else "disponible (pas encore testée)"


def construire(cfg: Config, fabrique: sessionmaker[Session]) -> APIRouter:
    r = APIRouter(prefix="/api")

    def contexte():
        decls, problemes = charger_sources(cfg)
        return decls, problemes

    def appliquer(patch: dict[str, Any], qui: str | None, action: str, detail: str = "", confirme: bool = False) -> dict[str, Any]:
        decls, _ = contexte()
        try:
            requis = rg.avertissements_requis(rg.charger(cfg), decls, patch)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        if requis and not confirme:  # l'avertissement est montré une fois, à l'activation ; la page redemande avec « confirme »
            raise HTTPException(409, {"avertissements": requis})
        if requis:
            patch = {**patch, "avertissements_vus": sorted({*rg.charger(cfg).get("avertissements_vus", []), *(a["source"] for a in requis)})}
        try:
            res = rg.appliquer(cfg, decls, presets.ids_connus(cfg), patch)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, qui or cfg.qui_par_defaut, action, detail)
        return res

    def refuser_si_test_echoue(decls: dict[str, Declaration], patch: dict[str, Any]) -> None:
        """Une source dont le test local a échoué ne peut pas être activée tant que le test ne passe pas (fiche 11)."""
        etats = lire_etat(cfg)
        voulues = dict(patch.get("sources") or {})
        if "source" in patch:
            voulues[patch["source"]["id"]] = patch["source"]
        for sid, ch in voulues.items():
            if (ch.get("chercher") or ch.get("verifier")) and sid in decls and adaptateur_manquant(decls[sid]):
                raise HTTPException(422, f"La source « {decls[sid].nom} » : {MESSAGE_ADAPTATEUR}")
            if (ch.get("chercher") or ch.get("verifier")) and sid in decls and (etats.get(sid) or {}).get("statut") == "echec":
                raise HTTPException(422, f"La source « {decls[sid].nom} » a échoué à son test ({etats[sid].get('raison', 'raison inconnue')}) : "
                                         "elle ne peut pas être activée tant que le test ne passe pas.")

    @r.get("/reglages")
    def lire() -> dict[str, Any]:
        decls, problemes = contexte()
        reg, casse = rg.charger_tolerant(cfg)
        if casse:
            problemes = [*problemes, {"fichier": cfg.fichier_reglages.name, "raison": casse}]
        problemes = [*problemes, *rg.problemes_de_valeurs(cfg, reg, decls)]  # valeurs retouchées à la main et inutilisables : dites, jamais fatales
        etats = lire_etat(cfg)
        aff = reg.get("affichage") or {}
        masquees = {"recherche": rg.ids_de_liste(aff.get("sources_masquees")), "verification": rg.ids_de_liste(aff.get("verification_masquees"))}
        lignes = []
        for d in sorted(decls.values(), key=lambda d: (cfg.ordre_familles.index(d.famille) if d.famille in cfg.ordre_familles else 99, d.nom)):
            ch = rg.choix_source(reg, d)
            e = etats.get(d.id)
            manquant = adaptateur_manquant(d)
            donnes = rg.parametres_donnes(reg, d.id)  # tolérant : une entrée retouchée à la main ne fait pas tomber la page
            vy = voyant(cfg, d, e, manquant, donnes)
            cle = None if not d.cles else ("presente" if cles.toutes_presentes(cfg, d.cles) else "absente")
            lignes.append({
                **d.vue(), "cle_nom": d.cle, "cles_noms": d.cles, "parametres": donnes, "chercher": ch["chercher"], "verifier": ch["verifier"], "confiance": ch["confiance"], "cout_effectif": ch["cout"],
                "cout_phrase": budget.cout_phrase(d, ch["cout"]), "cle": cle, "bloquee_par_cle": bool(d.cles) and cle == "absente" and (ch["chercher"] or ch["verifier"]),
                "etat": e or {}, "etat_phrase": MESSAGE_ADAPTATEUR if manquant else etat_phrase(e, d),
                "voyant": list(vy), "gratuite": not d.payant, "adaptateur_manquant": manquant, "domaine": presets.domaine_source(d),
                "masquee": {p: d.id in ids for p, ids in masquees.items()},
            })  # fmt: skip
        so = reg.get("sortie") or {}
        fmts = [{**f, "actif": f["id"] in so.get("actifs", ["csv"]), "contenus_choisis": (so.get("contenus") or {}).get(f["id"]) or f["contenus_defaut"]} for f in formats.vue(cfg)]
        return {
            "parties": {"recherche": lignes, "verification": [x for x in lignes if "verifier" in x["roles"]], "sortie": fmts},
            "familles": list(cfg.ordre_familles), "genres": list(cfg.genres), "pays_proposes": dict(cfg.pays_proposes), "problemes": problemes,
            "presets": presets.cartes(cfg, decls), "presets_coches": reg["presets_coches"], "budget": budget.vue(cfg, fabrique),
            "verification": {"active": reg["verification"]["active"] is True, "mode": str(reg["verification"].get("mode") or "memes"),
                             "verificatrices_seules": sorted(d.nom for d in decls.values() if "verifier" in d.roles and "chercher" not in d.roles and d.verifie_sur in ("site", "nom"))}, "sortie": {"dossier": so.get("dossier", ""), "webhook_url": so.get("webhook_url", "")}, "pays": reg["pays"],
            "modeles_ia": list(reg.get("modeles_ia") or []),
            "assistant": {"termine": bool(reg["assistant"].get("termine")), "premiere_installation": not rg.existe(cfg)},
            "catalogue_nb_pays": len(catalogue_pays.charger(cfg)[0]),
        }  # fmt: skip

    @r.put("/reglages/source/{sid}")
    def source(sid: str, corps: CorpsSource) -> dict[str, Any]:
        patch: dict[str, Any] = {"id": sid}
        for k in ("chercher", "verifier", "confiance", "cout", "parametres"):
            if getattr(corps, k) is not None:
                patch[k] = getattr(corps, k)
        decls, _ = contexte()
        refuser_si_test_echoue(decls, {"source": patch})
        appliquer({"source": patch}, corps.qui, "source_modifiee", f"{sid} {sorted(set(patch) - {'id'})}", corps.confirme)
        return {"ok": True}

    @r.post("/reglages/source/{sid}/masquer")
    def masquer(sid: str, corps: CorpsAffichage) -> dict[str, Any]:
        """Retire la source de l'AFFICHAGE d'une partie (et l'éteint pour ce rôle). Aucun fichier de source n'est touché."""
        decls, _ = contexte()
        try:
            rg.masquer(cfg, decls, presets.ids_connus(cfg), sid, corps.partie, True)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, corps.qui or cfg.qui_par_defaut, "source_retiree_de_l_affichage", f"{sid} {corps.partie}")
        return {"ok": True}

    @r.post("/reglages/source/{sid}/afficher")
    def afficher(sid: str, corps: CorpsAffichage) -> dict[str, Any]:
        """Remet à l'affichage une source enregistrée ; elle reste éteinte tant qu'on ne l'allume pas."""
        decls, _ = contexte()
        try:
            rg.masquer(cfg, decls, presets.ids_connus(cfg), sid, corps.partie, False)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, corps.qui or cfg.qui_par_defaut, "source_remise_a_l_affichage", f"{sid} {corps.partie}")
        return {"ok": True}

    @r.put("/reglages/budget")
    def plafond(corps: CorpsBudget) -> dict[str, Any]:
        appliquer({"budget": {"plafond_mensuel_usd": corps.plafond_mensuel_usd}}, corps.qui, "plafond_modifie", str(corps.plafond_mensuel_usd))
        return budget.vue(cfg, fabrique)

    @r.put("/reglages/verification")
    def verification(corps: CorpsVerification) -> dict[str, Any]:
        patch: dict[str, Any] = {"active": corps.active}
        if corps.mode is not None:
            patch["mode"] = corps.mode
        res = appliquer({"verification": patch}, corps.qui, "verification_activee" if corps.active else "verification_coupee", corps.mode or "")
        return {"active": corps.active, "mode": res["verification"].get("mode", "memes")}

    @r.put("/reglages/pays")
    def pays(corps: CorpsPays) -> dict[str, Any]:
        appliquer({"pays": corps.pays.strip().upper()}, corps.qui, "pays_choisi", corps.pays)
        return {"pays": corps.pays.strip().upper()}

    @r.put("/reglages/presets")
    def presets_coches(corps: CorpsPresets) -> dict[str, Any]:
        appliquer({"presets_coches": corps.coches}, corps.qui, "presets_coches", ",".join(corps.coches))
        return {"coches": corps.coches}

    @r.put("/reglages/sortie")
    def sortie(corps: CorpsSortie) -> dict[str, Any]:
        connus = formats.decouvrir(cfg)
        reg = rg.charger(cfg)
        actuel = dict(reg.get("sortie") or {})
        if corps.actifs is not None:
            mauvais = [f for f in corps.actifs if f not in connus]
            if mauvais:
                raise HTTPException(422, f"Le format « {mauvais[0]} » n'existe pas.")
            actuel["actifs"] = corps.actifs
        if corps.contenus is not None:
            for fid, cs in corps.contenus.items():
                if fid not in connus:
                    raise HTTPException(422, f"Le format « {fid} » n'existe pas.")
                if not cs or any(c not in connus[fid]["contenus"] for c in cs):
                    raise HTTPException(422, f"Le format « {connus[fid]['nom']} » propose : {', '.join(connus[fid]['contenus'])}.")
            actuel["contenus"] = corps.contenus
        if corps.dossier is not None:
            actuel["dossier"] = corps.dossier.strip()
        if corps.webhook_url is not None:
            actuel["webhook_url"] = corps.webhook_url.strip()
        appliquer({"sortie": actuel}, corps.qui, "sortie_modifiee", ",".join(actuel.get("actifs", [])))
        return {k: actuel.get(k) for k in ("actifs", "contenus", "dossier", "webhook_url")}

    @r.put("/cles/{nom}")
    def cle(nom: str, corps: CorpsCle) -> dict[str, Any]:
        try:
            cles.ecrire(cfg, nom, corps.valeur)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, corps.qui or cfg.qui_par_defaut, "cle_enregistree", nom)  # le NOM de la clé, jamais sa valeur
        return {"cle": "presente"}  # on ne renvoie jamais la valeur

    @r.post("/presets/personnaliser", status_code=201)
    def personnaliser(corps: CorpsPerso) -> dict[str, Any]:
        decls, _ = contexte()
        try:
            res = presets.personnaliser(cfg, decls, corps.depuis, corps.nom, corps.qui or cfg.qui_par_defaut)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, corps.qui or cfg.qui_par_defaut, "preset_personnalise", f"{corps.depuis} -> {res['id']}")
        return res

    def _preset_perso(qui: str | None, evenement: str, detail: str, f, *a):
        try:
            res = f(*a)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, qui or cfg.qui_par_defaut, evenement, detail)
        return res

    @r.post("/presets", status_code=201)
    def preset_vide(corps: CorpsPresetNom) -> dict[str, Any]:
        return _preset_perso(corps.qui, "preset_cree", corps.nom, presets.creer_vide, cfg, corps.nom)

    @r.put("/presets/{ident}")
    def preset_modifier(ident: str, corps: CorpsPresetSources) -> dict[str, Any]:
        decls, _ = contexte()
        return _preset_perso(corps.qui, "preset_modifie", ident, presets.modifier, cfg, decls, ident, corps.sources)

    @r.put("/presets/{ident}/infos")
    def preset_infos(ident: str, corps: CorpsPresetInfos) -> dict[str, Any]:
        return _preset_perso(corps.qui, "preset_decrit", ident, presets.decrire, cfg, ident, corps.nom, corps.phrase)

    @r.delete("/presets/{ident}")
    def preset_supprimer(ident: str, qui: str | None = None) -> dict[str, Any]:
        _preset_perso(qui, "preset_supprime", ident, presets.supprimer, cfg, ident)
        return {"ok": True}

    @r.get("/presets/{ident}/export")
    def preset_exporter(ident: str) -> Response:
        decls, _ = contexte()
        try:
            texte = presets.exporter(cfg, decls, ident)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        return Response(texte, media_type="text/yaml; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{ident}.preset.yaml"'})

    @r.post("/presets/importer", status_code=201)
    def preset_importer(corps: CorpsImport) -> dict[str, Any]:
        decls, _ = contexte()
        return _preset_perso(corps.qui, "preset_importe", "", presets.importer, cfg, decls, corps.texte)

    @r.post("/programmes-locaux", status_code=201)
    def programme_local_ajouter(corps: CorpsProgramme) -> dict[str, Any]:
        spec = corps.model_dump(exclude={"qui"}, exclude_none=True)
        try:
            d, test = programme_local.enregistrer(cfg, spec)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        actions.noter(cfg, corps.qui or cfg.qui_par_defaut, "programme_ajoute", d.id)
        return {"id": d.id, "active": False, "test": test, "etat_phrase": etat_phrase(lire_etat(cfg).get(d.id), d)}

    @r.get("/types-de-lieu")
    def types_de_lieu() -> dict[str, Any]:
        """Les types de lieu proposés dans Recherches (données : config/lieux_osm.yaml), avec leur libellé et les genres qui y renvoient."""
        f = cfg.dossier_config / "lieux_osm.yaml"
        y = lire_yaml(f) if f.exists() else {}
        return {"types": [{"id": k, "libelle": v.get("libelle", k)} for k, v in (y.get("types") or {}).items()], "genres": y.get("genres") or {}}

    @r.get("/portails-ckan")
    def portail_ckan(pays: str) -> dict[str, Any]:
        """Le portail de données ouvertes connu pour un pays — ou la phrase qui dit qu'il n'y en a pas, et propose l'ajout à la main."""
        code = pays.strip().upper()
        connus = portails_ckan(cfg)
        p = connus.get(code)
        if p:
            return {"pays": code, "portail": p["portail"], "verifie_le": str(p.get("verifie_le", "")), "message": ""}
        return {"pays": code, "portail": None, "verifie_le": "",
                "message": f"Aucun portail de données ouvertes de type CKAN n'est connu pour ce pays ({code or '?'}). "
                           "Si ton pays en a un, donne son adresse à la main, ou ajoute la source par la page Ajout."}  # fmt: skip

    @r.get("/catalogue-pays")
    def catalogue_du_pays(pays: str) -> dict[str, Any]:
        """Les bases officielles connues d'un pays (données : config/catalogue_pays/), cochées d'après les presets cochés. Ne télécharge rien."""
        coches = rg.charger(cfg).get("presets_coches") or []
        usages = [c["usage"] for c in presets._cartes_fichiers(cfg) if c.get("id") in coches and c.get("usage")]
        return catalogue_pays.pour_pays(cfg, pays, usages)

    @r.get("/catalogue-pays/taille")
    def taille_du_fichier(url: str) -> dict[str, Any]:
        """Le poids d'un fichier du catalogue, demandé au serveur. Refuse toute adresse absente du catalogue."""
        if url not in catalogue_pays.adresses_connues(cfg):
            raise HTTPException(404, "Cette adresse n'est pas dans le catalogue.")
        n = catalogue_pays.taille(url)
        libre = copies_locales.place_libre(cfg)
        return {"octets": n, "phrase": catalogue_pays.phrase_taille(n), "disque_libre_octets": libre, "tient": n is None or n < libre}

    @r.get("/copies-locales")
    def copies_locales_liste() -> dict[str, Any]:
        return {"copies": copies_locales.lister(cfg), "disque_libre": catalogue_pays.phrase_taille(copies_locales.place_libre(cfg)), "dossier": str(cfg.dossier_copies)}

    @r.get("/copies-locales/proposition")
    def copies_locales_proposition(pays: str, base: str, zone: str = "") -> dict[str, Any]:
        """Poids, place libre et licence, dits AVANT l'accord. N'écrit rien, ne télécharge rien."""
        try:
            return copies_locales.proposer(cfg, pays, base, zone=zone)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc

    @r.post("/copies-locales", status_code=201)
    def copies_locales_telecharger(corps: CorpsCopie) -> dict[str, Any]:
        try:
            copies_locales.refuser_filtre_mot_cle(corps.mot_cle)
            return copies_locales.telecharger(cfg, corps.pays, corps.base, confirme=corps.confirme, qui=corps.qui or cfg.qui_par_defaut, zone=corps.zone)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc

    @r.delete("/copies-locales/{copie_id}")
    def copies_locales_supprimer(copie_id: str, qui: str | None = None) -> dict[str, Any]:
        try:
            copies_locales.supprimer(cfg, copie_id, qui or cfg.qui_par_defaut)
        except ConfigRefusee as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"supprimee": copie_id}

    @r.post("/sources/{sid}/tester")
    def tester(sid: str) -> dict[str, Any]:
        """Test LOCAL : ne consomme rien (fiche 11)."""
        decls, _ = contexte()
        if sid not in decls:
            raise HTTPException(404, "Cette source n'existe pas.")
        res = tests_source.tester(cfg, decls[sid])
        return {**res, "etat_phrase": etat_phrase(lire_etat(cfg).get(sid), decls[sid])}

    @r.get("/sources/{sid}/test-reel")
    def test_reel_prix(sid: str) -> dict[str, Any]:
        """Le PRIX du test réel, dit avant le clic. N'appelle rien."""
        decls, _ = contexte()
        if sid not in decls:
            raise HTTPException(404, "Cette source n'existe pas.")
        d = decls[sid]
        reg, _ = rg.charger_tolerant(cfg)
        return {"source": sid, "nom": d.nom, "avertissement": d.avertissement,
                **tests_source.prix_du_test(d, rg.choix_source(reg, d)["cout"], budget.unites_du_mois(fabrique).get(sid, 0.0))}  # fmt: skip

    @r.post("/sources/{sid}/test-reel")
    def test_reel(sid: str, corps: CorpsTestReel) -> dict[str, Any]:
        """Facultatif : UNE vraie requête. Refusé tant que l'utilisateur n'a pas confirmé le prix, ou si le plafond mensuel ne le permet pas."""
        decls, _ = contexte()
        if sid not in decls:
            raise HTTPException(404, "Cette source n'existe pas.")
        d = decls[sid]
        reg, _ = rg.charger_tolerant(cfg)
        cout = rg.choix_source(reg, d)["cout"]
        prix = tests_source.prix_du_test(d, cout, budget.unites_du_mois(fabrique).get(sid, 0.0))
        if not corps.confirme:
            raise HTTPException(422, f"Confirmez d'abord le prix : {prix['phrase']}")
        qui = corps.qui or cfg.qui_par_defaut
        # sous verrou : deux tests réels lancés en même temps passaient tous les deux le plafond avant que l'un des deux
        # ne soit compté, et dépensaient donc le double de ce qui restait.
        with verrou(cfg.fichier_reglages):
            b = budget.vue(cfg, fabrique)
            if prix["dollars"] > 0 and prix["dollars"] > b["reste_usd"]:
                raise HTTPException(422, f"Le plafond mensuel ne permet pas ce test ({prix['phrase']} ; il reste {b['reste_usd']:.2f} $).".replace(".", ","))
            try:
                res = tests_source.test_reel(cfg, d, corps.mot, cout)
            except tests_source.Echec as exc:
                raise HTTPException(422, exc.raison) from exc
            unites = budget.unites_du_mois(fabrique).get(sid, 0.0)
            dollars = budget.dollars_pour(cout, res["appels"], unites)
            with fabrique.begin() as s:  # le test coûte de l'argent réel : il compte dans la dépense du mois, comme une recherche
                s.add(Recherche(qui=qui, sujet={"quoi": corps.mot, "test_reel": sid}, parametres={"test_reel": True}, etat="terminee",
                                couts={sid: {"unites": res["appels"] * float(cout.get("par_appel", 1) or 0), "dollars": dollars}} if dollars > 0 or cout.get("vers_dollar") else {},
                                message=f"Test réel de {d.nom}"))  # fmt: skip
        actions.noter(cfg, qui, "test_reel", sid)
        return {**res, "dollars": dollars}

    @r.post("/sources/{sid}/reprendre")
    def reprendre(sid: str, qui: str | None = None) -> dict[str, Any]:
        """Remet en service une source que le disjoncteur a mise en pause (geste de l'utilisateur, jamais automatique)."""
        decls, _ = contexte()
        if sid not in decls:
            raise HTTPException(404, "Cette source n'existe pas.")
        disjoncteur.reprendre(cfg, sid)
        actions.noter(cfg, qui or cfg.qui_par_defaut, "source_reprise", sid)
        return {"ok": True, "etat_phrase": etat_phrase(lire_etat(cfg).get(sid), decls[sid])}

    @r.post("/assistant/etape/{n}")
    def etape(n: int, corps: CorpsEtape) -> dict[str, Any]:
        """Rejoue UNE étape seule (depuis Réglages) : les deux autres ne sont pas touchées."""
        decls, _ = contexte()
        try:
            patch = assistant.patch_etape(n, corps.donnees, decls)
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        refuser_si_test_echoue(decls, patch)
        appliquer(patch, corps.qui, "assistant_etape", str(n), corps.confirme)
        return {"ok": True}

    @r.post("/assistant/terminer")
    def terminer(corps: CorpsTerminer) -> dict[str, Any]:
        """Dernier écran : écrit tout d'un coup (un seul fichier, une seule vérification) et ouvre le menu."""
        decls, _ = contexte()
        try:
            patch = assistant.fusion([
                assistant.patch_etape(1, corps.etape1, decls), assistant.patch_etape(2, corps.etape2, decls),
                assistant.patch_etape(3, corps.etape3, decls), {"assistant": {"termine": True}},
            ])  # fmt: skip
        except ConfigRefusee as exc:
            raise HTTPException(422, str(exc)) from exc
        refuser_si_test_echoue(decls, patch)
        appliquer(patch, corps.qui, "assistant_termine", "", corps.confirme)
        return {"ok": True}

    return r
