"""Le plan de travail APPLIQUÉ par le moteur (spécification 08 : « on tire les liens soi-même » — et le moteur obéit).

Deux temps, tous deux sans réseau et sans modèle :
 * `compiler(plan, …)` lit le plan (tuiles + liens) et en tire des consignes : quelles sources partent (celles dont un chemin va de « Ta saisie » à
   « Grappes »), quelles sources de vérification agissent sur les résultats de quelles sources, quelles étapes s'appliquent sur chaque
   branche (filtre, condition, script), quelle langue de requête chaque source reçoit. Ce qui n'est pas appliqué est DIT avec sa raison ;
   un plan incohérent est refusé avant tout appel.
 * `appliquer(lignes, consignes)` joue les étapes sur les noms trouvés. Règle de lecture d'un plan : un nom est gardé si AU MOINS UNE des sources
   qui l'ont trouvé a un chemin jusqu'à « Grappes » dont toutes les étapes le laissent passer. Un nom trouvé par une source qui n'est pas sur le
   plan (page d'un moteur de recherche, par exemple) n'est pas jugé : il est gardé, et compté à part.

Ce module n'importe rien de grappes : il tourne dans le service et dans le pont."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from pilote.refus import ConfigRefusee

CHAMPS = {
    "nom": "nom", "ville": "ville", "pays": "pays", "genre": "genre_de_chose", "categorie": "genre_de_chose", "type": "genre_de_chose",
    "origine": "genre_source", "site": "site", "numero": "numero_officiel", "numero officiel": "numero_officiel", "fonction": "fonction",
}  # fmt: skip
LANGUES = {
    "francais": "fr", "anglais": "en", "allemand": "de", "espagnol": "es", "italien": "it", "neerlandais": "nl", "portugais": "pt", "polonais": "pl", "russe": "ru",
    "finnois": "fi", "suedois": "sv", "norvegien": "no", "danois": "da", "tcheque": "cs", "estonien": "et", "arabe": "ar", "turc": "tr", "chinois": "zh", "japonais": "ja",
}  # fmt: skip
NON_APPLIQUES = {
    "boucle": "répéter une recherche pour chaque élément d'une liste n'est pas encore branché dans le moteur",
    "attente": "faire patienter une recherche quand un quota est atteint n'est pas encore branché : le moteur s'arrête à la limite d'appels",
    "budget": "le plafond de dépense est celui de Réglages (en dollars) : un budget propre à la recherche n'est pas encore branché",
    "ia": "l'Assistant IA ne s'exécute pas encore : rien de ce qu'il produirait n'entre dans une grappe",
    "rsshub": "transformer un site en flux RSS n'est pas encore branché",
}  # fmt: skip
MAX_CHEMINS = 300


def norme(t: Any) -> str:
    return re.sub(
        r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    ).strip()


def codes_langues(texte: str) -> list[str]:
    out = []
    for mot in re.split(r"[,;/]|\bet\b", texte):
        n = norme(mot)
        if not n:
            continue
        code = LANGUES.get(n) or (n if re.fullmatch(r"[a-z]{2,3}", n) else None)
        if not code:
            raise ConfigRefusee(
                f"« {mot.strip()} » n'est pas une langue connue : écris son nom (français, anglais…) ou son code (fr, en…)."
            )
        out.append(code)
    return list(dict.fromkeys(out))


def _option(opts: list, indice: int, mot: str = "") -> str:
    """La valeur d'une option de tuile : celle dont le libellé contient `mot`, sinon la n-ième (une tuile copie les options de sa fiche)."""
    for lib, v in opts:
        if mot and mot in norme(lib):
            return str(v)
    return str(opts[indice][1]) if len(opts) > indice else ""


