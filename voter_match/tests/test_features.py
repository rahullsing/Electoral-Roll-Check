"""Tests for the performance work and the new BLO features."""

from __future__ import annotations
import gzip
import json
import re
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import rapidfuzz.fuzz as rf_fuzz
import rapidfuzz.process as rf_process
from scipy.optimize import linear_sum_assignment
from PySide6.QtWidgets import QLabel

from voter_match.core.assignment import solve_sparse_assignment
from voter_match.core.blocking import CandidateBlocker
from voter_match.core.evaluation import evaluate, extract_labels, suggest_thresholds
from voter_match.core.forms import classify_form_actions, export_form_actions_excel, export_form_actions_pdf
from voter_match.core.learning import AliasManager, make_record_key
from voter_match.core.matcher import ElectoralRollMatcher, REJECTED_PAIR_CAP
from voter_match.core.normalize import normalize_hindi_name
from voter_match.core.scorer import ColumnMapping, RecordScorer, normalize_epic
from voter_match.core.similarity import name_similarity
from voter_match.core.transliterate import devanagari_to_roman, transliterate_roman_to_devanagari
from voter_match.storage.session_manager import (
    SavedSessionData,
    SessionManager,
    dict_to_session_data,
    session_data_to_dict,
)
from voter_match.storage.db import StorageManager

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = PROJECT_ROOT / "sample_data"


