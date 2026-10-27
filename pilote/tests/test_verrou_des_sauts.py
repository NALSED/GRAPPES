"""Un vert doit dire combien de tests ont VRAIMENT tourné (document 24, point 6). Tout test qui peut se sauter porte la marque `reseau` (`-m "not reseau"` ne saute alors jamais) ;
aucun `skipif` : un test que le chemin d'une machine rend muet restait vert sans rien prouver."""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ASSISTANTS_QUI_SAUTENT = {"overpass_reel", "_serveur"}  # un test qui appelle l'un d'eux saute lui aussi : même exigence


def _saute(noeud: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "skip" for n in ast.walk(noeud)) or any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ASSISTANTS_QUI_SAUTENT for n in ast.walk(noeud)
    )


def _fonctions():
    for f in sorted(TESTS.glob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.FunctionDef):
                yield f.name, n


def test_aucun_skipif_dans_la_suite():
    fautifs = [f.name for f in TESTS.glob("*.py") if f.name != Path(__file__).name and "skipif" in f.read_text(encoding="utf-8")]
    assert fautifs == [], f"skipif interdit (un chemin écrit en dur rend le test muet sans bruit) : {fautifs}"


def test_tout_test_qui_peut_se_sauter_porte_la_marque_reseau():
    fautifs = [f"{f}::{n.name}" for f, n in _fonctions() if n.name.startswith("test_") and _saute(n) and not any("mark.reseau" in ast.unparse(d) for d in n.decorator_list)]
    assert fautifs == [], f"ces tests se sautent sans porter @pytest.mark.reseau : {fautifs}"


def test_les_assistants_qui_sautent_sont_connus():
    """Un assistant ou une fixture qui saute fait sauter tous ses utilisateurs : il doit figurer dans ASSISTANTS_QUI_SAUTENT (ou être le navigateur de test, marqué par conftest)."""
    inconnus = [f"{f}::{n.name}" for f, n in _fonctions() if not n.name.startswith("test_") and _saute(n) and n.name not in ASSISTANTS_QUI_SAUTENT | {"chromium"}]
    assert inconnus == [], inconnus
