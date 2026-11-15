"""Record-Level Weighted Scorer with Devanagari Domain Rules.

Implements multi-column matching with Hindi reasons, sibling guard,
age tolerance, gender mapping, and penalty capping.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import re
from typing import Any

from voter_match.core.normalize import (
    NormalizedName,
    normalize_hindi_name,
    get_default_normalizer,
)
from voter_match.core.similarity import name_similarity
from voter_match.core.learning import AliasManager

IMPORTANCE_WEIGHTS: dict[str, float] = {
    "Paper Ref": 0.0,
    "कागज़ी संदर्भ (Paper Ref)": 0.0,
    "Must match": 1.2,
    "High": 1.0,
    "Medium": 0.6,
    "Low": 0.3,
    "Bonus only": 0.0,
    "Ignore": 0.0,
}


@dataclass
class ColumnMapping:
    """Configuration for a mapped column role."""
    role: str                       # e.g., 'serial_no', 'voter_name', 'relative_name', 'age', 'gender', 'house_no'
    col_a: str | None = None        # Header name in List A
    col_b: str | None = None        # Header name in List B
    importance: str = "High"        # 'Must match', 'High', 'Medium', 'Low', 'Bonus only', 'Paper Ref', 'Ignore'
    weight: float = 1.0
    col_type: str = "name"          # 'name', 'number', 'category', 'text'
    tolerance: int = 3              # For number/age
    year_offset: int = 0            # Age role: expected (age_B - age_A), i.e. roll year B - roll year A

    def is_active(self) -> bool:
        if self.role == "serial_no":
            return bool((self.col_a or self.col_b) and self.importance != "Ignore")
        return bool(self.col_a and self.col_b and self.importance != "Ignore")


@dataclass
class ScoreResult:
    """Outcome of scoring a pair of voter records."""
    score: float                                      # 0.0 to 1.0
    per_role_scores: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)  # Hindi explanations
    is_sibling_guard_applied: bool = False
    voter_name_sim: float = 0.0
    relative_name_sim: float = 0.0
    epic_match: bool = False        # Both EPIC (voter ID) numbers present and identical
    epic_mismatch: bool = False     # Both EPIC numbers present but different


def normalize_gender(val: Any) -> str:
    """Normalize common Hindi and English gender values."""
    if val is None:
        return ""
    raw = str(val).strip().lower()

    # Male checks
    if raw.startswith("पु") or raw in {"m", "male", "लड़का", "नर", "पुरुस", "पुरुष", "पुरूष", "पुरुश", "man", "boy"}:
        return "M"
    # Female checks
    if raw.startswith("म") or raw.startswith("स्त्री") or raw in {"f", "female", "औरत", "नारी", "महिला", "woman", "girl"}:
        return "F"
    # Transgender / Other checks
    if raw.startswith("अ") or raw in {"t", "trans", "tg", "third", "तीसरा", "अन्य"}:
        return "T"

    normalizer = get_default_normalizer()
    s = normalizer.apply_rules(raw)
    if s.startswith("पु") or s in {"पुरुस", "पुरुश", "m", "male"}:
        return "M"
    if s.startswith("म") or s in {"महिला", "f", "female"}:
        return "F"
    return s.upper()


def normalize_house_number(val: Any) -> str:
    """Normalize house number: digits normalized, leading zeros removed, stripped."""
    if val is None:
        return ""
    normalizer = get_default_normalizer()
    raw = normalizer.normalize_digits(str(val).strip())
    # Remove dots, dashes, slashes, spaces
    cleaned = re.sub(r"[\s\.\-_/\\,]", "", raw)
    # Strip leading zeros if purely numeric
    if cleaned.isdigit():
        return str(int(cleaned))
    return cleaned.lower()


def normalize_epic(val: Any) -> str:
    """Normalize an EPIC / voter-ID number: uppercase alphanumerics only.

    OCR / typing slips O->0, I->1 in the numeric tail are repaired
    (EPIC format: 3 letters followed by digits, e.g. ABC1234567).
    """
    if val is None:
        return ""
    raw = str(val).strip()
    if not raw or raw.lower() in {"nan", "none", "-"}:
        return ""
    normalizer = get_default_normalizer()
    s = re.sub(r"[^A-Z0-9]", "", normalizer.normalize_digits(raw).upper())
    if len(s) > 3 and s[:3].isalpha():
        s = s[:3] + s[3:].translate(str.maketrans("OIL", "011"))
    return s


def parse_age(val: Any) -> int | None:
    """Extract age as integer, converting Devanagari numerals if present."""
    if val is None:
        return None
    normalizer = get_default_normalizer()
    norm = normalizer.normalize_digits(str(val).strip())
    match = re.search(r"\d+", norm)
    if match:
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return None


class RecordScorer:
    """Scores a pair of records (List A row vs List B row)."""

    def __init__(
        self,
        mappings: list[ColumnMapping],
        gender_mapping: dict[str, str] | None = None,
        alias_manager: AliasManager | None = None,
    ):
        self.mappings = mappings
        self.gender_map = gender_mapping or {}
        self.alias_manager = alias_manager
        # Resolve special-role mappings once instead of on every pair
        self.age_m = self._find_role("age")
        self.gender_m = self._find_role("gender")
        self.house_m = self._find_role("house_no")
        self.epic_m = self._find_role("epic")
        # Per-run memo caches: names (especially fathers' names) and field values
        # repeat heavily across a roll, so identical comparisons are reused.
        self._sim_cache: dict[tuple[str, str], tuple[float, str]] = {}
        self._value_cache: dict[tuple[str, Any], Any] = {}

    def _similarity(self, a: NormalizedName, b: NormalizedName) -> tuple[float, str]:
        key = (a.original, b.original)
        hit = self._sim_cache.get(key)
        if hit is None:
            hit = name_similarity(a, b, self.alias_manager)
            if len(self._sim_cache) > 500_000:
                self._sim_cache.clear()
            self._sim_cache[key] = hit
        return hit

    def _cached(self, kind: str, fn, val: Any) -> Any:
        try:
            key = (kind, val)
            if key in self._value_cache:
                return self._value_cache[key]
        except TypeError:  # unhashable value
            return fn(val)
        res = fn(val)
        if len(self._value_cache) > 200_000:
            self._value_cache.clear()
        self._value_cache[key] = res
        return res

    def _find_role(self, role: str) -> ColumnMapping | None:
        return next((m for m in self.mappings if m.role == role and m.is_active()), None)

    def score_pair(
        self,
        record_a: dict[str, Any],
        record_b: dict[str, Any],
        norm_cache_a: dict[str, NormalizedName] | None = None,
        norm_cache_b: dict[str, NormalizedName] | None = None,
    ) -> ScoreResult:
        """Calculate record match score and generate Hindi reasoning."""
        per_role_scores: dict[str, float] = {}
        reasons: list[str] = []

        total_weight = 0.0
        weighted_sum = 0.0

        voter_name_sim = 1.0
        relative_name_sim = 1.0
        voter_core_sim = 1.0
        has_voter_name = False
        has_relative_name = False
        must_match_failed = False

        # Evaluate Name-type and Custom extra columns
        # Note: age, gender, house_no, ward have dedicated domain logic below
        for m in self.mappings:
            if not m.is_active():
                continue

            if m.role in {"age", "gender", "house_no", "ward", "serial_no", "epic"}:
                continue

            val_a = record_a.get(m.col_a)
            val_b = record_b.get(m.col_b)

            if m.col_type == "name":
                norm_a = (
                    norm_cache_a.get(m.col_a)
                    if norm_cache_a and m.col_a in norm_cache_a
                    else normalize_hindi_name(val_a)
                )
                norm_b = (
                    norm_cache_b.get(m.col_b)
                    if norm_cache_b and m.col_b in norm_cache_b
                    else normalize_hindi_name(val_b)
                )

                sim, method = self._similarity(norm_a, norm_b)
                per_role_scores[m.role] = sim

                w = IMPORTANCE_WEIGHTS.get(m.importance, m.weight)
                if m.importance == "Must match" and sim < 0.85:
                    must_match_failed = True

                weighted_sum += sim * w
                total_weight += w

                role_label = (
                    "मतदाता का नाम"
                    if m.role == "voter_name"
                    else ("पिता/पति/माता का नाम" if m.role == "relative_name" else m.role)
                )

                if sim >= 0.98:
                    reasons.append(f"{role_label}: समान ({method})")
                elif sim >= 0.80:
                    reasons.append(f"{role_label}: वर्तनी अंतर ({int(sim*100)}%, {method})")
                elif sim >= 0.50:
                    reasons.append(f"{role_label}: कम समानता ({int(sim*100)}%)")
                else:
                    reasons.append(f"{role_label}: भिन्न ({int(sim*100)}%)")

                if m.role == "voter_name":
                    voter_name_sim = sim
                    has_voter_name = True
                    # Also compute core similarity for sibling detection
                    core_a = normalize_hindi_name(norm_a.core)
                    core_b = normalize_hindi_name(norm_b.core)
                    c_sim, _ = self._similarity(core_a, core_b)
                    voter_core_sim = c_sim
                elif m.role == "relative_name":
                    relative_name_sim = sim
                    has_relative_name = True

            elif m.col_type == "category" or m.col_type == "text":
                # For user-defined custom extra columns
                s_a = str(val_a or "").strip()
                s_b = str(val_b or "").strip()
                if s_a and s_b:
                    sim = 1.0 if s_a == s_b else 0.0
                    per_role_scores[m.role] = sim
                    w = IMPORTANCE_WEIGHTS.get(m.importance, m.weight)
                    weighted_sum += sim * w
                    total_weight += w
                    if sim == 1.0:
                        reasons.append(f"{m.role}: समान")
                    else:
                        reasons.append(f"{m.role}: भिन्न")

        # Base score from weighted name roles
        base_score = (weighted_sum / total_weight) if total_weight > 0 else 0.5

        # Rule: If either main name role < 0.60 -> subtract 0.10
        if (has_voter_name and voter_name_sim < 0.60) or (has_relative_name and relative_name_sim < 0.60):
            base_score -= 0.10
            reasons.append("मुख्य नाम में अत्यधिक भिन्नता (-10% कटौती)")

        # Penalties & Bonuses for Age, Gender, House No
        age_bonus_penalty = 0.0
        gender_penalty = 0.0
        house_bonus = 0.0

        # Check Age mapping
        age_m = self.age_m
        if age_m:
            age_a = self._cached("age", parse_age, record_a.get(age_m.col_a))
            age_b = self._cached("age", parse_age, record_b.get(age_m.col_b))
            if age_a is not None and age_b is not None:
                offset = int(getattr(age_m, "year_offset", 0) or 0)
                # Lists from different roll years: B's age is expected to be A's age + offset
                diff = abs((age_b - age_a) - offset)
                if diff <= age_m.tolerance:
                    age_bonus_penalty = 0.03
                    if offset:
                        reasons.append(f"आयु समायोजित समान ({age_a}+{offset} vs {age_b} वर्ष, +3%)")
                    else:
                        reasons.append(f"आयु समान/समीप ({age_a} vs {age_b} वर्ष, +3%)")
                else:
                    extra = diff - age_m.tolerance
                    pen = min(0.20, extra * 0.025)
                    age_bonus_penalty = -pen
                    reasons.append(f"आयु अंतर {diff} वर्ष (-{int(pen*100)}%)")
            else:
                reasons.append("आयु अनुपलब्ध")

        # Check Gender mapping
        gender_m = self.gender_m
        if gender_m:
            gen_a = self._cached("gender", normalize_gender, record_a.get(gender_m.col_a))
            gen_b = self._cached("gender", normalize_gender, record_b.get(gender_m.col_b))
            if gen_a and gen_b:
                if gen_a == gen_b:
                    reasons.append("लिंग समान")
                    per_role_scores["gender"] = 1.0
                else:
                    gender_penalty = 0.20
                    reasons.append(f"लिंग अलग ({gen_a} vs {gen_b}, -20%)")
                    per_role_scores["gender"] = 0.0

        # Check House Number mapping
        house_m = self.house_m
        if house_m:
            h_a = self._cached("house", normalize_house_number, record_a.get(house_m.col_a))
            h_b = self._cached("house", normalize_house_number, record_b.get(house_m.col_b))
            if h_a and h_b and h_a == h_b:
                house_bonus = 0.04
                reasons.append("मकान नं० समान (+4%)")
                per_role_scores["house_no"] = 1.0
            else:
                per_role_scores["house_no"] = 0.0

        # Penalty cap: if both main names >= 0.95, total age+gender penalty capped at 0.05
        net_demerit = max(0.0, -age_bonus_penalty) + gender_penalty
        if has_voter_name and has_relative_name and voter_name_sim >= 0.95 and relative_name_sim >= 0.95:
            if net_demerit > 0.05:
                net_demerit = 0.05
                reasons.append("दोनों मुख्य नाम अति-सटीक (आयु/लिंग त्रुटि सीमा 5% तक सीमित)")
                final_score = base_score - net_demerit + house_bonus
                if age_bonus_penalty > 0:
                    final_score += age_bonus_penalty
            else:
                final_score = base_score + age_bonus_penalty - gender_penalty + house_bonus
        else:
            final_score = base_score + age_bonus_penalty - gender_penalty + house_bonus

        # Rule: Must match role failed (< 0.85) -> score capped at 0.5
        if must_match_failed:
            if final_score > 0.50:
                final_score = 0.50
                reasons.append("अनिवार्य स्तंभ ('Must Match') की शर्त पूरी नहीं हुई (अधिकतम 50%)")

        # EPIC (voter ID) number: a unique identifier, so an exact match settles identity
        epic_match = False
        epic_mismatch = False
        if self.epic_m:
            e_a = self._cached("epic", normalize_epic, record_a.get(self.epic_m.col_a))
            e_b = self._cached("epic", normalize_epic, record_b.get(self.epic_m.col_b))
            if e_a and e_b:
                if e_a == e_b:
                    epic_match = True
                    per_role_scores["epic"] = 1.0
                    final_score = max(final_score, 0.97)
                    reasons.insert(0, f"EPIC पहचान पत्र संख्या समान ({e_a}) — निश्चित मिलान")
                else:
                    epic_mismatch = True
                    per_role_scores["epic"] = 0.0
                    final_score -= 0.15
                    reasons.append(f"EPIC संख्या भिन्न ({e_a} vs {e_b}, -15%, जाँच आवश्यक)")

        # Sibling guard: relative name >= 0.95 but voter name < 0.80 (or core voter name < 0.80) -> never "मिला"
        # (skipped when EPIC numbers prove it is the same person)
        is_sibling = False
        if has_relative_name and has_voter_name and not epic_match:
            if relative_name_sim >= 0.95 and (voter_name_sim < 0.80 or voter_core_sim < 0.80):
                is_sibling = True
                if final_score >= 0.85:
                    final_score = 0.84
                reasons.append("संभावित सहोदर (भाई/बहन) - पिता/पति नाम समान, मतदाता नाम भिन्न (सत्यापन आवश्यक)")

        final_score = max(0.0, min(1.0, final_score))

        return ScoreResult(
            score=round(final_score, 4),
            per_role_scores=per_role_scores,
            reasons=reasons,
            is_sibling_guard_applied=is_sibling,
            voter_name_sim=voter_name_sim,
            relative_name_sim=relative_name_sim,
            epic_match=epic_match,
            epic_mismatch=epic_mismatch,
        )