def _mappings(extra: list[ColumnMapping] | None = None) -> list[ColumnMapping]:
    m = [
        ColumnMapping(role="serial_no", col_a="क्र", col_b="क्र", importance="Paper Ref"),
        ColumnMapping(role="voter_name", col_a="नाम", col_b="नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता", col_b="पिता", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium", col_type="number"),
    ]
    return m + (extra or [])


def _rec(i, name, rel, age=30, **kw):
    d = {"क्र": i, "नाम": name, "पिता": rel, "आयु": age}
    d.update(kw)
    return d


# ---------------------------------------------------------------- performance

def test_sparse_assignment_matches_dense_optimum():
    """Per-component solve == dense solve of the confidence objective."""
    rng = np.random.default_rng(42)
    for _ in range(150):
        nb, na = int(rng.integers(3, 40)), int(rng.integers(3, 40))
        edges = {}
        for _ in range(int(rng.integers(1, nb * 3))):
            edges[(int(rng.integers(nb)), int(rng.integers(na)))] = float(np.round(rng.uniform(0.5, 1.0), 4))
        dense = np.zeros((nb, na))
        for (b, a), s_ in edges.items():
            if s_ >= 0.55:
                dense[b, a] = -(s_ - 0.55 + 1e-6)
        r, c = linear_sum_assignment(dense)
        d_pairs = {int(x): int(y) for x, y in zip(r, c) if dense[x, y] < 0}
        sp = solve_sparse_assignment(((b, a, s_) for (b, a), s_ in edges.items()), 0.55)

        def objective(p):
            return sum(edges[(b, a)] - 0.55 for b, a in p.items())

        assert objective(sp) == pytest.approx(objective(d_pairs), abs=1e-4)
        assert len(set(sp.values())) == len(sp)  # strictly 1-to-1


def test_assignment_never_breaks_a_strong_match_for_weak_ones():
    """Regression: the old objective maximised the NUMBER of pairs, so it gave
    away a 100% match to form two weak pairs, marking a real match missing."""
    edges = [(0, 0, 1.00), (0, 1, 0.60), (1, 0, 0.56)]
    assert solve_sparse_assignment(edges, 0.55) == {0: 0}


def test_strong_candidate_taken_elsewhere_goes_to_review_not_missing():
    from voter_match.core.matcher import classify_tier
    from voter_match.core.scorer import ScoreResult

    weak = ScoreResult(score=0.60, voter_name_sim=0.6, relative_name_sim=0.6)
    tier = classify_tier(weak, True, 0.98, False, 0.90, 0.72, 0.90, 0.80, True)
    assert tier == "जाँचें"


def test_big_age_gap_is_never_auto_matched():
    m = _mappings()
    a = [_rec(1, "संजय", "ईश्वर दयाल", 64)]
    b = [_rec(1, "संजय", "ईश्वर दयाल", 36)]
    res = ElectoralRollMatcher(m, alias_manager=AliasManager()).run_matching(a, b)
    rec = res.records_b[0]
    assert rec.best_score_result.age_conflict
    assert rec.tier == "जाँचें"
    # a small gap within tolerance still matches automatically
    b2 = [_rec(1, "संजय", "ईश्वर दयाल", 65)]
    res2 = ElectoralRollMatcher(m, alias_manager=AliasManager()).run_matching(a, b2)
    assert res2.records_b[0].tier == "मिला"


def test_vectorized_blocking_equals_rowwise_extract():
    rng = random.Random(3)
    syll = ["रा", "म", "सु", "नी", "ल", "कु", "मा", "र", "शी", "ला", "दे", "वी", "प्र", "सा", "द"]
    names_a = ["".join(rng.choice(syll) for _ in range(rng.randint(2, 5))) for _ in range(300)]
    names_b = ["".join(rng.choice(syll) for _ in range(rng.randint(2, 5))) for _ in range(200)]
    na = [normalize_hindi_name(x) for x in names_a]
    nb = [normalize_hindi_name(x) for x in names_b]
    blk = CandidateBlocker("v", "v", top_k_fuzzy=25)
    a_strings = {i: n.space_free or n.clean for i, n in enumerate(na)}
    got = {b: set() for b in range(len(nb))}
    blk._add_fuzzy_topk(list(range(len(nb))), nb, a_strings, got, chunk_size=64)
    for b, n in enumerate(nb):
        ref = rf_process.extract(n.space_free or n.clean, a_strings, scorer=rf_fuzz.ratio, limit=25, score_cutoff=45.0)
        assert got[b] == {item[2] for item in ref}


def test_normalize_cache_returns_same_object():
    a = normalize_hindi_name("राम प्रसाद")
    b = normalize_hindi_name("राम प्रसाद")
    assert a is b


@pytest.mark.skipif(os.environ.get("VOTER_MATCH_SKIP_BENCH") == "1", reason="benchmark disabled")
def test_benchmark_large_roll_speed():
    """Regression guard: 3,000 x 3,000 synthetic rolls must match well under a minute."""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import benchmark  # noqa: E402

    n = int(os.environ.get("VOTER_MATCH_BENCH_N", "3000"))
    elapsed, stats = benchmark.run(n)
    assert stats["मिला"] > 0.7 * n
    assert elapsed < 60.0, f"{n}x{n} matching took {elapsed:.1f}s"


# ---------------------------------------------------------------- matching features

def test_transliteration_cross_script_match():
    assert transliterate_roman_to_devanagari("Ram Prasad") == "राम प्रसाद"
    sim, _ = name_similarity(normalize_hindi_name("Sunil Kumar"), normalize_hindi_name("सुनील कुमार"))
    assert sim >= 0.95
    sim2, _ = name_similarity(normalize_hindi_name("Omprakash"), normalize_hindi_name("ओमप्रकाश"))
    assert sim2 >= 0.85
    assert devanagari_to_roman("राम प्रसाद").lower().startswith("raam")


def test_epic_exact_match_overrides_name_typos():
    epic = ColumnMapping(role="epic", col_a="epic", col_b="epic", importance="High", col_type="text")
    a = [_rec(1, "जगदीश नारायण", "बद्री प्रसाद", 40, epic="ABC1234567"),
         _rec(2, "सुनील कुमार", "राम सेवक", 35, epic="XYZ7654321")]
    b = [_rec(1, "जगदिस नरायन", "बदरी परसाद", 41, epic="abc-1234567"),  # heavy typos, same EPIC
         _rec(2, "सुनील कुमार", "राम सेवक", 35, epic="XYZ0000000")]     # same names, different EPIC
    res = ElectoralRollMatcher(_mappings([epic]), alias_manager=AliasManager()).run_matching(a, b)
    assert res.records_b[0].assigned_a_idx == 0
    assert res.records_b[0].tier == "मिला"
    assert res.records_b[0].best_score_result.epic_match
    assert res.records_b[1].tier != "मिला"  # EPIC mismatch must go to review
    assert res.records_b[1].best_score_result.epic_mismatch
    assert normalize_epic("abc 123456O") == "ABC1234560"


def test_age_year_offset_between_rolls():
    m_plain = _mappings()
    m_off = _mappings()
    m_off[3] = ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium",
                             col_type="number", tolerance=1, year_offset=5)
    m_plain[3] = ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium",
                               col_type="number", tolerance=1)
    a, b = _rec(1, "राम", "श्याम", 40), _rec(1, "राम", "श्याम", 45)
    s_plain = RecordScorer(m_plain).score_pair(a, b)
    s_off = RecordScorer(m_off).score_pair(a, b)
    assert s_off.score > s_plain.score
    assert any("समायोजित" in r for r in s_off.reasons)


def test_rejected_pair_is_never_auto_assigned():
    mgr = AliasManager()
    a = [_rec(1, "रमेश कुमार", "सुरेश", 30)]
    b = [_rec(1, "रमेश कुमार", "सुरेश", 30)]
    first = ElectoralRollMatcher(_mappings(), alias_manager=mgr).run_matching(a, b)
    assert first.records_b[0].assigned_a_idx == 0
    mgr.add_rejection(make_record_key("रमेश कुमार", "सुरेश"), make_record_key("रमेश कुमार", "सुरेश"))
    second = ElectoralRollMatcher(_mappings(), alias_manager=mgr).run_matching(a, b)
    rec = second.records_b[0]
    assert rec.assigned_a_idx is None
    assert rec.top_candidates and rec.top_candidates[0].score_result.score == REJECTED_PAIR_CAP


