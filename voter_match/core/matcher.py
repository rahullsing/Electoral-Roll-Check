"""Global Optimal Matcher for Electoral Rolls.

Uses candidate blocking, record scoring, and Kuhn-Munkres (Hungarian)
optimal assignment via scipy.optimize.linear_sum_assignment to find the
globally optimal 1-to-1 match between voter lists without greedy bias.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
import numpy as np
from scipy.optimize import linear_sum_assignment

from voter_match.core.normalize import NormalizedName, normalize_hindi_name
from voter_match.core.scorer import RecordScorer, ColumnMapping, ScoreResult
from voter_match.core.blocking import CandidateBlocker
from voter_match.core.learning import AliasManager


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


@dataclass
class MatchSessionResult:
    """Overall result of matching run."""
    records_b: list[MatchRecordB]
    unmatched_a_indices: list[int]
    records_a: list[dict[str, Any]]
    stats: dict[str, int] = field(default_factory=dict)

    def recalculate_stats(self) -> None:
        """Update tier counts and unassigned A indices after BLO review decisions."""
        counts = {"मिला": 0, "जाँचें": 0, "लापता": 0, "केवल सूची A में": 0}
        assigned_a = set()
        for r in self.records_b:
            counts[r.tier] = counts.get(r.tier, 0) + 1
            if r.assigned_a_idx is not None and r.tier == "मिला":
                assigned_a.add(r.assigned_a_idx)

        unmatched = [i for i in range(len(self.records_a)) if i not in assigned_a]
        counts["केवल सूची A में"] = len(unmatched)
        self.unmatched_a_indices = unmatched
        self.stats = counts


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
            is_del_b = self.is_row_deleted(rec_b)
            if is_del_b:
                continue

            cache_b = {voter_col_b: norm_cache_b_voter[b_idx]}
            if rel_col_b and norm_cache_b_rel:
                cache_b[rel_col_b] = norm_cache_b_rel[b_idx]

            cands_a = b_candidates.get(b_idx, set())
            for a_idx in cands_a:
                rec_a = records_a[a_idx]
                if self.is_row_deleted(rec_a):
                    continue

                cache_a = {voter_col_a: norm_cache_a_voter[a_idx]}
                if rel_col_a and norm_cache_a_rel:
                    cache_a[rel_col_a] = norm_cache_a_rel[a_idx]

                score_res = self.scorer.score_pair(rec_a, rec_b, cache_a, cache_b)
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

        # Build sparse-to-dense cost matrix for assignment
        # Using cost = 1.0 - score for candidates >= 0.55, else large penalty cost 10.0
        # If n_b or n_a is 0, handle gracefully
        assigned_pairs: dict[int, int] = {}
        if n_b > 0 and n_a > 0:
            # We can construct cost matrix of shape (n_b, n_a)
            # Default unlinked cost = 2.0 (ensuring algorithm only picks candidates >= 0.55)
            cost_matrix = np.full((n_b, n_a), 2.0, dtype=np.float32)

            for (b_idx, a_idx), s_res in pair_scores.items():
                if s_res.score >= 0.55:
                    cost_matrix[b_idx, a_idx] = 1.0 - s_res.score

            row_ind, col_ind = linear_sum_assignment(cost_matrix)

            for r, c in zip(row_ind, col_ind):
                if cost_matrix[r, c] <= (1.0 - 0.55):  # Valid candidate score >= 0.55
                    assigned_pairs[r] = c

        # 5. Build output structures and classify tiers
        if progress_callback:
            progress_callback("अंतिम परिणाम एवं श्रेणी विभाजन (Categorizing)...", 95, 100)

        results_b: list[MatchRecordB] = []
        assigned_a_set = set(assigned_pairs.values())

        has_rel = bool(rel_col_a and rel_col_b)

        tier_counts = {"मिला": 0, "जाँचें": 0, "लापता": 0, "केवल सूची A में": 0}

        for b_idx in range(n_b):
            rec_b = records_b[b_idx]
            is_del = self.is_row_deleted(rec_b)

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
            tier = "लापता"
            if is_del:
                tier = "लापता"
            elif best_res and assigned_a is not None:
                s = best_res.score
                v_sim = best_res.voter_name_sim
                r_sim = best_res.relative_name_sim

                # 'मिला': score >= threshold_matched AND voter_sim >= min_voter AND (not has_rel or rel_sim >= min_rel)
                is_matched = (
                    s >= self.threshold_matched
                    and v_sim >= self.min_voter_sim
                    and (not has_rel or r_sim >= self.min_relative_sim)
                    and not best_res.is_sibling_guard_applied
                )

                if is_matched:
                    tier = "मिला"
                elif s >= self.threshold_review:
                    tier = "जाँचें"
                else:
                    tier = "लापता"
            elif top_3 and top_3[0].score_result.score >= self.threshold_review:
                tier = "जाँचें"
            else:
                tier = "लापता"

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
            )
            results_b.append(match_rec)

        # Unmatched A indices (exclude deleted)
        unmatched_a: list[int] = []
        for a_idx in range(n_a):
            if a_idx not in assigned_a_set and not self.is_row_deleted(records_a[a_idx]):
                unmatched_a.append(a_idx)

        tier_counts["केवल सूची A में"] = len(unmatched_a)

        if progress_callback:
            progress_callback("मिलान पूर्ण!", 100, 100)

        return MatchSessionResult(
            records_b=results_b,
            unmatched_a_indices=unmatched_a,
            records_a=records_a,
            stats=tier_counts,
        )