def _etape_champ(nom: str, opts: list, tuile: str, op: str) -> dict[str, Any]:
    champ = norme(_option(opts, 0, "champ"))
    if champ not in CHAMPS:
        raise ConfigRefusee(
            f"« {nom} » : le champ « {champ or '(vide)'} » n'existe pas. Champs : {', '.join(sorted({k for k in CHAMPS if k not in ('type', 'numero officiel', 'categorie')}))}."
        )
    valeurs = [v.strip() for v in re.split(r"[,;]", _option(opts, 1, "egal")) if v.strip()]
    if not valeurs:
        raise ConfigRefusee(f"« {nom} » : dis à quoi le champ « {champ} » doit être égal.")
    return {"op": op, "champ": CHAMPS[champ], "valeurs": valeurs, "tuile": tuile, "nom": nom}


def _genre_outil(o: dict[str, Any]) -> str:
    """Ce que fait un outil : son identifiant s'il est livré, le modèle dont il part s'il est créé, « script » s'il est collé."""
    if o.get("nature") == "script":
        return "script"
    return str(o.get("modele") or o["id"])


def compiler(plan: dict[str, Any], sources: list[dict[str, Any]], outils: list[dict[str, Any]], *, pays_equiv: dict[str, list[str]] | None = None,
             langue_saisie: str | None = None, traduction_disponible: bool = False) -> dict[str, Any]:  # fmt: skip
    nodes = {n["id"]: n for n in plan.get("nodes", [])}
    edges = [e for e in plan.get("edges", []) if e["from"] in nodes and e["to"] in nodes]
    par_source = {s["id"]: s for s in sources}
    par_outil = {o["id"]: o for o in outils}
    succ: dict[str, list[dict[str, Any]]] = {i: [] for i in nodes}
    pred: dict[str, list[str]] = {i: [] for i in nodes}
    for e in edges:
        succ[e["from"]].append(e)
        pred[e["to"]].append(e["from"])
    departs = [i for i, n in nodes.items() if n["role"] == "ENTREE"]
    arrivees = {i for i, n in nodes.items() if n["role"] == "GRAPPES"}
    if not departs or not arrivees:
        raise ConfigRefusee("Le plan n'a pas sa tuile « Ta saisie » ou sa tuile « Grappes ».")

    def atteint(depart: list[str], voisins: dict[str, list[str]]) -> set[str]:
        vus, pile = set(), list(depart)
        while pile:
            n = pile.pop()
            for m in voisins.get(n, []):
                if m not in vus:
                    vus.add(m)
                    pile.append(m)
        return vus

    avant = atteint(departs, {i: [e["to"] for e in v] for i, v in succ.items()})  # ce qui part de la saisie
    apres = atteint(list(arrivees), pred)  # ce qui peut arriver aux grappes
    for i in nodes:  # une boucle dans le plan : on ne sait pas dans quel ordre jouer ses étapes
        if i in avant and _dans_un_cycle(i, succ):
            raise ConfigRefusee(
                f"Le plan tourne en rond autour de « {nodes[i]['nom']} » : un lien doit toujours aller vers l'avant."
            )
    utiles = {
        i for i in nodes if (i in avant or i in departs) and (i in apres or i in arrivees)
    }  # sur un chemin de la saisie aux grappes
    ref = lambda i: nodes[i].get("ref")
    chemin_sources = [i for i in utiles if ref(i) in par_source]
    chemin_outils = [i for i in utiles if ref(i) in par_outil]
    appliques: list[dict[str, Any]] = []
    non_appliques: list[dict[str, Any]] = []

    def dire_non(i: str, raison: str) -> None:
        non_appliques.append({"tuile": i, "nom": nodes[i]["nom"], "raison": raison})

    # --- quelles sources partent, et lesquelles vérifient quoi
    ancetres_sources = {i: {a for a in atteint([i], pred) if ref(a) in par_source} for i in nodes}
    cherchent, verifient = [], []
    for i in chemin_sources:
        s = par_source[ref(i)]
        if s["role"] == "VERIFIER":
            verifient.append(
                {
                    "id": s["id"],
                    "tuile": i,
                    "en_amont": sorted(
                        {ref(a) for a in ancetres_sources[i] if par_source[ref(a)]["role"] != "VERIFIER"}
                    )
                    or None,
                }
            )
        else:
            cherchent.append(s["id"])
    # --- les étapes de chaque branche : tous les chemins d'une source jusqu'à « Grappes », avec les étapes des tuiles rencontrées
    chemins: list[dict[str, Any]] = []

    def etapes_de(m: str, sortie: dict[str, Any]) -> list[dict[str, Any]]:
        """Ce que la tuile `m` fait aux noms qui la traversent en sortant par le lien `sortie` (une condition n'a pas la même étape selon sa sortie)."""
        o = par_outil.get(ref(m))
        if o is None:
            return []
        node = nodes[m]
        genre = _genre_outil(o)
        opts = node.get("opts") or o.get("options") or []
        if genre == "filtre":
            return [_etape_champ(node["nom"], opts, m, "garder")]
        if genre == "si":
            if sortie.get("label") not in ("oui", "non"):
                raise ConfigRefusee(
                    f"« {node['nom']} » a deux sorties : dis laquelle est « oui » et laquelle est « non » (dans la fenêtre de la tuile)."
                )
            return [_etape_champ(node["nom"], opts, m, "garder" if sortie["label"] == "oui" else "ecarter")]
        if genre == "script":
            return [{"op": "script", "code": o.get("code", ""), "tuile": m, "nom": node["nom"]}]
        return []

    def visiter(m: str, etapes: list[dict[str, Any]], vu: tuple[str, ...], source: str) -> None:
        if m in arrivees:
            chemins.append({"source": source, "etapes": etapes})
            if len(chemins) > MAX_CHEMINS:
                raise ConfigRefusee(
                    "Le plan a trop de chemins différents entre les sources et « Grappes » : simplifie-le."
                )
            return
        for e in succ[m]:
            if e["to"] in utiles and e["to"] not in vu:
                visiter(e["to"], etapes + etapes_de(m, e), vu + (m,), source)

    for i in chemin_sources:
        if par_source[ref(i)]["role"] != "VERIFIER":
            visiter(i, [], (i,), par_source[ref(i)]["id"])
    # --- la sortie, les outils sans effet réel, ceux qu'on ne branche pas
    formats: list[str] | None = None
    traductions: dict[str, dict[str, Any]] = {}
    for i in chemin_outils:
        node, o = nodes[i], par_outil[ref(i)]
        genre = _genre_outil(o)
        opts = node.get("opts") or o.get("options") or []
        if o["etat"] == "off":
            raise ConfigRefusee(f"L'outil « {node['nom']} » est éteint dans Réglages : allume-le, ou retire sa tuile.")
        if genre in ("filtre", "si", "script"):
            appliques.append(
                {"tuile": i, "nom": node["nom"], "texte": "joué sur les résultats de chaque branche où il se trouve"}
            )
        elif genre == "fusion":
            appliques.append(
                {
                    "tuile": i,
                    "nom": node["nom"],
                    "texte": "le moteur regroupe déjà les doublons ; la règle « même entité si » n'est pas réglable",
                }
            )
        elif genre == "format":
            valeur = norme(_option(opts, 0, "format"))
            choisis = [f for f in ("csv", "json") if f in valeur.split()]
            if not choisis:
                raise ConfigRefusee(f"« {node['nom']} » : le format de sortie est CSV ou JSON.")
            formats = list(dict.fromkeys([*(formats or []), *choisis]))
            appliques.append(
                {
                    "tuile": i,
                    "nom": node["nom"],
                    "texte": f"sortie {', '.join(x.upper() for x in choisis)} (le séparateur n'est pas réglable)",
                }
            )
        elif genre == "traduction":
            _traduction(
                i,
                node,
                opts,
                ancetres_sources,
                nodes,
                par_source,
                cherchent,
                avant,
                pred,
                traductions,
                appliques,
                dire_non,
                langue_saisie,
                traduction_disponible,
            )
        elif genre in NON_APPLIQUES:
            dire_non(i, NON_APPLIQUES[genre])
        else:
            dire_non(i, "cet outil n'a pas de comportement connu du moteur")
    for v in verifient:
        appliques.append(
            {
                "tuile": v["tuile"],
                "nom": nodes[v["tuile"]]["nom"],
                "texte": "vérifie "
                + ("les résultats des sources placées avant elle" if v["en_amont"] else "tous les résultats"),
            }
        )
    ordre = {i: k for k, i in enumerate(nodes)}
    return {
        "sources": sorted(dict.fromkeys(cherchent), key=lambda s: min(ordre[i] for i in chemin_sources if ref(i) == s)), "verificateurs": [{"id": v["id"], "en_amont": v["en_amont"]} for v in verifient],
        "chemins": chemins, "traductions": traductions, "format": formats, "appliques": appliques, "non_appliques": non_appliques,
        "pays_equiv": pays_equiv or {},
    }  # fmt: skip


