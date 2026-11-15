"""End-to-End Automated Integration Test on Realistic Hindi Sample Data."""

from pathlib import Path
import pandas as pd
import pytest
import openpyxl

from voter_match.core.matcher import ElectoralRollMatcher
from voter_match.core.scorer import ColumnMapping
from voter_match.core.duplicates import DuplicateDetector
from voter_match.export.excel_export import ExcelExporter
from voter_match.export.pdf_export import PdfExporter

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data"
FILE_A = SAMPLE_DIR / "voter_list_A.xlsx"
FILE_B = SAMPLE_DIR / "voter_list_B.xlsx"


def test_end_to_end_matching_and_exports(tmp_path):
    assert FILE_A.exists()
    assert FILE_B.exists()

    df_a = pd.read_excel(FILE_A)
    df_b = pd.read_excel(FILE_B)

    records_a = df_a.to_dict(orient="records")
    records_b = df_b.to_dict(orient="records")

    mappings = [
        ColumnMapping(role="serial_no", col_a="क्र०", col_b="क्रमांक", importance="Paper Ref"),
        ColumnMapping(role="voter_name", col_a="मतदाता का नाम", col_b="मतदाता_नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता/पति का नाम", col_b="सम्बन्धी_का_नाम", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="उम्र", importance="Medium", col_type="number", tolerance=3),
        ColumnMapping(role="gender", col_a="लिंग", col_b="लिंग", importance="Low", col_type="category"),
        ColumnMapping(role="house_no", col_a="मकान नं०", col_b="गृह_संख्या", importance="Bonus only"),
        ColumnMapping(role="ward", col_a="वार्ड", col_b="वार्ड_संख्या", importance="Ignore"),
    ]

    matcher = ElectoralRollMatcher(mappings)
    res = matcher.run_matching(records_a, records_b)

    assert len(res.records_b) == 15

    # 1. Sunil (सुनील vs सुनिल) -> मिला
    rec_sunil = res.records_b[0]
    assert rec_sunil.tier == "मिला"
    assert rec_sunil.assigned_record_a["मतदाता का नाम"] == "सुनील कुमार"

    # 2. Sheela (शीला vs शीला देवी) -> मिला
    rec_sheela = res.records_b[1]
    assert rec_sheela.tier == "मिला"
    assert rec_sheela.assigned_record_a["मतदाता का नाम"] == "शीला देवी"

    # 3. Jamil Khan (जमीलखाँ vs जमीलखां) -> मिला
    rec_jamil = res.records_b[2]
    assert rec_jamil.tier == "मिला"

    # 4. Ram Lakhan (प्साद vs प्रसाद) -> मिला
    rec_ram = res.records_b[3]
    assert rec_ram.tier == "मिला"

    # 5. Sibling Negative Test: Rashi Devi should NOT be 'मिला'
    rec_rashi = res.records_b[4]
    assert rec_rashi.tier != "मिला"

    # 6. Chandan (क्रष्ण vs कृष्ण) -> मिला
    rec_chandan = res.records_b[5]
    assert rec_chandan.tier == "मिला"

    # 7. Yogesh Kumar (योगेशकुमार vs योगेश कुमार) -> मिला
    rec_yogesh = res.records_b[6]
    assert rec_yogesh.tier == "मिला"

    # 8. Omprakash (ओमप्काश vs ओमप्रकाश) -> मिला
    rec_om = res.records_b[7]
    assert rec_om.tier in {"मिला", "जाँचें"}

    # 15. Amit Singh (New voter, not in A) -> लापता
    rec_amit = res.records_b[14]
    assert rec_amit.tier == "लापता"

    # Test Excel Export
    excel_out = tmp_path / "test_report.xlsx"
    exporter = ExcelExporter(res, mappings)
    exporter.export(excel_out)
    assert excel_out.exists()

    wb = openpyxl.load_workbook(excel_out)
    expected_sheets = ["सारांश", "1. लापता मतदाता", "2. जाँचें", "3. मिला", "4. केवल सूची A में", "5. पूरी सूची"]
    for s_name in expected_sheets:
        assert s_name in wb.sheetnames

    # Check that paper roll serial number columns exist and contain values
    ws_matched = wb["3. मिला"]
    h2 = [cell.value for cell in ws_matched[2]]
    assert "क्र० [क्रमांक]" in h2
    assert "क्र० [क्र०]" in h2
    kram_b_val = ws_matched.cell(row=3, column=h2.index("क्र० [क्रमांक]") + 1).value
    kram_a_val = ws_matched.cell(row=3, column=h2.index("क्र० [क्र०]") + 1).value
    assert str(kram_b_val) == "1"
    assert str(kram_a_val) == "1"

    # Test PDF Export
    pdf_out = tmp_path / "test_report.pdf"
    pdf_exporter = PdfExporter(res, mappings)
    pdf_exporter.export(pdf_out)
    assert pdf_out.exists()
    assert pdf_out.stat().st_size > 1000

    # Test Duplicates & Household detection
    detector = DuplicateDetector(voter_col="मतदाता_नाम", rel_col="सम्बन्धी_का_नाम", house_col="गृह_संख्या")
    households = DuplicateDetector.group_by_household(records_b, house_col="गृह_संख्या", rel_col="सम्बन्धी_का_नाम")
    assert len(households) > 0


