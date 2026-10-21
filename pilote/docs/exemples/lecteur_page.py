#!/usr/bin/env python3
"""Exemple de programme local (fiche 15, chapitre 5) : lire une page web publique et rendre les noms d'une liste.

Ce n'est PAS une source du programme et rien ici ne contourne un site : une seule requête, qui dit qui elle est, sur une page que
l'utilisateur désigne. Il n'utilise que la bibliothèque standard (pas de BeautifulSoup) pour rester lisible en exemple ; pour une page
compliquée, remplacez `html.parser` par BeautifulSoup ou Scrapy, ou par Playwright si la page se construit en JavaScript.

Convention (voir fiche 10) : un JSON sur l'entrée standard, une liste de noms sur la sortie standard, chacun avec « nom » et « origine ».
Ajout : page Ajout > Programme local, commande `python docs/exemples/lecteur_page.py https://exemple.org/annuaire`.
Règle de fiabilité : un nom n'est rendu que s'il figure MOT POUR MOT dans la page."""

from __future__ import annotations

import json
import sys
import urllib.request
from html.parser import HTMLParser


class Liste(HTMLParser):
    """Collecte le texte des éléments de liste (<li>) et des titres de niveau 2 et 3."""

    def __init__(self) -> None:
        super().__init__()
        self.noms: list[str] = []
        self._dedans = 0
        self._tampon: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("li", "h2", "h3"):
            self._dedans += 1
            self._tampon = []

    def handle_data(self, data: str) -> None:
        if self._dedans:
            self._tampon.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("li", "h2", "h3") and self._dedans:
            self._dedans -= 1
            texte = " ".join("".join(self._tampon).split())
            if 2 <= len(texte) <= 120:
                self.noms.append(texte)


def lire(url: str, delai: float = 10.0) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "pilote-exemple (lecteur de page, une requete)"})
    with urllib.request.urlopen(req, timeout=delai) as r:
        page = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    p = Liste()
    p.feed(page)
    return [n for n in dict.fromkeys(p.noms) if n in " ".join(page.split())]  # sans doublon, et mot pour mot dans la page


if __name__ == "__main__":
    entree = json.load(sys.stdin)
    if len(sys.argv) < 2:
        sys.exit("Donnez l'adresse de la page en argument.")
    limite = int(entree.get("limite") or 50)
    print(json.dumps([{"nom": n, "origine": "page web", "site": sys.argv[1]} for n in lire(sys.argv[1])[:limite]], ensure_ascii=False))
