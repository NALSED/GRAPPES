"""Test LOCAL d'une source (fiche 11) : obligatoire avant d'activer, et il ne consomme RIEN (aucun crédit, aucun argent).

Quatre niveaux, dans l'ordre, arrêt au premier échec :
 1. configuration valide ;
 2. convention de sortie, vérifiée sur un exemple de réponse ENREGISTRÉ (la source n'est pas appelée) ;
 3. connexion et clé, seulement si le fournisseur offre un point d'accès GRATUIT pour ça, sinon « non vérifié » ;
 4. programme local : il tourne sur l'exemple, dans un processus séparé avec limite de temps.
Si tout passe, la source est « vérifiée hors ligne ». Sinon elle reste éteinte, avec la raison en français."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pilote import adaptateurs, cles
from pilote import reglages as rg
from pilote.adaptateurs import programmes
from pilote.config import Config
from pilote.etat_sources import maintenant_iso, noter
from pilote.grappes_lib import brancher
from pilote.refus import ConfigRefusee, lire_yaml
from pilote.sources import Declaration, valider_declaration

UA = "pilote/0.1 (outil local : test d'une source)"


class Echec(Exception):
    def __init__(self, niveau: int, raison: str):
        super().__init__(raison)
        self.niveau, self.raison = niveau, raison


def _definition_grappes(cfg: Config, moteur: dict[str, Any]) -> dict[str, Any]:
    """La définition (au format grappes) que la source utilisera : un fichier de grappes, ou une définition écrite dans la source."""
    if "prise" in moteur:
        dossier = cfg.dossier_grappes_config / "recherche"
        for f in sorted(dossier.glob("*.yaml")) if dossier.is_dir() else []:
            try:
                y = lire_yaml(f)
            except ConfigRefusee:
                continue
            if y.get("id") == moteur["prise"]:
                return y
        raise Echec(1, f"La prise « {moteur['prise']} » n'existe pas dans la configuration de grappes.")
    if "definition" in moteur:
        d = moteur["definition"]
        if not isinstance(d, dict) or d.get("type") not in ("http", "registre", "mcp"):
            raise Echec(1, "La définition de la source doit avoir un type : http, registre ou mcp.")
        return d
    raise Echec(1, "La source ne dit pas comment l'interroger (prise, définition ou programme).")


def _niveau1(cfg: Config, d: Declaration, brut: dict[str, Any]) -> dict[str, Any] | None:
    try:
        valider_declaration(brut, cfg, f"{d.id}.yaml")
    except ConfigRefusee as exc:
        raise Echec(1, str(exc)) from exc
    reg, _ = rg.charger_tolerant(cfg)
    donnes = rg.parametres_donnes(reg, d.id)
    for nom, spec in d.parametres.items():
        if spec.get("requis") and not str(donnes.get(nom, "")).strip():
            raise Echec(1, f"Il manque un réglage obligatoire : {str(spec.get('libelle', nom)).lower()}.")
    if "script" in d.moteur:
        s = d.moteur["script"]
        if not isinstance(s, dict) or not s.get("commande"):
            raise Echec(1, "Le programme local doit indiquer sa commande.")
        return None
    if "adaptateur" in d.moteur:
        try:
            adaptateurs.charger(str(d.moteur["adaptateur"]))
        except adaptateurs.ErreurSource as exc:
            raise Echec(1, f"Cette source demande un adaptateur : {exc}") from exc
        return None
    if "registre_grappes" in d.moteur:
        if d.moteur["registre_grappes"] not in ("wikidata", "sirene"):
            raise Echec(1, f"Le registre « {d.moteur['registre_grappes']} » n'est pas connu de grappes (wikidata ou sirene).")
        return None
    return _definition_grappes(cfg, d.moteur)


def extraire_noms(definition: dict[str, Any], corps: bytes) -> list[dict[str, str]]:
    """Applique à un exemple de réponse la lecture que grappes ferait : liste des éléments, puis nom (et ville, genre) de chacun."""
    brancher(CONFIG_COURANTE[0])
    from grappes.search.formats import decode
    from grappes.search.paths import resolve_field, select

    type_ = definition.get("type")
    if type_ == "registre":
        fmt = str(definition.get("format", "json"))
        champs = definition.get("fields") or {}
        cle_nom = "nom"
        items_path = (definition.get("response") or {}).get("items", "")
    else:
        resp = definition.get("response") or {}
        fmt = str(resp.get("format", "json"))
        champs = definition.get("fields") or {}
        cle_nom = "title"
        items_path = resp.get("items", "")
    try:
        racine = decode(corps, fmt, delimiter=str(definition.get("delimiter", ";")))
    except Exception as exc:
        raise Echec(2, "La sortie est illisible : l'exemple de réponse n'a pas le format annoncé.") from exc
    noms = []
    for it in select(racine, items_path) if items_path else (racine if isinstance(racine, list) else [racine]):
        nom = resolve_field(it, champs.get(cle_nom)).strip()
        if nom:
            noms.append({"nom": nom, "ville": resolve_field(it, champs.get("ville")).strip() if champs.get("ville") else ""})
    return noms


CONFIG_COURANTE: list[Config] = []


def _niveau2(cfg: Config, d: Declaration, definition: dict[str, Any] | None) -> list[dict[str, str]]:
    if not d.exemple_reponse:
        raise Echec(2, "La source ne fournit pas d'exemple de réponse enregistré : impossible de vérifier sa sortie sans l'appeler.")
    f = cfg.dossier_sources / d.exemple_reponse
    if not f.exists():
        raise Echec(2, f"L'exemple de réponse « {d.exemple_reponse} » est introuvable.")
    corps = f.read_bytes()
    if "adaptateur" in d.moteur:  # l'exemple est la réponse brute du service, que l'adaptateur sait lire
        return _lire_par_adaptateur(cfg, d, corps)
    if definition is None:  # programme local ou registre de grappes : l'exemple est la sortie attendue (liste JSON de noms)
        return _lire_sortie_programme(corps.decode("utf-8", "replace"))
    noms = extraire_noms(definition, corps)
    if not noms:
        raise Echec(2, "La sortie est illisible : aucun nom n'a pu être lu dans l'exemple de réponse.")
    return noms


def _lire_par_adaptateur(cfg: Config, d: Declaration, corps: bytes) -> list[dict[str, str]]:
    m = adaptateurs.charger(str(d.moteur["adaptateur"]))
    if not callable(getattr(m, "convertir", None)):
        raise Echec(2, "L'adaptateur ne sait pas lire un exemple de réponse enregistré.")
    texte = corps.decode("utf-8", "replace")
    reg, _ = rg.charger_tolerant(cfg)
    params = {**(d.moteur.get("parametres") or {}), **rg.parametres_donnes(reg, d.id)}
    try:
        brut: Any = texte if str(d.exemple_reponse).endswith(".txt") else json.loads(texte)
        try:
            if getattr(m, "LIT_PARAMETRES", False):  # adaptateur générique : sa lecture dépend des réglages de la source
                sortie = m.convertir(brut, parametres=params)
            else:
                sortie = m.convertir(brut, **({"portail": str(params.get("portail", "https://exemple.example"))} if "portail" in d.parametres else {}))
        except TypeError:
            sortie = m.convertir(brut)
    except adaptateurs.ErreurSource as exc:
        raise Echec(2, f"La sortie est illisible : {exc}") from exc
    except ValueError as exc:
        raise Echec(2, "La sortie est illisible : l'exemple de réponse n'a pas le format annoncé.") from exc
    return _lire_sortie_programme(json.dumps(sortie))


def _lire_sortie_programme(texte: str) -> list[dict[str, str]]:
    try:
        v = json.loads(texte)
    except ValueError as exc:
        raise Echec(2, "La sortie du programme n'est pas du JSON lisible.") from exc
    if isinstance(v, dict) and isinstance(v.get("noms"), list):
        v = v["noms"]
    if not isinstance(v, list) or not v:
        raise Echec(2, "Le programme doit rendre une liste de noms (au moins un).")
    out = []
    for x in v:
        if not isinstance(x, dict) or not str(x.get("nom", "")).strip() or not str(x.get("origine", "")).strip():
            raise Echec(2, "Chaque nom rendu par le programme doit avoir au minimum un « nom » et une « origine ».")
        out.append({"nom": str(x["nom"]).strip(), "ville": str(x.get("ville", "")).strip()})
    return out


def _niveau3(cfg: Config, d: Declaration) -> tuple[str, dict[str, Any] | None]:
    """('ok' | 'non_verifie', quota). Un point d'accès GRATUIT seulement ; sinon le niveau est sauté."""
    if d.cles and not cles.toutes_presentes(cfg, d.cles):
        raise Echec(3, f"La clé d'API ({', '.join(cles.manquantes(cfg, d.cles))}) est absente : ajoutez-la avant d'activer cette source.")
    t = d.test_connexion
    if not t or not t.get("url"):
        return "non_verifie", None
    req = urllib.request.Request(str(t["url"]), method=str(t.get("methode", "GET")), headers={"User-Agent": UA, "Accept": "application/json"})
    if d.cle and (t.get("auth") or {}).get("type", "bearer") == "bearer":
        req.add_header("Authorization", "Bearer " + cles.valeur(cfg, d.cle))
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            donnees = json.loads(r.read(1_000_000) or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise Echec(3, "La clé est refusée par le fournisseur.") from exc
        raise Echec(3, f"Le fournisseur a répondu une erreur ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Echec(3, "Le fournisseur ne répond pas.") from exc
    except ValueError as exc:
        raise Echec(3, "La réponse du point d'accès de test est illisible.") from exc
    quota = None
    q = t.get("quota") or {}
    if q:
        def chemin(path: str) -> Any:
            cur: Any = donnees
            for k in path.split("."):
                cur = cur[k]
            return cur

        try:
            total, utilise = float(chemin(q["limite"])), float(chemin(q["utilise"]))
            quota = {"restant": max(0.0, total - utilise), "total": total, "le": maintenant_iso()}
        except (KeyError, TypeError, ValueError):
            quota = None
    return "ok", quota


def _niveau4(cfg: Config, d: Declaration) -> list[dict[str, str]]:
    """Le programme local tourne sur l'exemple, dans un processus séparé, avec une limite de temps."""
    try:
        noms = programmes.executer(d.moteur["script"], {"sujet": "essai", "quoi": "essai", "lieu": "", "mots_cles": ["essai"], "pays": "", "limite": 5}, cwd=cfg.dossier_config)
    except adaptateurs.ErreurSource as exc:
        raise Echec(4, str(exc)) from exc
    return [{"nom": str(n["nom"]).strip(), "ville": str(n.get("ville", ""))} for n in noms]


def tester(cfg: Config, d: Declaration, brut: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lance le test local complet, écrit le dernier état connu de la source et le rend."""
    CONFIG_COURANTE[:] = [cfg]
    niveaux: dict[str, str] = {}
    quota = None
    noms: list[dict[str, str]] = []
    try:
        definition = _niveau1(cfg, d, brut if brut is not None else _brut(d))
        niveaux["1"] = "ok"
        noms = _niveau2(cfg, d, definition)
        niveaux["2"] = "ok"
        n3, quota = _niveau3(cfg, d)
        niveaux["3"] = n3
        if "script" in d.moteur:
            noms = _niveau4(cfg, d)
            niveaux["4"] = "ok"
        res = {"statut": "ok", "raison": "", "niveau_echec": None, "niveaux": niveaux, "noms_exemple": noms[:3]}
    except Echec as e:
        niveaux[str(e.niveau)] = "echec"
        res = {"statut": "echec", "raison": e.raison, "niveau_echec": e.niveau, "niveaux": niveaux, "noms_exemple": noms[:3]}
    champs: dict[str, Any] = {"teste_le": maintenant_iso(), "statut": res["statut"], "raison": res["raison"], "niveaux": niveaux}
    if quota:
        champs["quota"] = quota
    noter(cfg, d.id, **champs)
    return res


def _brut(d: Declaration) -> dict[str, Any]:
    """La déclaration relue sous forme de dictionnaire (pour la vérifier une seconde fois)."""
    return {
        "id": d.id, "nom": d.nom, "description": d.description, "trouve": d.trouve, "genres": d.genres, "pays": d.pays, "consomme": d.consomme,
        "produit": d.produit, "usages": d.usages, "main": d.main, "famille": d.famille, "cle": d.cles if len(d.cles) > 1 else d.cle, "cle_prefixe": d.cle_prefixe, "cout": d.cout, "confiance": d.confiance,
        "defaut": d.defaut, "roles": d.roles, "avertissement": d.avertissement, "mode": d.mode, "moteur": d.moteur, "exemple_reponse": d.exemple_reponse,
        "test_connexion": d.test_connexion, "verifie_le": d.verifie_le, "prestataire": d.prestataire, "note": d.note,
    }  # fmt: skip


# ---------------------------------------------------------------------------------------------------------------------
# Test RÉEL (facultatif, fiche 11) : une vraie requête. Le prix est dit AVANT le clic.


def prix_du_test(d: Declaration, cout: dict[str, Any], unites_deja: float = 0.0) -> dict[str, Any]:
    """Ce que coûtera le test réel : une requête. `cout` est le coût effectif de la source (celui de Réglages), et
    `unites_deja` ce qu'elle a déjà consommé ce mois-ci : sans lui, le prix annoncé disait « gratuit » après le quota
    gratuit épuisé, alors que la dépense était bien comptée."""
    from pilote import budget

    par = float(cout.get("par_appel", 1) or 0)
    dollars = budget.dollars_pour(cout, 1, unites_deja)
    if dollars <= 0:
        return {"gratuit": True, "dollars": 0.0, "unites": par, "phrase": "1 requête, gratuite : rien à payer."}
    unite = str(cout.get("unite", "appel"))
    detail = f" ({par:g} {unite}{'s' if par > 1 and not unite.endswith('s') else ''})" if par != 1 else ""
    return {"gratuit": False, "dollars": dollars, "unites": par, "phrase": f"1 requête{detail}, environ {dollars:.4f} $".replace(".", ",") + ", comptés dans votre plafond mensuel."}


def test_reel(cfg: Config, d: Declaration, mot: str, cout: dict[str, Any]) -> dict[str, Any]:
    """UNE vraie requête vers la source, avec le mot d'essai. Les sources interrogées par adaptateur ou programme sont prises en charge."""
    mot = mot.strip()
    if not mot:
        raise Echec(0, "Donnez un mot d'essai (par exemple « handball »).")
    if d.cles and not cles.toutes_presentes(cfg, d.cles):
        raise Echec(3, f"La clé d'API ({', '.join(cles.manquantes(cfg, d.cles))}) est absente : ajoutez-la d'abord.")
    entree = {"sujet": mot, "quoi": mot, "mots_cles": [], "lieu": "", "pays": "", "limite": 5}
    reg, _ = rg.charger_tolerant(cfg)
    params = {**(d.moteur.get("parametres") or {}), **rg.parametres_donnes(reg, d.id)}
    appels = 1
    try:
        if "script" in d.moteur:
            noms = programmes.executer(d.moteur["script"], entree, cwd=cfg.dossier_config)
        elif "adaptateur" in d.moteur:
            client = adaptateurs.Client(d.id, delai_s=0.5)
            params["_dossier_config"] = str(cfg.dossier_config)
            params["_dossier_copies"] = str(cfg.dossier_copies)
            if d.cles:
                params["_cle"] = cles.valeur(cfg, d.cles[0])
                params["_cles"] = {n: cles.valeur(cfg, n) for n in d.cles}
                if d.cle_prefixe:
                    params["_cle"] = d.cle_prefixe + params["_cle"]
            noms = adaptateurs.charger(str(d.moteur["adaptateur"])).chercher(entree, client, params)
            appels = max(1, client.appels)
        else:
            raise Echec(0, "Le test réel n'est pas encore proposé pour ce type de source : la première vraie recherche lui servira de test réel.")
    except adaptateurs.ErreurSource as exc:
        raise Echec(0, str(exc)) from exc
    except adaptateurs.LimiteAtteinte as exc:
        raise Echec(0, "Le test a été interrompu.") from exc
    noter(cfg, d.id, dernier_appel=maintenant_iso(), statut_reel="ok" if noms else "vide")
    return {"appels": appels, "total": len(noms), "noms": [{"nom": str(n["nom"]), "ville": str(n.get("ville", ""))} for n in noms[:5]]}
