"""Multi-booth batch matching.

Runs several (List A, List B) file pairs in one go — e.g. every part number
of a polling station — re-using one column-mapping template. Column names
that differ between files are re-resolved by keyword auto-suggestion.
Each pair gets its own full Excel report, plus one combined summary workbook.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from voter_match.core.matcher import ElectoralRollMatcher, MatchSessionResult
from voter_match.core.scorer import ColumnMapping

from voter_match.core.column_suggest import ROLE_KEYWORDS, column_role_score, suggest_columns


def find_best_column(cols: list[str], keywords: list[str], exclude: set[str] | None = None) -> str | None:
    best_col, best = None, 0.0
    for col in cols:
        if exclude and col in exclude:
            continue
        sc = column_role_score("", col, keywords)
        if sc > best and sc >= 60.0:
            best_col, best = col, sc
    return best_col


def load_table(path: str | Path, sheet: str | int = 0, header_row: int = 1) -> tuple[list[str], list[dict[str, Any]]]:
    """Read an Excel/CSV voter list with the same cleaning as the import screen."""
    path = Path(path)
    hdr = max(0, header_row - 1)
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, sheet_name=sheet, header=hdr)
    else:
        try:
            df = pd.read_csv(path, header=hdr, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(path, header=hdr, encoding="latin1")
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    df["_orig_row"] = df.index + hdr + 2
    text_cols = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype) in ("str", "string")]
    for c in text_cols:
        df[c] = df[c].astype(str).str.strip().replace("nan", "")
    cols = [c for c in df.columns if c != "_orig_row"]
    return cols, df.to_dict(orient="records")


def resolve_mappings(template: list[ColumnMapping], cols_a: list[str], cols_b: list[str]) -> list[ColumnMapping]:
    """Adapt a mapping template to a new file pair's actual column headers."""
    roles = [m.role for m in template]
    sug_a = suggest_columns(cols_a, roles)
    sug_b = suggest_columns(cols_b, roles)
    out: list[ColumnMapping] = []
    for m in template:
        col_a = m.col_a if m.col_a in cols_a else (sug_a.get(m.role) if m.col_a else None)
        col_b = m.col_b if m.col_b in cols_b else (sug_b.get(m.role) if m.col_b else None)
        out.append(replace(m, col_a=col_a, col_b=col_b))
    return out


@dataclass
class BatchJob:
    file_a: str
    file_b: str
    label: str = ""

    def display_name(self) -> str:
        return self.label or Path(self.file_b).stem


@dataclass
class BatchOutcome:
    job: BatchJob
    stats: dict[str, int] = field(default_factory=dict)
    total_a: int = 0
    total_b: int = 0
    report_path: str = ""
    elapsed: float = 0.0
    error: str = ""
    result: MatchSessionResult | None = None
    mappings: list[ColumnMapping] = field(default_factory=list)


def _safe_name(name: str) -> str:
    keep = "".join(ch if (ch.isalnum() or ch in " _-") else "_" for ch in name).strip()
    return keep[:80] or "report"


