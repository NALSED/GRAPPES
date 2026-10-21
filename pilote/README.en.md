# pilote

A local web application to launch, sort and decide the searches run by **grappes** (an open-source tool that finds the names of small organisations — clubs, associations, informal groups — from public sources and checks them against each other).

* **Plain stack**: FastAPI, SQLite, hand-written HTML/JS. No npm, no build step, no external request at runtime (the two front-end libraries, Tabulator and Cytoscape.js, are MIT-licensed and vendored in `static/vendor/`).
* **Local only**: the service listens on `127.0.0.1` by default, with a self-signed certificate. No accounts.

## Install (one command)

````
outils/installer_service.sh
````

pilote uses the sister project **grappes** as a library: put it next to pilote and set its path in `config/pilote.yaml` (`grappes.racine`). A clean install was checked on 2026-10-18 (fresh clone, fresh virtual environment, tests pass).

It creates the virtual environment, installs the package, and enables a user-level systemd service (no root needed). Open `https://127.0.0.1:8443`. A first-run assistant asks for your country, the presets you want, and where to write the results.

## Keys and privacy

* **No key is ever stored in the repository.** API keys go in `config/secrets.env`, which is git-ignored. The interface only shows whether a key is "present" or "absent".
* Sources that need a paid provider are **off by default** and show their cost before they can be turned on.
* Nothing is downloaded or sent without you seeing it first (cost, file size, free disk space).

## Method

The point of the project is that its results are **measured**, with a protocol written before the measurement. The protocol and its rules are published with the code in the sister repository (`grappes`: `CERTIFICATION.md`, `DECISION_FIABILITE.md`). pilote shows a name's reliability only from what grappes measured, never from an AI opinion.

## Tests

````
.venv/bin/python -m pytest
````

Browser tests use a headless Chromium (`outils/installer_navigateur_test.sh`) and are skipped when it is absent. Some tests call real public services (OpenStreetMap through a local Overpass server, Geofabrik headers) and skip when those do not answer.

## Status

* Licence: **MIT** (see `LICENSE`). The vendored libraries keep their own MIT licences (`static/vendor/*/LICENSE`).
* The interface is in French. Translation is planned (English first) and not started.
