from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final[int] = 2

CONNECTION_PRAGMAS: Final[tuple[str, ...]] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA cache_size=-16384",
    "PRAGMA mmap_size=268435456",
    "PRAGMA wal_autocheckpoint=1024",
)

MIGRATIONS: Final[tuple[tuple[str, ...], ...]] = (
    (
        """
        CREATE TABLE github_accounts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            label            TEXT NOT NULL UNIQUE,
            username         TEXT NOT NULL,
            token_ciphertext BLOB NOT NULL,
            created_at       REAL NOT NULL
        )
        """,
        """
        CREATE TABLE projects (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            slug              TEXT NOT NULL UNIQUE,
            display_name      TEXT NOT NULL,
            source_kind       TEXT NOT NULL CHECK (source_kind IN ('github', 'archive')),
            source_reference  TEXT NOT NULL,
            git_reference     TEXT,
            github_account_id INTEGER REFERENCES github_accounts(id) ON DELETE SET NULL,
            autostart         INTEGER NOT NULL DEFAULT 1,
            created_at        REAL NOT NULL,
            updated_at        REAL NOT NULL
        )
        """,
        "CREATE INDEX projects_slug_idx ON projects(slug)",
        """
        CREATE TABLE project_secrets (
            project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            value_ciphertext BLOB NOT NULL,
            updated_at       REAL NOT NULL,
            PRIMARY KEY (project_id, name)
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE alert_rules (
            kind             TEXT PRIMARY KEY,
            enabled          INTEGER NOT NULL,
            throttle_seconds INTEGER NOT NULL,
            updated_at       REAL NOT NULL
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE alert_preferences (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kind         TEXT NOT NULL,
            severity     TEXT NOT NULL,
            project_slug TEXT,
            message      TEXT NOT NULL,
            created_at   REAL NOT NULL
        )
        """,
        "CREATE INDEX events_recent_idx ON events(id DESC)",
        "CREATE INDEX events_project_idx ON events(project_slug, id DESC)",
    ),
    (
        """
        CREATE TABLE user_preferences (
            user_id INTEGER NOT NULL,
            key     TEXT NOT NULL,
            value   TEXT NOT NULL,
            PRIMARY KEY (user_id, key)
        ) WITHOUT ROWID
        """,
    ),
)
