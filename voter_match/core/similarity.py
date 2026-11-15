"""Multi-Method Hindi Name Similarity Calculator.

Evaluates Devanagari names using 8 complementary fuzzy, phonetic, and
syntactic dimensions and selects the optimal confidence score with reason attribution.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import rapidfuzz.distance.JaroWinkler as jw
from rapidfuzz import fuzz

from voter_match.core.normalize import NormalizedName
from voter_match.core.learning import AliasManager, get_default_alias_manager


def name_similarity(
    a: NormalizedName,
    b: NormalizedName,
    alias_manager: AliasManager | None = None,
) -> tuple[float, str]:
    """Calculate multi-method Hindi name similarity.

    Returns:
        tuple[float, str]: (similarity score between 0.0 and 1.0, method_used description)
    """
    if not a.original or not b.original:
        return 0.0, "रिक्त मान (Empty)"

    # Fast path: exact match on raw, clean or normalized
    if a.original == b.original or a.clean == b.clean:
        return 1.0, "पूर्ण समान (Exact)"
    if a.normalized and a.normalized == b.normalized:
        return 1.0, "पूर्ण सामान्यीकृत समान (Normalized Exact)"

    mgr = alias_manager or get_default_alias_manager()

    candidates: list[tuple[float, str]] = []

    # 1. Check learned aliases (Feature 9) -> 0.97
    if mgr.is_alias(a.normalized, b.normalized) or (a.core and b.core and mgr.is_alias(a.core, b.core)):
        candidates.append((0.97, "सीखी गई समानता (Learned Alias)"))
    else:
        diff_a = [t for t in a.tokens if t not in b.tokens]
        diff_b = [t for t in b.tokens if t not in a.tokens]
        if len(diff_a) == 1 and len(diff_b) == 1:
            if mgr.is_alias(diff_a[0], diff_b[0]):
                candidates.append((0.97, "सीखी गई शब्द समानता (Token Alias)"))

    r_ratio = 0.0
    # 2. Space-free fuzzy ratio
    if a.space_free and b.space_free:
        r_ratio = fuzz.ratio(a.space_free, b.space_free) / 100.0
        candidates.append((r_ratio, "अक्षर समरूपता (Ratio)"))

        # 3. Jaro-Winkler on space-free (good for prefix matches)
        jw_score = jw.similarity(a.space_free, b.space_free)
        candidates.append((jw_score, "अग्रभाग समानता (Jaro-Winkler)"))

        # 4. Containment (one inside another, min length >= 3) -> 0.92
        min_len = min(len(a.space_free), len(b.space_free))
        if min_len >= 3 and (a.space_free in b.space_free or b.space_free in a.space_free):
            candidates.append((0.92, "समावेशन (Containment)"))

    # 5. Token set ratio on token lists
    if a.tokens and b.tokens:
        tok_str_a = " ".join(a.tokens)
        tok_str_b = " ".join(b.tokens)
        ts_ratio = fuzz.token_set_ratio(tok_str_a, tok_str_b) / 100.0
        candidates.append((ts_ratio, "शब्द क्रम / अतिरिक्त शब्द (Token Set)"))

    # 6. Core form comparison (stopwords stripped)
    if a.core and b.core:
        if a.core == b.core and len(a.core) >= 2:
            candidates.append((0.93, "मूल नाम समान (Core Exact)"))
        else:
            core_ratio = (fuzz.ratio(a.core, b.core) / 100.0) * 0.92
            candidates.append((core_ratio, "मूल नाम समरूपता (Core Ratio)"))

    # 7. Consonant skeleton
    if a.skeleton and b.skeleton:
        skel_ratio = (fuzz.ratio(a.skeleton, b.skeleton) / 100.0) * 0.90
        candidates.append((skel_ratio, "वर्ण ढाँचा समानता (Skeleton)"))

    # 8. Phonetic key equality -> 0.88 (when supported by character ratio >= 0.60)
    if a.phonetic_key and b.phonetic_key and a.phonetic_key == b.phonetic_key:
        if r_ratio >= 0.60:
            candidates.append((0.88, "ध्वनि समानता (Phonetic Key)"))
        else:
            candidates.append((round(r_ratio * 1.15, 4), "ध्वनि समानता (Phonetic Key)"))

    if not candidates:
        return 0.0, "अमिलान (No Match)"

    best_score, best_method = max(candidates, key=lambda x: x[0])
    best_score = max(0.0, min(1.0, best_score))
    return round(best_score, 4), best_method
