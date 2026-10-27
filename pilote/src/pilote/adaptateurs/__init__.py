"""Adaptateurs de sources (fiches 04 à 09) : de petits modules qui interrogent UNE base et rendent des noms, sous une convention unique.

Entrée (un dictionnaire) : `sujet` (la phrase), `quoi` (ce qu'on cherche), `mots_cles` (mots à inclure), `pays` (code à deux lettres
ou vide), `lieu`, `limite`. Réglages propres à la source : `parametres`.
Sortie (une liste de dictionnaires) : au minimum `nom` et `origine` (d'où la source le tient, en mots) ; en plus, si la source les
donne : `ville`, `pays`, `site`, `numero` (identifiant officiel), `genre` (déjà ramené à un genre générique : club, entreprise,
association, administration, lieu, evenement, personne, page, compte), `relations` ([{type, vers}]), `coordonnees` ({lat, lon}),
`alias` (les autres noms que la source DÉCLARE pour cette entité : sigle, acronyme, ancien nom ; voir `alias_de`).

Un adaptateur ne connaît AUCUN code national : il fait correspondre le vocabulaire de sa base à des genres génériques."""

from __future__ import annotations

import importlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from types import ModuleType
from typing import Any

UA = "pilote/0.1 (outil libre de recherche d'acteurs ; adaptateur de source)"
MOTS_VIDES = frozenset(
    ["de", "du", "des", "la", "le", "les", "l", "d", "et", "en", "au", "aux", "un", "une", "pour", "par", "sur", "dans", "avec", "the", "of", "and", "for", "in", "on", "at", "to", "a", "an"]
)  # fmt: skip


TENTATIVES_429 = 3  # une demande d'attendre (429, 503) est respectée deux fois avant d'être comptée comme un échec
ATTENTE_MAX_S = 20.0


class LimiteAtteinte(Exception):
    """L'arrêt est demandé, ou la limite de temps ou d'appels est atteinte : l'adaptateur rend ce qu'il a."""


class ErreurSource(Exception):
    """La source a répondu une erreur ou ne répond pas ; le message est en français courant. `code` : le code HTTP quand la source en a rendu un (0 sinon)."""

    code: int = 0