def test_duplicate_b_rows_are_flagged():
    a = [_rec(1, "मोहन लाल", "गोपाल", 50), _rec(2, "सीता देवी", "मोहन लाल", 45)]
    b = [_rec(1, "मोहन लाल", "गोपाल", 50), _rec(2, "मोहन लाल", "गोपाल", 50), _rec(3, "सीता देवी", "मोहन लाल", 45)]
    res = ElectoralRollMatcher(_mappings(), alias_manager=AliasManager()).run_matching(a, b)
    assert res.records_b[0].conflict_b_indices == [1]
    assert res.records_b[1].conflict_b_indices == [0]
    assert res.records_b[2].conflict_b_indices == []


# ---------------------------------------------------------------- session format

def _small_session():
    a = [_rec(i, n, r) for i, (n, r) in enumerate([("राम", "श्याम"), ("सीता", "राम"), ("गीता", "हरि")])]
    b = [_rec(i, n, r) for i, (n, r) in enumerate([("राम", "श्याम"), ("सिता", "राम"), ("नया", "व्यक्ति")])]
    res = ElectoralRollMatcher(_mappings(), alias_manager=AliasManager()).run_matching(a, b)
    return SavedSessionData(session_id="t", title="t", file_a="", file_b="", records_a=a, records_b=b,
                            mappings=_mappings(), session_result=res)


def test_session_v2_dedupes_records_and_roundtrips():
    data = _small_session()
    d = session_data_to_dict(data)
    assert d["version"] == "2.0"
    sr = d["session_result"]
    assert sr.get("records_a_ref") == "top" and "records_a" not in sr
    for rb in sr["records_b"]:
        assert "record_b" not in rb
        for c in rb["top_candidates"]:
            assert "record_a" not in c

    back = dict_to_session_data(json.loads(json.dumps(d, ensure_ascii=False)))
    assert back.session_result.records_a is back.records_a
    for orig, new in zip(data.session_result.records_b, back.session_result.records_b):
        assert new.record_b == orig.record_b
        assert new.assigned_a_idx == orig.assigned_a_idx
        assert new.assigned_record_a == orig.assigned_record_a
        assert [c.a_idx for c in new.top_candidates] == [c.a_idx for c in orig.top_candidates]
        assert [c.record_a for c in new.top_candidates] == [c.record_a for c in orig.top_candidates]
        assert new.machine_tier == orig.machine_tier


def test_vsession_file_is_gzipped_and_legacy_v1_loads(tmp_path):
    sm = SessionManager(StorageManager(tmp_path / "s.db"))
    data = _small_session()
    path = tmp_path / "x.vsession"
    sm.export_session_file(data, path)
    assert path.read_bytes()[:2] == b"\x1f\x8b"
    loaded = sm.import_session_file(path)
    assert loaded.session_result.stats == data.session_result.stats

    # Legacy v1: plain JSON with full record copies everywhere
    legacy = session_data_to_dict(data)
    sr = legacy["session_result"]
    sr["records_a"] = legacy["records_a"]
    sr.pop("records_a_ref")
    for rb, orig in zip(sr["records_b"], data.session_result.records_b):
        rb["record_b"] = orig.record_b
        rb["assigned_record_a"] = orig.assigned_record_a
        for c, oc in zip(rb["top_candidates"], orig.top_candidates):
            c["record_a"] = oc.record_a
    legacy["version"] = "1.0"
    legacy_path = tmp_path / "old.vsession"
    legacy_path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2), encoding="utf-8")
    old = sm.import_session_file(legacy_path)
    assert old.session_result.records_b[0].record_b["नाम"] == "राम"

    # SQLite round-trip of compressed payload
    sm.save_session(data)
    again = sm.load_session("t")
    assert again.session_result.stats == data.session_result.stats


# ---------------------------------------------------------------- forms, evaluation, batch

def test_form_678_classification(tmp_path):
    data = _small_session()
    res = data.session_result
    res.records_b[0].notes = "मृतक (विलोपन हेतु प्रारूप 7 आवश्यक)"
    actions = classify_form_actions(res, data.mappings)
    forms = {(a.source, a.index): a.form for a in actions}
    assert forms[("B", 0)] == "7"        # remark overrides
    assert forms[("B", 2)] == "6"        # new voter, not in List A
    assert any(a.form == "7" and a.source == "A" for a in actions)  # only-in-A voter
    assert res.records_b[1].tier == "मिला"
    assert ("B", 1) not in forms         # सिता vs सीता is a matra variant, not a correction
    res.records_b[1].record_b["आयु"] = 55  # real discrepancy: age 30 in roll vs 55 in field
    forms = {(a.source, a.index): a for a in classify_form_actions(res, data.mappings)}
    assert forms[("B", 1)].form == "8" and "आयु" in forms[("B", 1)].reason
    export_form_actions_excel(actions, str(tmp_path / "f.xlsx"))
    export_form_actions_pdf(actions, str(tmp_path / "f.pdf"))
    assert (tmp_path / "f.xlsx").stat().st_size > 0 and (tmp_path / "f.pdf").stat().st_size > 0


