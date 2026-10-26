"""Raccord de la suite aux sources RÉELLES de pilote (`config/sources/*.yaml`) : la liste de la suite n'est plus un catalogue à part, c'est une
vue des déclarations. Rien n'est recopié :
 * nom, coût, origine, pays, description, clé requise, quota gratuit viennent de la déclaration (en lecture seule dans la suite) ;
 * allumer / éteindre écrit les cases « chercher » / « vérifier » de Réglages, par la même fonction que l'ancienne page ;
 * l'état (opérationnelle / à vérifier / éteinte) se déduit du dernier test et du voyant de l'ancienne page ;
 * le test est le test LOCAL de l'ancienne page (il ne consomme rien) ;
 * la clé est rangée sous son vrai nom de variable, dans le fichier de clés de pilote ;
 * seul ce que la suite ajoute est gardé dans la surcouche (`etat.json`, clé `surcouche`) : langue, retrait de la liste, rôle et catégorie
   d'affichage. La déclaration n'est jamais modifiée par l'usage."""

from __future__ import annotations

from typing import Any

from pilote import cles
from pilote import reglages as rg
from pilote.api_reglages import adaptateur_manquant, voyant
from pilote.config import Config
from pilote.etat_sources import lire as lire_etat
from pilote.presets import domaine_source
from pilote.refus import ConfigRefusee
from pilote.sources import Declaration, charger_sources

USAGE_VERS_CAT = {
    "associations": "assos", "entreprises": "entreprises", "organisations": "orgs", "web": "web", "reseaux_sociaux": "rs", "lieux": "lieux",
    "presse": "presse", "personnalise": "perso", "culture": "lieux",
}  # fmt: skip
CAT_VERS_USAGE = {
    "assos": "associations",
    "entreprises": "entreprises",
    "orgs": "organisations",
    "web": "web",
    "rs": "reseaux_sociaux",
    "lieux": "lieux",
    "presse": "presse",
    "perso": "personnalise",
}
PAYS_AFFICHE = {"GB": "UK", "monde": "Mondial"}
LANGUE_DU_PAYS = {
    "FR": "fr",
    "UK": "en",
    "US": "en",
    "AU": "en",
    "NZ": "en",
    "FI": "fi",
    "CH": "de",
    "UE": "en",
    "Mondial": "en",
}
FIABILITES = "ABCDEF"  # code Admiralty, axe « fiabilité de la source » (spécification 05) ; l'axe 1–6 (crédibilité d'un fait) n'est pas construit
FIABILITE_DE_LA_CLASSE = {"registre": "B", "encyclo": "C"}  # par défaut : B pour une source officielle, C pour une encyclopédie, D pour le web, la presse, le reste


def fiabilite_par_defaut(d: Declaration) -> str:
    return FIABILITE_DE_LA_CLASSE.get(d.origine, "D")


class AvertissementRequis(Exception):
    """Allumer cette source demande d'abord de lire un avertissement (prestataire payant, service à risque) : la page le montre, puis redemande."""

    def __init__(self, avertissements: list[dict[str, str]]):
        super().__init__("avertissement")
        self.avertissements = avertissements


def _pays(d: Declaration) -> list[str]:
    return [PAYS_AFFICHE.get(p, p.upper()) for p in d.pays] or ["Mondial"]


def _cats(d: Declaration) -> list[str]:
    cats = [USAGE_VERS_CAT[u] for u in d.usages if u in USAGE_VERS_CAT]
    if d.famille in ("fichier", "base", "python"):
        cats.append("perso")
    return list(dict.fromkeys(cats)) or ["perso"]


def _quota(d: Declaration, e: dict[str, Any], unites: dict[str, float] | None) -> dict[str, Any] | None:
    """Le quota LU, jamais inventé : celui que le fournisseur a rendu au dernier test, sinon le quota gratuit mensuel de la déclaration avec
    les unités réellement consommées ce mois-ci (sans `unites`, pas de chiffre : on ne dit pas « 0 » faute de savoir)."""
    q = e.get("quota") or {}
    if q.get("total") and q.get("restant") is not None:
        return {"utilise": round(q["total"] - q["restant"]), "plafond": round(q["total"]), "unite": "mois"}
    gratuit = float(d.cout.get("gratuit_par_mois", 0) or 0)
    if gratuit > 0 and unites is not None:
        return {"utilise": round(unites.get(d.id, 0.0)), "plafond": round(gratuit), "unite": "mois"}
    return None


