# grappes

Entités (personnes, groupes, sites) rangées en **grappes** par proximité sémantique et validation par recoupement d écosystèmes. 

## Installation

````bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
````

## Utilisation

````bash
grappes ingest <dossier_json> --ecosystem x|telegram|instagram|web
grappes run
grappes export --out ./sorties
````

Par défaut : base `donnees/grappes.db`, configuration `config/`. Options globales : `--db`, `--config`.

## Serveur MCP (lecture seule)

SDK `mcp` **2.3.0** (épinglé). Le SDK 2.x a renommé `FastMCP` en `MCPServer` (`from mcp.server.mcpserver import MCPServer`) : le code écrit pour 1.x ne s y applique pas tel quel. Transport stdio, base ouverte en `mode=ro`.

Variables : `GRAPPES_DB` (défaut `donnees/grappes.db`), `GRAPPES_CONFIG` (défaut `config`).

### Claude Code

````bash
claude mcp add grappes -e GRAPPES_DB=<chemin du dépôt>/grappes/donnees/grappes.db -e GRAPPES_CONFIG=<chemin du dépôt>/grappes/config -- <chemin du dépôt>/grappes/.venv/bin/python -m grappes.mcp.server
````

### Claude Desktop (`claude_desktop_config.json`)

````json
{
  "mcpServers": {
    "grappes": {
      "command": "<chemin du dépôt>/grappes/.venv/bin/python",
      "args": ["-m", "grappes.mcp.server"],
      "env": {"GRAPPES_DB": "<chemin du dépôt>/grappes/donnees/grappes.db", "GRAPPES_CONFIG": "<chemin du dépôt>/grappes/config"}
    }
  }
}
````

### Outils

`list_grappes`, `get_grappe`, `top_sources`, `search_entities`, `get_entity`, `explain_assignment`, `get_validated_refs`, `compare_grappes`. `limit` est plafonné à 100 ; les extraits de texte font au plus 280 caractères.

Test : `tests/test_mcp.py` lance le serveur en sous-processus stdio avec un vrai client MCP et appelle les outils. Inspecteur interactif : `npx @modelcontextprotocol/inspector .venv/bin/python -m grappes.mcp.server`.
