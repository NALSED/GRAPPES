"""recherche-entreprises (api.gouv.fr) : annuaire français des entreprises (SIRENE) et des associations (RNA). Première main.
Paramètre `filtre` : « association » (seulement les associations), « entreprise » (hors associations), ou vide (tout)."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs

URL = "https://recherche-entreprises.api.gouv.fr/search"
PAR_PAGE = 25


def _genre(r: dict[str, Any]) -> str:
    c = r.get("complements") or {}
    if c.get("est_association"):
        return "association"
    if c.get("collectivite_territoriale") or c.get("est_service_public") or c.get("est_administration"):
        return "administration"
    return "entreprise"


def _etablissement(r: dict[str, Any], nom_siege: str, et: dict[str, Any]) -> dict[str, Any] | None:
    """Un établissement distinct du siège, rendu comme un nom à part qui renvoie à son siège (Tri les regroupe dans un seul bloc)."""
    if et.get("est_siege") or et.get("etat_administratif") not in (None, "A"):
        return None
    ville = str(et.get("libelle_commune") or "").title()
    enseigne = ((et.get("liste_enseignes") or [None])[0]) or ""
    nom = str(enseigne).strip().title() or (f"{nom_siege} — {ville}" if ville else "")
    if not nom:
        return None
    e: dict[str, Any] = {"nom": nom, "origine": "annuaire des entreprises et des associations (registre officiel)", "numero": str(et.get("siret") or ""),
                         "ville": ville, "pays": "FR", "genre": "entreprise", "fonction": "établissement",
                         "relations": [{"type": "etablissement_de", "vers": nom_siege}]}  # fmt: skip
    if et.get("latitude") and et.get("longitude"):
        try:
            e["coordonnees"] = {"lat": float(et["latitude"]), "lon": float(et["longitude"])}
        except ValueError:
            pass
    return e


def convertir(rep: dict[str, Any], filtre: str = "", etablissements: int = 0) -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or "results" not in rep:
        raise ErreurSource("La réponse de l'annuaire des entreprises n'a pas la forme attendue.")
    out = []
    for r in rep.get("results") or []:
        nom = str(r.get("nom_complet") or r.get("nom_raison_sociale") or "").strip()
        if not nom:
            continue
        genre = _genre(r)
        if (filtre == "association" and genre != "association") or (filtre == "entreprise" and genre == "association"):
            continue
        s = r.get("siege") or {}
        c = r.get("complements") or {}
        e: dict[str, Any] = {
            "nom": nom, "origine": "annuaire des entreprises et des associations (registre officiel)",
            "numero": str(c.get("identifiant_association") or r.get("siren") or ""), "ville": str(s.get("libelle_commune") or "").title(),
            "pays": "FR", "genre": genre, "fonction": "siège",
        }  # fmt: skip
        if s.get("latitude") and s.get("longitude"):
            try:
                e["coordonnees"] = {"lat": float(s["latitude"]), "lon": float(s["longitude"])}
            except ValueError:
                pass
        out.append(e)
        if etablissements and genre != "association":
            autres = [x for x in (_etablissement(r, nom, et) for et in (r.get("matching_etablissements") or [])) if x]
            if autres:
                e["relations"] = [{"type": "a_pour_etablissement", "vers": x["nom"]} for x in autres[:etablissements]]
            out += autres[:etablissements]
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    pays = str(entree.get("pays") or "").upper()
    if pays and pays != "FR":
        return []
    filtre = str(parametres.get("filtre", ""))
    q = " ".join(mots_significatifs(" ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])]), 4))
    if not q:
        return []
    limite = int(entree.get("limite") or 25)
    extra: dict[str, Any] = {"est_association": "true"} if filtre == "association" else {}
    if entree.get("lieu"):
        extra["q"] = f"{q} {entree['lieu']}"
    out: list[dict[str, Any]] = []
    for page in range(1, 5):
        rep = client.get_json(URL, {"q": extra.pop("q", q), "page": page, "per_page": PAR_PAGE, "etat_administratif": "A", **extra})
        out += convertir(rep, filtre, int(parametres.get("etablissements", 0)))
        if len(out) >= limite or page >= int(rep.get("total_pages") or 1):
            break
    return out[:limite]