def _dans_un_cycle(i: str, succ: dict[str, list[dict[str, Any]]]) -> bool:
    vus, pile = set(), [e["to"] for e in succ[i]]
    while pile:
        n = pile.pop()
        if n == i:
            return True
        if n in vus:
            continue
        vus.add(n)
        pile += [e["to"] for e in succ[n]]
    return False


def _traduction(
    i,
    node,
    opts,
    ancetres_sources,
    nodes,
    par_source,
    cherchent,
    avant,
    pred,
    traductions,
    appliques,
    dire_non,
    langue_saisie,
    disponible,
) -> None:
    """Une Traduction AVANT une source traduit la requête vers la langue de cette source (son champ Langue, d'où l'intérêt du champ). Après une
    source, elle traduirait les résultats : pas branché. Et sans reconnaissance d'entités nommées, la protection des noms propres n'est pas possible."""
    descendants = set()
    pile = [i]
    succ_de = {}
    for n_id in nodes:
        for p in pred[n_id]:
            succ_de.setdefault(p, []).append(n_id)
    while pile:
        for m in succ_de.get(pile.pop(), []):
            if m not in descendants:
                descendants.add(m)
                pile.append(m)
    sources_apres = [
        m
        for m in descendants
        if nodes[m].get("ref") in par_source and par_source[nodes[m]["ref"]]["role"] != "VERIFIER"
    ]
    if not sources_apres:
        dire_non(i, "placée après les sources, elle traduirait les résultats : ce n'est pas encore branché")
        return
    if "propre" in norme(_option(opts, 2, "ne pas traduire")):
        dire_non(
            i,
            "« ne pas traduire les noms propres » demande une reconnaissance d'entités nommées, pas encore branchée : décoche cette option pour traduire toute la saisie",
        )
        return
    if not disponible:
        dire_non(i, "aucun moteur de traduction n'est réglé (suite.traduction_url dans pilote.yaml)")
        return
    cibles = codes_langues(_option(opts, 1, "traduire vers"))
    entree_txt = norme(_option(opts, 0, "entree"))
    entree = None if entree_txt in ("", "detecter", "auto") else (codes_langues(entree_txt) or [None])[0]
    entree = entree or langue_saisie
    if not entree:
        dire_non(i, "la langue de la saisie n'a pas pu être détectée : donne-la dans l'option « Langue d'entrée »")
        return
    faites = []
    for m in sources_apres:
        s = par_source[nodes[m]["ref"]]
        if s["langue"] in cibles and s["langue"] != entree:
            traductions[s["id"]] = {"tuile": i, "de": entree, "vers": s["langue"]}
            faites.append(s["nom"])
    appliques.append(
        {
            "tuile": i,
            "nom": node["nom"],
            "texte": ("requête traduite pour " + ", ".join(faites))
            if faites
            else f"aucune source après elle ne cherche dans une autre langue que {entree} parmi {', '.join(cibles)}",
        }
    )