def test_evaluation_and_threshold_suggestion_and_retier():
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import benchmark  # noqa: E402

    a, b = benchmark.generate(300, seed=11)
    res = ElectoralRollMatcher(benchmark.mappings(), alias_manager=AliasManager()).run_matching(a, b)
    # Simulate a BLO who confirms every machine proposal scoring >= 0.80 and rejects the rest
    for r in res.records_b:
        if r.machine_a_idx is not None and r.best_score_result.score >= 0.80:
            r.user_decision = "प्रत्याशी 1"
        else:
            r.user_decision = "लापता (पुष्टि की गई)"
            r.assigned_a_idx = None
    labels = extract_labels(res.records_b)
    assert len(labels) == len(res.records_b)
    rep = evaluate(labels, 0.90, 0.72)
    assert 0.0 <= rep.precision <= 1.0 and rep.labels == len(labels)
    sug = suggest_thresholds(labels, 0.90, 0.72)
    assert sug is not None
    assert sug.cost <= rep.cost
    assert 0.55 <= sug.thr_review < sug.thr_matched <= 0.99

    # Retier only touches undecided records
    for r in res.records_b[:50]:
        r.user_decision = None
    before = [r.tier for r in res.records_b[50:]]
    res.retier(0.99, 0.98, 0.9, 0.8, True)
    assert [r.tier for r in res.records_b[50:]] == before
    assert all(r.tier != "मिला" or r.best_score_result.score >= 0.99 or r.best_score_result.epic_match
               for r in res.records_b[:50])


def test_batch_run_produces_reports(tmp_path):
    from voter_match.core.batch import BatchJob, run_batch

    fa, fb = SAMPLE_DIR / "voter_list_A.xlsx", SAMPLE_DIR / "voter_list_B.xlsx"
    template = [
        ColumnMapping(role="voter_name", col_a="मतदाता का नाम", col_b="मतदाता_नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता/पति का नाम", col_b="सम्बन्धी_का_नाम", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="उम्र", importance="Medium", col_type="number"),
    ]
    jobs = [BatchJob(str(fa), str(fb), "भाग 1"), BatchJob(str(fa), str(tmp_path / "missing.xlsx"), "टूटा")]
    outcomes, summary = run_batch(jobs, template, tmp_path / "out", {"alias_manager": AliasManager()})
    assert Path(summary).exists()
    assert outcomes[0].error == "" and outcomes[0].stats["मिला"] > 0
    assert Path(outcomes[0].report_path).exists()
    assert outcomes[1].error  # bad file reported, batch continued


# ---------------------------------------------------------------- review UI: undo + learning

def test_review_undo_restores_decision_and_learning(qapp_or_skip, tmp_path):
    from voter_match.ui.review_page import ReviewPage

    data = _small_session()
    page = ReviewPage()
    page.storage = StorageManager(tmp_path / "r.db")
    page.alias_mgr = AliasManager()
    page.set_data(data.session_result.records_b, data.mappings, data.session_result, "s")
    page.combo_tier.setCurrentText("सभी मतदाता")
    page.apply_filter()

    rec = page.records[page.filtered_indices[0]]
    before = (rec.tier, rec.assigned_a_idx, rec.user_decision)
    page.record_decision("missing", None)
    assert rec.user_decision is not None and rec.tier == "लापता"
    assert page.alias_mgr.rejections  # negative learning recorded
    page.undo_last()
    assert (rec.tier, rec.assigned_a_idx, rec.user_decision) == before
    assert not page.alias_mgr.rejections
    assert page.storage.get_decisions("s") == {}


@pytest.fixture
def qapp_or_skip():
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        pytest.skip("PySide6 unavailable")
    app = QApplication.instance() or QApplication([])
    yield app


