"""
SQLite-backed store for profiles and HL7 standard caches.

Tables
------
profiles(id TEXT PK, message_type, trigger_event, hl7_version, description, updated_at, data JSON)
    Source of truth for user profiles.

hl7_raw(version, resource_type, resource_id, data JSON)
    Raw JSON from the HL7 Standard API — replaces the hl7standard_cache/ file tree.

hl7_segments(version, segment_name, data JSON, value_sets JSON)
    Pre-built SegmentDef JSON (fields + components + subcomponents) keyed by
    (version, segment_name).  Avoids rebuilding the same segment for every
    profile that shares it (e.g. PID is shared by all ADT messages).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

import yaml

from app.config import settings

_DB_FILE = Path("profiles.db")

# Single write lock — SQLite WAL allows concurrent readers but only one writer.
# Using a Python-level lock avoids the busy-timeout overhead when many threads
# try to write simultaneously (e.g. during HL7 standard import).
_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    return _DB_FILE


@contextmanager
def _conn(write: bool = False):
    """Open a SQLite connection.  Pass write=True to acquire the write lock."""
    if write:
        _write_lock.acquire()
    con = sqlite3.connect(str(_db_path()), check_same_thread=False, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA cache_size=-32000")   # 32 MB page cache
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
        if write:
            _write_lock.release()


# ---------------------------------------------------------------------------
# Initialisation & migration
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables and migrate any existing YAML profiles and file-based HL7 cache."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS shared_segments (
                id           TEXT PRIMARY KEY,
                segment_name TEXT NOT NULL,
                description  TEXT,
                updated_at   TEXT,
                data         TEXT NOT NULL,
                value_sets   TEXT NOT NULL DEFAULT '{}'
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id            TEXT PRIMARY KEY,
                message_type  TEXT NOT NULL DEFAULT '',
                trigger_event TEXT NOT NULL DEFAULT '',
                hl7_version   TEXT NOT NULL DEFAULT '',
                description   TEXT,
                updated_at    TEXT,
                data          TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS hl7_raw (
                version       TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id   TEXT NOT NULL,
                data          TEXT NOT NULL,
                PRIMARY KEY (version, resource_type, resource_id)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS hl7_segments (
                version       TEXT NOT NULL,
                segment_name  TEXT NOT NULL,
                data          TEXT NOT NULL,
                value_sets    TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (version, segment_name)
            )
        """)

    _migrate_yaml_profiles()
    _migrate_hl7_file_cache()


def _migrate_hl7_file_cache() -> None:
    """Import existing hl7standard_cache/ JSON files into hl7_raw table (one-time)."""
    cache_dir = settings.hl7standard_cache_dir
    if not cache_dir.exists():
        return

    # Check if already migrated (any rows present)
    with _conn() as con:
        count = con.execute("SELECT COUNT(*) FROM hl7_raw").fetchone()[0]
    if count > 0:
        return

    rows = []
    for version_dir in cache_dir.iterdir():
        if not version_dir.is_dir():
            continue
        version = version_dir.name  # e.g. "HL7v2.7"
        for resource_dir in version_dir.iterdir():
            if not resource_dir.is_dir():
                continue
            resource_type = resource_dir.name  # e.g. "fields", "segments"
            for json_file in resource_dir.glob("*.json"):
                try:
                    data = json_file.read_text(encoding="utf-8")
                    rows.append((version, resource_type, json_file.stem, data))
                except Exception:
                    continue
        # Top-level JSON files (e.g. TriggerEvents.json)
        for json_file in version_dir.glob("*.json"):
            try:
                data = json_file.read_text(encoding="utf-8")
                rows.append((version, "root", json_file.stem, data))
            except Exception:
                continue

    if not rows:
        return

    with _conn(write=True) as con:
        con.executemany(
            "INSERT OR IGNORE INTO hl7_raw (version, resource_type, resource_id, data) VALUES (?, ?, ?, ?)",
            rows,
        )


def _migrate_yaml_profiles() -> None:
    """Import YAML files from profiles_dir that are not yet in the DB."""
    if not settings.profiles_dir.exists():
        return

    yaml_files = list(settings.profiles_dir.glob("*.yaml"))
    if not yaml_files:
        return

    with _conn() as con:
        existing = {row[0] for row in con.execute("SELECT id FROM profiles")}

    for path in yaml_files:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not raw or "profile" not in raw:
                continue
            profile_id = raw["profile"].get("id") or path.stem
            if profile_id in existing:
                continue
            _upsert_raw(profile_id, raw)
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _upsert_raw(profile_id: str, data: dict) -> None:
    meta = data.get("profile", {})
    with _conn(write=True) as con:
        con.execute(
            """
            INSERT INTO profiles (id, message_type, trigger_event, hl7_version, description, updated_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                message_type  = excluded.message_type,
                trigger_event = excluded.trigger_event,
                hl7_version   = excluded.hl7_version,
                description   = excluded.description,
                updated_at    = excluded.updated_at,
                data          = excluded.data
            """,
            (
                profile_id,
                meta.get("message_type", ""),
                meta.get("trigger_event", ""),
                meta.get("hl7_version", ""),
                meta.get("description"),
                meta.get("updated_at"),
                json.dumps(data, ensure_ascii=False),
            ),
        )