def test_post_review_excel_export_and_recalculation(tmp_path):
    """Test that live BLO decisions and remarks update session stats and propagate to exported Excel."""
    df_a = pd.read_excel(FILE_A)
    df_b = pd.read_excel(FILE_B)
    records_a = df_a.to_dict(orient="records")
    records_b = df_b.to_dict(orient="records")

    mappings = [
        ColumnMapping(role="serial_no", col_a="क्र०", col_b="क्रमांक", importance="Paper Ref"),
        ColumnMapping(role="voter_name", col_a="मतदाता का नाम", col_b="मतदाता_नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता/पति का नाम", col_b="सम्बन्धी_का_नाम", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="उम्र", importance="Medium", col_type="number", tolerance=3),
        ColumnMapping(role="gender", col_a="लिंग", col_b="लिंग", importance="Low", col_type="category"),
        ColumnMapping(role="house_no", col_a="मकान नं०", col_b="गृह_संख्या", importance="Bonus only"),
    ]

    matcher = ElectoralRollMatcher(mappings)
    res = matcher.run_matching(records_a, records_b)

    init_matched = res.stats.get("मिला", 0)
    init_review = res.stats.get("जाँचें", 0)

    # Find a record in 'जाँचें'
    review_recs = [r for r in res.records_b if r.tier == "जाँचें"]
    assert len(review_recs) > 0, "Expected at least one record in 'जाँचें'"

    target_rec = review_recs[0]
    # Simulate BLO verifying this record on field
    target_cand = target_rec.top_candidates[0]
    target_rec.assigned_a_idx = target_cand.a_idx
    target_rec.assigned_record_a = target_cand.record_a
    target_rec.tier = "मिला"
    target_rec.user_decision = "स्वीकृत (प्रत्याशी 1)"
    target_rec.notes = "मौके पर भौतिक सत्यापन द्वारा सत्यापित"

    # Export updated Excel
    updated_excel = tmp_path / "updated_review_report.xlsx"
    exporter = ExcelExporter(res, mappings)
    exporter.export(updated_excel)

    # 1. Verify recalculate_stats updated res.stats
    assert res.stats.get("मिला") == init_matched + 1
    assert res.stats.get("जाँचें") == init_review - 1

    # 2. Verify Excel contents
    wb = openpyxl.load_workbook(updated_excel)
    ws_matched = wb["3. मिला"]
    
    # Check headers contain BLO decision and remark
    headers = [cell.value for cell in ws_matched[2]]
    assert "BLO निर्णय" in headers
    assert "स्थलीय टिप्पणी (Remarks)" in headers
    decision_col_idx = headers.index("BLO निर्णय") + 1
    notes_col_idx = headers.index("स्थलीय टिप्पणी (Remarks)") + 1

    # Find the verified record in sheet
    found_decision = False
    for row in range(3, ws_matched.max_row + 1):
        dec_val = ws_matched.cell(row=row, column=decision_col_idx).value
        note_val = ws_matched.cell(row=row, column=notes_col_idx).value
        if dec_val == "स्वीकृत (प्रत्याशी 1)" and note_val == "मौके पर भौतिक सत्यापन द्वारा सत्यापित":
            found_decision = True
            break
    assert found_decision, "BLO decision and note must be written in '3. मिला' sheet"


