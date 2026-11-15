"""Global Optimal Matcher for Electoral Rolls.

Uses candidate blocking, record scoring, and Kuhn-Munkres (Hungarian)
optimal assignment via scipy.optimize.linear_sum_assignment to find the
globally optimal 1-to-1 match between voter lists without greedy bias.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
from collections import defaultdict

from voter_match.core.normalize import NormalizedName, normalize_hindi_name
from voter_match.core.scorer import RecordScorer, ColumnMapping, ScoreResult, normalize_epic
from voter_match.core.blocking import CandidateBlocker
from voter_match.core.learning import AliasManager
from voter_match.core.assignment import solve_sparse_assignment

# Minimum score for a pair to be assignable 1-to-1
MIN_ASSIGN_SCORE = 0.55
# A pair the BLO explicitly rejected is capped here: still visible as a
# candidate (>= 0.50) but never auto-assigned (< MIN_ASSIGN_SCORE).
REJECTED_PAIR_CAP = 0.54


def classify_tier(
    best_res: ScoreResult | None,
    assigned: bool,
    top_score: float | None,
    is_deleted: bool,
    threshold_matched: float,
    threshold_review: float,
    min_voter_sim: float,
    min_relative_sim: float,
    has_relative: bool,
) -> str:
    """Single source of truth for the computer's tier verdict."""
    if is_deleted:
        return "लापता"
    if best_res is not None and assigned:
        is_matched = best_res.epic_match or (
            best_res.score >= threshold_matched
            and best_res.voter_name_sim >= min_voter_sim
            and (not has_relative or best_res.relative_name_sim >= min_relative_sim)
            and not best_res.is_sibling_guard_applied
            and not best_res.epic_mismatch
            and not best_res.age_conflict
        )
        if is_matched:
            return "मिला"
        if best_res.score >= threshold_review:
            return "जाँचें"
        # The assigned partner is weak, but a strong candidate exists (it went to
        # another List-B row, e.g. a duplicate entry): a human must decide.
        if top_score is not None and top_score >= threshold_review:
            return "जाँचें"
        return "लापता"
    if top_score is not None and top_score >= threshold_review:
        return "जाँचें"
    return "लापता"


@dataclass
class MatchCandidate:
    """A candidate match from List A for a List B record."""
    a_idx: int
    score_result: ScoreResult
    record_a: dict[str, Any]


@dataclass
class MatchRecordB:
    """Matching outcome for a single List B record."""
    b_idx: int
    record_b: dict[str, Any]
    assigned_a_idx: int | None = None
    assigned_record_a: dict[str, Any] | None = None
    best_score_result: ScoreResult | None = None
    top_candidates: list[MatchCandidate] = field(default_factory=list)
    tier: str = "लापता"  # 'मिला', 'जाँचें', 'लापता'
    user_decision: str | None = None  # Overridden in review: 'accepted_top1', 'accepted_top2', 'accepted_top3', 'missing'
    notes: str = ""                   # BLO Field remarks (e.g. मौके पर सत्यापित, मृतक, आदि)
    is_deleted: bool = False
    # Other List-B rows whose best candidate is the same List-A voter (possible
    # duplicate entries in List B, hidden by the 1-to-1 assignment otherwise)
    conflict_b_indices: list[int] = field(default_factory=list)
    # The computer's original verdict, kept unchanged by BLO review so that
    # accuracy can be measured against the BLO's decisions later.
    machine_tier: str | None = None
    machine_a_idx: int | None = None


