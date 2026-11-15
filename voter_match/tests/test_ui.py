"""Automated UI Headless Integration Test."""

import os
import sys
import pytest

# Ensure offscreen Qt platform for headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from voter_match.ui.main_window import MainWindow
from voter_match.ui.import_page import ImportPage
from voter_match.ui.mapping_page import MappingPage
from voter_match.ui.results_page import ResultsPage
from voter_match.ui.review_page import ReviewPage
from voter_match.core.matcher import ElectoralRollMatcher, MatchSessionResult
from voter_match.core.scorer import ColumnMapping

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_main_window_instantiation(qapp):
    win = MainWindow()
    assert win is not None
    assert win.stack.count() == 7
    assert win.btn_nav_import.text() == "1️⃣ फ़ाइलें आयात करें"
    win.close()


def test_import_page_and_table_contrast(qapp):
    page = ImportPage()
    assert page.btn_proceed.isEnabled() is False

    # Verify table stylesheet has explicit dark navy header and dark text
    qss = page.widget_a.table_preview.styleSheet()
    assert "background-color: #1E3A8A" in qss or "color: #FFFFFF" in qss
    assert "color: #0F172A" in qss or "color: #0F172A" in qss
    page.close()


def test_mapping_page_roles(qapp):
    page = MappingPage()
    cols_a = ["मतदाता का नाम", "पिता/पति का नाम", "आयु", "लिंग", "मकान नं०"]
    cols_b = ["मतदाता_नाम", "सम्बन्धी_का_नाम", "उम्र", "लिंग", "गृह_संख्या"]
    page.set_columns(cols_a, cols_b, {"मतदाता का नाम": "सुनील कुमार"}, {"मतदाता_नाम": "सुनिल"})

    assert len(page.role_cards) >= 6
    # Check auto-suggest for voter name and presence of serial_no
    serial_card = next(c for c in page.role_cards if c.role == "serial_no")
    assert serial_card is not None
    voter_card = next(c for c in page.role_cards if c.role == "voter_name")
    assert voter_card.combo_a.currentText() == "मतदाता का नाम"
    assert voter_card.combo_b.currentText() == "मतदाता_नाम"
    assert "सुनील कुमार" in voter_card.lbl_sample_a.text()
    assert "सुनिल" in voter_card.lbl_sample_b.text()

    # Verify single next button on Screen 2 (no duplicate buttons!)
    assert page.btn_run is not None
    assert page.btn_run_top is page.btn_run
    assert page.btn_run_bottom is page.btn_run
    page.close()


def test_results_page_single_button_and_proportions(qapp):
    page = ResultsPage()
    # Verify single forward action button on Screen 3
    assert page.btn_review is not None
    assert page.btn_review_top is page.btn_review
    assert page.btn_review_bottom is page.btn_review

    # Verify presence of criteria dropdown and search filter
    assert page.combo_criteria is not None
    assert page.combo_criteria.count() == 5
    assert page.txt_search is not None
    assert page.btn_save_session is not None

    # Verify high-contrast results table styling
    qss = page.table_results.styleSheet()
    assert "background-color: #1E3A8A" in qss or "color: #FFFFFF" in qss
    assert "color: #0F172A" in qss
    page.close()


