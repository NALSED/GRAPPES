"""Ce que veut dire un lancement : le sujet en champs séparés devient la phrase de grappes, la profondeur et les limites
deviennent les limites d'UN cycle (dans la copie de travail de la configuration, jamais dans la vraie)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pilote.config import Config


class LancementInvalide(ValueError):
    pass


def phrase_du_sujet(sujet: dict[str, Any]) -> str:
    """« clubs de handball professionnels » + pays -> « clubs de handball professionnels en France » ; un lieu plus précis
    (région ou ville, champ unique comme dans la maquette) -> « ... de Toulouse ». La préposition est de celles que grappes sait
    retirer du sujet pour ne pas les prendre pour des mots du sujet."""
    quoi = str(sujet.get("quoi", "")).strip()
    if not quoi:
        raise LancementInvalide("Dites ce que vous cherchez.")
    lieu, pays = (str(sujet.get(k, "")).strip() for k in ("lieu", "pays"))
    if lieu:
        return f"{quoi} de {lieu}"  # région ou ville : le champ n'en dit pas plus, grappes retire « de Lieu » du sujet
    return f"{quoi} en {pays}" if pays else quoi


def cran(cfg: Config, ident: str | None) -> dict[str, Any]:
    for p in cfg.profondeurs:
        if p["id"] == (ident or cfg.profondeur_par_defaut):
            return dict(p)
    raise LancementInvalide("Cette profondeur n'existe pas.")


def limites(cfg: Config, parametres: dict[str, Any]) -> dict[str, Any]:
    """Limites effectives : celles que l'utilisateur donne, sinon celles du cran. Les appels ne dépassent jamais le cran."""
    c = cran(cfg, parametres.get("profondeur"))
    lim = parametres.get("limites") or {}
    appels = int(lim.get("appels") or cfg.limites_par_defaut.get("appels") or c["appels"])
    minutes = lim.get("temps_minutes") or cfg.limites_par_defaut.get("temps_minutes")
    return {"appels": min(appels, int(c["appels"])), "temps_s": int(float(minutes) * 60) if minutes else None, "cran": c}


JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def libelle_quand(quand: dict[str, Any]) -> str:
    """« tous les jours 10 h 00 », « lundi 08 h 00 », « le 14/10 à 09 h 30 »."""
    if quand.get("date"):
        d = datetime.fromisoformat(quand["date"])
        return f"le {d:%d/%m} à {d:%H} h {d:%M}"
    h, m = str(quand.get("heure", "00:00")).split(":")
    jours = quand.get("jours") or []
    quand_jours = "tous les jours" if not jours or len(jours) == 7 else " et ".join(JOURS[j] for j in sorted(jours))
    return f"{quand_jours} {int(h):02d} h {int(m):02d}"


def prochaine_occurrence(quand: dict[str, Any], apres: datetime) -> datetime | None:
    """Prochain déclenchement (heure locale du serveur, rendu en UTC) strictement après `apres`. None = plus jamais.

    L'heure locale est calculée À LA DATE VISÉE : une date sans fuseau convertie par `.astimezone()` suit la règle d'heure d'été de ce
    jour-là. Avant, le décalage du moment du calcul était recopié tel quel : en France, « lundi 10:00 » calculé le samedi avant le passage
    à l'heure d'hiver partait à 9:00."""
    apres_local = apres.astimezone()
    if quand.get("date"):
        d = datetime.fromisoformat(quand["date"])
        d = d.astimezone()  # sans fuseau : heure locale de CE jour-là (heure d'été comprise) ; avec fuseau : gardé
        return d.astimezone(UTC) if d > apres_local else None
    try:
        h, m = (int(x) for x in str(quand["heure"]).split(":"))
    except (KeyError, ValueError) as exc:
        raise LancementInvalide("L'heure doit s'écrire comme 10:00.") from exc
    jours = set(quand.get("jours") or range(7))
    base = apres_local.replace(tzinfo=None)  # date murale locale, sans décalage figé
    for plus in range(8):
        jour = (base + timedelta(days=plus)).replace(hour=h, minute=m, second=0, microsecond=0).astimezone()
        if jour > apres_local and jour.weekday() in jours:
            return jour.astimezone(UTC)
    return None


