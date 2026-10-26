"""Pont entre pilote et grappes (D70) : UNE recherche de grappes, dans un dossier de travail à elle.

Lancé par pilote avec l'interpréteur de GRAPPES (`python executer.py <dossier>`), le dossier courant étant le dossier de
travail. N'importe rien de pilote (seulement la bibliothèque grappes, trouvée par `PYTHONPATH`). Lit `lancement.json`,
écrit `candidats.json` et `resultat_pont.json`. L'avancement est écrit par grappes lui-même (`GRAPPES_AVANCEMENT`).

Étapes (les fonctions sont celles de `grappes.cycle.engine`, appelées une fois chacune) : amorçage du sujet, collecte,
mise à jour des registres de fiabilité, recoupement (`run`), puis classement des candidats pour en tirer leurs FAITS.
Un arrêt demandé (fichier `ARRET`), la limite de temps ou la limite d'appels arrêtent la collecte PROPREMENT : ce qui est
déjà en base est gardé et passe par le recoupement et le classement.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path

from grappes import avancement


def main(dossier: str) -> int:
    os.chdir(dossier)
    spec = json.loads(Path("lancement.json").read_text(encoding="utf-8"))
    t0 = time.time()
    arret_fichier = Path("ARRET")
    appels_max = int(spec["limites"]["appels"])
    # Appels gardés pour les sources interrogées par adaptateur ou programme, qui passent après la collecte : la collecte s'arrête plus tôt, de
    # sorte qu'une source explicitement choisie ne se fasse jamais manger son appel par la récupération d'une page web.
    reserve = min(int(spec.get("reserve_sources") or 0), max(0, appels_max - 1))
    temps_max = float(spec["limites"]["temps_s"]) if spec["limites"].get("temps_s") else None
    resultat = {"statut": "erreur", "arret": "", "message": ""}

    def appels_faits() -> int:
        f = os.environ.get(avancement.VARIABLE)
        if not f or not Path(f).exists():
            return 0
        return sum(1 for ligne in Path(f).read_text(encoding="utf-8").splitlines() if '"evenement": "appel"' in ligne)

    pause_fichier = Path("PAUSE")
    pause = {"depuis": None, "total": 0.0}
    verrou_pause = threading.Lock()

    def temps_en_pause() -> float:
        """Secondes passées en pause (la pause ne compte pas dans la limite de temps ni dans celle d'une source)."""
        with verrou_pause:
            if pause_fichier.exists() and pause["depuis"] is None:
                pause["depuis"] = time.time()
            elif not pause_fichier.exists() and pause["depuis"] is not None:
                pause["total"] += time.time() - pause["depuis"]
                pause["depuis"] = None
            return pause["total"] + (time.time() - pause["depuis"] if pause["depuis"] is not None else 0.0)

    def raison_d_arret(marge: int = 0) -> str:
        if arret_fichier.exists():
            return "demande"
        if temps_max is not None and time.time() - t0 - temps_en_pause() > temps_max:
            return "temps"
        if appels_faits() >= appels_max - marge:
            return "appels"
        return ""

    def doit_s_arreter(marge: int = 0) -> bool:
        while pause_fichier.exists() and not arret_fichier.exists():  # pause demandée : on attend ici, sans rien perdre
            temps_en_pause()
            time.sleep(0.3)
        temps_en_pause()
        r = raison_d_arret(marge)
        if r:
            resultat["arret"] = resultat["arret"] or (r if not marge else raison_d_arret() or "")
        return bool(r)

    def arret_collecte() -> bool:
        """Arrêt de la COLLECTE de grappes : elle laisse la réserve d'appels aux sources qui passent après elle."""
        return doit_s_arreter(reserve)

    try:
        from grappes import vraisemblance as vr
        from grappes.amorcage import amorcer  # noqa: F401  (utilisé par _seed_subjects)
        from grappes.autonomy import load_autonomy
        from grappes.canon import site_key
        from grappes.classement import fusion
        from grappes.classement.candidats import charger
        from grappes.classement.production import charger_calibreur, charger_config, classer
        from grappes.config import load_config
        from grappes.cycle.collect import collect
        from grappes.cycle.engine import _seed_subjects, _update_fiabilite
        from grappes.decouverte.client import Http
        from grappes.decouverte.registres import DecouverteConfig, decouvrir
        from grappes.fetch import PageFetcher
        from grappes.ner.extraire import charger_config as charger_ner
        from grappes.ner.extraire import extraire
        from grappes.pipeline import run
        from grappes.search.base import Journal
        from grappes.search.config import load_search_config
        from grappes.storage.db import Database

        config = Path("config")
        from grappes.env import load_secrets

        load_secrets(config / "secrets.env")  # les clés des sources UTILISÉES (copie écrite par pilote) : les prises web les lisent dans l'environnement, comme en ligne de commande
        auto = load_autonomy(config)
        if not auto.autonome:
            resultat.update(statut="simulation", message="`autonome` est faux dans la configuration de grappes : aucun appel réel.")
            Path("resultat_pont.json").write_text(json.dumps(resultat, ensure_ascii=False), encoding="utf-8")
            return 0
        cfg, scfg = load_config(config), load_search_config(config)
        avancement.signaler("budget", requetes=auto.requetes_par_cycle, pages=auto.pages_par_cycle, appels_max=appels_max)
        avancement.signaler("etape", etape="recherche")
        db = Database(Path("donnees/grappes.db"))
        cfg, _graine, utilises, _etats = _seed_subjects(cfg, scfg, auto, _Chemins(config), 1, {}, 0)
        if spec.get("mots_a_inclure"):  # mots demandés : ajoutés au lexique de départ du sujet, au poids d'amorçage
            cfg = _ajouter_mots(cfg, config, spec["mots_a_inclure"], auto.amorcage_poids)
        fetcher = PageFetcher(auto, Journal(scfg.journal))
        budget = replace(auto, requetes_par_cycle=max(auto.requetes_par_cycle - utilises, 0))
        collect(db, cfg, scfg, budget, fetcher, execute=True, should_stop=arret_collecte)
        if not arret_collecte():
            avancement.signaler("etape", etape="verification")
            _update_fiabilite(db, cfg, scfg, None, __import__("datetime").datetime.now(__import__("datetime").UTC))
        else:
            avancement.signaler("etape", etape="verification")
        run(db, cfg)
        cc = charger_config(config)
        ctx = charger(None, cfg, db)
        phrase = cfg.grappes[0].subject
        if cc.registres:
            http = _http_borne(Http, arret_collecte)(Path("donnees/decouverte_cache"), delai_s=1.0, ttl_jours=cc.cache_jours)
            from grappes.decouverte.client import DecouverteError

            for source in cc.registres:  # une source à la fois : si la limite d'appels tombe au milieu de l'une, les autres restent
                try:
                    ctx.decouverts += decouvrir(phrase, http, DecouverteConfig(sources=(source,), naf=str(config / "naf_rev2.csv"), dossier_sources=str(config / "recherche")))
                    avancement.signaler("source_ok", prise=source)
                except DecouverteError as exc:
                    if not arret_collecte():  # arrêt, temps ou appels : pas une panne de la source
                        avancement.signaler("source_echec", prise=source, raison=str(exc)[:200] or "la source n'a pas répondu")
                except Exception as exc:  # noqa: BLE001 - une source de noms qui plante n'arrête pas les autres
                    avancement.signaler("source_echec", prise=source, raison=f"défaut inattendu ({type(exc).__name__})")
        from grappes.decouverte.registres import Decouvert

        from pilote import adaptateurs
        from pilote.adaptateurs import programmes

        entree_base = {"sujet": phrase, "pays": spec.get("pays_code", ""), "limite": int(spec.get("combien", 200)), **spec.get("entree", {})}

        def vers_decouvert(source: str, n: dict) -> Decouvert:
            num = str(n.get("numero", "") or "")
            return Decouvert(
                str(n["nom"]).strip(), source, num or str(n["nom"]).strip(), str(n.get("ville", "") or ""), str(n.get("site", "") or ""),
                num if num.isdigit() and len(num) in (9, 14) else "", str(n.get("origine", "")), str(n.get("genre", "") or ""), "",
                {k: json.dumps(n[k], ensure_ascii=False) for k in ("relations", "coordonnees", "fonction") if n.get(k)},
            )  # fmt: skip

        def cles_de_la_copie() -> dict[str, str]:
            out: dict[str, str] = {}
            f = config / "secrets.env"
            for ligne in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
                nom, _, val = ligne.partition("=")
                if nom.strip() and val.strip():
                    out[nom.strip()] = val.strip()
            return out

        plan = spec.get("plan") or {}
        effets_traduction: list[dict] = []
        traduits: dict[tuple, dict] = {}

        def entree_de(source: str) -> dict:
            """La requête que reçoit cette source : traduite vers sa langue si le plan place une Traduction avant elle (l'original reste dans le journal)."""
            t = (plan.get("traductions") or {}).get(source)
            if not t:
                return entree_base
            cle = (t["de"], t["vers"])
            if cle not in traduits:
                from pilote.suite_traduction import traduire

                try:
                    traduits[cle] = {k: traduire(plan["traduction_url"], entree_base[k], t["de"], t["vers"]) for k in ("sujet", "quoi") if entree_base.get(k)}
                    effets_traduction.append({"de": t["de"], "vers": t["vers"], "original": {k: entree_base[k] for k in traduits[cle]}, "traduit": traduits[cle]})
                except (OSError, ValueError) as exc:  # le moteur de traduction a échoué : la source cherche avec la requête d'origine, et on le dit
                    traduits[cle] = {}
                    effets_traduction.append({"de": t["de"], "vers": t["vers"], "echec": str(exc)[:200]})
            return {**entree_base, **traduits[cle]}

        secrets = cles_de_la_copie()  # seulement les clés des sources utilisées (écrites par pilote dans la copie de configuration)
        executions = [
            (a["source"], lambda a=a: adaptateurs.charger(a["module"]).chercher(
                entree_de(a["source"]), adaptateurs.Client(a["source"], doit_s_arreter, signaler=avancement.signaler, delai_s=a.get("delai_s", 0.2)),
                {**a.get("parametres", {}), **({"_cle": secrets.get(a["cles_noms"][0], ""), "_cles": {n: secrets.get(n, "") for n in a["cles_noms"]}} if a.get("cles_noms") else {})}))
            for a in spec.get("adaptateurs", [])
        ]  # fmt: skip
        executions += [(sc["source"], lambda sc=sc: programmes.executer(sc, entree_de(sc["source"]), cwd=Path.cwd())) for sc in spec.get("scripts", [])]
        limite_source = float(spec.get("limite_source_s") or 180)

        def isole(executer_):
            """Une source tourne ISOLÉE : son erreur (quelle qu'elle soit) ou son dépassement de temps n'arrête que cette source."""
            sortie: dict = {}

            def tourne() -> None:
                try:
                    sortie["noms"] = executer_()
                except BaseException as exc:  # noqa: BLE001 - la recherche continue avec les autres sources
                    sortie["exc"] = exc

            t = threading.Thread(target=tourne, daemon=True)
            t.start()
            debut, pause0 = time.time(), temps_en_pause()
            while t.is_alive():
                t.join(0.5)
                if t.is_alive() and time.time() - debut - (temps_en_pause() - pause0) > limite_source:
                    return None, f"délai dépassé ({limite_source:g} s)"
            if "exc" in sortie:
                raise sortie["exc"]
            return sortie["noms"], ""

        for n, (source, executer_) in enumerate(executions):
            if doit_s_arreter():
                # une source choisie qui n'est PAS appelée doit être dite : sans cela, « n sources sur n ont répondu » comptait
                # des sources jamais interrogées, et leur silence ressemblait à une absence de résultat.
                for reste, _ in executions[n:]:
                    avancement.signaler("source_echec", prise=reste, raison=f"non appelée : {resultat['arret'] or 'limite'} atteint avant son tour")
                break
            avancement.signaler("prise_debut", prise=source)
            raison = ""
            try:
                noms, raison = isole(executer_)
                if noms is None:
                    noms, statut = [], f"erreur : {raison}"
                else:
                    statut = "ok"
            except adaptateurs.LimiteAtteinte:
                doit_s_arreter()
                noms, statut = [], "arrêté"
            except adaptateurs.ErreurSource as exc:
                noms, statut, raison = [], f"erreur : {exc}", str(exc)
            except Exception as exc:  # noqa: BLE001 - un défaut d'une source ne doit jamais faire échouer la recherche
                noms, statut, raison = [], f"erreur : {type(exc).__name__}", f"la source a rencontré un défaut inattendu ({type(exc).__name__})"
            if statut.startswith("erreur"):
                avancement.signaler("source_echec", prise=source, raison=raison)
            elif statut == "ok":
                avancement.signaler("source_ok", prise=source)
            ctx.decouverts += [vers_decouvert(source, n) for n in noms]
            avancement.signaler("prise_fin", prise=source, trouves=len(noms), noms=len(noms), statut=statut)
        ner = charger_ner(config)
        if cc.noms and ner.modeles:
            ctx.nommes = extraire([(o.obs_id, o.source.key, o.text) for o in db.load_observations()], ner, Path("donnees/ner_cache"))
        lr = vr.charger(config / "lr.yaml")
        cal = charger_calibreur(config / Path(cc.calibration).name)
        classes = classer(ctx, cc, lr, cal)
        par_nom: dict[str, list] = {}
        for d in ctx.decouverts:
            par_nom.setdefault(fusion.norm_name(d.nom), []).append(d)
        from pilote.pont.faits import Provenance, faits_candidat

        eco_par_site: dict[str, str] = {}
        for o in db.load_observations():
            eco, _, ident = o.source.key.partition(":")
            eco_par_site[site_key(ident) if eco in ("web", "rss") else o.source.key] = eco
        fournisseurs_par_site: dict[str, set[str]] = {}
        fav = os.environ.get(avancement.VARIABLE)
        for ligne in (Path(fav).read_text(encoding="utf-8").splitlines() if fav and Path(fav).exists() else []):
            if '"evenement": "trouve"' in ligne:
                try:
                    e = json.loads(ligne)
                except ValueError:
                    continue
                eco, _, ident = e["cle"].partition(":")
                fournisseurs_par_site.setdefault(site_key(ident) if eco in ("web", "rss") else e["cle"], set()).add(e["prise"])
        prov = Provenance(spec.get("jetons", {}), spec.get("origines_sources", {}), spec.get("mains_sources", {}), eco_par_site, fournisseurs_par_site)
        exclus = [fusion.norm_name(m) for m in spec.get("mots_a_exclure", []) if m.strip()]
        lignes, vus = [], set()
        for c, _lg, _p in classes:
            nn = fusion.norm_name(c.nom or "")
            if not nn or nn in vus or any(m in nn.split() or m in nn for m in exclus):
                continue
            vus.add(nn)
            lignes.append(faits_candidat(c, par_nom.get(nn, []), site_key, spec.get("pays_code", ""), prov))
            if len(lignes) >= int(spec.get("combien", 200)):
                break
        if plan.get("chemins") is not None:  # le plan de travail : on ne garde que les noms que ses branches laissent passer, AVANT de vérifier (inutile de vérifier ce qu'on retire)
            from pilote import suite_plan, suite_script

            lignes, bilan_plan = suite_plan.appliquer(lignes, plan, suite_script.executer)
            resultat["plan"] = {**bilan_plan, "traductions": effets_traduction}
        from pilote.pont.verification import verifier_candidats

        # la vérification des candidats appartient à l'étape « vérification » : la jauge doit couvrir le travail qu'elle annonce.
        bilans = verifier_candidats(lignes, spec, secrets, doit_s_arreter, limite_source, avancement.signaler)
        avancement.signaler("etape", etape="sortie")
        Path("candidats.json").write_text(json.dumps(lignes, ensure_ascii=False, indent=1), encoding="utf-8")
        resultat["verifications"] = bilans
        avancement.signaler("noms", n=len(lignes))
        avancement.signaler("fin", statut="ok", arret=resultat["arret"])
        resultat.update(statut="ok", noms=len(lignes), appels=appels_faits(), duree_s=round(time.time() - t0, 1))
        db.close()
    except Exception as exc:  # noqa: BLE001 - tout est rendu à pilote en clair
        resultat.update(statut="erreur", message=f"{type(exc).__name__} : {exc}", trace=traceback.format_exc(limit=6))
    Path("resultat_pont.json").write_text(json.dumps(resultat, ensure_ascii=False), encoding="utf-8")
    return 0 if resultat["statut"] in ("ok", "simulation") else 1


def _http_borne(Http, doit_s_arreter):
    """Client de découverte qui REFUSE tout nouvel appel réseau dès qu'un arrêt est demandé ou qu'une limite (temps, appels)
    est atteinte ; les réponses déjà en cache passent. La découverte rend alors ce qu'elle a : une limite est une vraie
    limite, pas une indication."""
    from grappes.decouverte.client import DecouverteError

    class HttpBorne(Http):
        def _plein(self, url: str, suffixe: str) -> bool:
            p = self._path(url)
            p = p.with_suffix(suffixe) if suffixe else p
            return not (p.exists() and not self._perime(p)) and doit_s_arreter()

        def get_json(self, url):
            if self._plein(url, ""):
                raise DecouverteError("arrêt ou limite atteinte")
            return super().get_json(url)

        def get_text(self, url, encoding="utf-8-sig"):
            if self._plein(url, ".txt"):
                raise DecouverteError("arrêt ou limite atteinte")
            return super().get_text(url, encoding)

    return HttpBorne


class _Chemins:
    """Ce que `_seed_subjects` lit de `Paths` : le dossier de configuration."""

    def __init__(self, config: Path):
        self.config = config


def _ajouter_mots(cfg, config: Path, mots: list[str], poids: float):
    """Ajoute des mots au lexique d'amorçage du sujet (fichier d'amorçage de grappes), puis recharge la configuration."""
    import yaml
    from grappes.config import load_config
    from grappes.learned import seed_path
    from grappes.semantic.scoring import normalize

    g = cfg.grappes[0]
    f = seed_path(config, g.grappe_id)
    d = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {"grappe": g.grappe_id, "termes": {}}
    d.setdefault("termes", {})
    for m in mots:
        t = normalize(m).strip()
        if t and t not in d["termes"]:
            d["termes"][t] = {"poids": float(poids), "ajoute_cycle": 1, "vu_cycle": 1}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return load_config(config)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
