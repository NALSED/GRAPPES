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
    """Le texte traduit. Lève OSError / ValueError : l'appelant garde alors la requête d'origine et le dit."""
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