# ---------------------------------------------------------------- jouer les étapes


def valeur(ligne: dict[str, Any], champ: str) -> str:
    if champ == "fonction":
        return str((ligne.get("faits") or {}).get("fonction") or "")
    return str(ligne.get(champ) or "")


def _egal(v: str, valeurs: list[str], equiv: dict[str, list[str]]) -> bool:
    cibles = {norme(x) for x in valeurs}
    for c in list(cibles):
        cibles |= set(equiv.get(c, ()))
    n = norme(v)
    return n in cibles or any(n in equiv.get(c, ()) for c in cibles)


def _entree_script(ligne: dict[str, Any]) -> dict[str, Any]:
    return {"nom": ligne["nom"], "ville": ligne.get("ville", ""), "pays": ligne.get("pays", ""), "genre": ligne.get("genre_de_chose", ""), "origine": ligne.get("genre_source", ""),
            "site": ligne.get("site", ""), "numero": ligne.get("numero_officiel", ""), "fonction": valeur(ligne, "fonction"), "sources": list(ligne.get("trouve_par") or [])}  # fmt: skip


def appliquer(
    lignes: list[dict[str, Any]], consignes: dict[str, Any], lancer_script=None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Garde les noms que le plan laisse passer. `lancer_script(code, entree_json) -> {ok, sortie, erreur}` joue un script d'outil dans son bac à sable.
    Rend (noms gardés, bilan) ; le bilan dit, par tuile, combien de noms elle a retirés (et lesquels, en partie), et ce qui n'a pas pu être jugé."""
    import json

    equiv = consignes.get("pays_equiv") or {}
    plan_sources = set(consignes.get("sources") or [])
    gardes: set[int] = set()
    retires_par_tuile: dict[str, dict[str, Any]] = {}
    erreurs: list[str] = []
    for ch in consignes.get("chemins", []):
        courant = [k for k, ligne in enumerate(lignes) if ch["source"] in (ligne.get("trouve_par") or [])]
        for etape in ch["etapes"]:
            avant = len(courant)
            if etape["op"] in ("garder", "ecarter"):
                passe = [
                    k
                    for k in courant
                    if _egal(valeur(lignes[k], etape["champ"]), etape["valeurs"], equiv) == (etape["op"] == "garder")
                ]
            else:
                res = (
                    lancer_script(
                        etape["code"], json.dumps([_entree_script(lignes[k]) for k in courant], ensure_ascii=False)
                    )
                    if lancer_script
                    else {"ok": False, "erreur": "aucun bac à sable"}
                )
                if not res["ok"]:
                    erreurs.append(
                        f"« {etape['nom']} » : {res.get('erreur', 'le script a échoué')}. Les noms n'ont pas été jugés par ce script."
                    )
                    passe = courant
                else:
                    gardes_noms = {norme(x.get("nom")) for x in json.loads(res["sortie"]) if isinstance(x, dict)}
                    passe = [k for k in courant if norme(lignes[k]["nom"]) in gardes_noms]
            t = retires_par_tuile.setdefault(etape["tuile"], {"nom": etape["nom"], "n": 0, "noms": []})
            for k in set(courant) - set(passe):
                if lignes[k]["nom"] not in t["noms"] and len(t["noms"]) < 30:
                    t["noms"].append(lignes[k]["nom"])
            t["n"] += avant - len(passe)
            courant = passe
        gardes |= set(courant)
    non_attribues = [k for k, ligne in enumerate(lignes) if not (set(ligne.get("trouve_par") or []) & plan_sources)]
    gardes |= set(non_attribues)
    gardees = [ligne for k, ligne in enumerate(lignes) if k in gardes]
    bilan = {
        "gardes": len(gardees),
        "retires": len(lignes) - len(gardees),
        "non_attribues": len(non_attribues),
        "par_tuile": retires_par_tuile,
        "erreurs": erreurs,
    }
    return gardees, bilan
