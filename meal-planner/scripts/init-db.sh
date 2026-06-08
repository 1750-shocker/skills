#!/bin/bash
# Initialize pantry.db meal_plans and family_prefs tables
DB="${OPENCLAW_WORKSPACE_DIR:-/data/workspace}/pantry.db"
sqlite3 "$DB" "
CREATE TABLE IF NOT EXISTS meal_plans (
  week TEXT PRIMARY KEY,
  plan_json TEXT NOT NULL,
  budget REAL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS family_prefs (
  key TEXT PRIMARY KEY,
  value TEXT
);
"
echo "DB ready: $DB"
