"""Portails de données ouvertes « CKAN » : UNE source générique, l'adresse du portail est un PARAMÈTRE. Elle couvre ainsi des dizaines de
pays sans code propre à aucun. On y lit les organisations qui publient (`organization_list`). Première main."""

from __future__ import annotations

from typing import Any

from pilote.adaptateurs import Client, ErreurSource, mots_significatifs


def convertir(rep: dict[str, Any], portail: str, pays: str = "") -> list[dict[str, Any]]:
    if not isinstance(rep, dict) or not rep.get("success"):
        raise ErreurSource("Ce portail ne répond pas comme un portail CKAN (pas de liste d'organisations).")
    hote = portail.split("//", 1)[-1].split("/")[0]
    out = []
    for o in rep.get("result") or []:
        nom = str(o.get("display_name") or o.get("title") or "").strip()
        if nom:
            out.append({"nom": nom, "origine": f"portail de données ouvertes {hote}", "numero": "", "site": f"{portail}/organization/{o.get('name', '')}",
                        "pays": pays, "genre": "administration", "_id": str(o.get("id", nom))})  # fmt: skip
    return out


def chercher(entree: dict[str, Any], client: Client, parametres: dict[str, Any]) -> list[dict[str, Any]]:
    portail = str(parametres.get("portail", "")).strip().rstrip("/")
    if not portail.startswith(("http://", "https://")):
        raise ErreurSource("Donnez l'adresse du portail de données ouvertes de votre pays (elle commence par https://).")
    limite = int(entree.get("limite") or 20)
    vus: dict[str, dict[str, Any]] = {}
    for mot in mots_significatifs(" ".join([str(entree.get("quoi", "")), *map(str, entree.get("mots_cles") or [])])):
        rep = client.get_json(f"{portail}/api/3/action/organization_list", {"all_fields": "true", "q": mot, "limit": min(limite, 100)})
        for e in convertir(rep, portail, str(entree.get("pays") or "")):
            if e["_id"] not in vus:
                vus[e["_id"]] = {k: v for k, v in e.items() if k != "_id"}
        if len(vus) >= limite:
            break
    return list(vus.values())[:limite]
