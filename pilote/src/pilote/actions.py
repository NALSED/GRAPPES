"""Journal des actions de l'utilisateur sur la configuration (fondation « qui »). Un simple fichier texte : il n'y a PAS
d'historique des réglages dans l'interface (git le fait déjà), et la base ne garde que les recherches et les décisions."""

from __future__ import annotations

from datetime import UTC, datetime

from pilote.config import Config


def noter(cfg: Config, qui: str, action: str, detail: str = "") -> None:
    cfg.donnees.mkdir(parents=True, exist_ok=True)
    ligne = " | ".join((datetime.now(UTC).isoformat(timespec="seconds"), qui, action, detail.replace("\n", " ")))
    with cfg.journal_actions.open("a", encoding="utf-8") as f:
        f.write(ligne + "\n")  # jamais de valeur de clé : l'appelant ne la passe pas
