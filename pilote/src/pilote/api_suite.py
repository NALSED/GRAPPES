"""Routes de la suite pilote (spécification `suite/pilote`) : réglages des sources et des outils, plan de travail, recherches
sauvegardées, et les six fonctions de l'Aide. La logique est dans `suite.py` ; ici on ne fait que traduire HTTP."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from pilote import actions, budget, emoji_texte, rapprochements, suite, suite_modele, suite_plan, suite_reel, tri
from pilote.base import Candidat, Journal, Recherche
from pilote.config import Config
from pilote.refus import ConfigRefusee

Corps = Body(default_factory=dict)


def _refus(exc: ConfigRefusee, code: int = 422) -> HTTPException:
    return HTTPException(code, str(exc))


def _equivalences_de_pays(cfg: Config) -> dict[str, list[str]]:
    """« FR » et « France » sont le même pays pour un filtre : les deux écritures de `pays_proposes` se valent."""
    eq: dict[str, list[str]] = {}
    for code, nom in cfg.pays_proposes.items():
        ens = sorted({suite_plan.norme(code), suite_plan.norme(nom)})
        eq.update({k: ens for k in ens})
    return eq


def construire(cfg: Config, fabrique: sessionmaker[Session], gestionnaire: Any) -> APIRouter:
    r = APIRouter(prefix="/api/suite")

    def noter(corps: dict[str, Any], action: str, detail: str) -> None:
        actions.noter(
            cfg, str(corps.get("qui") or cfg.qui_par_defaut), action, detail
        )  # le NOM de l'objet, jamais une clé

    def appeler(fn, *a, **k):
        try:
            return fn(*a, **k)
        except ConfigRefusee as exc:
            raise _refus(exc) from exc

    def unites() -> dict[str, float]:
        return budget.unites_du_mois(fabrique)

    def etat_complet() -> dict[str, Any]:
        e = suite.charger(cfg, unites())
        v = suite.vue(cfg, e)
        with fabrique() as s:
            for rch in v["recherches"]:
                if rch.get("recherche_id"):
                    rch["resultat"] = _resultat(s, rch["recherche_id"]) or rch["resultat"]
                    rch["verification"] = _verification(s, rch["recherche_id"])
                    rch["ecartes"] = _ecartes(s, rch["recherche_id"])
                    rch["emoji"] = _emoji(s, rch["recherche_id"])
        v["modele"] = bool(cfg.suite_modele_url) and suite_modele.disponible(cfg.suite_modele_url)
        return v

    def _ecartes(s: Session, rid: str) -> dict[str, Any] | None:
        """Règle 1 : un nom écarté par un filtre ne disparaît pas en silence. Le nombre réel, et les noms que le journal a gardés (30 au plus par tuile)."""
        evts = s.scalars(select(Journal).where(Journal.recherche_id == rid, Journal.evenement == "plan_noms_retires")).all()
        n = sum(int((e.detail or {}).get("retires") or 0) for e in evts)
        if not n:
            return None
        return {"n": n, "noms": [x for e in evts for x in (e.detail or {}).get("noms", [])]}

    def _emoji(s: Session, rid: str) -> str:
        """« emoji non transmis à n sources » : la saisie contenait un emoji et ces sources ne déclarent pas le chercher."""
        rch = s.get(Recherche, rid)
        bilan = ((rch.avancement if rch else None) or {}).get("emoji") or {}
        non, aveugle = [str(x) for x in bilan.get("non_transmis") or []], [str(x) for x in bilan.get("a_l_aveugle") or []]
        nom_source = tri.noms_de_sources(cfg)
        morceaux = []
        if non:
            morceaux.append(f"emoji non transmis à {len(non)} source{'s' if len(non) > 1 else ''} : " + ", ".join(nom_source(x) for x in non))
        if aveugle:  # saisie faite seulement d'emoji : le moteur de collecte l'a reçue telle quelle, sans que ses sources déclarent le chercher
            morceaux.append(f"emoji envoyé tel quel à {len(aveugle)} source{'s' if len(aveugle) > 1 else ''} qui ne déclarent pas le chercher : " + ", ".join(nom_source(x) for x in aveugle))
        return " · ".join(morceaux)

    def _verification(s: Session, rid: str) -> str:
        """« X sur Y noms vérifiés » par source de vérification : une absence de signalement ne veut JAMAIS dire « vérifié » (décision du 27/10 : budget des clés gratuites, limite dite)."""
        rch = s.get(Recherche, rid)
        bilans = [b for b in ((rch.avancement if rch else None) or {}).get("verifications") or [] if isinstance(b, dict)]
        nom_source = tri.noms_de_sources(cfg)
        return " · ".join(
            f"{nom_source(str(b.get('source', '')))} : {b.get('examines', 0)} sur {b.get('a_verifier', 0)} noms {'enrichis' if b.get('fonction') == 'enrichir' else 'vérifiés'}" for b in bilans
        )

    def _resultat(s: Session, rid: str) -> str | None:
        rch = s.get(Recherche, rid)
        if rch is None:
            return None
        n = s.scalar(select(func.count()).select_from(Candidat).where(Candidat.recherche_id == rid)) or 0
        return {
            "terminee": f"{n} grappe{'s' if n > 1 else ''}",
            "arretee": f"arrêtée · {n} grappe{'s' if n > 1 else ''}",
            "echec": "échec",
            "interrompue": "interrompue",
        }.get(rch.etat, "en cours")

    @r.get("/etat")
    def etat() -> dict[str, Any]:
        return etat_complet()

    # ----- sources
    @r.post("/sources", status_code=201)
    def source_ajouter(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        s = appeler(suite.ajouter_source, cfg, corps)
        noter(corps, "suite_source_ajoutee", s["id"])
        return {"id": s["id"]}

    @r.put("/sources/{ident}")
    def source_modifier(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.modifier_source, cfg, ident, corps)
        noter(corps, "suite_source_modifiee", ident)
        return {"id": ident}

    @r.post("/sources/{ident}/allumer")
    def source_allumer(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        try:
            s = suite.changer_etat_source(cfg, ident, True, bool(corps.get("confirme")))
        except (
            suite_reel.AvertissementRequis
        ) as exc:  # la page montre l'avertissement, puis redemande avec « confirme »
            raise HTTPException(409, {"avertissements": exc.avertissements}) from exc
        except ConfigRefusee as exc:
            raise _refus(exc) from exc
        noter(corps, "suite_source_allumee", ident)
        return {"etat": s["etat"]}

    @r.post("/sources/{ident}/eteindre")
    def source_eteindre(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.changer_etat_source, cfg, ident, False)
        noter(corps, "suite_source_eteinte", ident)
        return {"etat": "off"}

    @r.post("/sources/{ident}/retirer")
    def source_retirer(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.retirer_source, cfg, ident)
        noter(corps, "suite_source_retiree", ident)
        return {"retiree": True}

    @r.post("/sources/{ident}/rajouter")
    def source_rajouter(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.rajouter_source, cfg, ident)
        noter(corps, "suite_source_rajoutee", ident)
        return {"retiree": False}

    @r.post("/sources/{ident}/test")
    def source_test(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        res = appeler(suite.tester_source, cfg, ident)
        noter(corps, "suite_source_testee", f"{ident} {'ok' if res['ok'] else 'echec'}")
        return {"ok": res["ok"], "raisons": res["raisons"], "etat": res["source"]["etat"]}

    @r.put("/sources/{ident}/cle")
    def source_cle(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.enregistrer_cle, cfg, "source", ident, str(corps.get("valeur", "")))
        noter(corps, "suite_cle_source_enregistree", ident)
        return {"cle": True}  # jamais la valeur

    # ----- outils
    @r.post("/outils", status_code=201)
    def outil_ajouter(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        o = appeler(suite.ajouter_outil, cfg, corps)
        noter(corps, "suite_outil_ajoute", o["id"])
        return {"id": o["id"]}

    @r.put("/outils/{ident}")
    def outil_modifier(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.modifier_outil, cfg, ident, corps)
        noter(corps, "suite_outil_modifie", ident)
        return {"id": ident}

    @r.post("/outils/{ident}/allumer")
    def outil_allumer(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        o = appeler(suite.allumer_outil, cfg, ident, bool(corps.get("avertissement_lu")))
        noter(corps, "suite_outil_allume", ident)
        return {"etat": o["etat"]}

    @r.post("/outils/{ident}/eteindre")
    def outil_eteindre(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.eteindre_outil, cfg, ident)
        noter(corps, "suite_outil_eteint", ident)
        return {"etat": "off"}

    @r.post("/outils/{ident}/retirer")
    def outil_retirer(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.retirer_outil, cfg, ident, True)
        noter(corps, "suite_outil_retire", ident)
        return {"retire": True}

    @r.post("/outils/{ident}/rajouter")
    def outil_rajouter(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.retirer_outil, cfg, ident, False)
        noter(corps, "suite_outil_rajoute", ident)
        return {"retire": False}

    @r.post("/outils/{ident}/test")
    def outil_test(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        res = appeler(suite.tester_outil, cfg, ident)
        noter(corps, "suite_outil_teste", f"{ident} {'ok' if res['ok'] else 'echec'}")
        return {k: res[k] for k in ("ok", "sortie", "raisons", "execute")} | {"etat": res["outil"]["etat"]}

    @r.put("/outils/{ident}/cle")
    def outil_cle(ident: str, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.enregistrer_cle, cfg, "outil", ident, str(corps.get("valeur", "")))
        noter(corps, "suite_cle_outil_enregistree", ident)
        return {"cle": True}

    # ----- plan de travail et recherche simple
    @r.put("/plan")
    def plan_ecrire(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        appeler(suite.ecrire_plan, cfg, corps)
        return {"ok": True}

    @r.put("/simple")
    def simple_ecrire(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        def f(e):
            e["simple"] = {
                "preset": corps.get("preset") if corps.get("preset") in suite.CATS else "entreprises",
                "pays": str(corps.get("pays") or "Tous")[:20], "ov": corps.get("ov") if isinstance(corps.get("ov"), dict) else {},
                "saisie": str(corps.get("saisie") or "")[:300],
            }  # fmt: skip

        suite.modifier(cfg, f)
        return {"ok": True}

    # ----- recherches sauvegardées et lancement
    @r.post("/recherches", status_code=201)
    def recherche_sauver(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        rch = appeler(suite.sauvegarder_recherche, cfg, corps)
        noter(corps, "suite_recherche_sauvee", rch["id"])
        return {"id": rch["id"]}

    @r.delete("/recherches/{ident}")
    def recherche_supprimer(ident: str, confirme: bool = False, qui: str | None = None) -> dict[str, Any]:
        try:
            suite.supprimer_recherche(cfg, ident, confirme)
        except ConfigRefusee as exc:
            raise _refus(exc, 409 if not confirme else 404) from exc
        actions.noter(cfg, qui or cfg.qui_par_defaut, "suite_recherche_supprimee", ident)
        return {"supprimee": True}

    @r.post("/lancer", status_code=202)
    def lancer(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        """Lance la recherche avec le moteur de pilote, sur les SOURCES choisies (les cases de la Recherche simple, les tuiles source du plan).
        Le moteur interroge ces sources puis regroupe : l'ordre des liens du plan et les outils posés ne sont pas encore appliqués (QUESTIONS
        suite-2). Une source choisie qui ne peut pas chercher est écartée et la réponse dit laquelle, et pourquoi."""
        saisie = str(corps.get("saisie") or "").strip()
        if not saisie:
            raise HTTPException(422, "Dis ce que tu cherches.")
        e = suite.charger(cfg, unites())
        par_id = {s["id"]: s for s in e["sources"]}
        comp: dict[str, Any] | None = None
        if corps.get("mode") == "Avancée" and corps.get(
            "plan"
        ):  # le plan est APPLIQUÉ : liens, branches et outils (suite_plan)
            try:
                plan = suite._plan_valide(corps["plan"])
                comp = suite_plan.compiler(plan, e["sources"], e["outils"], pays_equiv=_equivalences_de_pays(cfg), langue_saisie=suite.detecter_langue(saisie),
                                           traduction_disponible=bool(cfg.suite_traduction_url))  # fmt: skip
            except ConfigRefusee as exc:
                raise _refus(exc) from exc
            voulues = comp["sources"]
        else:
            voulues = [x for x in dict.fromkeys(corps.get("sources") or []) if isinstance(x, str)]
        if not voulues:
            raise HTTPException(422, "Choisis au moins une source.")
        retenues, ecartees = [], []
        for ident in voulues:
            s = par_id.get(ident)
            if s is None:
                raise HTTPException(422, f"La source « {ident} » n'existe pas.")
            raison = (
                "elle est éteinte dans Réglages" if s["etat"] == "off"
                else "elle ne fait que vérifier : elle ne cherche pas" if not s["peut_chercher"]
                else "sa clé d'API est absente" if s["cle_requise"] and not s["cle"]
                else "elle demande un adaptateur" if s["adaptateur_manquant"]
                else ""
            )  # fmt: skip
            (ecartees.append({"id": ident, "nom": s["nom"], "raison": raison}) if raison else retenues.append(ident))
        verifs: list[str] = []
        for v in comp["verificateurs"] if comp else []:
            s = par_id.get(v["id"])
            if s is None:
                raise HTTPException(422, f"La source « {v['id']} » n'existe pas.")
            verbe = "enrichit" if v.get("fonction") == "enrichir" else "vérifie"
            raison = (
                "elle est éteinte dans Réglages" if s["etat"] == "off"
                else f"elle ne {verbe} ni par l'adresse, ni par le nom, ni par la ville d'un résultat" if not s["verifie_sur"]
                else "sa clé d'API est absente" if s["cle_requise"] and not s["cle"]
                else ""
            )  # fmt: skip
            (ecartees.append({"id": v["id"], "nom": s["nom"], "raison": raison}) if raison else verifs.append(v["id"]))
        if not retenues:
            raise HTTPException(
                422,
                "Aucune des sources choisies ne peut chercher : "
                + " ; ".join(f"{x['nom']} ({x['raison']})" for x in ecartees)
                + ".",
            )
        qui = str(corps.get("qui") or cfg.qui_par_defaut)
        sujet = {"quoi": saisie[:300]}
        if corps.get("pays") == "FR":
            sujet["pays"] = "France"
        params: dict[str, Any] = {"sources": retenues}
        if comp is not None:
            params["plan"] = comp
            params["verificatrices"] = verifs
            if comp["format"]:
                params["sortie"] = {"actifs": comp["format"]}
        with fabrique.begin() as s:
            from pilote import reglages as rg_fichier

            params["verification"] = bool(rg_fichier.charger_tolerant(cfg)[0]["verification"]["active"])
            rch = Recherche(qui=qui, sujet=sujet, parametres=params)
            s.add(rch)
            s.flush()
            s.add(
                Journal(
                    recherche_id=rch.id, qui=qui, evenement="creation", detail={"origine": "suite", "sources": retenues}
                )
            )
            rid = rch.id
        entree = (
            suite.sauvegarder_recherche(
                cfg, {**corps, "titre": corps.get("titre") or saisie[:80], "resultat": "en cours", "recherche_id": rid}
            )
            if corps.get("sauver", True)
            else None
        )
        gestionnaire.lancer(rid)
        return {
            "recherche_id": rid,
            "id": entree["id"] if entree else None,
            "lancees": [par_id[i]["nom"] for i in retenues],
            "ecartees": ecartees,
            "verifient": [par_id[i]["nom"] for i in verifs],
            "appliques": comp["appliques"] if comp else [],
            "non_appliques": comp["non_appliques"] if comp else [],
        }

    # ----- Tri : la file des rapprochements (spécification 16)
    @r.get("/tri")
    def tri_file() -> dict[str, Any]:
        return rapprochements.file(cfg, fabrique)

    def _trancher(ident: int, action: str, corps: dict[str, Any]) -> dict[str, Any]:
        qui = str(corps.get("qui") or cfg.qui_par_defaut)
        try:
            return rapprochements.trancher(cfg, fabrique, ident, action, qui)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @r.post("/tri/{ident}/confirmer")
    def tri_confirmer(ident: int, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return _trancher(ident, "confirme", corps)

    @r.post("/tri/{ident}/separer")
    def tri_separer(ident: int, corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return _trancher(ident, "separe", corps)

    @r.post("/tri/proposer/{rid}")
    def tri_proposer(rid: str) -> dict[str, Any]:
        """Relance la recherche de rapprochements d'une recherche terminée (déjà faite à la fin de chaque recherche)."""
        try:
            return rapprochements.proposer(cfg, fabrique, rid)
        except rapprochements.Indisponible as exc:
            raise HTTPException(503, str(exc)) from exc

    # ----- l'Aide : les six fonctions, une route chacune
    @r.post("/aide/lister_sources")
    def aide_lister(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return {
            "sources": suite.lister_sources(
                suite.charger(cfg, unites()), corps.get("role"), corps.get("pays"), corps.get("etat")
            )
        }

    @r.post("/aide/lire_plan")
    def aide_lire() -> dict[str, Any]:
        return suite.lire_plan(suite.charger(cfg, unites()))

    @r.post("/aide/proposer_plan")
    def aide_proposer(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return appeler(
            suite.proposer_plan, suite.charger(cfg, unites()), str(corps.get("objectif", "")), corps.get("pays")
        )

    @r.post("/aide/verifier_plan")
    def aide_verifier(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        langue = suite.detecter_langue(str(corps["saisie"])) if corps.get("saisie") else corps.get("langue")
        return {"constats": suite.verifier_plan(suite.charger(cfg, unites()), langue, saisie_emoji=emoji_texte.contient(str(corps.get("saisie") or ""))), "langue_saisie": langue}

    @r.post("/aide/definir")
    def aide_definir(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return appeler(suite.definir, cfg, str(corps.get("mot", "")))

    @r.post("/aide/ouvrir")
    def aide_ouvrir(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return appeler(suite.ouvrir, str(corps.get("ecran", "")))

    @r.get("/aide/mots")
    def aide_mots() -> dict[str, Any]:
        return {"mots": sorted(suite.mots(cfg))}

    @r.get("/aide/objectifs")
    def aide_objectifs() -> dict[str, Any]:
        return {"objectifs": [{"id": k, "phrase": v, "categorie": suite.CATS[k]} for k, v in suite.OBJECTIFS.items()]}

    @r.post("/aide/phrase")
    def aide_phrase(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        """La phrase libre : le modèle CHOISIT une fonction, on l'exécute, et la page met en forme le retour. Sans modèle, rien ne se passe."""
        phrase = str(corps.get("phrase", "")).strip()
        if not phrase:
            raise HTTPException(422, "Écris ta question.")
        if not cfg.suite_modele_url or not suite_modele.disponible(cfg.suite_modele_url):
            return {"modele": False}
        choix = suite_modele.choisir_fonction(cfg.suite_modele_url, phrase)
        if choix is None:
            return {"modele": True, "fonction": None}
        a, f = choix["args"], choix["fonction"]
        e = suite.charger(cfg, unites())
        try:
            res = {
                "lister_sources": lambda: {
                    "sources": suite.lister_sources(e, a.get("role"), a.get("pays"), a.get("etat"))
                },
                "lire_plan": lambda: suite.lire_plan(e),
                "proposer_plan": lambda: suite.proposer_plan(e, str(a.get("objectif", "")), a.get("pays")),
                "verifier_plan": lambda: {"constats": suite.verifier_plan(e, None)},
                "definir": lambda: suite.definir(cfg, str(a.get("mot", ""))),
                "ouvrir": lambda: suite.ouvrir(str(a.get("ecran", ""))),
            }[f]()
        except ConfigRefusee as exc:
            return {"modele": True, "fonction": f, "refus": str(exc)}
        return {"modele": True, "fonction": f, "resultat": res}

    @r.post("/langue")
    def langue(corps: dict[str, Any] = Corps) -> dict[str, Any]:
        return {"langue": suite.detecter_langue(str(corps.get("texte", "")))}

    return r