def test_recalculate_stats_is_noop_right_after_matching():
    import pandas as pd

    fa, fb = SAMPLE_DIR / "Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx", SAMPLE_DIR / "Chanchpur_Bhatela_Check_List_B.xlsx"
    a, b = pd.read_excel(fa).to_dict("records"), pd.read_excel(fb).to_dict("records")
    m = [ColumnMapping(role="voter_name", col_a="नाम", col_b="निर्वाचक का नाम"),
         ColumnMapping(role="relative_name", col_a="पिता/पति का नाम", col_b="पिता/पति/माता का नाम"),
         ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium", col_type="number")]
    res = ElectoralRollMatcher(m, alias_manager=AliasManager()).run_matching(a, b)
    before = dict(res.stats), list(res.unmatched_a_indices)
    res.recalculate_stats()
    assert (dict(res.stats), list(res.unmatched_a_indices)) == before
    # Confirming a held record as missing frees exactly its List-A voter
    rec = next(r for r in res.records_b if r.assigned_a_idx is not None and r.tier == "जाँचें")
    freed = rec.assigned_a_idx
    rec.assigned_a_idx, rec.tier, rec.user_decision = None, "लापता", "लापता (पुष्टि की गई)"
    res.recalculate_stats()
    assert freed in res.unmatched_a_indices
    assert res.stats["केवल सूची A में"] == before[0]["केवल सूची A में"] + 1


def test_column_suggestions_on_real_headers():
    from voter_match.core.batch import load_table
    from voter_match.core.column_suggest import ROLE_KEYWORDS, suggest_columns

    cols, _ = load_table(SAMPLE_DIR / "Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx")
    sug = suggest_columns(cols, list(ROLE_KEYWORDS))
    assert sug["voter_name"] == "नाम"
    assert sug["serial_no"] == "क्रम संख्या"
    assert sug["house_no"] == "मकान संख्या"
    assert sug["epic"] == "EPIC संख्या"
    assert sug["relative_name"] == "पिता/पति का नाम"


def test_pdf_uses_devanagari_font_and_orders_i_matra(tmp_path):
    """Regression: Windows ships Nirmala UI as Nirmala.ttc; falling back to
    Helvetica printed every Hindi letter as a solid black box."""
    from voter_match.export import pdf_export

    if not any((pdf_export.WINDOWS_FONT_DIR / f).exists()
               for (f, _), _b in pdf_export._FONT_CANDIDATES):
        pytest.skip("no Devanagari system font on this machine")
    assert pdf_export.FONT_REGISTERED
    assert pdf_export.ACTIVE_FONT != "Helvetica"
    if not pdf_export.SHAPING_ENABLED:
        assert pdf_export.visual_order_devanagari("निकटतम") == "\u093fनकटतम"
        assert pdf_export.visual_order_devanagari("स्त्रि") == "\u093fस्त्र"
        assert pdf_export.visual_order_devanagari("राम") == "राम"
    data = _small_session()
    out = tmp_path / "r.pdf"
    pdf_export.PdfExporter(data.session_result, data.mappings).export(out)
    raw = out.read_bytes()
    assert b"Helvetica" not in raw or b"HindiFont" in raw or b"Nirmala" in raw


# ---------------------------------------------------------------- language switching

def test_i18n_translates_static_dynamic_and_composite_text():
    from voter_match.ui.i18n import translate

    assert translate("🔍 त्वरित खोज") == "🔍 Quick Search"
    assert translate("मिलान पूर्ण! मिला: 384, जाँचें: 104, लापता: 219") == \
        "Matching complete! Matched: 384, Review: 104, Missing: 219"
    # nested: template whose variable part is itself a translatable phrase
    assert translate("मतदाता का नाम: समान (पूर्ण समान (Exact))") == "Voter Name: same (Exact)"
    # composite reasons joined with '; ' are translated piece by piece
    joined = "मतदाता का नाम: कम समानता (74%); पिता/पति/माता का नाम: कम समानता (56%)"
    assert translate(joined) == "Voter Name: low similarity (74%); Father/Husband/Mother name: low similarity (56%)"
    # voter data is never altered
    assert translate("सुनील कुमार") == "सुनील कुमार"
    assert translate("1349") == "1349"


def test_i18n_switch_and_restore_widgets(qapp_or_skip):
    from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget
    from voter_match.ui import i18n

    root = QWidget()
    lay = QVBoxLayout(root)
    lbl = QLabel("मिलान पूर्ण!")
    btn = QPushButton("⚙️ सेटिंग्स")
    combo = i18n.mark_translatable(QComboBox())
    combo.addItem("सभी मतदाता", "all")
    plain_combo = QComboBox()
    plain_combo.addItem("आयु")  # a data column named like a UI word must NOT change
    for w in (lbl, btn, combo, plain_combo):
        lay.addWidget(w)
    try:
        i18n.set_language(i18n.LANG_EN, persist=False)
        i18n.apply_to(root, visible_only=False)
        assert lbl.text() == "Matching complete!"
        assert btn.text() == "⚙️ Settings"
        assert combo.itemText(0) == "All voters" and combo.itemData(0) == "all"
        assert plain_combo.itemText(0) == "आयु"
        # text changed by the app while in English mode becomes the new original
        lbl.setText("सत्यापित: 0 | शेष: 0")
        i18n.apply_to(root, visible_only=False)
        i18n.set_language(i18n.LANG_HI, persist=False)
        i18n.apply_to(root, visible_only=False)
        assert lbl.text() == "सत्यापित: 0 | शेष: 0"
        assert btn.text() == "⚙️ सेटिंग्स"
        assert combo.itemText(0) == "सभी मतदाता"
    finally:
        i18n.set_language(i18n.LANG_HI, persist=False)


def test_i18n_covers_every_ui_string():
    """Every Hindi literal shown by the UI has an English translation (or is a
    deliberate data keyword). Guards against new untranslated UI text."""
    import ast
    import re
    from voter_match.ui.i18n import translate

    dev = re.compile(r"[\u0900-\u097F]")
    ui_dir = PROJECT_ROOT / "voter_match" / "ui"
    # Hindi literals that are data/keywords or file names, not UI text
    allowed = {"_क्लस्टर_ID", "_समानता_स्कोर", "पिता", "पति", "माता", "गृह", "बैच_मिलान_रिपोर्ट"}
    # The language switch itself is deliberately bilingual so anyone can find it
    allowed |= {"हिंदी", "🌐 हिंदी", "🌐 भाषा / Language:", "भाषा बदलें / Change language (हिंदी ⇄ English)"}
    missing = []
    for f in ui_dir.glob("*.py"):
        if f.name.startswith("i18n"):
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
                    and id(n) not in inner and dev.search(n.value)):
                s = n.value
                if s in allowed or s.endswith((".xlsx", ".pdf")):
                    continue
                if translate(s) == s:
                    missing.append(f"{f.name}: {s!r}")
    assert not missing, "Untranslated UI strings:\n" + "\n".join(sorted(set(missing)))


