"""Global Fuzzy Search Page (त्वरित खोज).

Type any Hindi (or English) spelling variation of a name and instantly see the
most similar voters from both List A and List B, with enough detail (serial no.,
relative name, age, gender, house no.) to identify the right person.

Layout: one compact toolbar row; everything else is result tables.
"""

from __future__ import annotations
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from voter_match.core.column_suggest import ROLE_KEYWORDS, suggest_columns
import re

from voter_match.core.normalize import NormalizedName, get_default_normalizer, normalize_hindi_name
from voter_match.core.similarity import name_similarity
from voter_match.ui.i18n import mark_translatable
from voter_match.ui.theme import BORDER_COLOR, NAVY_PRIMARY, TEXT_DARK, scoped_style

MAX_RESULTS = 50
MIN_SIMILARITY = 0.40
ROLES = ["serial_no", "epic", "voter_name", "relative_name", "age", "gender", "house_no"]

MODE_NAME = "name"
MODE_RELATIVE = "relative"
MODE_BOTH = "both"
MODE_SERIAL = "serial"

HEADERS = ["#", "समानता", "क्र०", "मतदाता का नाम", "पिता/पति का नाम", "आयु", "लिंग", "मकान", "मूल पंक्ति"]


def normalize_epic_like(val: Any) -> str:
    """Serial numbers / EPIC: Devanagari digits -> ASCII, uppercase alphanumerics,
    leading zeros dropped from pure numbers ('०१२' == '12')."""
    if val is None:
        return ""
    s = re.sub(r"[^A-Z0-9]", "", get_default_normalizer().normalize_digits(str(val)).upper())
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


