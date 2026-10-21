"""Contrôle automatique des adresses mortes du catalogue par pays (fiche 15, chapitre 3).

Usage : .venv/bin/python outils/verifier_catalogue.py [--maj]
Sans option : rend la liste des adresses qui ne répondent plus (code de sortie 1 s'il y en a). Avec --maj : met aujourd'hui dans `verifie_le`
des entrées dont TOUTES les adresses répondent ; une entrée morte garde sa date, c'est ce qui la signale."""

from __future__ import annotations

import re
import sys
from datetime import date

from pilote import catalogue_pays
from pilote.config import charger


def main(maj: bool) -> int:
    cfg = charger()
    morts = catalogue_pays.verifier_adresses(cfg)
    for m in morts:
        print(f"MORT  {m['pays']}/{m['base']} : {m['adresse']} ({m['erreur']})")
    if maj:
        mortes = {(m["pays"], m["base"]) for m in morts}
        for f in sorted(catalogue_pays.dossier(cfg).glob("*.yaml")):
            texte, pays = f.read_text(encoding="utf-8"), f.stem
            blocs = re.split(r"(?m)^(?=  - id: )", texte)
            sortie = [blocs[0]]
            for b in blocs[1:]:
                ident = re.match(r"  - id: (\S+)", b).group(1)
                if (pays, ident) not in mortes:
                    b = re.sub(r"(?m)^(    verifie_le: ).*$", rf"\g<1>{date.today().isoformat()}", b)
                sortie.append(b)
            f.write_text("".join(sortie), encoding="utf-8")
    print(f"{len(morts)} adresse(s) morte(s).")
    return 1 if morts else 0


if __name__ == "__main__":
    sys.exit(main("--maj" in sys.argv))