def vue_source(
    cfg: Config,
    d: Declaration,
    reg: dict[str, Any],
    e: dict[str, Any],
    sur: dict[str, Any],
    unites: dict[str, float] | None,
) -> dict[str, Any]:
    ch = rg.choix_source(reg, d)
    allumee = bool(ch["chercher"] or ch["verifier"])
    manquant = adaptateur_manquant(d)
    couleur, mot = voyant(cfg, d, e, manquant, rg.parametres_donnes(reg, d.id))
    teste = e.get("statut") == "ok"
    if sur.get("nouvelle") and not teste:
        etat = "warn"  # une source que la suite vient d'ajouter démarre « à vérifier » jusqu'à son premier test réussi (spec 05), même éteinte
    elif not allumee:
        etat = "off"
    elif couleur == "ok" and teste:
        etat = "ok"
    else:
        etat = "warn"  # jamais testée, test échoué, clé absente, en pause, adaptateur manquant : « à vérifier »
    cats = _cats(d)
    pays = _pays(d)
    role = sur.get("role") or ("CHERCHER" if "chercher" in d.roles else "VERIFIER")
    tests = []
    if e.get("teste_le"):
        tests.append(
            f"{e['teste_le'][:10]} · {'test local réussi' if teste else 'échec : ' + str(e.get('raison', ''))}"
        )
    return {
        "id": d.id, "nom": d.nom, "cat": sur.get("cat") if sur.get("cat") in CAT_VERS_USAGE else cats[0], "cats": cats, "role": role,
        "cout": "payant" if d.payant else "gratuit", "fiabilite": sur.get("fiabilite") if sur.get("fiabilite") in tuple(FIABILITES) else fiabilite_par_defaut(d), "fiabilite_choisie": sur.get("fiabilite") in tuple(FIABILITES), "pays": pays[0], "pays_codes": pays,
        "langue": sur.get("langue") or LANGUE_DU_PAYS.get(pays[0], "en"), "etat": etat, "quota": _quota(d, e, unites), "description": d.description,
        "retiree": bool(sur.get("retiree")), "test_reussi": teste, "tests": tests, "declaree": True, "cle_requise": bool(d.cles),
        "cle": bool(d.cles) and cles.toutes_presentes(cfg, d.cles), "voyant": mot, "domaine": domaine_source(d), "chercher": ch["chercher"], "verifier": ch["verifier"],
        "peut_chercher": "chercher" in d.roles, "verifie_sur": d.verifie_sur if "adaptateur" in d.moteur else "", "avertissement": d.avertissement, "adaptateur_manquant": manquant,
    }  # fmt: skip


def sources(cfg: Config, surcouche: dict[str, Any], unites: dict[str, float] | None = None) -> list[dict[str, Any]]:
    decls, _ = charger_sources(cfg)
    reg, _ = rg.charger_tolerant(cfg)
    etats = lire_etat(cfg)
    ordre = {c: i for i, c in enumerate(CAT_VERS_USAGE)}
    vues = [
        vue_source(
            cfg,
            d,
            reg,
            etats.get(d.id) or {},
            surcouche.get(d.id) if isinstance(surcouche.get(d.id), dict) else {},
            unites,
        )
        for d in decls.values()
    ]
    return sorted(vues, key=lambda s: (ordre.get(s["cat"], 99), s["nom"].lower()))


def declaration(cfg: Config, ident: str) -> Declaration:
    decls, _ = charger_sources(cfg)
    if ident not in decls:
        raise ConfigRefusee(f"La source « {ident} » n'existe pas.")
    return decls[ident]