class Client:
    """Client HTTP poli d'un adaptateur : User-Agent identifiable, délai minimal entre deux appels, un appel compté et signalé à chaque
    fois, arrêt immédiat quand `doit_s_arreter()` devient vrai."""

    def __init__(self, source_id: str, doit_s_arreter: Callable[[], bool] = lambda: False, delai_s: float = 0.0,
                 signaler: Callable[..., None] | None = None, timeout: float = 30.0):  # fmt: skip
        self.source_id, self.doit_s_arreter, self.delai_s, self.signaler, self.timeout = source_id, doit_s_arreter, delai_s, signaler, timeout
        self.appels = 0
        self.tentatives_429 = TENTATIVES_429  # un client qui a son propre repli (Overpass : serveur suivant) le réduit à 1
        self._dernier = 0.0

    def _avant(self) -> None:
        if self.doit_s_arreter():
            raise LimiteAtteinte
        attente = self._dernier + self.delai_s - time.monotonic()
        if attente > 0:
            time.sleep(attente)
        self._dernier = time.monotonic()
        self.appels += 1
        if self.signaler:
            self.signaler("appel", prise=self.source_id)

    def get_json(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
        return self._json("GET", url, params, headers, None)

    def post_json(self, url: str, corps: Any = None, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> Any:
        return self._json("POST", url, params, headers, corps)

    def post_texte(self, url: str, donnees: str, headers: dict[str, str] | None = None) -> Any:
        self._avant()
        return self._envoyer("POST", url, headers, donnees.encode("utf-8"), json_=True, form=True)

    def _json(self, methode: str, url: str, params: dict[str, Any] | None, headers: dict[str, str] | None, corps: Any) -> Any:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        self._avant()
        data = json.dumps(corps).encode() if corps is not None else None
        return self._envoyer(methode, url, {**({"Content-Type": "application/json"} if data else {}), **(headers or {})}, data, json_=True)

    def get_texte(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        self._avant()
        return self._envoyer("GET", url, headers, None, json_=False)

    def _envoyer(self, methode: str, url: str, headers: dict[str, str] | None, data: bytes | None, json_: bool, form: bool = False) -> Any:
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            raise ErreurSource("L'adresse de la source doit commencer par http:// ou https://.")
        url = _url_ascii(url)  # jamais un emoji (ni un accent) brut dans une adresse : « ✊ » devient %E2%9C%8A
        h = {"User-Agent": UA, "Accept": "application/json" if json_ else "*/*", **({"Content-Type": "application/x-www-form-urlencoded"} if form else {}), **(headers or {})}
        req = urllib.request.Request(url, data=data, headers=h, method=methode)
        for essai in range(self.tentatives_429):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    corps = r.read(5_000_000)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 503) and essai < self.tentatives_429 - 1:  # la source demande d'attendre (limite de débit) : on attend ce qu'elle dit, plafonné, au lieu d'échouer
                    attente = min(ATTENTE_MAX_S, float(exc.headers.get("Retry-After") or 0) if str(exc.headers.get("Retry-After") or "").replace(".", "").isdigit() else 3.0 * (essai + 1))
                    fin = time.monotonic() + attente
                    while time.monotonic() < fin:
                        if self.doit_s_arreter():
                            raise LimiteAtteinte from exc
                        time.sleep(0.25)
                    continue
                erreur = ErreurSource(f"La source a répondu une erreur ({exc.code})" + (" : trop d'appels, elle demande d'attendre." if exc.code == 429 else "."))
                erreur.code = exc.code
                raise erreur from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise ErreurSource("La source ne répond pas.") from exc
        if not json_:
            return corps.decode("utf-8", "replace")
        try:
            return json.loads(corps)
        except ValueError as exc:
            raise ErreurSource("La réponse de la source n'est pas du JSON lisible.") from exc

    def mcp(self, url: str, outil: str, arguments: dict[str, Any], headers: dict[str, str] | None = None) -> str:
        """Appelle un outil d'un serveur MCP (bibliothèque MCP de l'interpréteur de grappes) et rend son texte.
        `headers` : en-têtes d'identification (ex. Authorization) pour un serveur qui demande une clé."""
        self._avant()
        import asyncio

        async def appel() -> str:
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async with (
                httpx2.AsyncClient(timeout=self.timeout, headers=headers or {}) as c,
                streamable_http_client(url, http_client=c) as streams,
                ClientSession(streams[0], streams[1]) as session,
            ):
                await session.initialize()
                res = await session.call_tool(outil, arguments, read_timeout_seconds=self.timeout)
                sc = getattr(res, "structured_content", None)
                if isinstance(sc, dict) and isinstance(sc.get("result"), str):
                    return sc["result"]
                return "".join(c.text for c in res.content if getattr(c, "type", "") == "text")

        try:
            return asyncio.run(asyncio.wait_for(appel(), self.timeout + 5))
        except Exception as exc:
            raise ErreurSource("Le serveur du catalogue ne répond pas.") from exc


def _url_ascii(url: str) -> str:
    """L'adresse en ASCII : le chemin, la requête et l'ancre sont encodés en UTF-8 (%XX), le nom d'hôte en IDNA (`café.fr` -> `xn--caf-dma.fr`), jamais en %XX (il ne se résoudrait pas)."""
    u = urllib.parse.urlsplit(url)
    hote = u.hostname or ""
    if hote and not hote.isascii():
        try:
            hote = hote.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ErreurSource("Le nom de domaine de la source n'est pas valide.") from exc
    reseau = (f"{u.username}:{u.password}@" if u.password else f"{u.username}@" if u.username else "") + (f"[{hote}]" if ":" in hote else hote) + (f":{u.port}" if u.port else "")
    quote = lambda t: re.sub(r"[^\x00-\x7f]+", lambda m: urllib.parse.quote(m.group()), t)
    return urllib.parse.urlunsplit((u.scheme, reseau, quote(u.path), quote(u.query), quote(u.fragment)))


def mots_significatifs(texte: str, maximum: int = 3) -> list[str]:
    """Mots utiles d'une phrase (sans petits mots), pour interroger une base qui cherche dans des NOMS. Un emoji est un mot à part entière, rendu tel que tapé
    (séquence entière, U+FE0F compris) : une saisie « collectif ♻️ Isère » donne trois éléments, et un emoji seul est une requête valable. Les emoji ne sont jamais coupés
    par la limite `maximum` au profit des mots."""
    from pilote.emoji_texte import EMOJI, reduit

    trouves: list[tuple[int, str, bool]] = []  # (position, élément, est un emoji)
    # Trois lettres suffisent (« Air France », « WWF », « CEA », « RFI ») : avec quatre, « Air France » devenait « France » et la source rendait tout autre chose.
    # Un sigle de deux majuscules (« AS Lyon ») compte aussi ; les petits mots (the, les, des, and…) restent dans MOTS_VIDES.
    for m in re.finditer(rf"({EMOJI.pattern})|([^\W\d_]{{3,}}(?:-[^\W\d_]+)*|\b[A-ZÀ-Ý]{{2}}\b)", texte or "", flags=re.UNICODE):
        trouves.append((m.start(), m.group(), m.group(1) is not None))
    vus: set[str] = set()
    gardes: list[tuple[int, str, bool]] = []
    for pos, el, est_emoji in trouves:
        cle = reduit(el) if est_emoji else el.lower()
        if (not est_emoji and cle in MOTS_VIDES) or cle in vus:
            continue
        vus.add(cle)
        gardes.append((pos, el, est_emoji))
    emojis = [g for g in gardes if g[2]][:maximum]
    mots = [g for g in gardes if not g[2]][: max(0, maximum - len(emojis))]
    return [el for _, el, _ in sorted([*emojis, *mots])]


def nom_normalise(nom: str) -> str:
    """Un nom comparable : sans accents, sans majuscules, sans ponctuation. Sert aux vérifications PAR NOM, qui n'acceptent
    que l'égalité exacte une fois cette mise à plat faite (jamais une ressemblance, qui accuserait des homonymes).
    Un emoji reste dans le nom, sous sa forme de comparaison (sans U+FE0F ni teinte de peau) : « Club ⚽ » et « Club 🏀 » ne deviennent pas le même nom."""
    import unicodedata

    from pilote.emoji_texte import reduit, trouver

    def plat(t: str) -> str:
        sans_accents = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]+", " ", sans_accents.casefold())

    morceaux, fin = [], 0
    for debut, f, e in trouver(nom):
        morceaux += [plat(nom[fin:debut]), f" {reduit(e)} "]
        fin = f
    morceaux.append(plat(nom[fin:]))
    return re.sub(r"\s+", " ", "".join(morceaux)).strip()


def alias_de(nom: str, *autres: Any) -> list[str]:
    """Les autres noms déclarés d'une entité, prêts à sortir d'un adaptateur : sans doublon, sans le nom lui-même, sans valeur vide (au plus 12).
    Un alias est une PREUVE (« ce registre dit que CEA est un nom de cette entité »), jamais une identité : il ne fusionne rien tout seul."""
    vus = {nom_normalise(nom)}
    out: list[str] = []
    for lot in autres:
        for a in [lot] if isinstance(lot, str) else (lot or []):
            a = str(a or "").strip()
            cle = nom_normalise(a)
            if cle and cle not in vus:
                vus.add(cle)
                out.append(a)
    return out[:12]


def singulier(texte: str) -> str:
    """Pluriel en -s ou -x retiré des mots de plus de quatre lettres (« universités » -> « université ») : les noms d'organisations sont au singulier."""
    return " ".join(m[:-1] if m == m.lower() and len(m) > 4 and m[-1] in "sx" and not m.endswith(("ss", "us")) else m for m in texte.split())


def charger(nom: str) -> ModuleType:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", nom):
        raise ErreurSource("Nom d'adaptateur invalide.")
    try:
        m = importlib.import_module(f"pilote.adaptateurs.{nom}")
    except ModuleNotFoundError as exc:
        raise ErreurSource(f"L'adaptateur « {nom} » n'existe pas.") from exc
    if not callable(getattr(m, "chercher", None)):
        raise ErreurSource(f"L'adaptateur « {nom} » n'a pas de fonction « chercher ».")
    return m