@dataclass
class MatchSessionResult:
    """Overall result of matching run."""
    records_b: list[MatchRecordB]
    unmatched_a_indices: list[int]
    records_a: list[dict[str, Any]]
    stats: dict[str, int] = field(default_factory=dict)
    # List-A rows flagged deleted at matching time (never "only in A")
    excluded_a_indices: list[int] = field(default_factory=list)

    def recalculate_stats(self) -> None:
        """Update tier counts and unassigned A indices after BLO review decisions."""
        counts = {"मिला": 0, "जाँचें": 0, "लापता": 0, "केवल सूची A में": 0}
        # An A voter is accounted for while some B row holds it, unless the BLO
        # explicitly confirmed that B row as missing. This matches the definition
        # used at matching time, so recalculating without decisions is a no-op.
        assigned_a = set(self.excluded_a_indices)
        for r in self.records_b:
            counts[r.tier] = counts.get(r.tier, 0) + 1
            if r.assigned_a_idx is not None and not (r.user_decision and r.tier == "लापता"):
                assigned_a.add(r.assigned_a_idx)

        unmatched = [i for i in range(len(self.records_a)) if i not in assigned_a]
        counts["केवल सूची A में"] = len(unmatched)
        self.unmatched_a_indices = unmatched
        self.stats = counts

    def retier(
        self,
        threshold_matched: float,
        threshold_review: float,
        min_voter_sim: float,
        min_relative_sim: float,
        has_relative: bool = True,
    ) -> int:
        """Re-apply new thresholds to every record the BLO has not decided yet.

        Uses the stored machine assignment and scores, so no re-matching is
        needed. Returns the number of records whose tier changed.
        """
        changed = 0
        for r in self.records_b:
            if r.user_decision is not None:
                continue
            machine_a = r.machine_a_idx if r.machine_tier is not None else r.assigned_a_idx
            top = r.top_candidates[0].score_result.score if r.top_candidates else None
            tier = classify_tier(
                r.best_score_result, machine_a is not None, top, r.is_deleted,
                threshold_matched, threshold_review, min_voter_sim, min_relative_sim, has_relative,
            )
            r.machine_tier = tier
            if tier != r.tier:
                changed += 1
            r.tier = tier
            r.assigned_a_idx = machine_a
            r.assigned_record_a = self.records_a[machine_a] if machine_a is not None and machine_a < len(self.records_a) else None
        self.recalculate_stats()
        return changed


