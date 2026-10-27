"""Traduction de la requête, pour chercher dans la langue d'une source (spécification 09). Le moteur n'est PAS choisi par le code : c'est un service
compatible LibreTranslate dont l'adresse se règle dans `pilote.yaml` (`suite.traduction_url`) ; sans adresse, la tuile Traduction n'est pas appliquée
et le plan le dit. L'original reste toujours à côté (règle 1) : la requête traduite n'écrase rien, elle est seulement envoyée à la source, et
le journal garde les deux."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DELAI_S = 20


def traduire(url: str, texte: str, de: str, vers: str) -> str:
    """Le texte traduit. Lève OSError / ValueError : l'appelant garde alors la requête d'origine et le dit.

    Les modèles installés vont de et vers l'anglais. Le service SAIT composer deux modèles (fr → es via en), mais la version 1.9.6 de LibreTranslate
    avec Argos 1.11 rend alors le texte anglais intermédiaire (constaté le 27/10/2026) : on pivote donc nous-mêmes, en deux appels."""
    if de not in ("en", "auto") and vers != "en" and de != vers:
        return _un_appel(url, _un_appel(url, texte, de, "en"), "en", vers)
    return _un_appel(url, texte, de, vers)


def _un_appel(url: str, texte: str, de: str, vers: str) -> str:
    """Un appel ; si le modèle rend le texte tel quel (il prend « Sports Association » en capitales pour un nom propre), un second essai en minuscules, la première lettre rétablie."""
    r = _appel(url, texte, de, vers)
    if r.casefold() == texte.casefold() and texte != texte.lower() and de != vers:
        r2 = _appel(url, texte.lower(), de, vers)
        if r2.casefold() != texte.casefold():
            return r2[:1].upper() + r2[1:] if texte[:1].isupper() else r2
    return r


def _appel(url: str, texte: str, de: str, vers: str) -> str:
    corps = json.dumps({"q": texte, "source": de, "target": vers, "format": "text"}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/translate", data=corps, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=DELAI_S) as r:
            rep = json.loads(r.read().decode())
    except urllib.error.URLError as exc:
        raise OSError(f"le moteur de traduction ne répond pas ({exc})") from exc
    t = rep.get("translatedText") if isinstance(rep, dict) else None
    if not isinstance(t, str) or not t.strip():
        raise ValueError("le moteur de traduction n'a rien rendu")
    return t.strip()
