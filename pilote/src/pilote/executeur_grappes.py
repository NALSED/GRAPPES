"""Exécuteur réel : une recherche de pilote = une collecte de grappes dans un dossier de travail à elle (fondation 1).

Le dossier de travail est une COPIE de la configuration de grappes, adaptée au lancement ; la vraie configuration n'est jamais
modifiée. grappes tourne dans SON interpréteur (ses dépendances), via le pont `pont/executer.py`. L'avancement est lu dans le
fichier que grappes écrit lui-même ; l'arrêt est un fichier `ARRET` que le pont regarde : il arrête la collecte proprement
et GARDE ce qui est déjà en base.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from pilote import budget
from pilote import reglages as rg
from pilote.config import Config
from pilote.lancement import code_pays, exploration, limites, phrase_du_sujet
from pilote.moteur_sources import materialiser
from pilote.taches import Arret, ContexteRecherche

PONT = Path(__file__).resolve().parent / "pont" / "executer.py"
SRC_PILOTE = Path(__file__).resolve().parents[1]
ETAPES = ("recherche", "verification", "sortie")


def appels_par_source(fichier: Path, jetons: dict[str, str]) -> dict[str, int]:
    """Nombre d'appels réellement faits par chaque source, lu dans le fichier d'avancement (prise -> source par les jetons)."""
    n: dict[str, int] = {}
    if not fichier.exists():
        return n
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ligne)
        except ValueError:
            continue
        if e.get("evenement") == "appel":
            sid = jetons.get(str(e.get("prise", "")))
            if sid:
                n[sid] = n.get(sid, 0) + 1
    return n


def preparer(cfg: Config, ctx: ContexteRecherche) -> dict[str, Any]:
    """Crée la copie de travail et le fichier `lancement.json` ; rend la spécification."""
    d = ctx.dossier
    src = cfg.dossier_grappes_config
    if not src.is_dir():
        raise RuntimeError(f"la configuration de grappes est introuvable ({src}) ; voir grappes.racine dans la configuration de pilote")
    cible = d / "config"
    if cible.exists():
        shutil.rmtree(cible)
    shutil.copytree(src, cible, ignore=shutil.ignore_patterns("apprentissage", "__pycache__"))
    (cible / "apprentissage").mkdir()
    sujet, params = ctx.sujet, ctx.parametres
    phrase = phrase_du_sujet(sujet)
    lim = limites(cfg, params)
    c = lim["cran"]
    (cible / "sujets.yaml").write_text(yaml.safe_dump({"sujets": [{"nom": "recherche", "phrase": phrase}]}, allow_unicode=True), encoding="utf-8")
    plafond = budget.plafond_mensuel(cfg)
    depense, unites = ctx.depense_du_mois() if ctx._fabrique is not None else (0.0, {})
    mat = materialiser(cfg, cible, {**params, "_budget": {"appels_max": lim["appels"], "plafond": plafond, "depense": depense, "unites": unites}})  # les sources choisies, leurs clés, rien d'autre
    auto = yaml.safe_load((cible / "autonomie.yaml").read_text(encoding="utf-8")) or {}
    auto.pop("quotas", None)
    auto.pop("profondeur_max", None)
    # Les sources interrogées par adaptateur ou programme passent APRÈS la collecte de grappes : sans réserve, la collecte web mangeait toute la
    # limite d'appels et ces sources n'étaient jamais appelées, en silence. On leur garde un appel chacune.
    reserve_verif = min(max(3 * len(mat.verificateurs), lim["appels"] // 4), max(0, lim["appels"] - 1)) if mat.verificateurs else 0  # la vérification passe en dernier : sans part réservée, elle examine 0 nom
    reserve = min(len(mat.adaptateurs) + len(mat.scripts), max(0, lim["appels"] - 1 - reserve_verif))
    auto.update({
        "requetes_par_cycle": lim["appels"], "pages_par_cycle": c["pages"], "nouvelles_sources_par_cycle": c["nouvelles_sources"],
        "elements_par_cycle": c["observations"], "profondeur": exploration(params), "stop_file": "donnees/STOP", "rapports_dir": "rapports",
    })  # fmt: skip
    if params.get("lire_la_page") is False:  # extrait seulement : on ne lit pas les pages entières, seulement ce que la recherche rend
        auto["pages_par_cycle"] = 0
    if params.get("sites_a_ignorer"):  # sites à ignorer : grappes ne les visite pas (liste d'interdits de sa propre configuration)
        interdits = auto.get("interdits") or []
        if isinstance(interdits, dict):
            interdits["domaines"] = sorted({*(interdits.get("domaines") or []), *params["sites_a_ignorer"]})
        else:  # forme courte de grappes : une simple liste (un nom de domaine y est un domaine interdit)
            interdits = [*interdits, *(d for d in params["sites_a_ignorer"] if d not in interdits)]
        auto["interdits"] = interdits
    (cible / "autonomie.yaml").write_text(yaml.safe_dump(auto, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cl = yaml.safe_load((cible / "classement.yaml").read_text(encoding="utf-8")) or {}
    cl["actif"] = False  # le pont fait lui-même le classement des faits ; la sortie de profils de grappes n'est pas utilisée
    (cible / "classement.yaml").write_text(yaml.safe_dump(cl, allow_unicode=True, sort_keys=False), encoding="utf-8")
    cl["fournisseurs"] = {**(cl.get("fournisseurs") or {}), "registres": mat.registres}  # seulement les registres choisis
    (cible / "classement.yaml").write_text(yaml.safe_dump(cl, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for nom in ("donnees", "sorties", "rapports"):
        (d / nom).mkdir(exist_ok=True)
    for lien in ("plugins",):  # code et modèles partagés en lecture, jamais copiés
        cible_lien = d / lien
        if not cible_lien.exists() and (cfg.grappes_racine / lien).exists():
            cible_lien.symlink_to(cfg.grappes_racine / lien)
    for lien in ("modeles", "tranco"):
        cible_lien = d / "donnees" / lien
        if not cible_lien.exists() and (cfg.grappes_racine / "donnees" / lien).exists():
            cible_lien.symlink_to(cfg.grappes_racine / "donnees" / lien)
    entree: dict[str, Any] = {"quoi": str(sujet.get("quoi", "")), "lieu": str(sujet.get("lieu", "")), "mots_cles": list(sujet.get("inclure") or [])}
    if params.get("type_lieu"):  # choisi dans Recherches (fiche 12) : un type ou plusieurs
        entree["type_lieu"] = [str(t) for t in params["type_lieu"]] if isinstance(params["type_lieu"], list) else [str(params["type_lieu"])]
    if params.get("genre"):
        entree["genre"] = str(params["genre"])
    for v in mat.verificateurs:  # chaque vérificatrice a sa part de la réserve : la première ne mange pas tout
        v["parametres"] = {**(v.get("parametres") or {})}
        v["parametres"].setdefault("max_candidats", max(1, reserve_verif // len(mat.verificateurs)))
    spec = {
        "phrase": phrase, "limites": {"appels": lim["appels"], "temps_s": lim["temps_s"]},
        "mots_a_inclure": list(sujet.get("inclure") or []), "mots_a_exclure": list(sujet.get("exclure") or []),
        "combien": int(sujet.get("combien") or 200), "pays_code": code_pays(cfg, sujet, rg.charger_tolerant(cfg)[0]), "sources": mat.ids, "adaptateurs": mat.adaptateurs, "verificateurs": mat.verificateurs, "scripts": mat.scripts, "jetons": mat.jetons,
        "exclues_budget": mat.exclues_budget, "origines_sources": mat.origines, "mains_sources": mat.mains, "entree": entree,
        "plafond_atteint": depense >= plafond, "limite_source_s": min(float(lim["temps_s"]), 180.0) if lim.get("temps_s") else 180.0, "en_pause": mat.en_pause, "reserve_sources": reserve, "reserve_verification": reserve_verif,
    }  # fmt: skip
    if params.get("plan"):  # le plan de travail compilé (suite_plan) : les étapes à jouer sur les noms, les requêtes à traduire, les vérifications à restreindre
        plan = dict(params["plan"])
        sait_traduire = {a["source"] for a in mat.adaptateurs} | {s["source"] for s in mat.scripts}  # une source passée par le moteur de collecte de grappes n'a qu'une langue de requête
        plan["traduction_non_appliquee"] = sorted(s for s in plan.get("traductions", {}) if s not in sait_traduire)
        plan["traductions"] = {s: v for s, v in plan.get("traductions", {}).items() if s in sait_traduire}
        plan["traduction_url"] = cfg.suite_traduction_url
        spec["plan"] = plan
    (d / "lancement.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    return spec


class Suivi:
    """Lit le fichier d'avancement de grappes (une ligne JSON par événement) et en tire l'état à montrer."""

    def __init__(self, fichier: Path, appels_max: int):
        self.fichier, self.pos = fichier, 0
        self.etat: dict[str, Any] = {"etape": "recherche", "appels_faits": 0, "appels_prevus": appels_max, "noms": 0, "prise": "", "prises": {}, "jauges": {}}
        self.debut = time.time()

    def lire(self) -> dict[str, Any]:
        if self.fichier.exists():
            with self.fichier.open("rb") as f:
                f.seek(self.pos)
                brut = f.read()
            fin = brut.rfind(b"\n") + 1
            self.pos += fin
            for ligne in brut[:fin].decode("utf-8", "replace").splitlines():
                try:
                    self._un(json.loads(ligne))
                except (ValueError, KeyError):
                    continue
        self.etat["secondes"] = round(time.time() - self.debut, 1)
        return self.etat

    def _un(self, e: dict[str, Any]) -> None:
        s, ev = self.etat, e.get("evenement")
        if ev == "plan":
            for p, n in (e.get("prises") or {}).items():
                s["prises"].setdefault(p, {"prevus": 0, "faits": 0, "trouves": 0, "fini": False})["prevus"] = n
        elif ev == "prise_debut":
            s["prise"] = e.get("prise", "")
            s["prises"].setdefault(s["prise"], {"prevus": 0, "faits": 0, "trouves": 0, "fini": False})
        elif ev == "appel":
            s["appels_faits"] += 1
            p = e.get("prise", "")
            if p in s["prises"]:
                s["prises"][p]["faits"] += 1
        elif ev == "prise_fin":
            p = s["prises"].setdefault(e.get("prise", ""), {"prevus": 0, "faits": 0, "trouves": 0, "fini": False})
            p.update(trouves=int(e.get("trouves", 0)), fini=True)
            s["noms"] = int(e.get("noms", s["noms"]))
        elif ev == "etape":
            s["etape"] = e.get("etape", s["etape"])
        elif ev == "noms":
            s["noms"] = int(e.get("n", s["noms"]))
        elif ev == "fin":
            s["etape"] = "fini"


class ExecuteurGrappes:
    def __init__(self, cfg: Config, intervalle: float = 0.5):
        self.cfg, self.intervalle = cfg, intervalle

    def __call__(self, ctx: ContexteRecherche) -> None:
        spec = preparer(self.cfg, ctx)
        if spec["exclues_budget"]:  # le plafond de dépense a écarté des sources payantes : on le dit (la page Recherches l'affichera)
            ctx.avancer(sources_ecartees=spec["exclues_budget"], limitee_aux_gratuites=bool(spec.get("plafond_atteint")))
            ctx.noter("sources_ecartees_par_le_plafond", sources=spec["exclues_budget"])
        if spec["en_pause"]:  # le disjoncteur a mis des sources en pause : elles ne sont pas appelées, et on le dit
            ctx.avancer(sources_en_pause=spec["en_pause"])
            ctx.noter("sources_en_pause", sources=spec["en_pause"])
        suivi_fichier = ctx.dossier / "avancement.jsonl"
        suivi_fichier.unlink(missing_ok=True)
        (ctx.dossier / "ARRET").unlink(missing_ok=True)
        py = self.cfg.python_grappes
        if not py.exists():
            raise RuntimeError(f"l'interpréteur de grappes est introuvable ({py}) ; voir grappes.python dans la configuration")
        env = dict(os.environ, GRAPPES_AVANCEMENT=str(suivi_fichier), PYTHONPATH=os.pathsep.join([str(self.cfg.grappes_racine / "src"), str(SRC_PILOTE)]))
        with (ctx.dossier / "pont.log").open("w", encoding="utf-8") as log:
            proc = subprocess.Popen([str(py), str(PONT), str(ctx.dossier)], cwd=ctx.dossier, env=env, stdout=log, stderr=subprocess.STDOUT)
        suivi = Suivi(suivi_fichier, spec["limites"]["appels"])
        arret_demande = False
        while proc.poll() is None:
            ctx.avancer(**suivi.lire())
            if ctx.doit_s_arreter() and not arret_demande:
                (ctx.dossier / "ARRET").write_text("arrêt demandé\n", encoding="utf-8")  # le pont arrête la collecte proprement
                arret_demande = True
            time.sleep(self.intervalle)
        ctx.avancer(**suivi.lire())
        res_f = ctx.dossier / "resultat_pont.json"
        res = json.loads(res_f.read_text(encoding="utf-8")) if res_f.exists() else {"statut": "erreur", "message": "le pont n'a rien rendu"}
        if res["statut"] == "erreur":
            raise RuntimeError(res.get("message") or "le pont a échoué")
        if res["statut"] == "simulation":
            raise RuntimeError(res.get("message", "simulation"))
        self.faire_le_bilan(ctx, spec, suivi_fichier)
        self.dire_le_plan(ctx, spec, res.get("plan"))
        self.dire_la_verification(ctx, res.get("verifications") or [])
        lignes = json.loads((ctx.dossier / "candidats.json").read_text(encoding="utf-8")) if (ctx.dossier / "candidats.json").exists() else []
        ctx.ajouter_candidats(lignes)
        self.proposer_les_rapprochements(ctx)
        self.compter_couts(ctx, spec, suivi_fichier)
        ctx.avancer(noms=len(lignes), arret=res.get("arret", ""), duree_s=res.get("duree_s"))
        if res.get("arret") in ("demande",):
            raise Arret()

    def proposer_les_rapprochements(self, ctx: ContexteRecherche) -> None:
        """Range en file (onglet Tri) les noms que Splink soupçonne d'être la même entité. Un échec du moteur de rapprochement est DIT au journal :
        il ne fait jamais échouer la recherche, et l'absence de proposition ne se lit pas comme l'absence de rapprochement possible."""
        from pilote import rapprochements

        try:
            rapprochements.proposer(self.cfg, ctx._fabrique, ctx.recherche_id)  # l'événement « rapprochements_proposes » est écrit par `proposer` lui-même
        except Exception as exc:  # noqa: BLE001 - le tri est un confort de relecture, pas une condition de la recherche
            ctx.noter("rapprochements_indisponibles", raison=str(exc)[:300])

    def dire_le_plan(self, ctx: ContexteRecherche, spec: dict[str, Any], jeu: dict[str, Any] | None) -> None:
        """Ce que le plan de travail a FAIT à cette recherche, au journal et dans l'avancement : combien de noms chaque tuile a retirés (et
        lesquels, en partie), les requêtes traduites avec leur original, ce qui n'a pas été appliqué et pourquoi. Un nom retiré par un filtre n'est
        pas dans la base : sans cette trace, il aurait simplement disparu."""
        plan = spec.get("plan")
        if not plan:
            return
        jeu = jeu or {}
        par_tuile = jeu.get("par_tuile") or {}
        ctx.avancer(plan={
            "appliques": plan.get("appliques", []), "non_appliques": plan.get("non_appliques", []), "retires": jeu.get("retires", 0), "non_attribues": jeu.get("non_attribues", 0),
            "par_tuile": {k: {"nom": v["nom"], "n": v["n"]} for k, v in par_tuile.items()}, "erreurs": jeu.get("erreurs", []),
            "traductions": jeu.get("traductions", []), "traduction_non_appliquee": plan.get("traduction_non_appliquee", []),
        })  # fmt: skip
        for tuile, v in par_tuile.items():
            if v["n"]:
                ctx.noter("plan_noms_retires", tuile=tuile, outil=v["nom"], retires=v["n"], noms=v["noms"])
        for e in jeu.get("erreurs", []):
            ctx.noter("plan_script_en_echec", raison=e)
        for tr in jeu.get("traductions", []):
            ctx.noter("plan_requete_traduite" if "echec" not in tr else "plan_traduction_en_echec", **tr)
        if plan.get("traduction_non_appliquee"):
            ctx.noter("plan_traduction_non_appliquee", sources=plan["traduction_non_appliquee"], raison="la source passe par le moteur de collecte de grappes, qui n'a qu'une langue de requête")

    def dire_la_verification(self, ctx: ContexteRecherche, bilans: list[dict[str, Any]]) -> None:
        """Combien de noms chaque source de vérification a pu examiner. Une vérification coupée au milieu est DITE : sans cela,
        les noms non examinés ressemblaient à des noms vérifiés sans trouvaille."""
        if not bilans:
            return
        ctx.avancer(verifications=bilans)
        for b in bilans:
            if not b.get("complete"):
                ctx.noter("verification_incomplete", source=b["source"], examines=b["examines"], a_verifier=b["a_verifier"], raison=b.get("raison", ""))

    def faire_le_bilan(self, ctx: ContexteRecherche, spec: dict[str, Any], suivi_fichier: Path) -> None:
        """Combien de sources ont répondu sur combien ont été utilisées ; met à jour le disjoncteur de chacune."""
        from pilote import disjoncteur
        from pilote.sources import charger_sources

        decls, _ = charger_sources(self.cfg)
        # les sources de vérification comptent dans le bilan comme les autres : sinon leur panne n'augmentait aucun compteur,
        # le disjoncteur ne les arrêtait jamais, et « 1 source sur 1 a répondu » cachait une vérification en échec.
        utilisees = [*spec.get("sources", []), *(v["source"] for v in spec.get("verificateurs", []))]
        b = disjoncteur.bilan(self.cfg, suivi_fichier, spec.get("jetons", {}), utilisees, {i: d.nom for i, d in decls.items()})
        ctx.avancer(sources_bilan=b)
        if b["echecs"]:
            ctx.noter("sources_en_echec", sources=b["echecs"], bilan=b["phrase"])
        for p in b["nouvelles_pauses"]:
            ctx.noter("source_mise_en_pause", **p)

    def compter_couts(self, ctx: ContexteRecherche, spec: dict[str, Any], suivi_fichier: Path) -> None:
        """Garde ce que la recherche a coûté (sources payantes seulement) : c'est la dépense du mois, comparée au plafond."""
        from pilote import budget
        from pilote.moteur_sources import choisies, verificatrices

        n = appels_par_source(suivi_fichier, spec.get("jetons", {}))
        if not n:
            return
        reg, _ = rg.charger_tolerant(self.cfg)
        sources = {d.id: (d, rg.choix_source(reg, d)["cout"]) for d in [*choisies(self.cfg, ctx.parametres), *verificatrices(self.cfg, ctx.parametres)]}
        _, unites = ctx.depense_du_mois()
        ctx.enregistrer_couts(budget.couts_de_la_recherche(sources, n, unites))
