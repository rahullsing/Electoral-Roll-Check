"""Hindi Normalization Pipeline.

Implements an ordered, data-driven normalization pipeline specifically
tailored for Hindi Devanagari voter roll variations and OCR errors.
"""

from __future__ import annotations
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voter_match.core.phonetic import hindi_phonetic_key
from voter_match.core.transliterate import has_latin, transliterate_roman_to_devanagari

# Bound for the per-normalizer memo cache (names repeat heavily: fathers, surnames)
_NORMALIZE_CACHE_MAX = 200_000

def _resolve_data_dir() -> Path:
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([
            meipass / "voter_match" / "data",
            meipass / "data",
        ])
    pkg_data = Path(__file__).resolve().parent.parent / "data"
    candidates.append(pkg_data)
    candidates.append(Path.cwd() / "voter_match" / "data")
    candidates.append(Path.cwd() / "data")

    for c in candidates:
        if (c / "rules_default.json").exists():
            return c
    return pkg_data


DATA_DIR = _resolve_data_dir()
DEFAULT_RULES_PATH = DATA_DIR / "rules_default.json"
DEFAULT_STOPWORDS_PATH = DATA_DIR / "stopwords_default.json"


@dataclass
class NormalizedName:
    """Dataclass holding all variations of a normalized Hindi name."""
    original: str
    clean: str = ""
    normalized: str = ""
    core: str = ""
    skeleton: str = ""
    space_free: str = ""
    tokens: list[str] = field(default_factory=list)
    core_tokens: list[str] = field(default_factory=list)
    phonetic_key: str = ""

    def __post_init__(self):
        if not self.clean:
            self.clean = self.original.strip() if self.original else ""


class HindiNormalizer:
    """Configurable, rule-driven Hindi text normalizer."""

    def __init__(
        self,
        rules_path: str | Path | None = None,
        stopwords_path: str | Path | None = None,
        rules_data: list[dict[str, Any]] | None = None,
        stopwords_data: list[str] | None = None,
    ):
        self.rules: list[dict[str, Any]] = []
        self.stopwords: list[str] = []

        if rules_data is not None:
            self.rules = rules_data
        else:
            p = Path(rules_path or DEFAULT_RULES_PATH)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    self.rules = json.load(f)

        if stopwords_data is not None:
            self.stopwords = stopwords_data
        else:
            sp = Path(stopwords_path or DEFAULT_STOPWORDS_PATH)
            if sp.exists():
                with open(sp, "r", encoding="utf-8") as f:
                    self.stopwords = json.load(f)

        # Pre-normalize stopwords so they match normalized tokens
        self.normalized_stopwords: set[str] = set()
        for sw in self.stopwords:
            self.normalized_stopwords.add(sw.strip())
            norm_sw = self.apply_rules(sw.strip())
            if norm_sw:
                self.normalized_stopwords.add(norm_sw)

        # Memo cache: raw text -> NormalizedName (treat returned objects as read-only)
        self._cache: dict[str, NormalizedName] = {}
        self.transliterate_roman = True

        # Regex for Devanagari digits to English digits
        self.digit_map = str.maketrans("०१२३४५६७८९", "0123456789")

        # Compiled regex for vowels and vowel signs (consonant skeleton)
        self.re_vowels_and_signs = re.compile(
            r"[\u0904-\u0914\u093E-\u094F\u0901-\u0903\u0951-\u0954\u0962-\u0963]"
        )

    def normalize_digits(self, text: str) -> str:
        """Translate Devanagari numerals (०-९) to ASCII (0-9)."""
        if not text:
            return ""
        return str(text).translate(self.digit_map)

    def apply_rules(self, text: str) -> str:
        """Apply the ordered data-driven normalization rules."""
        if not text:
            return ""

        # Initial NFC normalization
        curr = unicodedata.normalize("NFC", text)

        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            pattern = rule.get("pattern", "")
            repl = rule.get("replacement", "")

            if isinstance(repl, dict):
                def make_sub(mapping):
                    return lambda m: mapping.get(m.group(0), m.group(0))
                curr = re.sub(pattern, make_sub(repl), curr)
            elif isinstance(repl, str):
                curr = re.sub(pattern, repl, curr)

        # Whitespace collapse
        curr = re.sub(r"\s+", " ", curr).strip()
        return unicodedata.normalize("NFC", curr)

    def extract_skeleton(self, text: str) -> str:
        """Extract consonant skeleton by removing all vowel signs and independent vowels."""
        if not text:
            return ""
        skel = self.re_vowels_and_signs.sub("", text)
        skel = re.sub(r"\s+", "", skel)
        return skel

    def strip_stopwords(self, tokens: list[str]) -> list[str]:
        """Strip honorifics and common surname stopwords, keeping core names if length >= 2."""
        if not tokens:
            return []

        if len(tokens) <= 1:
            return tokens

        filtered = [t for t in tokens if t not in self.normalized_stopwords and t not in self.stopwords]

        if not filtered:
            return tokens

        if sum(len(t) for t in filtered) < 2:
            return tokens

        return filtered

    def clear_cache(self) -> None:
        """Invalidate memoised results (call after editing rules or stopwords)."""
        self._cache.clear()

    def normalize(self, text: str | Any) -> NormalizedName:
        """Produce full NormalizedName dataclass representation (memoised)."""
        if text is None:
            text = ""
        raw = str(text).strip()
        if not raw:
            return NormalizedName(original="")

        cached = self._cache.get(raw)
        if cached is not None:
            return cached
        result = self._normalize_uncached(raw)
        if len(self._cache) >= _NORMALIZE_CACHE_MAX:
            self._cache.clear()
        self._cache[raw] = result
        return result

    def _normalize_uncached(self, raw: str) -> NormalizedName:
        # 1. Clean form (Roman-script names are transliterated to Devanagari first)
        clean = unicodedata.normalize("NFC", raw)
        if self.transliterate_roman and has_latin(clean):
            clean = unicodedata.normalize("NFC", transliterate_roman_to_devanagari(clean))

        # 2. Fully normalized string
        norm = self.apply_rules(clean)

        # 3. Tokens & space-free form
        tokens = [t for t in norm.split() if t]
        space_free = "".join(tokens)

        # 4. Stopwords / Core form
        core_tokens = self.strip_stopwords(tokens)
        core = " ".join(core_tokens)

        # 5. Consonant Skeleton
        skeleton = self.extract_skeleton(norm)

        # 6. Phonetic key
        pkey = hindi_phonetic_key(norm)

        return NormalizedName(
            original=raw,
            clean=clean,
            normalized=norm,
            core=core,
            skeleton=skeleton,
            space_free=space_free,
            tokens=tokens,
            core_tokens=core_tokens,
            phonetic_key=pkey,
        )


# Global default normalizer instance
_default_normalizer: HindiNormalizer | None = None


def get_default_normalizer() -> HindiNormalizer:
    global _default_normalizer
    if _default_normalizer is None:
        _default_normalizer = HindiNormalizer()
    return _default_normalizer


def normalize_hindi_name(text: str | Any) -> NormalizedName:
    """Convenience function using the default normalizer."""
    return get_default_normalizer().normalize(text)
