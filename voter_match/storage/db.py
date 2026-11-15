"""SQLite Storage and Persistence Layer.

Provides local, fully offline storage for mapping profiles, review decisions,
learned aliases, session states, and audit trails.
"""

from __future__ import annotations
import os
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from voter_match.core.scorer import ColumnMapping


def get_app_data_dir() -> Path:
    """Resolve writable directory for application database and logs.

    Tries:
    1. %LOCALAPPDATA%/ElectoralRollCheck (Standard Windows user directory)
    2. ~/.electoral_roll_check
    3. Workspace / local folder fallback (.app_data)
    """
    candidates = []
    local_app = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local_app:
        candidates.append(Path(local_app) / "ElectoralRollCheck")
    candidates.append(Path.home() / ".electoral_roll_check")
    candidates.append(Path(__file__).resolve().parent.parent.parent / ".app_data")

    for p in candidates:
        try:
            p.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = p / ".test_write"
            test_file.touch()
            test_file.unlink()
            return p
        except Exception:
            continue

    # Final fallback: current working directory
    fallback = Path.cwd() / ".app_data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


APP_DATA_DIR = get_app_data_dir()
DEFAULT_DB_PATH = APP_DATA_DIR / "voter_match.db"


class StorageManager:
    """Manages SQLite tables for profiles, decisions, and system persistence."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Mapping profiles table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS mapping_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    mappings_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Saved match review decisions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS review_decisions (
                    session_id TEXT NOT NULL,
                    b_idx INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    assigned_a_idx INTEGER,
                    notes TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_id, b_idx)
                )
                """
            )

            # Session tracker
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    file_a TEXT,
                    file_b TEXT,
                    stats_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Audit trail
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.commit()

    # --- Profile Operations ---

    def save_profile(self, name: str, mappings: list[ColumnMapping]) -> bool:
        """Save or update a named column mapping profile."""
        mappings_data = [asdict(m) for m in mappings]
        mappings_json = json.dumps(mappings_data, ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mapping_profiles (name, mappings_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    mappings_json=excluded.mappings_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (name.strip(), mappings_json),
            )
            conn.commit()
            self.log_audit("profile_saved", f"प्रोफ़ाइल सहेजा गया: {name}")
        return True

    def get_profile(self, name: str) -> list[ColumnMapping] | None:
        """Load a profile by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mappings_json FROM mapping_profiles WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["mappings_json"])
            known = set(ColumnMapping.__dataclass_fields__)
            return [ColumnMapping(**{k: v for k, v in d.items() if k in known}) for d in data]

    def list_profiles(self) -> list[str]:
        """List all saved profile names."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM mapping_profiles ORDER BY name")
            return [r["name"] for r in cursor.fetchall()]

    def delete_profile(self, name: str) -> bool:
        """Delete a profile by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mapping_profiles WHERE name = ?", (name,))
            conn.commit()
            self.log_audit("profile_deleted", f"प्रोफ़ाइल हटाया गया: {name}")
        return True

    def find_matching_profile(self, cols_a: list[str], cols_b: list[str]) -> str | None:
        """Find if existing profile matches current file headers."""
        set_a = set(cols_a)
        set_b = set(cols_b)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, mappings_json FROM mapping_profiles")
            for row in cursor.fetchall():
                try:
                    data = json.loads(row["mappings_json"])
                    all_present = True
                    for m in data:
                        c_a = m.get("col_a")
                        c_b = m.get("col_b")
                        if c_a and c_a not in set_a:
                            all_present = False
                            break
                        if c_b and c_b not in set_b:
                            all_present = False
                            break
                    if all_present and data:
                        return row["name"]
                except Exception:
                    continue
        return None

    # --- Review Decision Operations ---

    def save_decision(
        self,
        session_id: str,
        b_idx: int,
        decision: str,
        assigned_a_idx: int | None = None,
        notes: str = "",
    ) -> None:
        """Persist BLO verification decision for a record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO review_decisions (session_id, b_idx, decision, assigned_a_idx, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id, b_idx) DO UPDATE SET
                    decision=excluded.decision,
                    assigned_a_idx=excluded.assigned_a_idx,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (session_id, b_idx, decision, assigned_a_idx, notes),
            )
            conn.commit()

    def delete_decision(self, session_id: str, b_idx: int) -> None:
        """Remove a stored decision (used by Undo to return a record to pending)."""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM review_decisions WHERE session_id = ? AND b_idx = ?",
                (session_id, b_idx),
            )
            conn.commit()

    def get_decisions(self, session_id: str) -> dict[int, dict[str, Any]]:
        """Retrieve all decisions for a session."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT b_idx, decision, assigned_a_idx, notes FROM review_decisions WHERE session_id = ?",
                (session_id,),
            )
            res: dict[int, dict[str, Any]] = {}
            for row in cursor.fetchall():
                res[row["b_idx"]] = {
                    "decision": row["decision"],
                    "assigned_a_idx": row["assigned_a_idx"],
                    "notes": row["notes"],
                }
            return res

    # --- Audit Log Operations ---

    def log_audit(self, event_type: str, description: str, session_id: str | None = None) -> None:
        """Write an action to the audit trail."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO audit_trail (session_id, event_type, description) VALUES (?, ?, ?)",
                    (session_id, event_type, description),
                )
                conn.commit()
        except Exception:
            pass


# Global storage manager instance
_default_storage: StorageManager | None = None


def get_default_storage() -> StorageManager:
    global _default_storage
    if _default_storage is None:
        _default_storage = StorageManager()
    return _default_storage
