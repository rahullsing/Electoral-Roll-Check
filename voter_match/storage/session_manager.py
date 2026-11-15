"""Session Persistence and State Recovery Manager.

Enables saving and reopening complete voter-matching sessions, including
source records, column mappings, matched results, candidates, and review decisions.
Supports both SQLite local database persistence and portable .vsession files.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime
import gzip
import json
import math
import zlib
from pathlib import Path
from typing import Any
import sqlite3

from voter_match.core.scorer import ColumnMapping, ScoreResult
from voter_match.core.matcher import MatchRecordB, MatchCandidate, MatchSessionResult
from voter_match.storage.db import get_app_data_dir, get_default_storage, StorageManager

SESSION_FILE_EXTENSION = ".vsession"
# v2: records stored once and referenced by index; files gzip-compressed
SESSION_FORMAT_VERSION = "2.0"
_GZIP_MAGIC = b"\x1f\x8b"
_ZLIB_PREFIX = b"VMZ1"  # marker for zlib-compressed JSON stored in SQLite


def clean_value_for_json(val: Any) -> Any:
    """Recursively convert NumPy/Pandas scalar types, NaNs, and custom objects to native Python types."""
    if val is None:
        return None

    # Check for pandas/numpy NA or NaN
    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except Exception:
        pass

    if isinstance(val, (int, str, bool)):
        return val
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return val

    # Numpy/Pandas scalars like np.int64, np.float64, np.bool_
    if hasattr(val, "item"):
        try:
            it = val.item()
            if isinstance(it, float) and (math.isnan(it) or math.isinf(it)):
                return None
            return it
        except Exception:
            pass

    # Collections
    if isinstance(val, dict):
        return {str(k): clean_value_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [clean_value_for_json(item) for item in val]

    return str(val)


def json_default_fallback(o: Any) -> Any:
    """Fallback handler for json.dumps/dump if any foreign object slips through."""
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    try:
        import pandas as pd
        if pd.isna(o):
            return None
    except Exception:
        pass
    try:
        import numpy as np
        if isinstance(o, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(o)
        if isinstance(o, (np.floating, np.float64, np.float32)):
            return None if math.isnan(o) or math.isinf(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    return str(o)


@dataclass
class SavedSessionData:
    """Complete snapshot of a voter matching session."""
    session_id: str
    title: str
    file_a: str
    file_b: str
    cols_a: list[str] = field(default_factory=list)
    cols_b: list[str] = field(default_factory=list)
    records_a: list[dict[str, Any]] = field(default_factory=list)
    records_b: list[dict[str, Any]] = field(default_factory=list)
    mappings: list[ColumnMapping] = field(default_factory=list)
    session_result: MatchSessionResult | None = None
    created_at: str = ""
    updated_at: str = ""


# --- Serialization Helpers ---

def score_result_to_dict(sr: ScoreResult | None) -> dict[str, Any] | None:
    if not sr:
        return None
    return {
        "score": sr.score,
        "per_role_scores": sr.per_role_scores,
        "reasons": sr.reasons,
        "is_sibling_guard_applied": sr.is_sibling_guard_applied,
        "voter_name_sim": sr.voter_name_sim,
        "relative_name_sim": sr.relative_name_sim,
        "epic_match": sr.epic_match,
        "epic_mismatch": sr.epic_mismatch,
    }


def dict_to_score_result(d: dict[str, Any] | None) -> ScoreResult | None:
    if not d:
        return None
    return ScoreResult(
        score=float(d.get("score", 0.0)),
        per_role_scores=d.get("per_role_scores", {}),
        reasons=d.get("reasons", []),
        is_sibling_guard_applied=d.get("is_sibling_guard_applied", False),
        voter_name_sim=float(d.get("voter_name_sim", 0.0)),
        relative_name_sim=float(d.get("relative_name_sim", 0.0)),
        epic_match=bool(d.get("epic_match", False)),
        epic_mismatch=bool(d.get("epic_mismatch", False)),
    )


def _same_ref(obj: Any, pool: list[dict[str, Any]] | None, idx: int | None) -> bool:
    """True when obj is literally pool[idx] (so it can be stored as an index)."""
    return (
        pool is not None
        and idx is not None
        and 0 <= idx < len(pool)
        and pool[idx] is obj
    )


def _resolve(pool: list[dict[str, Any]] | None, idx: Any) -> dict[str, Any]:
    try:
        i = int(idx)
    except (TypeError, ValueError):
        return {}
    if pool is not None and 0 <= i < len(pool):
        return pool[i]
    return {}


def match_candidate_to_dict(mc: MatchCandidate, records_a: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "a_idx": mc.a_idx,
        "score_result": score_result_to_dict(mc.score_result),
    }
    if not _same_ref(mc.record_a, records_a, mc.a_idx):
        d["record_a"] = mc.record_a
    return d


def dict_to_match_candidate(d: dict[str, Any], records_a: list[dict[str, Any]] | None = None) -> MatchCandidate:
    a_idx = int(d.get("a_idx", 0))
    record_a = d["record_a"] if "record_a" in d else _resolve(records_a, a_idx)
    return MatchCandidate(
        record_a=record_a,
        a_idx=a_idx,
        score_result=dict_to_score_result(d.get("score_result")) or ScoreResult(0.0),
    )


def match_record_b_to_dict(
    rb: MatchRecordB,
    records_a: list[dict[str, Any]] | None = None,
    records_b: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "b_idx": rb.b_idx,
        "assigned_a_idx": rb.assigned_a_idx,
        "best_score_result": score_result_to_dict(rb.best_score_result),
        "top_candidates": [match_candidate_to_dict(c, records_a) for c in rb.top_candidates],
        "tier": rb.tier,
        "user_decision": rb.user_decision,
        "notes": rb.notes,
        "is_deleted": rb.is_deleted,
        "conflict_b_indices": list(rb.conflict_b_indices),
        "machine_tier": rb.machine_tier,
        "machine_a_idx": rb.machine_a_idx,
    }
    if not _same_ref(rb.record_b, records_b, rb.b_idx):
        d["record_b"] = rb.record_b
    if rb.assigned_record_a is None or not _same_ref(rb.assigned_record_a, records_a, rb.assigned_a_idx):
        d["assigned_record_a"] = rb.assigned_record_a
    return d


def dict_to_match_record_b(
    d: dict[str, Any],
    records_a: list[dict[str, Any]] | None = None,
    records_b: list[dict[str, Any]] | None = None,
) -> MatchRecordB:
    b_idx = int(d.get("b_idx", 0))
    assigned = d.get("assigned_a_idx")
    record_b = d["record_b"] if "record_b" in d else _resolve(records_b, b_idx)
    if "assigned_record_a" in d:
        assigned_rec = d["assigned_record_a"]
    else:
        assigned_rec = _resolve(records_a, assigned) if assigned is not None else None
    return MatchRecordB(
        b_idx=b_idx,
        record_b=record_b,
        assigned_a_idx=assigned,
        assigned_record_a=assigned_rec,
        best_score_result=dict_to_score_result(d.get("best_score_result")),
        top_candidates=[dict_to_match_candidate(c, records_a) for c in d.get("top_candidates", [])],
        tier=d.get("tier", "लापता"),
        user_decision=d.get("user_decision"),
        notes=d.get("notes", ""),
        is_deleted=d.get("is_deleted", False),
        conflict_b_indices=list(d.get("conflict_b_indices", []) or []),
        machine_tier=d.get("machine_tier"),
        machine_a_idx=d.get("machine_a_idx"),
    )


def session_result_to_dict(
    sr: MatchSessionResult | None,
    records_b: list[dict[str, Any]] | None = None,
    shared_records_a: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Serialize a session result. Records already stored at the top level of the
    session (shared_records_a / records_b) are referenced by index, not copied."""
    if not sr:
        return None
    d: dict[str, Any] = {
        "records_b": [match_record_b_to_dict(r, sr.records_a, records_b) for r in sr.records_b],
        "unmatched_a_indices": sr.unmatched_a_indices,
        "stats": sr.stats,
        "excluded_a_indices": list(sr.excluded_a_indices),
    }
    if shared_records_a is not None and sr.records_a is shared_records_a:
        d["records_a_ref"] = "top"
    else:
        d["records_a"] = sr.records_a
    return d