def test_english_mode_never_alters_voter_names(qapp_or_skip):
    """Regression: diff highlighting split 'अनामिका' into HTML fragments and the
    translator turned the fragment 'म' into 'F' (gender), showing 'अनाFका'."""
    from voter_match.ui import i18n
    from voter_match.ui.review_page import CandidateCardWidget, highlight_diff_html
    from voter_match.core.matcher import MatchCandidate
    from voter_match.core.scorer import ScoreResult

    # matras stay attached to their consonant (no dotted-circle fragments)
    html_b = highlight_diff_html("मीना देवी", "मीनू देवी")[1]
    assert "ू" in html_b and ">ू<" not in html_b and ">ा<" not in html_b

    rec_a = {"नाम": "अनामिका कौशिक", "पिता": "राजकुमार कौशिक", "लिंग": "म", "आयु": 24}
    maps = [ColumnMapping(role="voter_name", col_a="नाम", col_b="नाम"),
            ColumnMapping(role="relative_name", col_a="पिता", col_b="पिता"),
            ColumnMapping(role="gender", col_a="लिंग", col_b="लिंग", col_type="category")]
    cand = MatchCandidate(a_idx=0, score_result=ScoreResult(score=0.84), record_a=rec_a)
    try:
        i18n.set_language(i18n.LANG_EN, persist=False)
        card = CandidateCardWidget(1, cand, "मीनेश कौशिक", "राजकुमार कौशिक", "नाम", "पिता", maps)
        i18n.apply_to(card, visible_only=False)
        texts = " ".join(l.text() for l in card.findChildren(QLabel))
        plain = re.sub(r"<[^>]+>", "", texts)
        assert "अनामिका" in plain and "F" not in plain.replace("Female", "")
        assert "Voter:" in plain and "Female" in plain   # caption + gender localised
    finally:
        i18n.set_language(i18n.LANG_HI, persist=False)


def test_table_copy_produces_excel_tsv_without_changing_cells(qapp_or_skip):
    from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
    from voter_match.ui.copy_support import copy_table, enable_table_copy, table_to_tsv
    from voter_match.ui import i18n

    t = enable_table_copy(i18n.mark_translatable(QTableWidget(3, 3)), read_only=True)
    t.setHorizontalHeaderLabels(["क्र०", "मतदाता का नाम", "स्थिति (Status)"])
    data = [["1", "अनामिका कौशिक", "मिला"], ["2", "राम\tप्रसाद", "लापता"], ["3", "सीता", "जाँचें"]]
    for r, row in enumerate(data):
        for c, v in enumerate(row):
            t.setItem(r, c, QTableWidgetItem(v))
    # Excel-style block selection of rows 0-1, columns 1-2
    t.setRangeSelected(__import__("PySide6.QtWidgets", fromlist=["QTableWidgetSelectionRange"])
                       .QTableWidgetSelectionRange(0, 1, 1, 2), True)
    assert table_to_tsv(t) == "अनामिका कौशिक\tमिला\nराम प्रसाद\tलापता"   # tab inside a cell is flattened
    assert table_to_tsv(t, with_headers=True).splitlines()[0] == "मतदाता का नाम\tस्थिति (Status)"
    assert table_to_tsv(t, whole_table=True, with_headers=True).count("\n") == 3
    assert copy_table(t) == 2 and QApplication.clipboard().text().startswith("अनामिका कौशिक")
    # copying never alters the table
    assert t.item(0, 1).text() == "अनामिका कौशिक" and t.item(1, 1).text() == "राम\tप्रसाद"
    assert t.editTriggers() == t.EditTrigger.NoEditTriggers


