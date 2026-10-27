"""Format de sortie « FollowTheMoney » : un fichier NDJSON (une entité par ligne, extension `.ftm`) que les outils du même écosystème lisent
(Aleph, OpenAleph, la commande `ftm`). Idée reprise de leur modèle, pas leur code : une entité = `id` + `schema` + `properties`, chaque valeur est
une LISTE, et l'identifiant est stable (le même nom avec le même numéro officiel donne le même `id` d'une recherche à l'autre, donc une
réimportation ne crée pas de doublon).

Traçabilité (règle 1 de grappes) : seules les clés standard d'une entité sont écrites, la provenance est donc dans `notes` — une ligne par source
qui a trouvé le nom, la date et la recherche de collecte, et la décision de l'utilisateur quand il y en a une. Le format ne devine rien : une
propriété que pilote ne connaît pas n'est pas écrite, et un pays qui n'est pas un code à deux lettres n'est pas écrit comme `country`."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

FORMAT = {
    "id": "ftm",
    "nom": "FollowTheMoney",
    "description": "Une entité par ligne (NDJSON), lisible par Aleph et OpenAleph : identifiants stables, sources et date de collecte dans les notes.",
    "extension": ".ftm",
    "famille": "fichier",
    "contenus": ["detail"],
    "contenus_defaut": ["detail"],
}

SCHEMA_DU_GENRE = {
    "entreprise": "Company", "association": "Organization", "club": "Organization", "administration": "Organization",
    "evenement": "Event", "lieu": "Address",
}  # fmt: skip
DECISIONS = {"garder": "gardé", "rejeter": "rejeté", "plus_tard": "mis de côté"}


def _norme(t: str) -> str:
    return re.sub(
        r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    ).strip()


def identifiant(r: dict) -> str:
    """Stable : le nom normalisé, le numéro officiel et le pays. Sans numéro, deux homonymes d'un même pays se confondent (c'est dit dans la description du format)."""
    cle = "|".join((_norme(r["nom"]), _norme(r.get("numero_officiel") or ""), _norme(r.get("pays") or "")))
    return "pilote-" + hashlib.sha1(cle.encode("utf-8")).hexdigest()[:24]


def entite(r: dict, trace: dict) -> dict:
    genre = (r.get("genre") or "").strip().lower()
    schema = SCHEMA_DU_GENRE.get(genre, "LegalEntity")
    p: dict[str, list[str]] = {}

    def ajouter(cle: str, v: object) -> None:
        v = str(v or "").strip()
        if v:
            p.setdefault(cle, []).append(v)

    if schema == "Address":
        ajouter("full", r["nom"])
        ajouter("city", r.get("ville"))
    else:
        ajouter("name", r["nom"])
        ajouter("address", r.get("ville"))
        if schema in ("Company", "Organization", "LegalEntity"):
            ajouter("registrationNumber", r.get("numero_officiel"))
            ajouter("website", r.get("site"))
    pays = str(r.get("pays") or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", pays) and schema != "Event":
        ajouter("country", pays.lower())
    for s in r.get("sources") or []:
        ajouter("notes", f"Trouvé par : {s}")
    ajouter(
        "notes", f"Collecté le {str(trace.get('date', ''))[:10]} par pilote (recherche {trace.get('recherche', '')})."
    )
    if r.get("decision") in DECISIONS:
        ajouter("notes", f"Décision de l'utilisateur : {DECISIONS[r['decision']]}.")
    return {"id": identifiant(r), "schema": schema, "properties": p}


def _personne_physique(r: dict) -> bool:
    """Règle 8, pour CETTE sortie. Deux signaux, pas un :

    * le genre « personne » écrit sur la fiche ;
    * `regle8_personne`, le constat posé à la collecte (`pilote.regle8.est_personne`), qui reste vrai même quand le levier de recherche
      « afficher les comptes écartés » a laissé le genre déclaré par la source. Sans ce second signal, un levier prévu pour le seul
      rapprochement ouvrait aussi cette sortie, en silence.

    Une seule chose rouvre la porte : qu'une personne ait explicitement déclaré CETTE fiche comme personne morale dans l'onglet Tri
    (`regle8_leve`). Un interrupteur de recherche ne suffit jamais ; une décision humaine, fiche par fiche, oui."""
    if r.get("regle8_leve"):
        return False
    return (r.get("genre") or "").strip().lower() == "personne" or bool(r.get("regle8_personne"))


def ecrire(jeu: dict, contenu: str, options: dict, chemin: Path) -> dict:
    """Règle 8 de grappes : on vise les personnes morales. Une fiche de personne physique n'est PAS écrite (le schéma `Person` n'existe
    pas ici) ; leur nombre est rendu, pour que l'absence se dise. Voir `_personne_physique` pour ce qui compte comme telle."""
    gardees = [r for r in jeu["lignes"] if not _personne_physique(r)]
    lignes = [json.dumps(entite(r, jeu["trace"]), ensure_ascii=False, sort_keys=True) for r in gardees]
    chemin.write_text("".join(x + "\n" for x in lignes), encoding="utf-8")
    return {"fichiers": [chemin], "ignorees_personnes_physiques": len(jeu["lignes"]) - len(gardees)}