def run_batch(
    jobs: list[BatchJob],
    template: list[ColumnMapping],
    output_dir: str | Path,
    matcher_kwargs: dict[str, Any] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    keep_results: bool = False,
) -> tuple[list[BatchOutcome], str]:
    """Run all jobs sequentially. Returns (outcomes, combined_summary_path)."""
    from voter_match.export.excel_export import ExcelExporter

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    outcomes: list[BatchOutcome] = []
    kwargs = dict(matcher_kwargs or {})

    for i, job in enumerate(jobs):
        if is_cancelled and is_cancelled():
            break
        name = job.display_name()
        if progress:
            progress(i, len(jobs), f"({i + 1}/{len(jobs)}) {name}: मिलान जारी...")
        oc = BatchOutcome(job=job)
        t0 = time.time()
        try:
            cols_a, recs_a = load_table(job.file_a)
            cols_b, recs_b = load_table(job.file_b)
            mappings = resolve_mappings(template, cols_a, cols_b)
            if not any(m.role == "voter_name" and m.is_active() for m in mappings):
                raise ValueError("मतदाता नाम का कॉलम दोनों फ़ाइलों में नहीं मिला")
            matcher = ElectoralRollMatcher(mappings=mappings, **kwargs)
            res = matcher.run_matching(recs_a, recs_b)
            report = out_dir / f"{i + 1:02d}_{_safe_name(name)}_मिलान_रिपोर्ट.xlsx"
            ExcelExporter(res, mappings).export(report)
            oc.stats = dict(res.stats)
            oc.total_a, oc.total_b = len(recs_a), len(recs_b)
            oc.report_path = str(report)
            oc.mappings = mappings
            if keep_results:
                oc.result = res
        except Exception as e:  # one bad file must not stop the whole batch
            oc.error = str(e)
        oc.elapsed = time.time() - t0
        outcomes.append(oc)

    summary_path = str(out_dir / "00_संयुक्त_सारांश_Combined_Summary.xlsx")
    export_batch_summary(outcomes, summary_path)
    if progress:
        progress(len(jobs), len(jobs), "बैच मिलान पूर्ण!")
    return outcomes, summary_path


def export_batch_summary(outcomes: list[BatchOutcome], output_path: str) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from voter_match.export.excel_export import CELL_BORDER, auto_fit_columns, style_print_setup

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "संयुक्त सारांश"
    headers = ["क्र०", "भाग / बूथ", "सूची A फ़ाइल", "सूची B फ़ाइल", "सूची A मतदाता", "सूची B मतदाता",
               "मिला", "जाँचें", "लापता", "केवल सूची A में", "मिलान %", "समय (सेकंड)", "रिपोर्ट / त्रुटि"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(1, 1, "बहु-बूथ बैच मिलान — संयुक्त सारांश (Multi-Booth Batch Summary)")
    ws.cell(1, 1).font = Font(name="Nirmala UI", size=14, bold=True, color="FFFFFF")
    ws.cell(1, 1).fill = PatternFill("solid", fgColor="1F4E79")
    ws.cell(1, 1).alignment = Alignment(horizontal="center")
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(2, c, h)
        cell.font = Font(name="Nirmala UI", bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E1F2")
        cell.border = CELL_BORDER

    totals = {"a": 0, "b": 0, "मिला": 0, "जाँचें": 0, "लापता": 0, "केवल सूची A में": 0}
    row = 3
    for i, oc in enumerate(outcomes, start=1):
        st = oc.stats
        pct = f"{(st.get('मिला', 0) / oc.total_b) * 100:.1f}%" if oc.total_b else "-"
        vals = [i, oc.job.display_name(), Path(oc.job.file_a).name, Path(oc.job.file_b).name,
                oc.total_a, oc.total_b, st.get("मिला", 0), st.get("जाँचें", 0), st.get("लापता", 0),
                st.get("केवल सूची A में", 0), pct, round(oc.elapsed, 1),
                (f"त्रुटि: {oc.error}" if oc.error else Path(oc.report_path).name)]
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row, c, v)
            cell.font = Font(name="Nirmala UI", color="9C0006" if oc.error else "000000")
            cell.border = CELL_BORDER
        if not oc.error:
            totals["a"] += oc.total_a
            totals["b"] += oc.total_b
            for k in ("मिला", "जाँचें", "लापता", "केवल सूची A में"):
                totals[k] += st.get(k, 0)
        row += 1

    pct = f"{(totals['मिला'] / totals['b']) * 100:.1f}%" if totals["b"] else "-"
    tot_vals = ["", "कुल योग", "", "", totals["a"], totals["b"], totals["मिला"], totals["जाँचें"],
                totals["लापता"], totals["केवल सूची A में"], pct, "", ""]
    for c, v in enumerate(tot_vals, start=1):
        cell = ws.cell(row, c, v)
        cell.font = Font(name="Nirmala UI", bold=True)
        cell.fill = PatternFill("solid", fgColor="E2EFDA")
        cell.border = CELL_BORDER
    ws.freeze_panes = "A3"
    style_print_setup(ws)
    auto_fit_columns(ws, max_width=40)
    wb.save(output_path)
