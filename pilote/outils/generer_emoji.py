"""Génère `src/pilote/emoji_donnees.py` : les points de code d'emoji de la norme UTS #51 (Unicode Emoji), tirés du paquet `emoji` (BSD), pour que le programme les reconnaisse
avec la seule bibliothèque standard (les adaptateurs tournent aussi dans l'interpréteur de grappes, où l'on ne suppose rien de plus).

À relancer quand une nouvelle version d'Unicode sort :   .venv/bin/python outils/generer_emoji.py   (nécessite `pip install emoji`, dépendance de développement seulement)
Le test `tests/test_f26_web_social.py` compare ensuite la reconnaissance du programme à celle du paquet, emoji par emoji."""

from __future__ import annotations

from pathlib import Path

import emoji

SORTIE = Path(__file__).resolve().parent.parent / "src" / "pilote" / "emoji_donnees.py"
ZWJ, VS16, CLE, PEAU = 0x200D, 0xFE0F, 0x20E3, range(0x1F3FB, 0x1F400)


def classe(points: set[int]) -> str:
    """Une classe de caractères d'expression régulière (intervalles), en échappant tout."""
    tri, out = sorted(points), []
    i = 0
    while i < len(tri):
        j = i
        while j + 1 < len(tri) and tri[j + 1] == tri[j] + 1:
            j += 1
        out.append(f"\\U{tri[i]:08x}" + (f"-\\U{tri[j]:08x}" if j > i else ""))
        i = j + 1
    return "".join(out)


def main() -> None:
    seuls, qualifies, tous = set(), set(), set()
    for s, d in emoji.EMOJI_DATA.items():
        pts = [ord(c) for c in s]
        tous.update(p for p in pts if p not in (ZWJ, VS16, CLE) and p not in PEAU and not 0xE0020 <= p <= 0xE007F)
        if d["status"] == emoji.STATUS["fully_qualified"] and len(pts) == 1:
            seuls.add(pts[0])  # emoji par défaut (Emoji_Presentation) : reconnu seul
        if d["status"] == emoji.STATUS["fully_qualified"] and len(pts) == 2 and pts[1] == VS16:
            qualifies.add(pts[0])  # texte par défaut (♻, ©) : emoji seulement suivi de U+FE0F
    seuls -= set(range(0x30, 0x3A)) | {0x23, 0x2A}
    qualifies -= seuls
    SORTIE.write_text(
        '"""Généré par `outils/generer_emoji.py` à partir du paquet `emoji` ' + emoji.__version__ + " (norme UTS #51, Unicode Emoji). Ne pas éditer à la main.\"\"\"\n\n"
        f"EMOJI_SEUL = \"{classe(seuls)}\"  # emoji par défaut : reconnu sans sélecteur\n"
        f"EMOJI_QUALIFIE = \"{classe(qualifies)}\"  # texte par défaut : emoji quand U+FE0F suit\n"
        f"EMOJI_TOUS = \"{classe(tous)}\"  # tout point de code qui entre dans une séquence (après un liant U+200D)\n",
        encoding="utf-8",
    )
    print(f"{SORTIE.name} : {len(seuls)} emoji par défaut, {len(qualifies)} à sélecteur, {len(tous)} points de code")


if __name__ == "__main__":
    main()
