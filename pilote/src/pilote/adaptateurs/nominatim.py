"""Nominatim (OpenStreetMap) : transforme le nom d'un endroit en zone géographique, et cherche des lieux nommés par texte libre.
Gratuit, mais UNE REQUÊTE PAR SECONDE AU MAXIMUM (politique d'usage de la fondation OpenStreetMap) : l'adaptateur impose ce délai quel
que soit le réglage, et s'identifie par un User-Agent précis. Seconde main : Nominatim ne fait que chercher dans les données
d'OpenStreetMap, que l'autre source (Overpass) lit directement ; il ne compte donc pas comme une confirmation de plus."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource

URL = "https://nominatim.openstreetmap.org/search"
DELAI_MIN_S = 1.0
RELATION, VOIE = 3_600_000_000, 2_400_000_000  # décalage des identifiants de zone d'Overpass


def _chercher(client: Client, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    client.delai_s = max(client.delai_s, DELAI_MIN_S)
    rep = client.get_json(url, {"format": "jsonv2", **params})
    if not isinstance(rep, list):
        raise ErreurSource("La réponse de Nominatim n'a pas la forme attendue.")
    return rep


def zone(client: Client, lieu: str, pays: str = "", url: str = URL) -> dict[str, Any]:
    """Zone d'un endroit : `{"area": identifiant Overpass}` si c'est une surface (ville, commune...), sinon `{"bbox": (sud, ouest, nord, est)}`."""
    p: dict[str, Any] = {"q": lieu, "limit": 5, "addressdetails": 0}
    if pays:
        p["countrycodes"] = pays.lower()
    trouves = _chercher(client, url, p)
    if not trouves:
        raise ErreurSource(f"Nominatim ne connaît pas l'endroit « {lieu} »" + (f" dans le pays {pays}." if pays else "."))
    def rectangle(r: dict[str, Any]) -> tuple[float, float, float, float] | None:
        bb = r.get("boundingbox")
        if not bb or len(bb) != 4:
            return None
        s, n, w, e = (float(x) for x in bb)  # Nominatim donne sud, nord, ouest, est
        return (s, w, n, e)

    for r in trouves:  # la première surface (ville, commune, région) d'abord
        if r.get("osm_type") == "relation" or (r.get("osm_type") == "way" and r.get("category") == "boundary"):
            decalage = RELATION if r["osm_type"] == "relation" else VOIE
            out: dict[str, Any] = {"area": decalage + int(r["osm_id"]), "nom": r.get("display_name", "")}
            if rectangle(r):  # le rectangle sert de secours quand les serveurs ne savent pas répondre par surface
                out["bbox"] = rectangle(r)
            return out
    bbox = rectangle(trouves[0])
    if not bbox:
        raise ErreurSource(f"Nominatim n'a pas donné de zone pour « {lieu} ».")
    return {"bbox": bbox, "nom": trouves[0].get("display_name", "")}


def convertir(rep: Any) -> list[dict[str, Any]]:
    """Lieux nommés rendus par Nominatim (nom, ville, coordonnées). Les surfaces administratives (villes, régions) ne sont pas des lieux à garder."""
    if not isinstance(rep, list):
        raise ErreurSource("La réponse de Nominatim n'a pas la forme attendue.")
    out = []
    for r in rep:
        if r.get("category") in ("boundary", "place") or not r.get("name"):
            continue
        morceaux = [m.strip() for m in str(r.get("display_name", "")).split(",")]
        e: dict[str, Any] = {"nom": str(r["name"]).strip(), "origine": "OpenStreetMap (recherche Nominatim)", "numero": f"{r.get('osm_type', '')}/{r.get('osm_id', '')}",
                             "ville": next((m for m in morceaux[1:4] if m and not m.isdigit()), ""), "genre": "lieu"}  # fmt: skip
        try:
            e["coordonnees"] = {"lat": float(r["lat"]), "lon": float(r["lon"])}
        except (KeyError, ValueError):
            pass
        out.append(e)
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    mots = " ".join([str(entree.get("quoi", "")).strip(), *map(str, entree.get("mots_cles") or [])]).strip()
    lieu = str(entree.get("lieu") or "").strip()
    if not mots or not lieu:
        return []  # sans endroit, une recherche de texte libre rendrait n'importe quoi à travers le monde
    p: dict[str, Any] = {"q": f"{mots} {lieu}", "limit": min(int(entree.get("limite") or 20), 40), "addressdetails": 0}
    if entree.get("pays"):
        p["countrycodes"] = str(entree["pays"]).lower()
    return convertir(_chercher(client, str(parametres.get("url", URL)), p))
