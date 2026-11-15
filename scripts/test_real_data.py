"""Test script executing full pipeline against real user files:
List A: sample_data/Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx (649 rows)
List B: sample_data/Chanchpur_Bhatela_Check_List_B.xlsx (707 rows)
"""

from pathlib import Path
import sys
import pandas as pd
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from voter_match.core.matcher import ElectoralRollMatcher
from voter_match.core.scorer import ColumnMapping
from voter_match.export.excel_export import ExcelExporter
from voter_match.export.pdf_export import PdfExporter
from voter_match.core.duplicates import DuplicateDetector
FILE_A = PROJECT_ROOT / "sample_data" / "Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx"
FILE_B = PROJECT_ROOT / "sample_data" / "Chanchpur_Bhatela_Check_List_B.xlsx"

def run_test():
    print(f"Reading List A (Reference): {FILE_A.name}")
    df_a = pd.read_excel(FILE_A)
    print(f"List A Shape: {df_a.shape}")
    print(f"List A Columns: {df_a.columns.tolist()}")

    print(f"\nReading List B (Verification): {FILE_B.name}")
    df_b = pd.read_excel(FILE_B)
    print(f"List B Shape: {df_b.shape}")
    print(f"List B Columns: {df_b.columns.tolist()}")

    # Setup mappings
    mappings = [
        ColumnMapping(role="serial_no", col_a="क्रम संख्या", col_b="क्र०सं०", importance="Paper Ref"),
        ColumnMapping(role="voter_name", col_a="नाम", col_b="निर्वाचक का नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता/पति का नाम", col_b="पिता/पति/माता का नाम", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium", col_type="number", tolerance=3),
        ColumnMapping(role="gender", col_a="लिंग", col_b="लिंग", importance="Low", col_type="category"),
        ColumnMapping(role="house_no", col_a="मकान संख्या", col_b="मकान नं०", importance="Bonus only"),
    ]

    records_a = df_a.to_dict(orient="records")
    records_b = df_b.to_dict(orient="records")

    print("\nStarting Matching Pipeline (Optimal Assignment + Blocking)...")
    start_time = time.time()
    matcher = ElectoralRollMatcher(mappings)
    res = matcher.run_matching(records_a, records_b)
    elapsed = time.time() - start_time
    print(f"Matching finished in {elapsed:.2f} seconds!")

    print("\n=== Matching Statistics ===")
    for k, v in res.stats.items():
        pct = (v / len(records_b)) * 100 if k != "केवल सूची A में" else (v / len(records_a)) * 100
        print(f"  • {k}: {v} ({pct:.1f}%)")

    # Inspect a few sample matches
    print("\n=== Sample Matched Records (मिला) ===")
    matched_recs = [r for r in res.records_b if r.tier == "मिला"][:5]
    for r in matched_recs:
        b_name = r.record_b.get("निर्वाचक का नाम")
        b_rel = r.record_b.get("पिता/पति/माता का नाम")
        b_kram = r.record_b.get("क्र०सं०")
        a_name = r.assigned_record_a.get("नाम")
        a_rel = r.assigned_record_a.get("पिता/पति का नाम")
        a_kram = r.assigned_record_a.get("क्रम संख्या")
        score = int((r.best_score_result.score if r.best_score_result else 0) * 100)
        reasons = "; ".join(r.best_score_result.reasons[:2]) if r.best_score_result else ""
        print(f"  [क्र० {b_kram} -> {a_kram}] '{b_name}' ({b_rel}) <=> '{a_name}' ({a_rel}) | स्कोर: {score}% | कारण: {reasons}")

    print("\n=== Sample Review Records (जाँचें) ===")
    review_recs = [r for r in res.records_b if r.tier == "जाँचें"][:5]
    for r in review_recs:
        b_name = r.record_b.get("निर्वाचक का नाम")
        b_rel = r.record_b.get("पिता/पति/माता का नाम")
        b_kram = r.record_b.get("क्र०सं०")
        cand = r.top_candidates[0] if r.top_candidates else None
        a_name = cand.record_a.get("नाम") if cand else "-"
        a_rel = cand.record_a.get("पिता/पति का नाम") if cand else "-"
        a_kram = cand.record_a.get("क्रम संख्या") if cand else "-"
        score = int(cand.score_result.score * 100) if cand else 0
        reasons = "; ".join(cand.score_result.reasons[:2]) if cand else ""
        print(f"  [क्र० {b_kram} ?-> {a_kram}] '{b_name}' ({b_rel}) <?> '{a_name}' ({a_rel}) | स्कोर: {score}% | कारण: {reasons}")

    print("\n=== Sample Missing Records (लापता) ===")
    missing_recs = [r for r in res.records_b if r.tier == "लापता"][:5]
    for r in missing_recs:
        b_name = r.record_b.get("निर्वाचक का नाम")
        b_rel = r.record_b.get("पिता/पति/माता का नाम")
        b_kram = r.record_b.get("क्र०सं०")
        print(f"  [क्र० {b_kram}] '{b_name}' ({b_rel}) — संदर्भ सूची में नहीं मिला")

    # Export Excel
    out_excel = PROJECT_ROOT / "sample_data" / "Chanchpur_Bhatela_Matching_Report.xlsx"
    print(f"\nExporting Formatted Excel: {out_excel.name}")
    exporter = ExcelExporter(res, mappings, label_a="2026 विधानसभा सूची A", label_b="सत्यापन सूची B")
    exporter.export(out_excel)
    print(f"Excel Export Complete! Size: {out_excel.stat().st_size:,} bytes")

    # Export PDF
    out_pdf = PROJECT_ROOT / "sample_data" / "Chanchpur_Bhatela_Matching_Report.pdf"
    print(f"\nExporting Printable PDF: {out_pdf.name}")
    pdf_exporter = PdfExporter(res, mappings, label_a="2026 विधानसभा सूची A", label_b="सत्यापन सूची B")
    pdf_exporter.export(out_pdf)
    print(f"PDF Export Complete! Size: {out_pdf.stat().st_size:,} bytes")

if __name__ == "__main__":
    run_test()