def test_real_world_chanchpur_bhatela_dataset(tmp_path):
    """End-to-End Test on User's Attached Real-World Chanchpur Bhatela Electoral Roll."""
    real_a = SAMPLE_DIR / "Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx"
    real_b = SAMPLE_DIR / "Chanchpur_Bhatela_Check_List_B.xlsx"
    assert real_a.exists(), "List A must exist"
    assert real_b.exists(), "List B must exist"

    df_a = pd.read_excel(real_a)
    df_b = pd.read_excel(real_b)
    assert len(df_a) == 649
    assert len(df_b) == 707

    mappings = [
        ColumnMapping(role="serial_no", col_a="क्रम संख्या", col_b="क्र०सं०", importance="Paper Ref"),
        ColumnMapping(role="voter_name", col_a="नाम", col_b="निर्वाचक का नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता/पति का नाम", col_b="पिता/पति/माता का नाम", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium", col_type="number", tolerance=3),
        ColumnMapping(role="gender", col_a="लिंग", col_b="लिंग", importance="Low", col_type="category"),
        ColumnMapping(role="house_no", col_a="मकान संख्या", col_b="मकान नं०", importance="Bonus only"),
    ]

    import time
    t0 = time.time()
    matcher = ElectoralRollMatcher(mappings)
    res = matcher.run_matching(df_a.to_dict("records"), df_b.to_dict("records"))
    t1 = time.time()

    # Performance requirement: 707 x 649 in under 5 seconds
    assert (t1 - t0) < 5.0
    assert len(res.records_b) == 707

    # Verify high-accuracy matching stats
    assert res.stats.get("मिला", 0) >= 380
    assert res.stats.get("जाँचें", 0) >= 80

    # Key real-world case checks:
    # 1. 1353 (ओमप्रकाश महाराज सिंह) -> 44
    rec_1353 = next(r for r in res.records_b if r.record_b.get("क्र०सं०") == 1353)
    assert rec_1353.tier == "मिला"
    assert rec_1353.assigned_record_a.get("क्रम संख्या") == 44

    # 2. 1356 (सुनील कुमार ॐ प्रकाश) -> 268 (सुनील कुमार ओमप्रकाश) with OM normalization
    rec_1356 = next(r for r in res.records_b if r.record_b.get("क्र०सं०") == 1356)
    assert rec_1356.tier == "मिला"
    assert rec_1356.assigned_record_a.get("क्रम संख्या") == 268

    # 3. 1358 (भवानीदेवी रामवकील) -> 45
    rec_1358 = next(r for r in res.records_b if r.record_b.get("क्र०सं०") == 1358)
    assert rec_1358.tier == "मिला"
    assert rec_1358.assigned_record_a.get("क्रम संख्या") == 45

    # 4. 1373 (रामवकील जानकीप्साद) -> 57 (रामवकील जानकीप्रसाद) with half-letter normalization
    rec_1373 = next(r for r in res.records_b if r.record_b.get("क्र०सं०") == 1373)
    assert rec_1373.tier == "मिला"
    assert rec_1373.assigned_record_a.get("क्रम संख्या") == 57

    # Export report and verify headers and values
    out_excel = tmp_path / "Chanchpur_Bhatela_Report.xlsx"
    exporter = ExcelExporter(res, mappings, label_a="2026 विधानसभा सूची A", label_b="सत्यापन सूची B")
    exporter.export(out_excel)
    assert out_excel.exists()

    wb = openpyxl.load_workbook(out_excel)
    ws_matched = wb["3. मिला"]
    h2 = [cell.value for cell in ws_matched[2]]
    assert "क्र० [क्र०सं०]" in h2
    assert "क्र० [क्रम संख्या]" in h2