def dict_to_session_result(
    d: dict[str, Any] | None,
    top_records_a: list[dict[str, Any]] | None = None,
    top_records_b: list[dict[str, Any]] | None = None,
) -> MatchSessionResult | None:
    if not d:
        return None
    if d.get("records_a_ref") == "top" and top_records_a is not None:
        records_a = top_records_a
    else:
        records_a = d.get("records_a", []) or []
    return MatchSessionResult(
        records_b=[dict_to_match_record_b(r, records_a, top_records_b) for r in d.get("records_b", [])],
        unmatched_a_indices=d.get("unmatched_a_indices", []),
        records_a=records_a,
        stats=d.get("stats", {}),
        excluded_a_indices=list(d.get("excluded_a_indices", []) or []),
    )


def session_data_to_dict(data: SavedSessionData) -> dict[str, Any]:
    raw_dict = {
        "version": SESSION_FORMAT_VERSION,
        "session_id": data.session_id,
        "title": data.title,
        "file_a": data.file_a,
        "file_b": data.file_b,
        "cols_a": data.cols_a,
        "cols_b": data.cols_b,
        "records_a": data.records_a,
        "records_b": data.records_b,
        "mappings": [asdict(m) for m in data.mappings],
        "session_result": session_result_to_dict(
            data.session_result, records_b=data.records_b, shared_records_a=data.records_a
        ),
        "created_at": data.created_at or datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    return clean_value_for_json(raw_dict)


def dict_to_session_data(d: dict[str, Any]) -> SavedSessionData:
    known = set(ColumnMapping.__dataclass_fields__)
    mappings = [ColumnMapping(**{k: v for k, v in m.items() if k in known}) for m in d.get("mappings", [])]
    records_a = d.get("records_a", []) or []
    records_b = d.get("records_b", []) or []
    session_result = dict_to_session_result(d.get("session_result"), records_a, records_b)
    return SavedSessionData(
        session_id=d.get("session_id", ""),
        title=d.get("title", "मतदाता मिलान सत्र"),
        file_a=d.get("file_a", ""),
        file_b=d.get("file_b", ""),
        cols_a=d.get("cols_a", []),
        cols_b=d.get("cols_b", []),
        records_a=records_a,
        records_b=records_b,
        mappings=mappings,
        session_result=session_result,
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


class SessionManager:
    """Manages SQLite storage and file-based export/import for application sessions."""

    def __init__(self, storage: StorageManager | None = None):
        self.storage = storage or get_default_storage()
        self.init_session_table()

    def get_connection(self) -> sqlite3.Connection:
        return self.storage.get_connection()

    def init_session_table(self) -> None:
        """Create saved_sessions table in SQLite if not exists."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    file_a TEXT,
                    file_b TEXT,
                    total_records_b INTEGER DEFAULT 0,
                    matched_count INTEGER DEFAULT 0,
                    review_count INTEGER DEFAULT 0,
                    missing_count INTEGER DEFAULT 0,
                    data_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def save_session(self, data: SavedSessionData) -> bool:
        """Save or update a session in SQLite."""
        if not data.session_id:
            data.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        data_dict = session_data_to_dict(data)
        data_json = _ZLIB_PREFIX + zlib.compress(
            json.dumps(data_dict, ensure_ascii=False, default=json_default_fallback).encode("utf-8"), 6
        )

        total_b = len(data.records_b)
        matched = 0
        review = 0
        missing = 0
        if data.session_result and data.session_result.stats:
            matched = data.session_result.stats.get("मिला", 0)
            review = data.session_result.stats.get("जाँचें", 0)
            missing = data.session_result.stats.get("लापता", 0)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO saved_sessions (
                    session_id, title, file_a, file_b,
                    total_records_b, matched_count, review_count, missing_count,
                    data_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    title=excluded.title,
                    file_a=excluded.file_a,
                    file_b=excluded.file_b,
                    total_records_b=excluded.total_records_b,
                    matched_count=excluded.matched_count,
                    review_count=excluded.review_count,
                    missing_count=excluded.missing_count,
                    data_json=excluded.data_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    data.session_id,
                    data.title.strip() or "मतदाता मिलान सत्र",
                    Path(data.file_a).name if data.file_a else "",
                    Path(data.file_b).name if data.file_b else "",
                    total_b,
                    matched,
                    review,
                    missing,
                    data_json,
                ),
            )
            conn.commit()
            self.storage.log_audit("session_saved", f"सत्र सहेजा गया: {data.title} ({data.session_id})")
        return True

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions ordered by most recently updated."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, title, file_a, file_b,
                       total_records_b, matched_count, review_count, missing_count,
                       updated_at
                FROM saved_sessions
                WHERE session_id NOT LIKE '__autosave_%'
                ORDER BY updated_at DESC
                """
            )
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "session_id": row["session_id"],
                    "title": row["title"],
                    "file_a": row["file_a"],
                    "file_b": row["file_b"],
                    "total_records_b": row["total_records_b"],
                    "matched_count": row["matched_count"],
                    "review_count": row["review_count"],
                    "missing_count": row["missing_count"],
                    "updated_at": str(row["updated_at"]),
                })
            return sessions

    def load_session(self, session_id: str) -> SavedSessionData | None:
        """Load session data from SQLite by session_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data_json FROM saved_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return dict_to_session_data(_decode_stored_json(row["data_json"]))

    def delete_session(self, session_id: str) -> bool:
        """Delete a saved session from SQLite."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM saved_sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            self.storage.log_audit("session_deleted", f"सत्र हटाया गया: {session_id}")
        return True

    def auto_save(self, data: SavedSessionData) -> None:
        """Quick auto-save for crash protection."""
        auto_data = SavedSessionData(
            session_id="__autosave_latest__",
            title=f"ऑटो-सेव: {data.title}",
            file_a=data.file_a,
            file_b=data.file_b,
            cols_a=data.cols_a,
            cols_b=data.cols_b,
            records_a=data.records_a,
            records_b=data.records_b,
            mappings=data.mappings,
            session_result=data.session_result,
        )
        try:
            self.save_session(auto_data)
        except Exception:
            pass

    def get_auto_saved_session(self) -> SavedSessionData | None:
        """Retrieve latest auto-saved session if available."""
        try:
            return self.load_session("__autosave_latest__")
        except Exception:
            return None

    def export_session_file(self, data: SavedSessionData, file_path: Path | str) -> None:
        """Export session data to a portable .vsession file."""
        target = Path(file_path)
        if not target.suffix:
            target = target.with_suffix(SESSION_FILE_EXTENSION)
        data_dict = session_data_to_dict(data)
        payload = json.dumps(data_dict, ensure_ascii=False, default=json_default_fallback).encode("utf-8")
        with gzip.open(target, "wb", compresslevel=6) as f:
            f.write(payload)

    def import_session_file(self, file_path: Path | str) -> SavedSessionData:
        """Import session data from a portable .vsession file."""
        raw = Path(file_path).read_bytes()
        if raw[:2] == _GZIP_MAGIC:
            raw = gzip.decompress(raw)
        return dict_to_session_data(json.loads(raw.decode("utf-8-sig")))


def _decode_stored_json(value: Any) -> dict[str, Any]:
    """Decode a saved_sessions.data_json value (zlib v2 blob or legacy JSON text)."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        b = bytes(value)
        if b.startswith(_ZLIB_PREFIX):
            b = zlib.decompress(b[len(_ZLIB_PREFIX):])
        return json.loads(b.decode("utf-8"))
    return json.loads(value)


# Global singleton instance
_default_session_manager: SessionManager | None = None


def get_default_session_manager() -> SessionManager:
    global _default_session_manager
    if _default_session_manager is None:
        _default_session_manager = SessionManager()
    return _default_session_manager
