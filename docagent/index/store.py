"""SQLite-backed index store.

Tables:
- schema_version    — single-row meta
- symbols           — extracted symbols per file
- refs              — references between symbols (kind: semantic|lexical)
- mentions          — identifier-name occurrences in artifact prose
- file_hashes       — content hash per file, for change detection
- artifacts         — generated artifact metadata
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS symbols (
    id              INTEGER PRIMARY KEY,
    qualified_name  TEXT NOT NULL,
    kind            TEXT NOT NULL,
    file            TEXT NOT NULL,
    byte_start      INTEGER NOT NULL,
    byte_end        INTEGER NOT NULL,
    line_start      INTEGER NOT NULL,
    line_end        INTEGER NOT NULL,
    signature       TEXT NOT NULL DEFAULT '',
    existing_doc    TEXT,
    language_id     TEXT NOT NULL,
    source_hash     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_qn ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file);

CREATE TABLE IF NOT EXISTS refs (
    id     INTEGER PRIMARY KEY,
    src    TEXT NOT NULL,
    dst    TEXT NOT NULL,
    kind   TEXT NOT NULL CHECK (kind IN ('semantic','lexical'))
);
CREATE INDEX IF NOT EXISTS idx_refs_dst ON refs(dst);
CREATE INDEX IF NOT EXISTS idx_refs_src ON refs(src);

CREATE TABLE IF NOT EXISTS mentions (
    id            INTEGER PRIMARY KEY,
    identifier    TEXT NOT NULL,
    artifact_id   TEXT NOT NULL,
    artifact_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mentions_ident ON mentions(identifier);
CREATE INDEX IF NOT EXISTS idx_mentions_artifact ON mentions(artifact_id);
CREATE INDEX IF NOT EXISTS idx_mentions_artifact_path ON mentions(artifact_id, artifact_path);

CREATE TABLE IF NOT EXISTS file_hashes (
    file        TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    language_id TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Composite primary key (artifact_id, path) lets a multi-file artifact like
-- ``api_reference`` register one row per generated page. Single-file artifacts
-- behave identically — they just have one row.
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT NOT NULL,
    path        TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    last_run    TEXT NOT NULL,
    digest      TEXT NOT NULL,
    PRIMARY KEY (artifact_id, path)
);

-- Per-unit fingerprints (e.g. per-module for ``api_reference``). Lets
-- multi-unit artifacts skip LLM calls when the inputs that produced a unit
-- haven't changed. ``unit_key`` is artifact-defined (a dotted module name,
-- a symbol qualified name, a file path, etc).
CREATE TABLE IF NOT EXISTS artifact_unit_fingerprints (
    artifact_id TEXT NOT NULL,
    unit_key    TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    last_run    TEXT NOT NULL,
    PRIMARY KEY (artifact_id, unit_key)
);
"""


