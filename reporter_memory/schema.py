"""Reporter memory SQLite schema definitions."""

from __future__ import annotations

SCHEMA_VERSION = "3"

_DDL = """
CREATE TABLE IF NOT EXISTS context_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS storylines (
    id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    priority INTEGER NOT NULL DEFAULT 2,
    arc_type TEXT,
    importance INTEGER NOT NULL DEFAULT 4,
    origin_week INTEGER,
    future_callback_condition TEXT,
    tags TEXT,
    team_ids TEXT,
    week_created INTEGER NOT NULL,
    week_last_updated INTEGER NOT NULL,
    last_accessed_week INTEGER,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_storylines_league
    ON storylines(league_id, season, status);
CREATE INDEX IF NOT EXISTS idx_storylines_importance
    ON storylines(league_id, season, importance);

CREATE TABLE IF NOT EXISTS team_context (
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    roster_id INTEGER NOT NULL,
    narrative TEXT NOT NULL,
    outlook TEXT,
    week_last_updated INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, roster_id)
);

CREATE TABLE IF NOT EXISTS league_context (
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    week_last_updated INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, key)
);

CREATE TABLE IF NOT EXISTS storyline_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storyline_id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    week INTEGER NOT NULL,
    snapshot_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_storyline
    ON storyline_history(league_id, season, storyline_id, week);

CREATE TABLE IF NOT EXISTS persisted_facts (
    storyline_id TEXT NOT NULL,
    week_recorded INTEGER NOT NULL,
    fact_id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    data_refs TEXT,
    numbers TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, storyline_id, week_recorded, fact_id)
);
CREATE INDEX IF NOT EXISTS idx_facts_storyline
    ON persisted_facts(league_id, season, storyline_id);

CREATE TABLE IF NOT EXISTS story_events (
    id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    week INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 1,
    confidence TEXT NOT NULL DEFAULT 'needs_verification',
    source_refs_json TEXT,
    numbers_json TEXT,
    transaction_id TEXT,
    matchup_id TEXT,
    last_accessed_week INTEGER,
    last_accessed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_story_events_week
    ON story_events(league_id, season, week, event_type);
CREATE INDEX IF NOT EXISTS idx_story_events_transaction
    ON story_events(league_id, season, transaction_id);
CREATE INDEX IF NOT EXISTS idx_story_events_matchup
    ON story_events(league_id, season, matchup_id);

CREATE TABLE IF NOT EXISTS story_event_entities (
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    event_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, event_id, entity_type, entity_id, role)
);
CREATE INDEX IF NOT EXISTS idx_story_event_entities_lookup
    ON story_event_entities(league_id, season, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS storyline_event_links (
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    storyline_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, storyline_id, event_id, link_type)
);
CREATE INDEX IF NOT EXISTS idx_storyline_event_links_event
    ON storyline_event_links(league_id, season, event_id);

CREATE TABLE IF NOT EXISTS storyline_triggers (
    id TEXT NOT NULL,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    storyline_id TEXT,
    event_id TEXT,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    target_week INTEGER,
    condition_json TEXT,
    fire_policy TEXT NOT NULL DEFAULT 'one_shot',
    fired_week INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (league_id, season, id)
);
CREATE INDEX IF NOT EXISTS idx_storyline_triggers_status
    ON storyline_triggers(league_id, season, status, target_week);
CREATE INDEX IF NOT EXISTS idx_storyline_triggers_storyline
    ON storyline_triggers(league_id, season, storyline_id);

CREATE VIRTUAL TABLE IF NOT EXISTS story_memory_fts USING fts5(
    owner_type UNINDEXED,
    owner_id UNINDEXED,
    league_id UNINDEXED,
    season UNINDEXED,
    headline,
    summary,
    tags,
    entity_text,
    trigger_text
);

CREATE TABLE IF NOT EXISTS memory_accesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id TEXT NOT NULL,
    season TEXT NOT NULL,
    week INTEGER NOT NULL,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    usage TEXT NOT NULL,
    linked_storyline_id TEXT,
    fact_links_json TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_accesses_owner
    ON memory_accesses(league_id, season, owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_memory_accesses_usage
    ON memory_accesses(league_id, season, usage, week);
"""