def allumer(cfg: Config, ident: str, allumee: bool, confirme: bool = False) -> None:
    """Allume ou éteint par les cases de Réglages (la même fonction que l'ancienne page : mêmes refus, même verrou, mêmes avertissements)."""
    from pilote import presets

    d = declaration(cfg, ident)
    decls, _ = charger_sources(cfg)
    if allumee:
        if adaptateur_manquant(d):
            raise ConfigRefusee(f"La source « {d.nom} » demande un adaptateur : elle ne peut pas être allumée.")
        e = lire_etat(cfg).get(ident) or {}
        if e.get("statut") == "echec":
            raise ConfigRefusee(
                f"La source « {d.nom} » a échoué à son test ({e.get('raison', 'raison inconnue')}) : elle ne peut pas être allumée tant que le test ne passe pas."
            )
    patch: dict[str, Any] = {
        "id": ident,
        "chercher": allumee and "chercher" in d.roles,
        "verifier": allumee and "verifier" in d.roles and "chercher" not in d.roles,
    }
    if not allumee:
        patch.update(chercher=False, verifier=False)
    requis = rg.avertissements_requis(rg.charger(cfg), decls, {"source": patch})
    if requis and not confirme:
        raise AvertissementRequis(requis)
    if requis:
        patch_global = {
            "source": patch,
            "avertissements_vus": sorted(
                {*rg.charger(cfg).get("avertissements_vus", []), *(a["source"] for a in requis)}
            ),
        }
    else:
        patch_global = {"source": patch}
    rg.appliquer(cfg, decls, presets.ids_connus(cfg), patch_global)


def tester(cfg: Config, ident: str) -> dict[str, Any]:
    from pilote import tests_source

    return tests_source.tester(cfg, declaration(cfg, ident))


def ecrire_cle(cfg: Config, ident: str, valeur: str) -> None:
    d = declaration(cfg, ident)
    if not d.cle:
        raise ConfigRefusee(f"« {d.nom} » n'a pas de clé d'API.")
    cles.ecrire(cfg, d.cle, valeur)


def ajouter_api(cfg: Config, d: dict[str, Any]) -> str:
    """AJOUTER une source : sa déclaration est écrite par la même fonction que l'ancienne page Ajout (type « API »), puis son test local
    tourne. Elle est enregistrée ÉTEINTE ; elle ne s'allume qu'après un test réussi. Les autres types (MCP, fichier, base, programme local,
    flux RSS) gardent leur voie dans l'ancienne page Ajout."""
    from pilote import sources_ajout

    def t(k: str) -> str:
        v = d.get(k, "")
        return v.strip() if isinstance(v, str) else ""

    cat = d.get("cat")
    if cat not in CAT_VERS_USAGE:
        raise ConfigRefusee("Choisis la catégorie de la source.")
    if d.get("role") not in ("CHERCHER", "VERIFIER", "ENRICHIR", "CATALOGUE", "OUTIL", "RAPPROCHER"):
        raise ConfigRefusee("Choisis le rôle de la source.")
    if not t("url"):
        raise ConfigRefusee("Donne l'adresse de la source (https://…).")
    if not t("champ_nom"):
        raise ConfigRefusee("Dis quel champ de la réponse contient le NOM.")
    if not t("parametre_requete"):
        raise ConfigRefusee("Dis sous quel nom la source reçoit ce qu'on cherche (par exemple q).")
    cout: dict[str, Any] = {}
    if d.get("cout") == "payant":
        try:
            prix = float(str(d.get("tarif", "")).replace(",", "."))
        except ValueError:
            prix = 0.0
        if prix <= 0:
            raise ConfigRefusee(
                "Une source payante demande son prix par appel, en dollars (un nombre supérieur à zéro)."
            )
        cout = {"vers_dollar": prix, "par_appel": 1, "unite": "appel"}
    pays = t("pays")
    spec: dict[str, Any] = {
        "nom": t("nom"), "url": t("url"), "parametre_requete": t("parametre_requete"), "champs": {"nom": t("champ_nom")}, "liste": t("liste"),
        "usages": [CAT_VERS_USAGE[cat]], "main": "seconde", "cout": cout,  # une source ajoutée ici est de seconde main : elle ne compte jamais comme un endroit de plus tant qu'on ne l'a pas déclarée autrement
       
        "pays": [{"UK": "GB", "Mondial": "monde"}.get(pays, pays)] if pays else ["monde"], "description": t("description") or f"Source ajoutée par l'utilisateur ({t('nom')}).",
        "roles": ["verifier"] if d.get("role") == "VERIFIER" else ["chercher"],
    }  # fmt: skip
    if d.get("exemple") not in (None, ""):
        spec["exemple"] = d[
            "exemple"
        ]  # la réponse que l'utilisateur a vue : le test local la lit, il n'appelle jamais le service
    if t("cle_valeur"):
        spec.update(cle_valeur=t("cle_valeur"), auth={"type": t("auth") or "bearer"})
    decl, _ = sources_ajout.enregistrer(cfg, "api", spec)
    return decl.id