def test_review_copy_buttons_copy_original_record_in_both_languages(qapp_or_skip, tmp_path):
    from PySide6.QtWidgets import QApplication
    from voter_match.ui import i18n
    from voter_match.ui.review_page import CandidateCardWidget, ReviewPage

    data = _small_session()
    page = ReviewPage()
    page.storage = StorageManager(tmp_path / "c.db")
    page.alias_mgr = AliasManager()
    page.set_data(data.session_result.records_b, data.mappings, data.session_result, "s")
    page.combo_tier.setCurrentIndex(1)  # all voters
    page.apply_filter()
    rec = page.records[page.filtered_indices[0]]
    try:
        for lang in (i18n.LANG_HI, i18n.LANG_EN):
            i18n.set_language(lang, persist=False)
            page.btn_copy_b.click()
            clip = QApplication.clipboard().text()
            # original values, in mapping order (S.No., name, relative, age), never translated
            assert clip.split("\t")[:4] == [str(rec.record_b["क्र"]), rec.record_b["नाम"],
                                            rec.record_b["पिता"], str(rec.record_b["आयु"])]
            assert page._current_b_tsv(True).splitlines()[0].split("\t")[0] == i18n.tr("क्र०")
            # button label follows the language and is restored after the "copied" flash
            assert page.btn_copy_b.text().startswith("✅")
        i18n.set_language(i18n.LANG_HI, persist=False)
        assert page.btn_copy_b.text() in ("📋 विवरण कॉपी करें [Ctrl+Shift+C]", "✅ कॉपी हुआ")
        cards = page.cands_container.findChildren(CandidateCardWidget)
        assert cards, "candidate cards rendered"
    finally:
        i18n.set_language(i18n.LANG_HI, persist=False)


def test_duplicates_use_relative_name_and_never_chain(qapp_or_skip):
    from voter_match.core.duplicates import DuplicateDetector
    from voter_match.core.column_suggest import suggest_columns

    recs = [
        {"मतदाता का नाम": "मीरा देवी", "संबंधी का नाम": "राजेश", "आयु": 40},
        {"मतदाता का नाम": "मीना देवी", "संबंधी का नाम": "सुरेश", "आयु": 35},
        {"मतदाता का नाम": "मनीषा देवी", "संबंधी का नाम": "विनोद", "आयु": 30},
        {"मतदाता का नाम": "मीनादेवी", "संबंधी का नाम": "सुरेश", "आयु": 36},
        {"मतदाता का नाम": "शिव कुमार कौशिक", "संबंधी का नाम": "रामनिवास", "आयु": 50},
        {"मतदाता का नाम": "अश्वनी कुमार कौशिक", "संबंधी का नाम": "रामनिवास", "आयु": 45},
        {"मतदाता का नाम": "राकेश पचौरी", "संबंधी का नाम": "गजाधर पचौरी", "आयु": 49},
        {"मतदाता का नाम": "राकश", "संबंधी का नाम": "गजाधर", "आयु": 49},
        {"मतदाता का नाम": "मुकेश कुमार", "संबंधी का नाम": "रामपाल", "आयु": 52},
        {"मतदाता का नाम": "मुकेश कुमार", "संबंधी का नाम": "हरिओम", "आयु": 30},
    ]
    # 'संबंधी का नाम' (anusvara spelling) is recognised as the relative column
    assert suggest_columns(list(recs[0]), ["voter_name", "relative_name"])["relative_name"] == "संबंधी का नाम"
    det = DuplicateDetector(voter_col="मतदाता का नाम", rel_col="संबंधी का नाम", age_col="आयु")
    groups = sorted(sorted(c.indices) for c in det.find_duplicates(recs))
    assert groups == [[1, 3], [6, 7]]  # same person only; no brothers, namesakes or chains


def test_duplicates_page_uses_step2_mapping(qapp_or_skip):
    from voter_match.ui.duplicates_page import DuplicatesPage

    page = DuplicatesPage()
    cols_b = ["क्रम", "मतदाता का नाम", "संबंधी का नाम", "आयु", "पुराना भाग संख्या"]
    page.set_data([], [{c: "" for c in cols_b}], ["नाम"], cols_b)
    page.mapping_provider = lambda: [
        ColumnMapping(role="voter_name", col_a="नाम", col_b="मतदाता का नाम"),
        ColumnMapping(role="relative_name", col_a=None, col_b="संबंधी का नाम"),
    ]
    cols = page.resolve_columns(use_b=True)
    assert cols["voter_name"] == "मतदाता का नाम" and cols["relative_name"] == "संबंधी का नाम"
    assert cols["age"] == "आयु"  # gap filled by auto-detection
    assert "संबंधी का नाम" in page.lbl_columns.text()


def test_duplicates_columns_line_keeps_column_names_in_english_mode(qapp_or_skip):
    from voter_match.ui import i18n
    from voter_match.ui.duplicates_page import DuplicatesPage

    page = DuplicatesPage()
    cols_b = ["मतदाता का नाम", "संबंधी का नाम", "आयु"]
    page.set_data([], [{c: "" for c in cols_b}], ["नाम"], cols_b)
    try:
        i18n.set_language(i18n.LANG_EN, persist=False)
        i18n.apply_to(page, visible_only=False)
        txt = page.lbl_columns.text()
        assert txt.startswith("🧩 Columns used:")
        assert "मतदाता का नाम" in txt and "संबंधी का नाम" in txt and "= आयु" in txt  # data kept as-is
    finally:
        i18n.set_language(i18n.LANG_HI, persist=False)


