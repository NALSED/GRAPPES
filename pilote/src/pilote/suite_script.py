"""Exécution d'un script d'outil, pour son TEST seulement : un processus à part, sans réseau (espace de noms réseau vide quand le
système le permet), 10 secondes de processeur au plus, 256 Mo de mémoire, aucune variable d'environnement héritée (donc aucune clé).

Ce n'est pas un coffre-fort : un script malveillant local n'est pas l'ennemi visé, une erreur de l'utilisateur l'est (boucle sans fin,
appel réseau par réflexe). Le script reçoit une liste de dictionnaires et doit rendre une liste."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DELAI_S = 10
SORTIE_MAX = 20_000

_ENVELOPPE = r"""
import json, resource, sys
resource.setrlimit(resource.RLIMIT_CPU, (%(cpu)d, %(cpu)d))
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
entree = json.loads(sys.stdin.read())
espace = {}
exec(compile(open(sys.argv[1], encoding="utf-8").read(), "script", "exec"), espace)
resultat = espace["run"](entree)
if not isinstance(resultat, list):
    raise TypeError("run() doit renvoyer une liste")
sys.stdout.write(json.dumps(resultat, ensure_ascii=False))
"""


def executer(code: str, entree: str) -> dict:
    """{ok, sortie, erreur?}. L'entrée est une liste JSON de dictionnaires."""
    try:
        donnees = json.loads(entree)
    except ValueError:
        return {
            "ok": False,
            "sortie": "",
            "erreur": 'L\'exemple d\'entrée d\'un script est une liste JSON, par exemple [{"pays": "FR"}].',
        }
    if not isinstance(donnees, list) or not all(isinstance(x, dict) for x in donnees):
        return {"ok": False, "sortie": "", "erreur": "L'exemple d'entrée d'un script est une liste de dictionnaires."}
    with tempfile.TemporaryDirectory(prefix="suite-script-") as d:
        script = Path(d) / "script.py"
        script.write_text(code, encoding="utf-8")
        enveloppe = Path(d) / "enveloppe.py"
        enveloppe.write_text(_ENVELOPPE % {"cpu": DELAI_S}, encoding="utf-8")
        cmd = [sys.executable, "-I", str(enveloppe), str(script)]
        if shutil.which("unshare"):
            cmd = [
                "unshare",
                "-rn",
                *cmd,
            ]  # pas de réseau ; si l'espace de noms est refusé, on retombe sur l'exécution simple ci-dessous
        # Repli sans `unshare` : on retire les DEUX éléments du préfixe (« unshare », « -rn »). En retirer trois perdait
        # l'interpréteur, et la commande de repli levait FileNotFoundError('-I') sur toute machine où l'espace de noms
        # existe mais est refusé (noyau sans espaces de noms non privilégiés, conteneur sans droits).
        essais = [cmd, cmd[2:]] if cmd[0] == "unshare" else [cmd]
        for essai in essais:
            try:
                p = subprocess.run(
                    essai,
                    input=json.dumps(donnees),
                    capture_output=True,
                    text=True,
                    timeout=DELAI_S + 2,
                    env={},
                    cwd=d,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "sortie": "", "erreur": f"Le script a dépassé {DELAI_S} secondes."}
            except OSError as exc:  # commande introuvable : dit en français, jamais une pile d'appels à l'écran
                return {"ok": False, "sortie": "", "erreur": f"Le script n'a pas pu être lancé ({exc})."}
            if p.returncode != 0 and "unshare" in p.stderr and essai is not essais[-1]:
                continue
            break
    if p.returncode in (-24, 152, -9):  # SIGXCPU / SIGKILL : la limite de processeur ou de mémoire a coupé le script
        return {
            "ok": False,
            "sortie": "",
            "erreur": f"Le script a dépassé sa limite ({DELAI_S} secondes de calcul, 256 Mo).",
        }
    if p.returncode != 0:
        derniere = (p.stderr.strip().splitlines() or ["le script a échoué"])[-1]
        return {"ok": False, "sortie": "", "erreur": derniere[:300]}
    return {"ok": True, "sortie": p.stdout[:SORTIE_MAX]}
