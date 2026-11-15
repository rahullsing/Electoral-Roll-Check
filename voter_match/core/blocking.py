"""Blocking and Candidate Pair Generation.

Reduces O(n*m) complexity to sub-quadratic scale (5,000 x 5,000 in < 60s)
using multi-index indexing: phonetic key prefix, consonant dual-anchoring,
and high-speed RapidFuzz C-extension candidate extraction.
"""

from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable

import numpy as np
import rapidfuzz.process as rf_process
import rapidfuzz.fuzz as rf_fuzz

from voter_match.core.normalize import NormalizedName, normalize_hindi_name
from voter_match.core.phonetic import get_first_consonant


class CandidateBlocker:
    """Generates candidate match pairs between List A and List B."""

    def __init__(
        self,
        voter_col_a: str,
        voter_col_b: str,
        rel_col_a: str | None = None,
        rel_col_b: str | None = None,
        ward_col_a: str | None = None,
        ward_col_b: str | None = None,
        match_within_ward: bool = False,
        top_k_fuzzy: int = 20,
    ):
        self.voter_col_a = voter_col_a
        self.voter_col_b = voter_col_b
        self.rel_col_a = rel_col_a
        self.rel_col_b = rel_col_b
        self.ward_col_a = ward_col_a
        self.ward_col_b = ward_col_b
        self.match_within_ward = match_within_ward
        self.top_k_fuzzy = top_k_fuzzy

    def generate_candidate_pairs(
        self,
        records_a: list[dict[str, Any]],
        records_b: list[dict[str, Any]],
        norm_cache_a: list[NormalizedName],
        norm_cache_b: list[NormalizedName],
        rel_norm_cache_a: list[NormalizedName] | None = None,
        rel_norm_cache_b: list[NormalizedName] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[int, set[int]]:
        """Generate candidate pairs: mapping b_idx -> set of candidate a_idx.

        Candidate criteria (Feature 7):
        1. Same phonetic key prefix (first 3 chars) of voter name.
        2. Same first consonant of voter name AND relative name.
        3. RapidFuzz process.extract top-20 on space-free voter name (cutoff 45).
        4. Ward partition when match_within_ward is enabled.
        """
        n_a = len(records_a)
        n_b = len(records_b)

        # Handle ward partitioning
        if self.match_within_ward and self.ward_col_a and self.ward_col_b:
            ward_buckets_a: dict[str, list[int]] = defaultdict(list)
            for i, rec in enumerate(records_a):
                w = str(rec.get(self.ward_col_a, "")).strip().lower()
                ward_buckets_a[w].append(i)

            ward_buckets_b: dict[str, list[int]] = defaultdict(list)
            for j, rec in enumerate(records_b):
                w = str(rec.get(self.ward_col_b, "")).strip().lower()
                ward_buckets_b[w].append(j)

            b_candidates: dict[int, set[int]] = defaultdict(set)
            all_wards = set(ward_buckets_b.keys())
            total_b = n_b
            done_b = 0

            for ward, b_indices in ward_buckets_b.items():
                a_indices = ward_buckets_a.get(ward, [])
                # If ward not found in A or empty, fallback to searching all A
                active_a = a_indices if a_indices else list(range(n_a))
                sub_res = self._block_subset(
                    active_a,
                    b_indices,
                    records_a,
                    records_b,
                    norm_cache_a,
                    norm_cache_b,
                    rel_norm_cache_a,
                    rel_norm_cache_b,
                )
                b_candidates.update(sub_res)
                done_b += len(b_indices)
                if progress_callback:
                    progress_callback(done_b, total_b)
            return b_candidates

        # Global blocking across all records
        all_a_idx = list(range(n_a))
        all_b_idx = list(range(n_b))
        return self._block_subset(
            all_a_idx,
            all_b_idx,
            records_a,
            records_b,
            norm_cache_a,
            norm_cache_b,
            rel_norm_cache_a,
            rel_norm_cache_b,
            progress_callback,
        )

    def _block_subset(
        self,
        a_indices: list[int],
        b_indices: list[int],
        records_a: list[dict[str, Any]],
        records_b: list[dict[str, Any]],
        norm_cache_a: list[NormalizedName],
        norm_cache_b: list[NormalizedName],
        rel_norm_cache_a: list[NormalizedName] | None = None,
        rel_norm_cache_b: list[NormalizedName] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[int, set[int]]:
        """Block a subset of indices."""
        b_candidates: dict[int, set[int]] = {b_i: set() for b_i in b_indices}
        if not a_indices or not b_indices:
            return b_candidates

        # 1. Build index for Phonetic Key Prefix (first 3 chars)
        phonetic_index_a: dict[str, list[int]] = defaultdict(list)
        # 2. Build index for Dual Consonants (first cons of voter + first cons of rel)
        dual_cons_index_a: dict[tuple[str, str], list[int]] = defaultdict(list)
        # 3. Space-free string dictionary for RapidFuzz
        a_strings: dict[int, str] = {}

        for a_idx in a_indices:
            norm_voter = norm_cache_a[a_idx]
            pkey = norm_voter.phonetic_key[:3]
            if pkey:
                phonetic_index_a[pkey].append(a_idx)

            voter_cons = get_first_consonant(norm_voter.clean)
            rel_cons = ""
            if rel_norm_cache_a and a_idx < len(rel_norm_cache_a):
                rel_cons = get_first_consonant(rel_norm_cache_a[a_idx].clean)
            if voter_cons and rel_cons:
                dual_cons_index_a[(voter_cons, rel_cons)].append(a_idx)

            a_strings[a_idx] = norm_voter.space_free or norm_voter.clean

        total_b = len(b_indices)
        step = max(1, total_b // 50)

        for count, b_idx in enumerate(b_indices):
            cands = b_candidates[b_idx]
            norm_b = norm_cache_b[b_idx]

            # Signal 1: Phonetic prefix (first 3)
            pkey_b = norm_b.phonetic_key[:3]
            if pkey_b in phonetic_index_a:
                cands.update(phonetic_index_a[pkey_b])

            # Signal 2: Dual consonants (voter + relative)
            v_cons_b = get_first_consonant(norm_b.clean)
            r_cons_b = ""
            if rel_norm_cache_b and b_idx < len(rel_norm_cache_b):
                r_cons_b = get_first_consonant(rel_norm_cache_b[b_idx].clean)
            if v_cons_b and r_cons_b:
                pair = (v_cons_b, r_cons_b)
                if pair in dual_cons_index_a:
                    cands.update(dual_cons_index_a[pair])

            if progress_callback and (count % step == 0 or count == total_b - 1):
                progress_callback(count + 1, total_b)

        # Signal 3: RapidFuzz top-k, vectorised. A single multi-threaded C++
        # cdist call per chunk replaces one Python-level extract() per row.
        self._add_fuzzy_topk(b_indices, norm_cache_b, a_strings, b_candidates)

        return b_candidates

    def _add_fuzzy_topk(
        self,
        b_indices: list[int],
        norm_cache_b: list[NormalizedName],
        a_strings: dict[int, str],
        b_candidates: dict[int, set[int]],
        chunk_size: int = 512,
        score_cutoff: float = 45.0,
    ) -> None:
        """Add the top-k most similar A rows (fuzz.ratio >= cutoff) for every B row."""
        a_ids = [i for i, s in a_strings.items() if s]
        if not a_ids:
            return
        a_strs = [a_strings[i] for i in a_ids]
        a_ids_arr = np.asarray(a_ids, dtype=np.int64)

        queries = [
            (b_idx, norm_cache_b[b_idx].space_free or norm_cache_b[b_idx].clean)
            for b_idx in b_indices
        ]
        queries = [(b, q) for b, q in queries if q]
        if not queries:
            return

        k = min(self.top_k_fuzzy, len(a_ids))
        ties_empty = np.empty(0, dtype=np.int64)
        for start in range(0, len(queries), chunk_size):
            chunk = queries[start:start + chunk_size]
            mat = rf_process.cdist(
                [q for _, q in chunk],
                a_strs,
                scorer=rf_fuzz.ratio,
                score_cutoff=score_cutoff,
                dtype=np.float32,
                workers=-1,
            )
            # k-th best score per row (O(n) partition instead of a full sort)
            if k < len(a_ids):
                kth = -np.partition(-mat, k - 1, axis=1)[:, k - 1]
            else:
                kth = np.zeros(len(chunk), dtype=np.float32)
            for row, (b_idx, _) in enumerate(chunk):
                scores = mat[row]
                thr = max(float(kth[row]), score_cutoff)
                above = np.flatnonzero(scores > thr)
                # Ties at the k-th score are broken by lowest A index, exactly
                # like rapidfuzz.process.extract(limit=k) did row by row.
                need = k - above.size
                if need > 0:
                    ties = np.flatnonzero(scores == thr)[:need] if thr >= score_cutoff else ties_empty
                    picked = np.concatenate((above, ties))
                else:
                    picked = above
                if picked.size:
                    b_candidates[b_idx].update(a_ids_arr[picked].tolist())