class ElectoralRollMatcher:
    """High-performance Hindi Electoral Roll Matcher."""

    def __init__(
        self,
        mappings: list[ColumnMapping],
        threshold_matched: float = 0.90,
        threshold_review: float = 0.72,
        min_voter_sim: float = 0.90,
        min_relative_sim: float = 0.80,
        match_within_ward: bool = False,
        deleted_col: str | None = None,
        deleted_values: set[str] | None = None,
        alias_manager: AliasManager | None = None,
    ):
        self.mappings = mappings
        self.threshold_matched = threshold_matched
        self.threshold_review = threshold_review
        self.min_voter_sim = min_voter_sim
        self.min_relative_sim = min_relative_sim
        self.match_within_ward = match_within_ward
        self.deleted_col = deleted_col
        self.deleted_values = deleted_values or {"deleted", "विलोपित", "हटाया", "मृत", "स्थानांतरित", "#", "q"}
        self.alias_manager = alias_manager
        self.scorer = RecordScorer(mappings, alias_manager=alias_manager)

    def is_row_deleted(self, record: dict[str, Any]) -> bool:
        """Check if record has deletion flag."""
        if not self.deleted_col:
            return False
        val = str(record.get(self.deleted_col, "")).strip().lower()
        return val in self.deleted_values

    def run_matching(
        self,
        records_a: list[dict[str, Any]],
        records_b: list[dict[str, Any]],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> MatchSessionResult:
        """Execute the full matching pipeline.

        Steps:
        1. Pre-normalize names in memory.
        2. Block candidates using phonetic, consonant, and RapidFuzz top-20.
        3. Score candidate pairs.
        4. Solve 1-to-1 global assignment using linear_sum_assignment.
        5. Assign tiers ('मिला', 'जाँचें', 'लापता') and detect unassigned in A.
        """
        n_a = len(records_a)
        n_b = len(records_b)

        voter_map = next((m for m in self.mappings if m.role == "voter_name" and m.is_active()), None)
        rel_map = next((m for m in self.mappings if m.role == "relative_name" and m.is_active()), None)
        ward_map = next((m for m in self.mappings if m.role == "ward" and m.is_active()), None)

        voter_col_a = voter_map.col_a if voter_map else ""
        voter_col_b = voter_map.col_b if voter_map else ""
        rel_col_a = rel_map.col_a if rel_map else None
        rel_col_b = rel_map.col_b if rel_map else None
        ward_col_a = ward_map.col_a if ward_map else None
        ward_col_b = ward_map.col_b if ward_map else None

        # 1. Pre-normalize all names
        if progress_callback:
            progress_callback("सूची A और B का नाम सामान्यीकरण (Normalizing)...", 5, 100)

        norm_cache_a_voter = [normalize_hindi_name(r.get(voter_col_a)) for r in records_a]
        norm_cache_b_voter = [normalize_hindi_name(r.get(voter_col_b)) for r in records_b]

        norm_cache_a_rel = (
            [normalize_hindi_name(r.get(rel_col_a)) for r in records_a]
            if rel_col_a
            else None
        )
        norm_cache_b_rel = (
            [normalize_hindi_name(r.get(rel_col_b)) for r in records_b]
            if rel_col_b
            else None
        )

        # Pre-compute per-row flags and identity keys once (not per candidate pair)
        deleted_a = [self.is_row_deleted(r) for r in records_a]
        deleted_b = [self.is_row_deleted(r) for r in records_b]

        def _keys(voter_cache, rel_cache):
            keys = []
            for i, v in enumerate(voter_cache):
                rel = rel_cache[i].normalized if rel_cache else ""
                keys.append(f"{v.normalized}|{rel}" if v.normalized else "")
            return keys

        mgr = self.alias_manager
        use_rejections = bool(mgr is not None and getattr(mgr, "rejections", None))
        keys_a = _keys(norm_cache_a_voter, norm_cache_a_rel) if use_rejections else []
        keys_b = _keys(norm_cache_b_voter, norm_cache_b_rel) if use_rejections else []

        # 2. Blocking
        if progress_callback:
            progress_callback("संभावित प्रत्याशियों का चयन (Blocking)...", 20, 100)

        blocker = CandidateBlocker(
            voter_col_a=voter_col_a,
            voter_col_b=voter_col_b,
            rel_col_a=rel_col_a,
            rel_col_b=rel_col_b,
            ward_col_a=ward_col_a,
            ward_col_b=ward_col_b,
            match_within_ward=self.match_within_ward,
            top_k_fuzzy=25,
        )

        b_candidates = blocker.generate_candidate_pairs(
            records_a,
            records_b,
            norm_cache_a_voter,
            norm_cache_b_voter,
            norm_cache_a_rel,
            norm_cache_b_rel,
        )

        # EPIC fast-path: an identical voter-ID number is always a candidate,
        # even when the names were typed very differently.
        epic_map = next((m for m in self.mappings if m.role == "epic" and m.is_active()), None)
        if epic_map:
            epic_index_a: dict[str, list[int]] = defaultdict(list)
            for a_idx, rec in enumerate(records_a):
                e = normalize_epic(rec.get(epic_map.col_a))
                if e:
                    epic_index_a[e].append(a_idx)
            for b_idx, rec in enumerate(records_b):
                e = normalize_epic(rec.get(epic_map.col_b))
                if e and e in epic_index_a:
                    b_candidates.setdefault(b_idx, set()).update(epic_index_a[e])

        # 3. Candidate Scoring
        if progress_callback:
            progress_callback("प्रत्याशियों का विस्तृत स्कोरिंग (Scoring)...", 45, 100)

        # Store candidate scores per B record: b_idx -> list of (a_idx, ScoreResult)
        all_candidate_scores: dict[int, list[tuple[int, ScoreResult]]] = {i: [] for i in range(n_b)}
        pair_scores: dict[tuple[int, int], ScoreResult] = {}

        total_b = max(1, n_b)
        step = max(1, total_b // 20)

        for b_idx in range(n_b):
            rec_b = records_b[b_idx]
            if deleted_b[b_idx]:
                continue

            cache_b = {voter_col_b: norm_cache_b_voter[b_idx]}
            if rel_col_b and norm_cache_b_rel:
                cache_b[rel_col_b] = norm_cache_b_rel[b_idx]

            cands_a = b_candidates.get(b_idx, set())
            key_b = keys_b[b_idx] if use_rejections else ""
            for a_idx in cands_a:
                if deleted_a[a_idx]:
                    continue
                rec_a = records_a[a_idx]

                cache_a = {voter_col_a: norm_cache_a_voter[a_idx]}
                if rel_col_a and norm_cache_a_rel:
                    cache_a[rel_col_a] = norm_cache_a_rel[a_idx]

                score_res = self.scorer.score_pair(rec_a, rec_b, cache_a, cache_b)
                if (
                    use_rejections
                    and key_b
                    and score_res.score > REJECTED_PAIR_CAP
                    and mgr.is_rejected(key_b, keys_a[a_idx])
                ):
                    score_res.score = REJECTED_PAIR_CAP
                    score_res.reasons.insert(0, "BLO द्वारा पूर्व में अस्वीकृत जोड़ी (Previously rejected)")
                if score_res.score >= 0.50:
                    all_candidate_scores[b_idx].append((a_idx, score_res))
                    pair_scores[(b_idx, a_idx)] = score_res

            # Sort candidates by score descending
            all_candidate_scores[b_idx].sort(key=lambda x: x[1].score, reverse=True)

            if progress_callback and b_idx % step == 0:
                pct = 45 + int(35 * (b_idx / total_b))
                progress_callback(f"स्कोरिंग प्रगति: {b_idx}/{n_b} मतदाता", pct, 100)

        # 4. Global Optimal Assignment (linear_sum_assignment)
        if progress_callback:
            progress_callback("सर्वोत्तम 1-to-1 मिलान निर्धारण (Optimal Assignment)...", 85, 100)

        # Solve per connected component of the sparse candidate graph: identical
        # optimum to a dense Hungarian solve, without the O(n_b * n_a) matrix.
        assigned_pairs: dict[int, int] = solve_sparse_assignment(
            ((b_idx, a_idx, s_res.score) for (b_idx, a_idx), s_res in pair_scores.items()),
            min_score=MIN_ASSIGN_SCORE,
        )

        # 5. Build output structures and classify tiers
        if progress_callback:
            progress_callback("अंतिम परिणाम एवं श्रेणी विभाजन (Categorizing)...", 95, 100)

        results_b: list[MatchRecordB] = []
        assigned_a_set = set(assigned_pairs.values())

        has_rel = bool(rel_col_a and rel_col_b)

        tier_counts = {"मिला": 0, "जाँचें": 0, "लापता": 0, "केवल सूची A में": 0}

        for b_idx in range(n_b):
            rec_b = records_b[b_idx]
            is_del = deleted_b[b_idx]

            cands_list = all_candidate_scores.get(b_idx, [])
            top_3 = [
                MatchCandidate(
                    a_idx=a_i,
                    score_result=s_res,
                    record_a=records_a[a_i],
                )
                for a_i, s_res in cands_list[:3]
            ]

            assigned_a = assigned_pairs.get(b_idx)
            best_res: ScoreResult | None = None
            assigned_rec_a: dict[str, Any] | None = None

            if assigned_a is not None:
                assigned_rec_a = records_a[assigned_a]
                best_res = pair_scores.get((b_idx, assigned_a))
                if not best_res:
                    best_res = self.scorer.score_pair(assigned_rec_a, rec_b)
            elif top_3:
                # If unassigned globally, record the highest candidate for reference
                best_res = top_3[0].score_result

            # Determine Tier
            tier = classify_tier(
                best_res,
                assigned_a is not None,
                top_3[0].score_result.score if top_3 else None,
                is_del,
                self.threshold_matched,
                self.threshold_review,
                self.min_voter_sim,
                self.min_relative_sim,
                has_rel,
            )

            tier_counts[tier] += 1

            match_rec = MatchRecordB(
                b_idx=b_idx,
                record_b=rec_b,
                assigned_a_idx=assigned_a,
                assigned_record_a=assigned_rec_a,
                best_score_result=best_res,
                top_candidates=top_3,
                tier=tier,
                is_deleted=is_del,
                machine_tier=tier,
                machine_a_idx=assigned_a,
            )
            results_b.append(match_rec)

        # Cross-list duplicate check: several B rows whose strongest candidate is
        # the same A voter. The 1-to-1 assignment gives A to only one of them,
        # silently hiding a likely duplicate entry in List B.
        # Only strong claims count (both names match well, not a sibling pattern),
        # otherwise common names like "रचना देवी" would flag different people.
        dup_score = max(0.90, self.threshold_matched)
        claims: dict[int, list[int]] = defaultdict(list)
        for rec in results_b:
            if rec.is_deleted or not rec.top_candidates:
                continue
            top = rec.top_candidates[0]
            sr = top.score_result
            strong = sr.epic_match or (
                sr.score >= dup_score
                and sr.voter_name_sim >= self.min_voter_sim
                and (not has_rel or sr.relative_name_sim >= self.min_relative_sim)
                and not sr.is_sibling_guard_applied
            )
            if strong:
                claims[top.a_idx].append(rec.b_idx)
        for b_list in claims.values():
            if len(b_list) > 1:
                for b_i in b_list:
                    results_b[b_i].conflict_b_indices = [o for o in b_list if o != b_i]

        # Unmatched A indices (exclude deleted)
        unmatched_a: list[int] = [
            a_idx for a_idx in range(n_a) if a_idx not in assigned_a_set and not deleted_a[a_idx]
        ]

        tier_counts["केवल सूची A में"] = len(unmatched_a)

        if progress_callback:
            progress_callback("मिलान पूर्ण!", 100, 100)

        return MatchSessionResult(
            records_b=results_b,
            unmatched_a_indices=unmatched_a,
            records_a=records_a,
            stats=tier_counts,
            excluded_a_indices=[i for i in range(n_a) if deleted_a[i]],
        )
