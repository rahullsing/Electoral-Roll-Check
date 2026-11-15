"""Learned Alias System for Hindi Voter Matching.

Stores token-level and phrase-level aliases learned from BLO confirmation decisions.
Supports JSON import/export and SQLite persistence.
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Iterable


class AliasManager:
    """Manages learned aliases in-memory with optional SQLite/JSON persistence."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path) if db_path else None
        # Pair set stored bidirectionally: (w1, w2) and (w2, w1)
        self.aliases: set[tuple[str, str]] = set()
        if self.db_path:
            self.init_db()
            self.load_from_db()

    def init_db(self) -> None:
        """Create aliases table if not present."""
        if not self.db_path:
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS learned_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term1 TEXT NOT NULL,
                    term2 TEXT NOT NULL,
                    source TEXT DEFAULT 'user_review',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(term1, term2)
                )
                """
            )
            conn.commit()

    def load_from_db(self) -> None:
        """Load all aliases from SQLite into in-memory set."""
        if not self.db_path:
            return
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT term1, term2 FROM learned_aliases")
            for t1, t2 in cursor.fetchall():
                self.aliases.add((t1, t2))
                self.aliases.add((t2, t1))

    def add_alias(self, term1: str, term2: str, source: str = "user_review") -> bool:
        """Add an alias pair."""
        t1 = term1.strip()
        t2 = term2.strip()
        if not t1 or not t2 or t1 == t2:
            return False

        pair1 = (t1, t2)
        pair2 = (t2, t1)
        if pair1 in self.aliases:
            return False

        self.aliases.add(pair1)
        self.aliases.add(pair2)

        if self.db_path:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR IGNORE INTO learned_aliases (term1, term2, source) VALUES (?, ?, ?)",
                        (t1, t2, source),
                    )
                    conn.commit()
            except Exception:
                pass
        return True

    def remove_alias(self, term1: str, term2: str) -> bool:
        """Delete an alias pair."""
        t1 = term1.strip()
        t2 = term2.strip()
        self.aliases.discard((t1, t2))
        self.aliases.discard((t2, t1))

        if self.db_path:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM learned_aliases WHERE (term1 = ? AND term2 = ?) OR (term1 = ? AND term2 = ?)",
                    (t1, t2, t2, t1),
                )
                conn.commit()
            return True
        return True

    def is_alias(self, term1: str, term2: str) -> bool:
        """Check if two terms are registered aliases."""
        return (term1, term2) in self.aliases

    def get_all_aliases(self) -> list[dict[str, str]]:
        """Return unique alias pairs for UI display."""
        seen = set()
        result = []
        for t1, t2 in sorted(self.aliases):
            canon = tuple(sorted([t1, t2]))
            if canon not in seen:
                seen.add(canon)
                result.append({"term1": canon[0], "term2": canon[1]})
        return result

    def export_to_json(self, file_path: str | Path) -> None:
        """Export aliases to JSON for BLO sharing."""
        pairs = self.get_all_aliases()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(pairs, f, ensure_ascii=False, indent=2)

    def import_from_json(self, file_path: str | Path) -> int:
        """Import aliases from JSON file. Returns count of newly added aliases."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = 0
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    t1 = item.get("term1", "")
                    t2 = item.get("term2", "")
                    if self.add_alias(t1, t2, source="imported_json"):
                        count += 1
        return count


# Global default instance
_default_alias_manager: AliasManager | None = None


def get_default_alias_manager() -> AliasManager:
    global _default_alias_manager
    if _default_alias_manager is None:
        _default_alias_manager = AliasManager()
    return _default_alias_manager
