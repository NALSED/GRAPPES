"""Faux serveur MCP de test (sous l'interpréteur de grappes, qui a la bibliothèque MCP). Il refuse (401) toute demande sans l'en-tête
Authorization attendu, enregistre les arguments reçus dans un fichier, et répond comme un prestataire : du JSON (« call-actor ») ou
du texte à liens (« search_engine »). Usage : faux_mcp.py PORT FICHIER_JOURNAL JETON_ATTENDU"""

import json
import sys

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

port, journal, attendu = int(sys.argv[1]), sys.argv[2], sys.argv[3]
mcp = MCPServer("faux-prestataire")


def noter(outil: str, arguments: dict) -> None:
    with open(journal, "a", encoding="utf-8") as f:
        f.write(json.dumps({"outil": outil, "arguments": arguments}, ensure_ascii=False) + "\n")


@mcp.tool(name="call-actor")
def call_actor(actor: str, input: dict) -> str:
    noter("call-actor", {"actor": actor, "input": input})
    return json.dumps([{"fullName": "Club Imaginaire", "url": "https://www.instagram.com/club_imaginaire/", "city": "Ville-Exemple"}, {"fullName": "Section Fictive", "url": "https://www.instagram.com/section_fictive/"}])


@mcp.tool(name="search_engine")
def search_engine(query: str, engine: str = "google") -> str:
    noter("search_engine", {"query": query, "engine": engine})
    return "1. [Association Imaginaire (@asso_imaginaire) • Instagram](https://www.instagram.com/asso_imaginaire/)\n2. [Page Fictive - Facebook](https://www.facebook.com/page.fictive)"


app = mcp.streamable_http_app(host="127.0.0.1")




class ExigerJeton(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.headers.get("authorization") != attendu:
            return PlainTextResponse("non autorisé", status_code=401)
        return await call_next(request)


app.add_middleware(ExigerJeton)


uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
