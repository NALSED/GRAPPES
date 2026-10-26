"""Génère, depuis la charte livrée dans `suite/pilote/charte`, les fichiers que la suite pilote reprend telle quelle :
jetons CSS, styles de texte et espacements (tirés de tokens.json), table des pictogrammes, liste close des mots.
Rien n'est écrit à la main dans ces fichiers : relancer ce script les régénère."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CHARTE = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/grappes/suite/pilote/charte")
SORTIE = RACINE / "static" / "suite"


def typo_et_espaces(tokens: dict) -> str:
    fam = tokens["type"]["families"]
    out = ["/* Généré par outils/generer_suite.py depuis charte/tokens.json — ne pas modifier à la main. */", ":root {"]
    out.append(f"  --police-sans: {fam['sans']};")
    out.append(f"  --police-mono: {fam['mono']};")
    for g in tokens["type"]["groups"]:
        for s in g["styles"]:
            n = s["name"]
            out.append(f"  --{n}-taille: {s['fontSize']};")
            out.append(f"  --{n}-interligne: {s['lineHeight']};")
            out.append(f"  --{n}-graisse: {s['fontWeight']};")
            if s.get("letterSpacing"):
                out.append(f"  --{n}-crenage: {s['letterSpacing']};")
    for t in tokens["spacing"]["tokens"]:
        out.append(f"  --{t['name']}: {t['value']};")
    out.append("}")
    out.append("")
    for g in tokens["type"]["groups"]:
        fam_var = "var(--police-mono)" if g["family"] == "mono" else "var(--police-sans)"
        for s in g["styles"]:
            n = s["name"]
            lig = [
                f"font-family: {fam_var}",
                f"font-size: var(--{n}-taille)",
                f"line-height: var(--{n}-interligne)",
                f"font-weight: var(--{n}-graisse)",
            ]
            if s.get("letterSpacing"):
                lig.append(f"letter-spacing: var(--{n}-crenage)")
            if n == "etiquette":
                lig.append("text-transform: uppercase")
            out.append(f".t-{n} {{ " + "; ".join(lig) + "; }")
    return "\n".join(out) + "\n"


def pictogrammes(readme: str) -> dict[str, str]:
    res = {}
    for m in re.finditer(r"^\| `([a-z-]+)` \|.*\| `([^`]+)` \|$", readme, re.MULTILINE):
        res[m.group(1)] = m.group(2)
    return res


def main() -> None:
    (SORTIE / "charte").mkdir(parents=True, exist_ok=True)
    (SORTIE / "js").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CHARTE / "jetons.css", SORTIE / "charte" / "jetons.css")
    tokens = json.loads((CHARTE / "tokens.json").read_text(encoding="utf-8"))
    (SORTIE / "charte" / "typo.css").write_text(typo_et_espaces(tokens), encoding="utf-8")
    picto = pictogrammes((CHARTE / "composants" / "Pictogrammes" / "README.md").read_text(encoding="utf-8"))
    if len(picto) != 31:
        raise SystemExit(f"31 pictogrammes attendus, {len(picto)} lus")
    js = "// Généré par outils/generer_suite.py : la table unique des 31 pictogrammes (charte/composants/Pictogrammes).\n"
    js += "export const PICTOGRAMMES = " + json.dumps(picto, ensure_ascii=False, indent=2) + ";\n"
    (SORTIE / "js" / "pictogrammes.js").write_text(js, encoding="utf-8")
    (RACINE / "config" / "suite").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CHARTE / "nommage.md", RACINE / "config" / "suite" / "nommage.md")
    print("ok :", len(picto), "pictogrammes")


if __name__ == "__main__":
    main()