# ---------------------------------------------------------------------------
# Public API (used by profile_service)
# ---------------------------------------------------------------------------

def list_summaries() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, message_type, trigger_event, hl7_version, description, updated_at "
            "FROM profiles ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def load(profile_id: str) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT data FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"Profile '{profile_id}' not found")
    return json.loads(row["data"])


def save(profile_id: str, data: dict) -> None:
    _upsert_raw(profile_id, data)


def delete(profile_id: str) -> None:
    with _conn(write=True) as con:
        cur = con.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    if cur.rowcount == 0:
        raise FileNotFoundError(f"Profile '{profile_id}' not found")


def exists(profile_id: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    return row is not None


def all_as_yaml() -> list[tuple[str, str]]:
    """Return [(profile_id, yaml_str)] for all profiles — used by backup."""
    with _conn() as con:
        rows = con.execute("SELECT id, data FROM profiles ORDER BY id").fetchall()
    result = []
    for row in rows:
        data = json.loads(row["data"])
        yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        result.append((row["id"], yaml_str))
    return result


def load_yaml(profile_id: str) -> str:
    """Return the YAML representation of a single profile."""
    data = load(profile_id)
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# HL7 raw API cache (replaces file-based hl7standard_cache/)
# ---------------------------------------------------------------------------

def hl7_raw_get(version: str, resource_type: str, resource_id: str) -> dict | None:
    """Return cached raw HL7 API response, or None if not cached."""
    with _conn() as con:
        row = con.execute(
            "SELECT data FROM hl7_raw WHERE version=? AND resource_type=? AND resource_id=?",
            (version, resource_type, resource_id),
        ).fetchone()
    return json.loads(row["data"]) if row else None


def hl7_raw_set(version: str, resource_type: str, resource_id: str, data: dict) -> None:
    """Store raw HL7 API response."""
    with _conn(write=True) as con:
        con.execute(
            "INSERT OR REPLACE INTO hl7_raw (version, resource_type, resource_id, data) VALUES (?, ?, ?, ?)",
            (version, resource_type, resource_id, json.dumps(data, ensure_ascii=False)),
        )


# ---------------------------------------------------------------------------
# HL7 segment cache (pre-built SegmentDef + value_sets)
# ---------------------------------------------------------------------------

def segment_cache_get(version: str, segment_name: str) -> tuple[dict, dict] | None:
    """Return (segment_data, value_sets_data) for a pre-built segment, or None."""
    with _conn() as con:
        row = con.execute(
            "SELECT data, value_sets FROM hl7_segments WHERE version=? AND segment_name=?",
            (version, segment_name),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["data"]), json.loads(row["value_sets"])


def segment_cache_set(version: str, segment_name: str, segment_data: dict, value_sets: dict) -> None:
    """Store a pre-built segment definition."""
    with _conn(write=True) as con:
        con.execute(
            "INSERT OR REPLACE INTO hl7_segments (version, segment_name, data, value_sets) VALUES (?, ?, ?, ?)",
            (
                version,
                segment_name,
                json.dumps(segment_data, ensure_ascii=False),
                json.dumps(value_sets, ensure_ascii=False),
            ),
        )


# ---------------------------------------------------------------------------
# Shared segments library
# ---------------------------------------------------------------------------

def shared_list() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, segment_name, description, updated_at FROM shared_segments ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def shared_get(shared_id: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT id, segment_name, description, updated_at, data, value_sets FROM shared_segments WHERE id=?",
            (shared_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "segment_name": row["segment_name"],
        "description": row["description"],
        "updated_at": row["updated_at"],
        "data": json.loads(row["data"]),
        "value_sets": json.loads(row["value_sets"]),
    }


def shared_save(shared_id: str, segment_name: str, description: str | None,
                updated_at: str, segment_data: dict, value_sets: dict) -> None:
    with _conn(write=True) as con:
        con.execute(
            """INSERT INTO shared_segments (id, segment_name, description, updated_at, data, value_sets)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 segment_name = excluded.segment_name,
                 description  = excluded.description,
                 updated_at   = excluded.updated_at,
                 data         = excluded.data,
                 value_sets   = excluded.value_sets""",
            (shared_id, segment_name, description, updated_at,
             json.dumps(segment_data, ensure_ascii=False),
             json.dumps(value_sets, ensure_ascii=False)),
        )


def shared_delete(shared_id: str) -> None:
    with _conn(write=True) as con:
        cur = con.execute("DELETE FROM shared_segments WHERE id=?", (shared_id,))
    if cur.rowcount == 0:
        raise FileNotFoundError(f"Shared segment '{shared_id}' not found")


def shared_exists(shared_id: str) -> bool:
    with _conn() as con:
        row = con.execute("SELECT 1 FROM shared_segments WHERE id=?", (shared_id,)).fetchone()
    return row is not None
