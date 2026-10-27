"""Précision et rappel de Fusion/doublons par seuil sur le jeu de cas difficiles français (`autocal_rapprochement_fr/cas.jsonl`)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pilote.rapprochement_splink import scorer

SEUILS = (0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95)


def mesurer(chemin: Path = RACINE / "autocal_rapprochement_fr" / "cas.jsonl") -> list[dict]:
    """Chaque paire est notée seule : les probabilités m/u sont fixes, une paire n'influence pas les autres."""
    out = []
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if not ligne.strip():
            continue
        cas = json.loads(ligne)
        paires = scorer([{"id": 1, **cas["a"]}, {"id": 2, **cas["b"]}], 0.0)
        out.append({**cas, "confiance": paires[0]["confiance"] if paires else 0.0})
    return out


def tableau(res: list[dict]) -> str:
    lignes = ["seuil  proposées  VP  FP  FN  précision  rappel"]
    vrais = sum(r["verdict"] == "meme" for r in res)
    for s in SEUILS:
        prop = [r for r in res if r["confiance"] >= s]
        vp = sum(r["verdict"] == "meme" for r in prop)
        fp, fn = len(prop) - vp, vrais - vp
        lignes.append(f"{s:5.2f}  {len(prop):9d}  {vp:2d}  {fp:2d}  {fn:2d}  {vp / len(prop) if prop else 1.0:9.3f}  {vp / vrais:6.3f}")
    return "\n".join(lignes)


if __name__ == "__main__":
    res = mesurer()
    seuil = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
    print(f"{len(res)} cas\n{tableau(res)}\n\nFaux positifs à {seuil} :")
    for r in sorted(res, key=lambda r: -r["confiance"]):
        if r["verdict"] == "differentes" and r["confiance"] >= seuil:
            print(f"  {r['confiance']:.2f}  {r['id']} — {r['raison']}")
    print(f"Faux négatifs à {seuil} :")
    for r in sorted(res, key=lambda r: r["confiance"]):
        if r["verdict"] == "meme" and r["confiance"] < seuil:
            print(f"  {r['confiance']:.2f}  {r['id']} — {r['raison']}")
