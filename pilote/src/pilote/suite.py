"""Logique de la suite pilote (specification `suite/pilote`) : l'état (sources, outils, plan de travail, recherches sauvegardées), ses
règles, et les six fonctions de l'Aide. Aucun appel réseau, aucun modèle : tout ce qui est ici est déterministe.

Règles de la spécification tenues par le code, pas seulement par l'affichage :
 * retirer (`retirer_source`) ne touche à rien d'autre qu'un drapeau, et se défait ; supprimer (`supprimer_recherche`) est définitif
   et refuse sans confirmation explicite : deux fonctions distinctes ;
 * une source ou un outil créé démarre « à vérifier » et ne devient « opérationnel » qu'après un test réussi ;
 * l'Assistant IA ne s'allume qu'une fois l'avertissement lu ;
 * l'Aide ne fabrique aucun nom : ils viennent des retours de fonction ci-dessous."""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from pilote import cles, suite_reel
from pilote.config import Config
from pilote.refus import ConfigRefusee, ecrire_atomique, verrou
from pilote.suite_graine import CATEGORIES, EFFETS, ROLES, code_modele, graine, identifiant

SEUIL_QUOTA = 80  # même seuil partout dans grappes (spécification 13)
CATS = dict(CATEGORIES)
ROLES_DE_PARCOURS = {
    "CHERCHER": 0,
    "VERIFIER": 1,
    "ENRICHIR": 2,
}  # l'ordre d'une branche : chercher, puis vérifier, puis enrichir
ECRANS = {
    "tableau-de-bord": None, "tri": None,  # pas conçus : visibles, grisés, inactifs
    "recherche": "recherche", "recherche/simple": "recherche/simple", "recherche/avancee": "recherche/avancee",
    "recherche/sauvegardees": "recherche/sauvegardees", "reglages": "reglages", "reglages/sources": "reglages/sources",
    "reglages/outils": "reglages/outils",
}  # fmt: skip
OBJECTIFS = {  # la phrase d'un objectif et sa catégorie : la liste de la puce « Comment je fais… » (spécification 11)
    "entreprises": "Trouver une entreprise.", "assos": "Trouver une association dans les registres officiels.",
    "orgs": "Trouver une administration ou un organisme public.", "web": "Chercher sur le web ouvert.",
    "rs": "Chercher des groupes et des événements sur les réseaux ouverts.", "lieux": "Trouver et localiser un lieu.",
    "presse": "Chercher dans la presse et les médias.", "perso": "Utiliser mes sources et mes scripts.",
}  # fmt: skip


# ---------------------------------------------------------------- stockage


def fichier(cfg: Config):
    return cfg.donnees / "suite" / "etat.json"


def _valide(e: Any) -> bool:
    return (
        isinstance(e, dict)
        and all(isinstance(e.get(k), list) for k in ("outils", "recherches"))
        and isinstance(e.get("plan"), dict)
        and isinstance(e.get("simple"), dict)
    )


def _brut(cfg: Config) -> dict[str, Any]:
    """L'état tel qu'écrit sur disque (sans les sources, qui sont lues dans les déclarations). Un fichier absent donne l'état de départ ; un
    fichier abîmé est mis de côté (`.abime`) et remplacé plutôt que de bloquer toute la page (même tolérance que Réglages)."""
    f = fichier(cfg)
    if not f.exists():
        return graine()
    try:
        e = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e = None
    if _valide(e):
        if not isinstance(e.get("surcouche"), dict):
            e["surcouche"] = {}
        e.pop(
            "sources", None
        )  # un état de la première version (catalogue à part) : ignoré, les sources viennent des déclarations
        return e
    try:
        f.replace(f.with_name(f.name + ".abime"))
    except OSError:
        pass
    return graine()


def charger(cfg: Config, unites: dict[str, float] | None = None) -> dict[str, Any]:
    """L'état courant : ce qui est écrit sur disque, plus la liste des sources RÉELLES (`e["sources"]`, calculée à chaque lecture, jamais écrite).
    `unites` : les unités consommées ce mois-ci par source (pour le quota gratuit), que seule la couche web sait lire dans la base."""
    e = _brut(cfg)
    e["sources"] = suite_reel.sources(cfg, e["surcouche"], unites)
    return e


