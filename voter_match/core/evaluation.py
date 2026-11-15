"""Accuracy measurement and threshold tuning from BLO review decisions.

Every record a BLO reviews by hand becomes a labelled example:
  * accepted candidate k  -> true match with a specific List-A voter
  * marked missing        -> true non-match
(Bulk auto-approvals are machine decisions, so they are not used as labels.)

Using those labels we replay the computer's original verdict under any
threshold pair and report how often it would have been right, then search
for the thresholds that minimise the BLO's total effort:
    cost = ERROR_COST * (wrong automatic decisions) + (records sent to review)
"""

from __future__ import annotations
from dataclasses import dataclass

from voter_match.core.matcher import MatchRecordB, MatchSessionResult

# One wrong automatic decision (a wrong Form 6/7 or a wrong "matched") costs
# far more than one extra record the BLO has to look at.
ERROR_COST = 5.0
MIN_LABELS_FOR_SUGGESTION = 20


@dataclass
class Label:
    accepted: bool              # BLO says this B row is someone in List A
    chosen_a_idx: int | None    # which A row (when accepted)
    machine_a_idx: int | None   # A row the computer proposed
    score: float                # computer's score for that proposal
    voter_sim: float
    relative_sim: float
    sibling: bool
    epic_match: bool
    epic_mismatch: bool
    age_conflict: bool = False


@dataclass
class EvalReport:
    labels: int
    auto_matched: int           # computer would mark "मिला"
    auto_correct: int           # ... and BLO agreed (same A voter)
    auto_wrong: int
    review: int                 # computer would send to "जाँचें"
    auto_missing: int           # computer would mark "लापता"
    missing_wrong: int          # ... but BLO found the voter in List A
    true_matches: int
    precision: float            # auto_correct / auto_matched
    recall: float               # auto_correct / true_matches
    cost: float
    thr_matched: float
    thr_review: float


def _is_manual(decision: str | None) -> bool:
    return bool(decision) and not decision.startswith("स्वतः")


def extract_labels(records: list[MatchRecordB]) -> list[Label]:
    labels: list[Label] = []
    for r in records:
        if r.is_deleted or not _is_manual(r.user_decision):
            continue
        accepted = not r.user_decision.startswith("लापता")
        machine_a = r.machine_a_idx
        sr = r.best_score_result
        if machine_a is None and r.top_candidates:
            # Unassigned by the 1-to-1 solver: the computer's best guess is candidate 1
            machine_a = r.top_candidates[0].a_idx
            sr = r.top_candidates[0].score_result
        if sr is None:
            labels.append(Label(accepted, r.assigned_a_idx if accepted else None, None,
                                0.0, 0.0, 0.0, False, False, False))
            continue
        labels.append(Label(
            accepted=accepted,
            chosen_a_idx=r.assigned_a_idx if accepted else None,
            machine_a_idx=machine_a,
            score=sr.score,
            voter_sim=sr.voter_name_sim,
            relative_sim=sr.relative_name_sim,
            sibling=sr.is_sibling_guard_applied,
            epic_match=sr.epic_match,
            epic_mismatch=sr.epic_mismatch,
            age_conflict=sr.age_conflict,
        ))
    return labels


def evaluate(
    labels: list[Label],
    thr_matched: float,
    thr_review: float,
    min_voter_sim: float = 0.90,
    min_relative_sim: float = 0.80,
    has_relative: bool = True,
) -> EvalReport:
    auto_m = auto_ok = review = auto_miss = miss_wrong = 0
    true_matches = sum(1 for lb in labels if lb.accepted)
    for lb in labels:
        is_match = lb.machine_a_idx is not None and (lb.epic_match or (
            lb.score >= thr_matched
            and lb.voter_sim >= min_voter_sim
            and (not has_relative or lb.relative_sim >= min_relative_sim)
            and not lb.sibling
            and not lb.epic_mismatch
            and not lb.age_conflict
        ))
        if is_match:
            auto_m += 1
            if lb.accepted and lb.chosen_a_idx == lb.machine_a_idx:
                auto_ok += 1
        elif lb.machine_a_idx is not None and lb.score >= thr_review:
            review += 1
        else:
            auto_miss += 1
            if lb.accepted:
                miss_wrong += 1
    auto_wrong = auto_m - auto_ok
    return EvalReport(
        labels=len(labels),
        auto_matched=auto_m,
        auto_correct=auto_ok,
        auto_wrong=auto_wrong,
        review=review,
        auto_missing=auto_miss,
        missing_wrong=miss_wrong,
        true_matches=true_matches,
        precision=(auto_ok / auto_m) if auto_m else 1.0,
        recall=(auto_ok / true_matches) if true_matches else 1.0,
        cost=ERROR_COST * (auto_wrong + miss_wrong) + review,
        thr_matched=thr_matched,
        thr_review=thr_review,
    )


def suggest_thresholds(
    labels: list[Label],
    current_matched: float,
    current_review: float,
    min_voter_sim: float = 0.90,
    min_relative_sim: float = 0.80,
    has_relative: bool = True,
) -> EvalReport | None:
    """Grid-search (matched, review) thresholds minimising BLO effort.

    Ties prefer the pair closest to the current settings (stability).
    Returns None when there are too few labelled records to be trustworthy.
    """
    if len(labels) < MIN_LABELS_FOR_SUGGESTION:
        return None
    best: EvalReport | None = None
    best_key = None
    for m100 in range(80, 100):
        m = m100 / 100
        for r100 in range(55, min(m100, 86)):  # review slider allows up to 85%
            r = r100 / 100
            rep = evaluate(labels, m, r, min_voter_sim, min_relative_sim, has_relative)
            key = (rep.cost, abs(m - current_matched) + abs(r - current_review))
            if best_key is None or key < best_key:
                best, best_key = rep, key
    return best


def session_report(
    result: MatchSessionResult,
    thr_matched: float,
    thr_review: float,
    min_voter_sim: float = 0.90,
    min_relative_sim: float = 0.80,
    has_relative: bool = True,
) -> tuple[EvalReport, EvalReport | None]:
    labels = extract_labels(result.records_b)
    current = evaluate(labels, thr_matched, thr_review, min_voter_sim, min_relative_sim, has_relative)
    suggestion = suggest_thresholds(labels, thr_matched, thr_review, min_voter_sim, min_relative_sim, has_relative)
    return current, suggestion