def code_pays(cfg: Config, sujet: dict[str, Any], reglages: dict[str, Any]) -> str:
    """Code à deux lettres du pays de la recherche : celui du formulaire (code ou nom connu), sinon le pays choisi dans l'assistant."""
    brut = str(sujet.get("pays", "")).strip()
    if len(brut) == 2 and brut.isalpha():
        return brut.upper()
    for code, nom in (cfg.pays_proposes or {}).items():
        if nom.casefold() == brut.casefold():
            return str(code).upper()
    return str(reglages.get("pays", "") or "").upper()


# ---------------------------------------------------------------------------------------------------------------------
# Options de la page Recherches (fiche 12) : validées, puis gardées avec la recherche (elle les garde jusqu'au bout)


def nom_de_domaine(texte: str) -> str:
    """« https://www.Exemple.org/page » -> « exemple.org » ; vide si ce n'est pas une adresse de site."""
    t = texte.strip().lower()
    t = t.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].split("@")[-1].split(":", 1)[0]
    t = t.removeprefix("www.")
    return t if "." in t and all(c.isalnum() or c in ".-" for c in t) else ""


def exploration(parametres: dict[str, Any]) -> int:
    """Profondeur d'exploration (0, 1 ou 2) : éteinte (0) par défaut. C'est la profondeur de liens suivis par grappes."""
    return int(parametres.get("exploration") or 0)


def valider_options(cfg: Config, parametres: dict[str, Any], formats_connus: set[str] | None = None, presets_connus: set[str] | None = None) -> dict[str, Any]:
    """Les paramètres d'une recherche, vérifiés (refus en français) et normalisés. Les clés inconnues sont gardées telles quelles."""
    p = dict(parametres)
    if p.get("profondeur") is not None and cfg.profondeurs:
        cran(cfg, p["profondeur"])
    if p.get("exploration") not in (None, 0, 1, 2):
        raise LancementInvalide("La profondeur d'exploration doit être 0 (éteinte), 1 ou 2.")
    if p.get("lire_la_page") is not None and not isinstance(p["lire_la_page"], bool):
        raise LancementInvalide("« Page entière ou extrait » se règle par oui ou non.")
    if "sites_a_ignorer" in p:
        brut = p["sites_a_ignorer"]
        if not isinstance(brut, list):
            raise LancementInvalide("Les sites à ignorer forment une liste d'adresses.")
        domaines = []
        for x in brut:
            d = nom_de_domaine(str(x))
            if not d:
                raise LancementInvalide(f"« {x} » n'est pas une adresse de site (par exemple exemple.org).")
            if d not in domaines:
                domaines.append(d)
        p["sites_a_ignorer"] = domaines
    if p.get("presets") is not None:
        if not isinstance(p["presets"], list):
            raise LancementInvalide("Les presets cochés forment une liste.")
        inconnus = [x for x in p["presets"] if presets_connus is not None and x not in presets_connus]
        if inconnus:
            raise LancementInvalide(f"Le preset « {inconnus[0]} » n'existe pas.")
    so = p.get("sortie")
    if so is not None:
        if not isinstance(so, dict) or not isinstance(so.get("actifs", []), list):
            raise LancementInvalide("La sortie de cette recherche donne la liste des formats voulus.")
        mauvais = [f for f in so.get("actifs", []) if formats_connus is not None and f not in formats_connus]
        if mauvais:
            raise LancementInvalide(f"Le format « {mauvais[0]} » n'existe pas.")
    lim = p.get("limites")
    if lim is not None:
        if not isinstance(lim, dict):
            raise LancementInvalide("Les limites donnent un temps (minutes) et un nombre d'appels.")
        for k in ("appels", "temps_minutes"):
            if lim.get(k) not in (None, "") and float(lim[k]) <= 0:
                raise LancementInvalide("Une limite doit être supérieure à zéro.")
    return p


FOURCHETTE_GROSSIERE_S = (0.5, 8.0)  # secondes par appel, sans aucune mesure : volontairement large


def _duree_phrase(bas_s: float, haut_s: float) -> str:
    def un(s: float) -> str:
        if s < 60:
            return "moins d'une minute"
        m = round(s / 60)
        return f"{m} minute{'s' if m > 1 else ''}"

    b, h = un(bas_s), un(haut_s)
    if bas_s < 60 and haut_s < 60:
        return "moins d'une minute"
    if b == h:
        return f"environ {h}"
    return f"de {b.replace(' minutes', '').replace(' minute', '')} à {h}" if bas_s >= 60 else f"de moins d'une minute à {h}"
