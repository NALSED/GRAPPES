"""Appelle UN outil du serveur MCP du catalogue data.gouv.fr (page Ajout, façon ①).

Lancé par pilote avec l'interpréteur de GRAPPES (qui a la bibliothèque MCP) : `python catalogue_mcp.py '<json>'` avec
`{"url": ..., "outil": ..., "arguments": {...}, "delai_s": 60}`. Écrit sur la sortie standard une ligne JSON :
`{"ok": true, "texte": "..."}` ou `{"ok": false, "erreur": "..."}`. Un résultat d'outil est une DONNÉE non fiable : seul le
texte est rendu, il n'est jamais exécuté.
"""

from __future__ import annotations

import asyncio
import json
import sys


async def appeler(url: str, outil: str, arguments: dict, delai_s: float) -> str:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with (
        httpx2.AsyncClient(timeout=delai_s) as client,
        streamable_http_client(url, http_client=client) as streams,
        ClientSession(streams[0], streams[1]) as session,
    ):
        await session.initialize()
        res = await session.call_tool(outil, arguments, read_timeout_seconds=delai_s)
        if getattr(res, "is_error", False):
            raise RuntimeError("le catalogue a signalé une erreur")
        sc = getattr(res, "structured_content", None)
        if isinstance(sc, dict) and isinstance(sc.get("result"), str):
            return sc["result"]
        return "".join(c.text for c in res.content if getattr(c, "type", "") == "text")


def main() -> int:
    spec = json.loads(sys.argv[1])
    try:
        texte = asyncio.run(asyncio.wait_for(appeler(spec["url"], spec["outil"], spec.get("arguments") or {}, float(spec.get("delai_s", 60))), float(spec.get("delai_s", 60)) + 5))
        print(json.dumps({"ok": True, "texte": texte[:200_000]}, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - tout est rendu à pilote en clair
        print(json.dumps({"ok": False, "erreur": f"{type(exc).__name__} : {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