def test_session_persistence_roundtrip(qapp):
    from voter_match.storage.session_manager import (
        SavedSessionData,
        get_default_session_manager,
    )
    from voter_match.core.matcher import MatchRecordB, MatchSessionResult
    from voter_match.core.scorer import ColumnMapping, ScoreResult

    sm = get_default_session_manager()

    rec_b = MatchRecordB(
        b_idx=0,
        record_b={"नाम": "सुनिल कुमार", "पिता": "राम प्रकाश"},
        tier="मिला",
        best_score_result=ScoreResult(score=0.95, reasons=["नाम शत-प्रतिशत समान"]),
        notes="मौके पर सत्यापित",
    )
    sr = MatchSessionResult(
        records_b=[rec_b],
        unmatched_a_indices=[1],
        records_a=[{"नाम": "सुनील कुमार", "पिता": "राम प्रकाश"}, {"नाम": "अमर सिंह", "पिता": "देवकी नंदन"}],
        stats={"मिला": 1, "जाँचें": 0, "लापता": 0, "केवल सूची A में": 1},
    )

    data = SavedSessionData(
        session_id="test_unit_sess_01",
        title="चांदपुर भटेला परीक्षण",
        file_a="Chanchpur_List_A.xlsx",
        file_b="Chanchpur_List_B.xlsx",
        cols_a=["नाम", "पिता"],
        cols_b=["नाम", "पिता"],
        records_a=sr.records_a,
        records_b=[rec_b.record_b],
        mappings=[ColumnMapping(role="voter_name", col_a="नाम", col_b="नाम")],
        session_result=sr,
    )

    # Save to SQLite
    assert sm.save_session(data) is True

    # List sessions
    sessions = sm.list_sessions()
    found = next((s for s in sessions if s["session_id"] == "test_unit_sess_01"), None)
    assert found is not None
    assert found["title"] == "चांदपुर भटेला परीक्षण"
    assert found["matched_count"] == 1

    # Load from SQLite
    loaded = sm.load_session("test_unit_sess_01")
    assert loaded is not None
    assert loaded.title == "चांदपुर भटेला परीक्षण"
    assert len(loaded.session_result.records_b) == 1
    assert loaded.session_result.records_b[0].notes == "मौके पर सत्यापित"
    assert loaded.session_result.records_b[0].tier == "मिला"

    # Clean up
    sm.delete_session("test_unit_sess_01")


def test_results_page_filtering_criteria(qapp):
    from voter_match.core.matcher import MatchRecordB, MatchSessionResult
    from voter_match.core.scorer import ColumnMapping, ScoreResult

    page = ResultsPage()
    mappings = [
        ColumnMapping(role="voter_name", col_a="नाम_a", col_b="नाम_b"),
        ColumnMapping(role="relative_name", col_a="पिता_a", col_b="पिता_b"),
        ColumnMapping(role="serial_no", col_a="क्र_a", col_b="क्र_b"),
    ]

    r_matched = MatchRecordB(
        b_idx=0,
        record_b={"नाम_b": "सुनील कुमार", "पिता_b": "राम प्रकाश", "क्र_b": "101"},
        assigned_record_a={"नाम_a": "सुनील कुमार", "पिता_a": "राम प्रकाश", "क्र_a": "205"},
        tier="मिला",
        best_score_result=ScoreResult(score=1.0, reasons=["शत-प्रतिशत समान"]),
    )
    r_review = MatchRecordB(
        b_idx=1,
        record_b={"नाम_b": "सुनील", "पिता_b": "राम प्रकाश", "क्र_b": "102"},
        top_candidates=[],
        tier="जाँचें",
        best_score_result=ScoreResult(score=0.78, reasons=["वर्तनी भिन्नता"]),
    )
    r_missing = MatchRecordB(
        b_idx=2,
        record_b={"नाम_b": "दीपक सिंह", "पिता_b": "सुरेश चंद्र", "क्र_b": "103"},
        top_candidates=[],
        tier="लापता",
        best_score_result=None,
    )
    sr = MatchSessionResult(
        records_b=[r_matched, r_review, r_missing],
        unmatched_a_indices=[0],
        records_a=[{"नाम_a": "केवल संदर्भ मतदाता", "पिता_a": "गोपाल", "क्र_a": "301"}],
        stats={"मिला": 1, "जाँचें": 1, "लापता": 1, "केवल सूची A में": 1},
    )

    page.set_results(sr, mappings)

    # 1. Default: all records
    assert page.table_results.rowCount() == 3

    # 2. Filter: मिला (Matched Only)
    page.combo_criteria.setCurrentIndex(1)
    assert page.table_results.rowCount() == 1
    assert "सुनील कुमार" in page.table_results.item(0, 5).text()

    # 3. Filter: जाँचें (Needs Review Only)
    page.combo_criteria.setCurrentIndex(2)
    assert page.table_results.rowCount() == 1
    assert "सुनील" in page.table_results.item(0, 5).text()

    # 4. Filter: केवल नहीं मिला / लापता (Missing Only)
    page.combo_criteria.setCurrentIndex(3)
    assert page.table_results.rowCount() == 1
    assert "दीपक सिंह" in page.table_results.item(0, 5).text()

    # 5. Filter: केवल सूची A में (Only in List A)
    page.combo_criteria.setCurrentIndex(4)
    assert page.table_results.rowCount() == 1
    assert "केवल संदर्भ मतदाता" in page.table_results.item(0, 7).text()

    # 6. Reset filter
    page.reset_filter()
    assert page.table_results.rowCount() == 3

    page.close()
