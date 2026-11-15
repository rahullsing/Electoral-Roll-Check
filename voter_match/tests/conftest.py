"""Shared pytest configuration."""

import os

# Keep learned aliases / rejections in memory so tests never touch the user's real app DB.
os.environ.setdefault("VOTER_MATCH_IN_MEMORY", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