class Store:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        self.conn.executescript(SCHEMA)
        cur = self.conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        if row is None:
            self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self.conn.commit()
        elif row[0] != SCHEMA_VERSION:
            raise RuntimeError(
                f"Index schema version mismatch: db={row[0]} expected={SCHEMA_VERSION}. "
                "Delete .docagent/index.db to rebuild."
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()

    def replace_symbols_for_file(self, file: str, rows: list[tuple]) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM symbols WHERE file = ?", (file,))
            conn.executemany(
                """
                INSERT INTO symbols (
                    qualified_name, kind, file, byte_start, byte_end,
                    line_start, line_end, signature, existing_doc,
                    language_id, source_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def upsert_file_hash(self, file: str, sha256: str, language_id: str, ts: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO file_hashes (file, sha256, language_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file) DO UPDATE SET
                    sha256=excluded.sha256,
                    language_id=excluded.language_id,
                    updated_at=excluded.updated_at
                """,
                (file, sha256, language_id, ts),
            )

    def artifacts_mentioning(self, identifier: str) -> list[tuple[str, str]]:
        cur = self.conn.execute(
            "SELECT DISTINCT artifact_id, artifact_path FROM mentions WHERE identifier = ?",
            (identifier,),
        )
        return list(cur.fetchall())

    def replace_mentions_for_artifact(
        self,
        artifact_id: str,
        rows: list[tuple],
        path: str | None = None,
    ) -> None:
        """Replace mention rows for an artifact.

        When ``path`` is ``None``, replaces *all* rows for ``artifact_id`` —
        the right behavior for single-file artifacts. When ``path`` is given,
        replaces only the rows for that specific ``(artifact_id, path)`` pair,
        which is what multi-file artifacts need so writing page 2 doesn't
        erase page 1's mentions.
        """
        with self.transaction() as conn:
            if path is None:
                conn.execute("DELETE FROM mentions WHERE artifact_id = ?", (artifact_id,))
            else:
                conn.execute(
                    "DELETE FROM mentions WHERE artifact_id = ? AND artifact_path = ?",
                    (artifact_id, path),
                )
            conn.executemany(
                "INSERT INTO mentions (identifier, artifact_id, artifact_path) VALUES (?, ?, ?)",
                rows,
            )

    def known_symbol_names(self) -> set[str]:
        """Set of identifier strings the mention index can intersect against.

        Includes both the full qualified name (e.g. ``Foo.bar``) and the
        trailing leaf (``bar``) so that prose mentioning either form is caught
        when the symbol is renamed.
        """
        names: set[str] = set()
        cur = self.conn.execute("SELECT qualified_name FROM symbols")
        for (qn,) in cur.fetchall():
            names.add(qn)
            tail = qn.rsplit(".", 1)[-1]
            if tail and tail != qn:
                names.add(tail)
        return names

    def upsert_artifact(
        self,
        artifact_id: str,
        path: str,
        digest: str,
        last_run: str,
        version: int = 1,
    ) -> None:
        """Upsert a single ``(artifact_id, path)`` row.

        Multi-file artifacts call this once per output path; single-file
        artifacts call it once. The composite primary key ensures each
        ``(artifact_id, path)`` pair is uniquely tracked.
        """
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (artifact_id, path, version, last_run, digest)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id, path) DO UPDATE SET
                    version=excluded.version,
                    last_run=excluded.last_run,
                    digest=excluded.digest
                """,
                (artifact_id, path, version, last_run, digest),
            )

    def get_artifact_digest(self, artifact_id: str, path: str | None = None) -> str | None:
        """Return the digest for a specific ``(artifact_id, path)`` pair.

        When ``path`` is omitted, returns the digest of the first matching
        row (deterministic via ``ORDER BY path``) — convenience for
        single-file artifacts.
        """
        if path is None:
            cur = self.conn.execute(
                "SELECT digest FROM artifacts WHERE artifact_id = ? ORDER BY path LIMIT 1",
                (artifact_id,),
            )
        else:
            cur = self.conn.execute(
                "SELECT digest FROM artifacts WHERE artifact_id = ? AND path = ?",
                (artifact_id, path),
            )
        row = cur.fetchone()
        return row[0] if row else None

    def list_artifacts(self) -> list[tuple[str, str, str]]:
        """Return rows of ``(artifact_id, path, digest)`` for all known
        artifacts. Multi-file artifacts produce one row per output path; the
        result may therefore have multiple rows sharing an ``artifact_id``."""
        cur = self.conn.execute(
            "SELECT artifact_id, path, digest FROM artifacts ORDER BY artifact_id, path"
        )
        return list(cur.fetchall())

    def artifact_paths(self) -> set[str]:
        """Set of relative paths registered in the artifacts table.

        Used by ``update`` mode to skip files that ARE artifacts — we never
        treat a user's edit to a generated README as a "source change" worth
        re-running anything on.
        """
        cur = self.conn.execute("SELECT path FROM artifacts")
        return {row[0] for row in cur.fetchall()}

    def get_unit_fingerprint(self, artifact_id: str, unit_key: str) -> str | None:
        cur = self.conn.execute(
            "SELECT fingerprint FROM artifact_unit_fingerprints "
            "WHERE artifact_id = ? AND unit_key = ?",
            (artifact_id, unit_key),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_unit_fingerprint(
        self, artifact_id: str, unit_key: str, fingerprint: str, last_run: str
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO artifact_unit_fingerprints
                    (artifact_id, unit_key, fingerprint, last_run)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(artifact_id, unit_key) DO UPDATE SET
                    fingerprint=excluded.fingerprint,
                    last_run=excluded.last_run
                """,
                (artifact_id, unit_key, fingerprint, last_run),
            )

    def symbols_for_file(self, file: str) -> list[tuple[str, str]]:
        """Return ``(qualified_name, kind)`` rows recorded for ``file``.

        Called before re-indexing during ``update`` so the orchestrator can
        compute the set of removed/renamed symbols.
        """
        cur = self.conn.execute(
            "SELECT qualified_name, kind FROM symbols WHERE file = ?", (file,)
        )
        return list(cur.fetchall())


def open_store(repo_root: Path) -> Store:
    return Store(repo_root / ".docagent" / "index.db")