def modifier(cfg: Config, fn):
    """Lire, modifier, écrire sous le verrou de fichier (jamais deux changements qui s'écrasent). `fn(etat)` rend la valeur à renvoyer."""
    f = fichier(cfg)
    with verrou(f):
        e = charger(cfg)
        res = fn(e)
        a_ecrire = {k: v for k, v in e.items() if k != "sources"}
        ecrire_atomique(f, json.dumps(a_ecrire, ensure_ascii=False, indent=1))
    return res


def maintenant() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- vues (jamais une clé d'API)


def cle_nom(kind: str, ident: str) -> str:
    return "SUITE_" + kind.upper() + "_" + re.sub(r"[^A-Z0-9]+", "_", ident.upper()).strip("_")


def vue(cfg: Config, e: dict[str, Any]) -> dict[str, Any]:
    """L'état tel que le navigateur le reçoit : « clé enregistrée » est un booléen, la valeur ne sort jamais."""
    out = json.loads(json.dumps(e))
    for s in out["sources"]:
        s["pct"] = pourcentage(
            s
        )  # « cle » est déjà un booléen venu des déclarations : la valeur d'une clé ne passe jamais ici
    for o in out["outils"]:
        o["cle"] = cles.presente(cfg, cle_nom("outil", o["id"]))
    out["categories"] = [{"id": i, "nom": n} for i, n in CATEGORIES]
    return out


def pourcentage(s: dict[str, Any]) -> int | None:
    q = s.get("quota")
    if not q or not q.get("plafond"):
        return None
    return min(100, round(q["utilise"] / q["plafond"] * 100))


# ---------------------------------------------------------------- sources


def _texte(d: dict[str, Any], k: str, defaut: str = "") -> str:
    v = d.get(k, defaut)
    return v.strip() if isinstance(v, str) else defaut


def _trouver(liste: list[dict[str, Any]], ident: str, quoi: str) -> dict[str, Any]:
    for x in liste:
        if x["id"] == ident:
            return x
    raise ConfigRefusee(f"{quoi} « {ident} » n'existe pas.")


def _id_libre(liste: list[dict[str, Any]], base: str) -> str:
    ids, i, cand = {x["id"] for x in liste}, 2, base
    while cand in ids:
        cand, i = f"{base}-{i}", i + 1
    return cand


def ajouter_source(cfg: Config, d: dict[str, Any]) -> dict[str, Any]:
    """AJOUTER : écrit la déclaration d'une source API par la fonction de l'ancienne page Ajout (éteinte, test local lancé), puis garde ce que la
    suite ajoute (langue, rôle, catégorie) dans la surcouche."""
    if str(d.get("langue") or "").strip() and not re.fullmatch(
        r"[a-z]{2,3}(-[a-z]{2,4})?", str(d["langue"]).strip().lower()
    ):
        raise ConfigRefusee("La langue s'écrit avec son code : fr, en, de…")  # avant d'écrire quoi que ce soit
    ident = suite_reel.ajouter_api(cfg, d)
    _surcouche(cfg, ident, {k: d[k] for k in ("langue", "role", "cat", "fiabilite") if d.get(k)})

    def f(e):
        e["surcouche"].setdefault(ident, {})["nouvelle"] = True

    modifier(cfg, f)
    return {"id": ident}


def _surcouche(cfg: Config, ident: str, champs: dict[str, Any]) -> None:
    langue = str(champs.get("langue") or "").strip().lower()
    if langue and not re.fullmatch(r"[a-z]{2,3}(-[a-z]{2,4})?", langue):
        raise ConfigRefusee("La langue s'écrit avec son code : fr, en, de…")
    if "role" in champs and champs["role"] not in ROLES:
        raise ConfigRefusee("Choisis le rôle de la source.")
    if "fiabilite" in champs and champs["fiabilite"] not in tuple(suite_reel.FIABILITES):
        raise ConfigRefusee("La fiabilité de la source est une lettre de A à F.")
    if "cat" in champs and champs["cat"] not in CATS:
        raise ConfigRefusee("Choisis la catégorie de la source.")
    suite_reel.declaration(cfg, ident)  # refuse une source inconnue

    def f(e):
        cur = dict(e["surcouche"].get(ident) or {})
        for k in ("role", "cat", "fiabilite"):
            if k in champs:
                cur[k] = champs[k]
        if "langue" in champs:
            if langue:
                cur["langue"] = langue
            else:
                cur.pop("langue", None)
        e["surcouche"][ident] = cur

    modifier(cfg, f)


def modifier_source(cfg: Config, ident: str, d: dict[str, Any]) -> dict[str, Any]:
    """MODIFIER : seul ce que la suite ajoute change (langue, rôle d'affichage, catégorie, fiabilité A–F). Le nom, le coût, le pays, le quota sont ceux de
    la déclaration : ils ne se changent pas depuis ici, et un envoi qui les contient est simplement ignoré."""
    _surcouche(cfg, ident, {k: d[k] for k in ("langue", "role", "cat", "fiabilite") if k in d})
    return {"id": ident}


def changer_etat_source(cfg: Config, ident: str, allumee: bool, confirme: bool = False) -> dict[str, Any]:
    suite_reel.allumer(cfg, ident, allumee, confirme)
    s = next(x for x in charger(cfg)["sources"] if x["id"] == ident)
    return s


def _drapeau_retiree(cfg: Config, ident: str, retiree: bool) -> dict[str, Any]:
    suite_reel.declaration(cfg, ident)

    def f(e):
        cur = dict(e["surcouche"].get(ident) or {})
        if retiree:
            cur["retiree"] = True
        else:
            cur.pop("retiree", None)
        e["surcouche"][ident] = cur

    modifier(cfg, f)
    return {"id": ident, "retiree": retiree}


def retirer_source(cfg: Config, ident: str) -> dict[str, Any]:
    """RETIRER : la source sort de la liste de la suite, rien d'autre ne change (ni Réglages, ni la déclaration, ni les cases) et rien n'est
    effacé (règle 4 de la spécification)."""
    return _drapeau_retiree(cfg, ident, True)


def rajouter_source(cfg: Config, ident: str) -> dict[str, Any]:
    return _drapeau_retiree(cfg, ident, False)


def tester_source(cfg: Config, ident: str) -> dict[str, Any]:
    """Le test LOCAL de l'ancienne page (configuration, exemple de réponse enregistré, connexion seulement si le fournisseur offre un point d'accès
    gratuit). Il ne consomme rien ; son résultat est écrit dans l'état de la source, d'où se déduit « opérationnelle » ou « à vérifier »."""
    res = suite_reel.tester(cfg, ident)
    s = next(x for x in charger(cfg)["sources"] if x["id"] == ident)
    ok = res["statut"] == "ok"
    return {"ok": ok, "raisons": [] if ok else [res["raison"]], "source": s, "niveaux": res.get("niveaux", {})}


def enregistrer_cle(cfg: Config, kind: str, ident: str, valeur: str) -> None:
    """La clé va dans le fichier de clés de pilote (droits 600), jamais dans l'état, jamais renvoyée. Pour une source : sous le NOM DE VARIABLE de sa
    déclaration (celui que le moteur lit). Pour un outil : sous un nom propre à la suite."""
    if kind == "source":
        suite_reel.ecrire_cle(cfg, ident, valeur)
        return
    e = charger(cfg)
    _trouver(e["outils"], ident, "L'outil")
    cles.ecrire(cfg, cle_nom(kind, ident), valeur)


# ---------------------------------------------------------------- outils


def _champs_outil(d: dict[str, Any], ancien: dict[str, Any] | None) -> dict[str, Any]:
    nom = _texte(d, "nom")
    if not nom:
        raise ConfigRefusee("Donne un nom à l'outil.")
    nature = d.get("nature", "modele")
    if nature not in ("modele", "script"):
        raise ConfigRefusee("Un outil est un modèle ou un script.")
    role = d.get("role", "OUTIL")
    if role not in ("OUTIL", "RAPPROCHER", "CATALOGUE"):
        raise ConfigRefusee("Le rôle d'un outil est OUTIL, RAPPROCHER ou CATALOGUE.")
    effet = d.get("effet", "journal")
    if effet not in EFFETS:
        raise ConfigRefusee("L'effet dans le Tableau de bord est : rien, compteur, journal ou alerte.")
    options = d.get("options", [])
    if not isinstance(options, list) or not all(
        isinstance(o, list) and len(o) == 2 and all(isinstance(x, str) for x in o) for o in options
    ):
        raise ConfigRefusee("Les options sont des paires libellé / valeur.")
    code = d.get("code", "") if isinstance(d.get("code", ""), str) else ""
    modele = d.get("modele")
    if nature == "script" and not re.search(r"^def run\(\s*resultats\s*\)\s*:", code, re.MULTILINE):
        raise ConfigRefusee("Le script doit définir « def run(resultats): » et renvoyer une liste.")
    if nature == "modele" and not modele:
        raise ConfigRefusee("Choisis un modèle.")
    return {
        "nom": nom, "nature": nature, "modele": modele if nature == "modele" else None, "role": role, "effet": effet, "options": options,
        "code": code if nature == "script" else "", "fait": _texte(d, "fait"), "recoit": _texte(d, "recoit"), "renvoie": _texte(d, "renvoie"),
        "test_entree": _texte(d, "test_entree"), "test_sortie": _texte(d, "test_sortie"),
    }  # fmt: skip


def _etat_voulu(x: dict[str, Any], etat: str) -> str:
    """« opérationnel » n'est jamais écrit à la main : il vient d'un test réussi. Demander « opérationnel » sans test donne « à vérifier »."""
    if etat == "ok" and not x.get("test_reussi"):
        return "warn"
    return etat


def ajouter_outil(cfg: Config, d: dict[str, Any]) -> dict[str, Any]:
    def f(e):
        champs = _champs_outil(d, None)
        o = {
            "id": _id_libre(e["outils"], identifiant(champs["nom"])),
            **champs,
            "etat": "warn",
            "test_reussi": False,
            "livre": False,
            "retire": False,
            "cle": False,
        }
        e["outils"].append(o)
        return o

    return modifier(cfg, f)


def modifier_outil(cfg: Config, ident: str, d: dict[str, Any]) -> dict[str, Any]:
    def f(e):
        o = _trouver(e["outils"], ident, "L'outil")
        o.update(_champs_outil({**o, **d}, o))
        o["test_reussi"] = False if any(k in d for k in ("code", "options", "modele")) else o["test_reussi"]
        if o["etat"] == "ok" and not o["test_reussi"]:
            o["etat"] = "warn"  # on a changé ce qui avait été testé : il faut le tester de nouveau
        return o

    return modifier(cfg, f)


def allumer_outil(cfg: Config, ident: str, avertissement_lu: bool = False) -> dict[str, Any]:
    def f(e):
        o = _trouver(e["outils"], ident, "L'outil")
        if o["id"] == "ia" and o["etat"] == "off" and not avertissement_lu:
            raise ConfigRefusee("Allumer l'Assistant IA demande de lire l'avertissement d'abord.")
        o["etat"] = _etat_voulu(o, "ok")
        return o

    return modifier(cfg, f)


def eteindre_outil(cfg: Config, ident: str) -> dict[str, Any]:
    """Éteindre ne redemande rien : on n'avertit que dans le sens risqué (spécification 10)."""

    def f(e):
        o = _trouver(e["outils"], ident, "L'outil")
        o["etat"] = "off"
        return o

    return modifier(cfg, f)


def retirer_outil(cfg: Config, ident: str, retire: bool = True) -> dict[str, Any]:
    """RETIRER un outil : il sort de la grille, rien n'est effacé, on le remet avec `retire=False`."""

    def f(e):
        o = _trouver(e["outils"], ident, "L'outil")
        o["retire"] = retire
        return o

    return modifier(cfg, f)


def tester_outil(cfg: Config, ident: str) -> dict[str, Any]:
    from pilote import suite_script

    def f(e):
        o = _trouver(e["outils"], ident, "L'outil")
        if o["nature"] == "script":
            res = suite_script.executer(o["code"], o["test_entree"])
            ok = res["ok"] and (not o["test_sortie"].strip() or _meme_sortie(res["sortie"], o["test_sortie"]))
            if res["ok"] and not ok:
                res = {**res, "ok": False, "erreur": "La sortie obtenue n'est pas celle attendue."}
            sortie = res["sortie"] if res["ok"] or res.get("sortie") else res.get("erreur", "")
            raisons = [] if ok else [res.get("erreur") or "Le test a échoué."]
        else:  # un modèle livré ne s'exécute pas encore sur de vraies données : on vérifie la fiche, et on le dit
            raisons = [
                m
                for m, vide in (
                    ("l'exemple d'entrée est vide", not o["test_entree"].strip()),
                    ("la sortie attendue est vide", not o["test_sortie"].strip()),
                )
                if vide
            ]
            ok, sortie = not raisons, o["test_sortie"]
        o["test_reussi"] = ok
        if not ok and o["etat"] == "ok":
            o["etat"] = "warn"
        elif ok and o["etat"] == "warn":
            o["etat"] = "ok"
        return {"ok": ok, "sortie": sortie, "raisons": raisons, "execute": o["nature"] == "script", "outil": o}

    return modifier(cfg, f)


def _meme_sortie(obtenue: str, attendue: str) -> bool:
    def norme(t: str) -> Any:
        try:
            return json.loads(t)
        except ValueError:
            return t.strip()

    return norme(obtenue) == norme(attendue)


# ---------------------------------------------------------------- plan de travail


def _plan_valide(p: dict[str, Any]) -> dict[str, Any]:
    nodes, edges = p.get("nodes"), p.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ConfigRefusee("Le plan est une liste de tuiles et une liste de liens.")
    vus: dict[str, dict[str, Any]] = {}
    propres = []
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not n["id"]:
            raise ConfigRefusee("Une tuile n'a pas d'identifiant.")
        if n["id"] in vus:
            raise ConfigRefusee(f"La tuile « {n['id']} » est posée deux fois.")
        role = n.get("role")
        if role not in (*ROLES, "ENTREE", "GRAPPES"):
            raise ConfigRefusee(f"Le rôle de la tuile « {n.get('nom', n['id'])} » est inconnu.")
        try:
            x, y = int(n.get("x", 0)), int(n.get("y", 0))
        except (TypeError, ValueError):
            raise ConfigRefusee("Une tuile a des coordonnées qui ne sont pas des nombres.") from None
        opts = n.get("opts", [])
        if not isinstance(opts, list):
            raise ConfigRefusee("Les options d'une tuile sont une liste de paires.")
        t = {
            "id": n["id"], "nom": str(n.get("nom", n["id"]))[:80], "role": role, "x": max(0, x), "y": max(0, y),
            "removable": role not in ("ENTREE", "GRAPPES"), "opts": opts, "cat": n.get("cat"), "ref": n.get("ref"),
        }  # fmt: skip
        vus[t["id"]] = t
        propres.append(t)
    liens, ids = [], set()
    for ed in edges:
        a, b = (ed.get("from"), ed.get("to")) if isinstance(ed, dict) else (None, None)
        if a not in vus or b not in vus:
            raise ConfigRefusee("Un lien part d'une tuile ou arrive sur une tuile qui n'est pas sur le plan.")
        if a == b:
            raise ConfigRefusee("Une tuile ne se relie pas à elle-même.")
        if vus[b]["role"] == "ENTREE" or vus[a]["role"] == "GRAPPES":
            raise ConfigRefusee("« Ta saisie » n'a pas d'entrée et « Grappes » n'a pas de sortie.")
        if f"{a}>{b}" in ids:
            continue  # un lien en double n'existe pas : on garde le premier
        ids.add(f"{a}>{b}")
        lien = {"id": f"{a}>{b}", "from": a, "to": b}
        if ed.get("label") in ("oui", "non"):
            lien["label"] = ed["label"]  # la sortie « oui » ou « non » d'une condition : sans elle le moteur ne sait pas quelle branche garder
        liens.append(lien)
    cats = [c for c in p.get("cats", []) if c in CATS]
    saisies = {k: str(v)[:300] for k, v in (p.get("saisies") or {}).items() if k in CATS}
    return {
        "nodes": propres,
        "edges": liens,
        "cats": cats,
        "saisies": saisies,
        "saisie": str(p.get("saisie") or "")[:300],
    }


def ecrire_plan(cfg: Config, plan: dict[str, Any]) -> dict[str, Any]:
    propre = _plan_valide(plan)

    def f(e):
        e["plan"] = propre
        return propre

    return modifier(cfg, f)


# ---------------------------------------------------------------- recherches sauvegardées


def sauvegarder_recherche(cfg: Config, d: dict[str, Any]) -> dict[str, Any]:
    mode = d.get("mode")
    if mode not in ("Simple", "Avancée"):
        raise ConfigRefusee("Une recherche est « Simple » ou « Avancée ».")
    titre = _texte(d, "titre")
    if not titre:
        raise ConfigRefusee("Donne un titre à la recherche.")
    cats = [c for c in d.get("cats", []) if c in CATS]
    entree: dict[str, Any] = {
        "id": uuid.uuid4().hex[:10], "titre": titre[:120], "mode": mode, "cats": cats, "detail": _texte(d, "detail")[:400],
        "date": maintenant(), "resultat": _texte(d, "resultat") or "—", "recherche_id": d.get("recherche_id"),
    }  # fmt: skip
    if mode == "Avancée":
        entree["plan"] = _plan_valide(
            d.get("plan") or {"nodes": [], "edges": []}
        )  # les tuiles à leurs coordonnées et TOUS les liens (spécification 12)
    else:
        s = d.get("simple") or {}
        entree["simple"] = {"preset": s.get("preset") if s.get("preset") in CATS else (cats[0] if cats else None), "pays": _texte(s, "pays") or "Tous",
                            "ov": s.get("ov") if isinstance(s.get("ov"), dict) else {}, "saisie": _texte(s, "saisie")}  # fmt: skip

    def f(e):
        e["recherches"].insert(0, entree)
        return entree

    return modifier(cfg, f)


def supprimer_recherche(cfg: Config, ident: str, confirme: bool) -> None:
    """SUPPRIMER : définitif. Le serveur refuse sans confirmation explicite, quoi qu'ait fait la page (règle 4)."""
    if not confirme:
        raise ConfigRefusee("Supprimer une recherche est définitif : confirme d'abord.")

    def f(e):
        _trouver(e["recherches"], ident, "La recherche")
        e["recherches"] = [r for r in e["recherches"] if r["id"] != ident]

    modifier(cfg, f)


def noter_resultat(cfg: Config, ident: str, resultat: str, recherche_id: str | None = None) -> None:
    def f(e):
        for r in e["recherches"]:
            if r["id"] == ident:
                r["resultat"] = resultat
                if recherche_id is not None:
                    r["recherche_id"] = recherche_id

    modifier(cfg, f)


# ---------------------------------------------------------------- les six fonctions de l'Aide


def _sans_accent(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()


def lister_sources(
    e: dict[str, Any], role: str | None = None, pays: str | None = None, etat: str | None = None
) -> list[dict[str, Any]]:
    """Des sources RÉELLES de la configuration : c'est d'ici que l'Aide tire tous ses noms de source."""
    out = []
    for s in e["sources"]:
        if s["retiree"] or (role and s["role"] != role) or (pays and s["pays"] != pays) or (etat and s["etat"] != etat):
            continue
        out.append({k: s[k] for k in ("id", "nom", "cat", "role", "pays", "langue", "etat")})
    return out


def lire_plan(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "tuiles": [{k: n[k] for k in ("id", "nom", "role")} for n in e["plan"]["nodes"]],
        "liens": [dict(ed) for ed in e["plan"]["edges"]],
    }


def _correspond_pays(s: dict[str, Any], pays: str | None) -> bool:
    if not pays or pays == "Tous":
        return True
    codes = s.get("pays_codes") or [s["pays"]]
    return "Mondial" in codes or pays in codes or (pays == "UE" and any(c in ("FI", "UE") for c in codes))


def proposer_plan(e: dict[str, Any], objectif: str, pays: str | None = None) -> dict[str, Any]:
    """Une suite de tuiles et de liens construite avec les sources allumées de la catégorie. NON POSÉE : la fenêtre la montre, une personne
    la pose avec un bouton. Rien n'est inventé : chaque tuile est une source ou un outil de la configuration."""
    if objectif not in CATS:
        raise ConfigRefusee("Cet objectif n'existe pas.")
    etapes: list[list[dict[str, Any]]] = [[], [], []]
    for s in e["sources"]:
        if (
            objectif not in s["cats"]
            or s["retiree"]
            or s["etat"] == "off"
            or s["role"] not in ROLES_DE_PARCOURS
            or s["role"] == "VERIFIER"
        ):
            continue  # vérifier est éteint par défaut dans les préréglages (case décochée) : l'Aide ne le pose pas sans qu'on le demande
        if _correspond_pays(s, pays):
            etapes[ROLES_DE_PARCOURS[s["role"]]].append(s)
    suite = [x for x in etapes if x]
    nodes: list[dict[str, Any]] = [{"id": "saisie", "nom": "Ta saisie", "role": "ENTREE", "ref": None}]
    edges: list[dict[str, str]] = []
    precedents = ["saisie"]
    for groupe in suite:
        courant = []
        for s in groupe:
            nid = f"{objectif}:{s['id']}"
            nodes.append({"id": nid, "nom": s["nom"], "role": s["role"], "ref": s["id"], "cat": objectif})
            edges += [{"id": f"{p}>{nid}", "from": p, "to": nid} for p in precedents]
            courant.append(nid)
        precedents = courant
    sources_posees = [n for n in nodes if n["role"] != "ENTREE"]
    fusion = next((o for o in e["outils"] if o["id"] == "fusion" and o["etat"] != "off"), None)
    if fusion and len(sources_posees) > 1:
        nodes.append({"id": "fusion", "nom": fusion["nom"], "role": fusion["role"], "ref": fusion["id"]})
        edges += [{"id": f"{p}>fusion", "from": p, "to": "fusion"} for p in precedents]
        precedents = ["fusion"]
    nodes.append({"id": "grappes", "nom": "Grappes", "role": "GRAPPES", "ref": None})
    edges += [{"id": f"{p}>grappes", "from": p, "to": "grappes"} for p in precedents]
    return {
        "titre": OBJECTIFS[objectif],
        "objectif": objectif,
        "vide": not sources_posees,
        "tuiles": [{k: n.get(k) for k in ("id", "nom", "role")} for n in nodes],
        "nodes": nodes,
        "edges": edges,
    }


def _aval(edges: list[dict[str, str]], depart: str) -> set[str]:
    vus, pile = set(), [depart]
    while pile:
        n = pile.pop()
        for ed in edges:
            if ed["from"] == n and ed["to"] not in vus:
                vus.add(ed["to"])
                pile.append(ed["to"])
    return vus


def _amont(edges: list[dict[str, str]], arrivee: str) -> set[str]:
    return _aval([{"from": ed["to"], "to": ed["from"]} for ed in edges], arrivee)


def _accepte_entree(n: dict[str, Any]) -> bool:
    return n["role"] != "ENTREE"


def verifier_plan(e: dict[str, Any], langue_saisie: str | None = None) -> list[dict[str, Any]]:
    """Les huit contrôles de la spécification 11, dans l'ordre, sans aucun modèle : les mêmes tuiles donnent toujours les mêmes constats.
    Deux niveaux : « bloquant » (la recherche ne donnera rien) et « remarque » (elle tournera mais mal)."""
    nodes, edges = e["plan"]["nodes"], e["plan"]["edges"]
    par_id = {n["id"]: n for n in nodes}
    sources = {s["id"]: s for s in e["sources"]}
    outils = {o["id"]: o for o in e["outils"]}
    constats: list[dict[str, Any]] = []

    def c(num: int, niveau: str, n: dict[str, Any], texte: str) -> None:
        constats.append({"regle": num, "niveau": niveau, "tuile": n["id"], "nom": n["nom"], "texte": texte})

    entrants = {n["id"]: [ed for ed in edges if ed["to"] == n["id"]] for n in nodes}
    sortants = {n["id"]: [ed for ed in edges if ed["from"] == n["id"]] for n in nodes}
    for n in nodes:  # 1
        if n["role"] != "ENTREE" and not entrants[n["id"]]:
            c(1, "bloquant", n, "n'a aucun lien entrant : elle n'est jamais interrogée.")
    for n in nodes:  # 2
        if n["role"] != "GRAPPES" and not sortants[n["id"]]:
            c(2, "bloquant", n, "n'a aucun lien sortant : son résultat se perd.")
    for n in nodes:  # 3
        s = sources.get(n.get("ref") or "")
        o = outils.get(n.get("ref") or "")
        if s and (s["etat"] == "off" or s["retiree"]):
            c(3, "bloquant", n, "est posée mais éteinte dans Réglages : elle ne répondra pas.")
        elif o and o["etat"] == "off":
            c(3, "bloquant", n, "est posé mais éteint dans Réglages : il ne répondra pas.")
    posees = [n for n in nodes if n.get("ref") in sources]
    for n in posees:  # 4
        role = sources[n["ref"]]["role"]
        memes = [m for m in posees if sources[m["ref"]]["role"] == role]
        if role in ROLES_DE_PARCOURS and len(memes) > 1:
            derriere = _aval(edges, n["id"])
            if not any(par_id[i]["role"] == "RAPPROCHER" for i in derriere):
                c(
                    4,
                    "remarque",
                    n,
                    "a une autre source du même rôle et aucun rapprochement derrière : les doublons arriveront jusqu'à la grappe.",
                )
    for n in posees:  # 5
        pct = pourcentage(sources[n["ref"]])
        if pct is not None and pct >= SEUIL_QUOTA:
            c(
                5,
                "remarque",
                n,
                "a atteint son quota : la recherche s'arrêtera en route."
                if pct >= 100
                else f"est à {pct} % de son quota : la recherche risque de s'arrêter en route.",
            )
    if langue_saisie:  # 6 : sans langue connue pour la saisie, le contrôle n'est pas possible et ne dit rien
        for n in posees:
            s = sources[n["ref"]]
            if s["langue"] and s["langue"] != langue_saisie:
                avant = _amont(edges, n["id"])
                if not any(par_id[i].get("ref") == "traduction" for i in avant):
                    c(
                        6,
                        "remarque",
                        n,
                        f"cherche en {s['langue']}, ta saisie est en {langue_saisie} : elle cherchera avec les mots d'une autre langue. Une tuile Traduction avant réglerait ça.",
                    )
    for ed in edges:  # 7
        a, b = par_id[ed["from"]], par_id[ed["to"]]
        if b["role"] == "ENTREE" or a["role"] == "GRAPPES":
            c(7, "bloquant", b, f"reçoit un lien de « {a['nom']} » qui ne lui passera rien.")
    for n in nodes:  # 8
        if n.get("ref") == "ia":
            c(8, "remarque", n, "Rappel : sa sortie est marquée « IA » et ne compte jamais comme un fait vérifié.")
    ordre = {"bloquant": 0, "remarque": 1}
    return sorted(constats, key=lambda k: (ordre[k["niveau"]], k["regle"]))


_LIGNE_MOT = re.compile(r"^\|\s*\*\*([^*|]+?)\*\*\s*\|(.*)\|\s*$")


def mots(cfg: Config) -> dict[str, str]:
    """La liste close de `config/suite/nommage.md`, ligne par ligne : mot -> la ligne telle qu'écrite (sans les barres du tableau)."""
    f = cfg.dossier_config / "suite" / "nommage.md"
    if not f.exists():
        return {}
    out: dict[str, str] = {}
    for ligne in f.read_text(encoding="utf-8").splitlines():
        m = _LIGNE_MOT.match(ligne)
        if m:
            cellules = [c.strip() for c in m.group(2).split("|")]
            out.setdefault(m.group(1).strip(), " — ".join(c for c in cellules if c))
    return out


def definir(cfg: Config, mot: str) -> dict[str, Any]:
    table = mots(cfg)
    cible = _sans_accent(mot)
    for k, v in table.items():
        if _sans_accent(k) == cible:
            return {"mot": k, "definition": v}
    raise ConfigRefusee(f"« {mot} » n'est pas dans la liste des mots de grappes.")


def ouvrir(ecran: str) -> dict[str, Any]:
    if ecran not in ECRANS:
        raise ConfigRefusee(f"L'écran « {ecran} » n'existe pas.")
    if ECRANS[ecran] is None:
        raise ConfigRefusee("Cet onglet n'est pas encore conçu : il reste grisé.")
    return {"ecran": ECRANS[ecran]}


def detecter_langue(texte: str) -> str | None:
    """Langue d'une saisie, par une bibliothèque de détection éprouvée (langdetect), jamais par une règle maison. Rien si le texte est
    trop court pour que la détection vaille quelque chose."""
    t = texte.strip()
    if len(t) < 12 or len(t.split()) < 2:
        return None
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0  # même texte, même réponse
        return detect(t)
    except Exception:  # noqa: BLE001 - bibliothèque absente ou texte indétectable : pas de langue, pas de contrôle 6
        return None


__all__ = ["code_modele"]
