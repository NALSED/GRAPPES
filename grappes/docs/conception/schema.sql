-- Schéma SQLite (MISSION §10.3). Colonnes ajoutées à `observations` : mentions, links,
-- hashtags, engagement (JSON/entier), nécessaires pour rejouer `run` sans les JSON d'origine.
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, ts TEXT NOT NULL, config_hash TEXT NOT NULL, code_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    ref_key TEXT PRIMARY KEY, ecosystem TEXT NOT NULL, ident TEXT NOT NULL,
    weight REAL NOT NULL, display_name TEXT
);
CREATE TABLE IF NOT EXISTS observations (
    obs_id TEXT PRIMARY KEY, source_key TEXT NOT NULL, ts TEXT, text TEXT NOT NULL,
    mentions TEXT NOT NULL DEFAULT '[]', links TEXT NOT NULL DEFAULT '[]',
    hashtags TEXT NOT NULL DEFAULT '[]', engagement INTEGER NOT NULL DEFAULT 0,
    raw_ref TEXT, run_id TEXT
);
CREATE TABLE IF NOT EXISTS citations (
    citer TEXT NOT NULL, cited TEXT NOT NULL, ecosystem TEXT NOT NULL,
    obs_id TEXT NOT NULL, ts TEXT, run_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY, type TEXT NOT NULL, primary_ref TEXT NOT NULL UNIQUE,
    display_name TEXT
);
CREATE TABLE IF NOT EXISTS memberships (
    entity_id TEXT NOT NULL, grappe_id TEXT NOT NULL, semantic REAL NOT NULL,
    ecosystem REAL NOT NULL, anchor REAL NOT NULL, confidence REAL NOT NULL,
    via TEXT NOT NULL, status TEXT NOT NULL, run_id TEXT NOT NULL,
    PRIMARY KEY (entity_id, grappe_id, run_id)
);
CREATE TABLE IF NOT EXISTS validations (
    cited TEXT NOT NULL, grappe_id TEXT NOT NULL, n_citers INTEGER NOT NULL,
    n_ecosystems INTEGER NOT NULL, weight_sum REAL NOT NULL, validated INTEGER NOT NULL,
    reasons TEXT NOT NULL, run_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_source ON observations(source_key);
CREATE INDEX IF NOT EXISTS idx_cit_cited ON citations(cited);
CREATE INDEX IF NOT EXISTS idx_mem_grappe ON memberships(grappe_id, run_id);