class _ListSide:
    """Search state for one list (A or B)."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.cols: dict[str, str | None] = {}
        self.norm_voter: list[NormalizedName] = []
        self.norm_rel: list[NormalizedName] = []

    def load(self, records: list[dict[str, Any]], cols: dict[str, str | None]) -> None:
        self.records = records
        self.cols = cols
        v, r = cols.get("voter_name"), cols.get("relative_name")
        self.norm_voter = [normalize_hindi_name(rec.get(v)) for rec in records] if v else []
        self.norm_rel = [normalize_hindi_name(rec.get(r)) for rec in records] if r else []

    def value(self, rec: dict[str, Any], role: str) -> str:
        col = self.cols.get(role)
        if not col:
            return ""
        v = rec.get(col, "")
        s = "" if v is None else str(v).strip()
        return "" if s.lower() == "nan" else s


class SearchPage(QWidget):
    """Global search across both lists with live Indic ranking."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.side_a = _ListSide()
        self.side_b = _ListSide()
        self._raw_a: list[dict[str, Any]] = []
        self._raw_b: list[dict[str, Any]] = []
        self._cols_a: list[str] = []
        self._cols_b: list[str] = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.run_search)
        self.init_ui()

    # Legacy attribute names used elsewhere/tests
    @property
    def records_a(self) -> list[dict[str, Any]]:
        return self.side_a.records

    @property
    def records_b(self) -> list[dict[str, Any]]:
        return self.side_b.records

    # ------------------------------------------------------------------ UI

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Single compact toolbar (~40px): title | search box | mode | count | button
        bar = QFrame()
        scoped_style(bar, "background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 5, 10, 5)
        bar_layout.setSpacing(8)

        title = QLabel("🔍 त्वरित खोज")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {NAVY_PRIMARY};")
        title.setToolTip(
            "किसी भी मतदाता को तुरंत खोजें — नाम की स्पेलिंग गलत हो तब भी "
            "(जैसे 'सुनील' की जगह 'सुनिल', 'ओमप्रकाश' की जगह 'ओमप्काश', या अंग्रेज़ी में 'Sunil')।"
        )
        bar_layout.addWidget(title)

        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText(
            "नाम टाइप करें — गलत स्पेलिंग भी चलेगी (उदा० सुनिल, ओमप्काश, जमीलखां, Ram Prasad)"
        )
        self.txt_query.setClearButtonEnabled(True)
        self.txt_query.setStyleSheet("font-size: 14px; padding: 5px 8px;")
        self.txt_query.textChanged.connect(self._on_text_changed)
        self.txt_query.returnPressed.connect(self.run_search)
        bar_layout.addWidget(self.txt_query, stretch=1)

        lbl_mode = QLabel("खोजें:")
        lbl_mode.setStyleSheet("font-weight: bold; color: #334155;")
        bar_layout.addWidget(lbl_mode)

        self.combo_mode = mark_translatable(QComboBox())
        self.combo_mode.addItem("मतदाता का नाम", MODE_NAME)
        self.combo_mode.addItem("पिता/पति का नाम", MODE_RELATIVE)
        self.combo_mode.addItem("दोनों नाम", MODE_BOTH)
        self.combo_mode.addItem("क्र० सं० / EPIC", MODE_SERIAL)
        self.combo_mode.currentIndexChanged.connect(self.run_search)
        bar_layout.addWidget(self.combo_mode)

        self.btn_search = QPushButton("खोजें")
        self.btn_search.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 6px 18px; border-radius: 5px;"
        )
        self.btn_search.clicked.connect(self.run_search)
        bar_layout.addWidget(self.btn_search)

        main_layout.addWidget(bar)

        self.lbl_status = QLabel("सूचियाँ लोड करने के बाद ऊपर नाम टाइप करें — परिणाम तुरंत दिखेंगे।")
        self.lbl_status.setStyleSheet("color: #475569; font-size: 12px; padding: 0 4px;")
        main_layout.addWidget(self.lbl_status)

        # Results take all remaining space
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.table_a, self.lbl_a = self._make_result_panel(splitter, "सूची A (संदर्भ)")
        self.table_b, self.lbl_b = self._make_result_panel(splitter, "सूची B (सत्यापन)")
        splitter.setSizes([500, 500])
        main_layout.addWidget(splitter, stretch=1)

    def _make_result_panel(self, splitter: QSplitter, title: str) -> tuple[QTableWidget, QLabel]:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lbl = QLabel(f"<b>{title}</b>")
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet(f"color: {NAVY_PRIMARY}; font-size: 13px; padding: 2px 4px;")
        lay.addWidget(lbl)

        table = mark_translatable(QTableWidget(0, len(HEADERS)))
        table.setHorizontalHeaderLabels(HEADERS)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(28)
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        table.setStyleSheet(
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 13px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 5px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 2px 4px; }}"
        )
        lay.addWidget(table, stretch=1)
        splitter.addWidget(panel)
        return table, lbl

    # ------------------------------------------------------------------ data

    @staticmethod
    def _resolve_cols(cols: list[str], mappings: list | None, side: str) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        if mappings:
            for m in mappings:
                if m.role in ROLES:
                    col = m.col_a if side == "a" else m.col_b
                    if col and col in cols:
                        out[m.role] = col
        missing = [r for r in ROLES if r not in out]
        if missing:
            used = set(out.values())
            sug = suggest_columns([c for c in cols if c not in used], missing,
                                  {r: ROLE_KEYWORDS[r] for r in missing})
            out.update(sug)
        return out

    def set_data(
        self,
        recs_a: list[dict[str, Any]],
        recs_b: list[dict[str, Any]],
        cols_a: list[str],
        cols_b: list[str],
        mappings: list | None = None,
    ) -> None:
        self._raw_a, self._raw_b = recs_a, recs_b
        self._cols_a, self._cols_b = cols_a, cols_b
        self.side_a.load(recs_a, self._resolve_cols(cols_a, mappings, "a"))
        self.side_b.load(recs_b, self._resolve_cols(cols_b, mappings, "b"))
        self.lbl_status.setText(
            f"सूची A: {len(recs_a):,} मतदाता | सूची B: {len(recs_b):,} मतदाता — ऊपर नाम टाइप करें।"
        )
        if self.txt_query.text().strip():
            self.run_search()

    def set_mappings(self, mappings: list) -> None:
        """Use the confirmed Step-2 column mapping (more reliable than guessing)."""
        if self._raw_a or self._raw_b:
            self.set_data(self._raw_a, self._raw_b, self._cols_a, self._cols_b, mappings)

    # ------------------------------------------------------------------ search

    def _on_text_changed(self, text: str) -> None:
        if len(text.strip()) >= 2:
            self._debounce.start()
        elif not text.strip():
            self.table_a.setRowCount(0)
            self.table_b.setRowCount(0)

    def _score_side(self, side: _ListSide, query: str, mode: str) -> list[tuple[float, str, int]]:
        scored: list[tuple[float, str, int]] = []
        if mode == MODE_SERIAL:
            q = normalize_epic_like(query)
            for i, rec in enumerate(side.records):
                serial = normalize_epic_like(side.value(rec, "serial_no"))
                epic = normalize_epic_like(side.value(rec, "epic"))
                if q and (q == serial or q == epic):
                    scored.append((1.0, "पूर्ण समान", i))
                elif q and len(q) >= 3 and epic and q in epic:
                    scored.append((0.9, "EPIC का भाग", i))
            return scored

        nq = normalize_hindi_name(query)
        for i in range(len(side.records)):
            best, how = 0.0, ""
            if mode in (MODE_NAME, MODE_BOTH) and i < len(side.norm_voter):
                best, how = name_similarity(nq, side.norm_voter[i])
            if mode in (MODE_RELATIVE, MODE_BOTH) and i < len(side.norm_rel):
                s, m = name_similarity(nq, side.norm_rel[i])
                if s > best:
                    best, how = s, ("पिता/पति नाम: " + m) if mode == MODE_BOTH else m
            if best > MIN_SIMILARITY:
                scored.append((best, how, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def run_search(self) -> None:
        self._debounce.stop()
        query = self.txt_query.text().strip()
        if not query:
            return
        mode = self.combo_mode.currentData() or MODE_NAME
        res_a = self._score_side(self.side_a, query, mode)
        res_b = self._score_side(self.side_b, query, mode)
        self._populate(self.table_a, self.side_a, res_a[:MAX_RESULTS])
        self._populate(self.table_b, self.side_b, res_b[:MAX_RESULTS])
        self.lbl_a.setText(f"<b>सूची A (संदर्भ)</b> — {min(len(res_a), MAX_RESULTS)} / {len(res_a)} परिणाम")
        self.lbl_b.setText(f"<b>सूची B (सत्यापन)</b> — {min(len(res_b), MAX_RESULTS)} / {len(res_b)} परिणाम")
        if not res_a and not res_b:
            self.lbl_status.setText(f"'{query}' से मिलता-जुलता कोई मतदाता नहीं मिला। स्पेलिंग बदलकर या 'खोजें' विकल्प बदलकर देखें।")
        else:
            self.lbl_status.setText(
                f"'{query}' के लिए परिणाम — सबसे अधिक समानता वाले ऊपर। हरा ≥ 88%, पीला ≥ 70%। "
                "समानता पर माउस रखें तो मिलान का प्रकार दिखेगा।"
            )

    # Backwards-compatible name
    def _populate_search_table(self, table, items, voter_col) -> None:  # pragma: no cover
        self.run_search()

    def _populate(self, table: QTableWidget, side: _ListSide, items: list[tuple[float, str, int]]) -> None:
        table.setRowCount(len(items))
        dark = QBrush(QColor(15, 23, 42))
        muted = QBrush(QColor(71, 85, 105))
        bold = QFont("Nirmala UI", 10, QFont.Bold)
        for row, (sim, method, idx) in enumerate(items):
            rec = side.records[idx]
            orig_row = rec.get("_orig_row", idx + 2)
            values = [
                str(row + 1),
                f"{int(sim * 100)}%",
                side.value(rec, "serial_no"),
                side.value(rec, "voter_name"),
                side.value(rec, "relative_name"),
                side.value(rec, "age"),
                side.value(rec, "gender"),
                side.value(rec, "house_no"),
                str(orig_row),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setForeground(dark if col in (3, 4) else muted)
                if col in (0, 1, 2, 5, 6, 7, 8):
                    item.setTextAlignment(Qt.AlignCenter)
                if col == 3:
                    item.setFont(bold)
                if col == 1:
                    item.setFont(bold)
                    item.setToolTip(f"मिलान का प्रकार: {method}")
                    if sim >= 0.88:
                        item.setBackground(QBrush(QColor(220, 252, 231)))
                        item.setForeground(QBrush(QColor(22, 101, 52)))
                    elif sim >= 0.70:
                        item.setBackground(QBrush(QColor(254, 243, 199)))
                        item.setForeground(QBrush(QColor(146, 64, 14)))
                table.setItem(row, col, item)
