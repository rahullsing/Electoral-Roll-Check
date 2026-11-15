"""Duplicate Detection and Household / Family Clustering for Electoral Rolls.

Identifies internal duplicate voters (same person entered twice with slight
spelling, age, or EPIC variations) and clusters families by house number and lineage.
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from voter_match.core.normalize import normalize_hindi_name, NormalizedName
from voter_match.core.scorer import (
    RecordScorer,
    ColumnMapping,
    normalize_house_number,
)
from voter_match.core.blocking import CandidateBlocker


@dataclass
class DuplicateCluster:
    """Group of records representing the same individual entered multiple times."""
    cluster_id: int
    records: list[dict[str, Any]]
    indices: list[int]
    similarity_score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class HouseholdGroup:
    """Group of voters belonging to the same household / family unit."""
    house_no_clean: str
    original_house_no: str
    members: list[dict[str, Any]]
    member_count: int
    family_head_or_relative: str = ""


class DuplicateDetector:
    """Finds intra-list duplicate voters and household clusters."""

    def __init__(
        self,
        voter_col: str,
        rel_col: str | None = None,
        age_col: str | None = None,
        gender_col: str | None = None,
        house_col: str | None = None,
        score_threshold: float = 0.92,
        min_voter_sim: float = 0.90,
        min_relative_sim: float = 0.85,
        voter_only_min_sim: float = 0.97,
    ):
        self.voter_col = voter_col
        self.rel_col = rel_col
        self.age_col = age_col
        self.gender_col = gender_col
        self.house_col = house_col
        self.score_threshold = score_threshold
        self.min_voter_sim = min_voter_sim
        self.min_relative_sim = min_relative_sim
        self.voter_only_min_sim = voter_only_min_sim

        # Setup internal mappings
        mappings = [
            ColumnMapping(role="voter_name", col_a=voter_col, col_b=voter_col, importance="High"),
        ]
        if rel_col:
            mappings.append(ColumnMapping(role="relative_name", col_a=rel_col, col_b=rel_col, importance="High"))
        if age_col:
            mappings.append(ColumnMapping(role="age", col_a=age_col, col_b=age_col, importance="Medium", col_type="number"))
        if gender_col:
            mappings.append(ColumnMapping(role="gender", col_a=gender_col, col_b=gender_col, importance="Low", col_type="category"))
        if house_col:
            mappings.append(ColumnMapping(role="house_no", col_a=house_col, col_b=house_col, importance="Bonus only"))

        self.scorer = RecordScorer(mappings)

    def find_duplicates(
        self,
        records: list[dict[str, Any]],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> list[DuplicateCluster]:
        """Detect intra-list duplicates and group into clusters."""
        n = len(records)
        if n < 2:
            return []

        if progress_callback:
            progress_callback("मतदाता सूची का सामान्यीकरण...", 10, 100)

        norm_voter = [normalize_hindi_name(r.get(self.voter_col)) for r in records]
        norm_rel = (
            [normalize_hindi_name(r.get(self.rel_col)) for r in records]
            if self.rel_col
            else None
        )

        if progress_callback:
            progress_callback("संभावित डुप्लिकेट्स का चयन...", 30, 100)

        # Block candidates within list
        blocker = CandidateBlocker(
            voter_col_a=self.voter_col,
            voter_col_b=self.voter_col,
            rel_col_a=self.rel_col,
            rel_col_b=self.rel_col,
            top_k_fuzzy=15,
        )

        candidate_map = blocker.generate_candidate_pairs(
            records_a=records,
            records_b=records,
            norm_cache_a=norm_voter,
            norm_cache_b=norm_voter,
            rel_norm_cache_a=norm_rel,
            rel_norm_cache_b=norm_rel,
        )

        if progress_callback:
            progress_callback("डुप्लिकेट स्कोरिंग...", 60, 100)

        matched_pairs: list[tuple[int, int, float, list[str]]] = []
        seen_pairs: set[tuple[int, int]] = set()

        for b_idx, a_set in candidate_map.items():
            cache_b = {self.voter_col: norm_voter[b_idx]}
            if self.rel_col and norm_rel:
                cache_b[self.rel_col] = norm_rel[b_idx]

            for a_idx in a_set:
                if a_idx >= b_idx:
                    continue  # Compare each unordered pair once
                pair = (a_idx, b_idx)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                cache_a = {self.voter_col: norm_voter[a_idx]}
                if self.rel_col and norm_rel:
                    cache_a[self.rel_col] = norm_rel[a_idx]

                s_res = self.scorer.score_pair(records[a_idx], records[b_idx], cache_a, cache_b)
                if self.is_duplicate_pair(s_res, records[a_idx], records[b_idx]):
                    matched_pairs.append((a_idx, b_idx, s_res.score, s_res.reasons))

        # Complete-linkage grouping: strongest pairs first, and two groups are
        # merged only if EVERY member of one is a duplicate of every member of
        # the other. (Plain union-find chained A~B, B~C into one group even when
        # A and C were clearly different people.)
        dup_pairs = {(a, b) for a, b, _, _ in matched_pairs}
        group_of: dict[int, list[int]] = {}
        for a_i, b_i, _sc, _r in sorted(matched_pairs, key=lambda p: -p[2]):
            ga = group_of.get(a_i, [a_i])
            gb = group_of.get(b_i, [b_i])
            if ga is gb:
                continue
            if all((min(x, y), max(x, y)) in dup_pairs for x in ga for y in gb):
                merged = ga + gb
                for idx in merged:
                    group_of[idx] = merged
        groups: dict[int, list[int]] = {}
        for members in group_of.values():
            groups[id(members)] = sorted(members)

        # Create DuplicateCluster objects for groups of size >= 2
        clusters: list[DuplicateCluster] = []
        cid = 1
        for root, member_indices in groups.items():
            if len(member_indices) >= 2:
                # Find max score and reasons among members
                cluster_reasons = []
                max_score = 0.0
                for a_i, b_i, sc, r_list in matched_pairs:
                    if a_i in member_indices and b_i in member_indices:
                        if sc > max_score:
                            max_score = sc
                            cluster_reasons = r_list

                if max_score == 0.0:
                    max_score = self.score_threshold
                    cluster_reasons = ["समान नाम एवं विवरण"]

                clusters.append(
                    DuplicateCluster(
                        cluster_id=cid,
                        records=[records[idx] for idx in member_indices],
                        indices=member_indices,
                        similarity_score=round(max_score, 4),
                        reasons=cluster_reasons,
                    )
                )
                cid += 1

        if progress_callback:
            progress_callback(f"डुप्लिकेट जाँच पूर्ण ({len(clusters)} समूह प्राप्त)!", 100, 100)

        # Sort clusters by size descending
        clusters.sort(key=lambda c: len(c.records), reverse=True)
        return clusters

    def _same_age(self, rec_a, rec_b, max_diff: int = 1) -> bool:
        from voter_match.core.scorer import parse_age

        if not self.age_col or rec_a is None or rec_b is None:
            return False
        a, b = parse_age(rec_a.get(self.age_col)), parse_age(rec_b.get(self.age_col))
        return a is not None and b is not None and abs(a - b) <= max_diff

    def is_duplicate_pair(self, s_res, rec_a=None, rec_b=None) -> bool:
        """Strict rule: same person entered twice, not a namesake or sibling."""
        if s_res.is_sibling_guard_applied or getattr(s_res, "age_conflict", False):
            return False
        if s_res.score < self.score_threshold:
            return False
        if self.rel_col:
            if s_res.voter_name_sim >= self.min_voter_sim and s_res.relative_name_sim >= self.min_relative_sim:
                return True
            # Typing slip in the voter name (राकेश / राकश) with an identical
            # relative and the same age: still the same person.
            return (
                s_res.voter_name_sim >= 0.85
                and s_res.relative_name_sim >= 0.95
                and self._same_age(rec_a, rec_b)
            )
        # Without a relative column a near-exact name is required
        return s_res.voter_name_sim >= self.voter_only_min_sim

    @staticmethod
    def group_by_household(
        records: list[dict[str, Any]],
        house_col: str,
        rel_col: str | None = None,
    ) -> list[HouseholdGroup]:
        """Group records into family / household units based on House Number."""
        house_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        orig_house_names: dict[str, str] = {}

        for rec in records:
            raw_h = rec.get(house_col, "")
            clean_h = normalize_house_number(raw_h)
            if clean_h:
                house_groups[clean_h].append(rec)
                if clean_h not in orig_house_names:
                    orig_house_names[clean_h] = str(raw_h).strip()

        result: list[HouseholdGroup] = []
        for clean_h, members in house_groups.items():
            # Identify most frequent relative name as presumptive head/lineage
            head_name = ""
            if rel_col:
                rel_counts: dict[str, int] = defaultdict(int)
                for m in members:
                    r_val = str(m.get(rel_col, "")).strip()
                    if r_val:
                        rel_counts[r_val] += 1
                if rel_counts:
                    head_name = max(rel_counts.items(), key=lambda x: x[1])[0]

            result.append(
                HouseholdGroup(
                    house_no_clean=clean_h,
                    original_house_no=orig_house_names.get(clean_h, clean_h),
                    members=members,
                    member_count=len(members),
                    family_head_or_relative=head_name,
                )
            )

        # Sort by family size descending
        result.sort(key=lambda g: g.member_count, reverse=True)
        return result