def test_quick_search_logic(qapp_or_skip):
    from voter_match.ui import i18n
    from voter_match.ui.search_page import SearchPage, MODE_SERIAL

    recs_b = [
        {"क्रम": 1349.0, "मतदाता का नाम": "सुनील कुमार", "संबंधी का नाम": "ओमप्रकाश", "आयु": 27.0, "लिंग": "पु"},
        {"क्रम": float("nan"), "मतदाता का नाम": "मकान", "संबंधी का नाम": "सूची", "आयु": 40, "लिंग": "म"},
    ]
    cols_b = list(recs_b[0])
    page = SearchPage()
    page.set_data([], recs_b, [], cols_b)
    # live Step-2 mapping is followed even before matching starts
    page.mapping_provider = lambda: [ColumnMapping(role="serial_no", col_a=None, col_b="क्रम"),
                                     ColumnMapping(role="voter_name", col_a=None, col_b="मतदाता का नाम"),
                                     ColumnMapping(role="relative_name", col_a=None, col_b="संबंधी का नाम")]
    # serial stored as a float (column had a blank) is still found and shown without '.0'
    page.combo_mode.setCurrentIndex(page.combo_mode.findData(MODE_SERIAL))
    page.txt_query.setText("1349")
    page.run_search()
    assert page.table_b.rowCount() == 1 and page.table_b.item(0, 2).text() == "1349"
    assert page.table_b.item(0, 5).text() == "27"
    # result cells are data: never translated in English mode, headings are
    page.combo_mode.setCurrentIndex(0)
    try:
        i18n.set_language(i18n.LANG_EN, persist=False)
        page.txt_query.setText("मकान")
        page.run_search()
        i18n.apply_to(page, visible_only=False)
        names = [page.table_b.item(r, 3).text() for r in range(page.table_b.rowCount())]
        assert "मकान" in names            # a voter literally named like a UI word stays as-is
        assert page.table_b.horizontalHeaderItem(3).text() == "Voter Name"
        assert page.table_b.item(0, 1).toolTip().startswith("Match type:")
    finally:
        i18n.set_language(i18n.LANG_HI, persist=False)


def test_english_mode_never_alters_user_data_anywhere(qapp_or_skip):
    """Adversarial end-to-end check: voter names, relatives, column names and
    values that are identical to UI words in the translation table must be shown
    exactly as entered on every screen when the app runs in English."""
    from PySide6.QtWidgets import QLabel
    from voter_match.ui import i18n
    from voter_match.ui.main_window import MainWindow

    # data deliberately equal to dictionary words
    trap_names = ["मकान", "सूची", "सफल", "विवरण", "निर्णय", "आयु"]
    cols = ["क्रम", "नाम", "संबंधी का नाम", "आयु", "लिंग"]
    recs_a = [{"क्रम": i + 1, "नाम": n, "संबंधी का नाम": "मतदाता", "आयु": 30 + i, "लिंग": "महिला",
               "_orig_row": i + 2} for i, n in enumerate(trap_names)]
    recs_b = [dict(r) for r in recs_a]
    w = MainWindow()
    try:
        w.on_files_ready_to_map(cols, cols, recs_a, recs_b)
        maps = [c.get_mapping() for c in w.page_mapping.role_cards]
        w.mappings = maps
        res = ElectoralRollMatcher(maps, alias_manager=AliasManager()).run_matching(recs_a, recs_b)
        w.on_matching_finished(res)
        w.page_search.txt_query.setText("मकान")
        w.page_search.run_search()

        i18n.set_language(i18n.LANG_EN, persist=False)
        for page in range(7):
            w.switch_page(page)
            i18n.apply_to(w, visible_only=False)

        # Results table: names / relatives untouched, status translated
        t = w.page_results.table_results
        shown_names = {t.item(r, 5).text() for r in range(t.rowCount())}
        assert set(trap_names) <= shown_names
        assert {t.item(r, 6).text() for r in range(t.rowCount())} == {"मतदाता"}
        assert t.item(0, 3).text().strip() in {"Matched", "Review", "Missing"}
        # Mapping: sample value "महिला" and column names stay data
        g_card = next(c for c in w.page_mapping.role_cards if c.role == "gender")
        assert "महिला" in g_card.lbl_sample_a.text() and g_card.lbl_sample_a.text().startswith("✓ List A")
        assert g_card.combo_a.currentText() == "लिंग"
        # Quick Search: typed query echoed unchanged; cells unchanged
        assert "'मकान'" in w.page_search.lbl_status.text()
        assert w.page_search.table_b.item(0, 3).text() == "मकान"
        # Review: name labels unchanged
        w.switch_page(3)
        w.page_review.combo_tier.setCurrentIndex(1)
        w.page_review.apply_filter()
        labels = " ".join(l.text() for l in w.page_review.findChildren(QLabel))
        assert any(n in labels for n in trap_names) and "मतदाता" in labels
    finally:
        i18n.set_language(i18n.LANG_HI, persist=False)
        w.close()
