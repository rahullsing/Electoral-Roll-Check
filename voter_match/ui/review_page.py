"""Side-by-Side Verification Screen (स्थलीय सत्यापन).

Space-optimized, high-efficiency dashboard designed for Government School Teachers and BLOs.
Includes live decision tracking, field remarks/notes, 1-click updated Excel export,
bulk high-confidence auto-approval, and keyboard-driven rapid verification.
"""

from __future__ import annotations
import difflib
from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QColor, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QFrame,
    QScrollArea,
    QSplitter,
    QMessageBox,
    QFileDialog,
    QCheckBox,
    QSizePolicy,
)

from voter_match.core.matcher import MatchRecordB, MatchCandidate, MatchSessionResult
from voter_match.core.scorer import ColumnMapping
from voter_match.storage.db import get_default_storage
from voter_match.core.learning import get_default_alias_manager
from voter_match.export.excel_export import ExcelExporter
from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    TEXT_MUTED,
    GREEN_PRIMARY,
    GREEN_BG,
    GREEN_TEXT,
    AMBER_BG,
    AMBER_TEXT,
    RED_BG,
    RED_TEXT,
    RED_PRIMARY,
    BORDER_COLOR,
)

COMMON_FIELD_REMARKS = [
    "-- सामान्य सत्यापन --",
    "मौके पर भौतिक रूप से सत्यापित (समान व्यक्ति)",
    "मृतक (विलोपन हेतु प्रारूप 7 आवश्यक)",
    "स्थानांतरित (अन्यत्र निवास)",
    "विवाहोपरांत अन्यत्र प्रस्थान",
    "अनुपस्थित / ताला बंद",
    "नया मतदाता (प्रारूप 6 आवश्यक)",
    "नाम वर्तनी लिपिकीय त्रुटि (संशोधन प्रारूप 8)",
]


def highlight_diff_html(s1: str, s2: str) -> tuple[str, str]:
    """Generate HTML highlighting identical vs differing characters with high contrast."""
    s1 = s1 or ""
    s2 = s2 or ""
    matcher = difflib.SequenceMatcher(None, s1, s2)
    h1 = []
    h2 = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        sub1 = s1[i1:i2]
        sub2 = s2[j1:j2]
        if tag == "equal":
            h1.append(f"<span style='color: #15803D; font-weight: bold;'>{sub1}</span>")
            h2.append(f"<span style='color: #15803D; font-weight: bold;'>{sub2}</span>")
        else:
            h1.append(
                f"<span style='background-color: #FEE2E2; color: #991B1B; font-weight: bold; "
                f"border-radius: 2px; padding: 0 2px; text-decoration: underline;'>{sub1}</span>"
            )
            h2.append(
                f"<span style='background-color: #FEF3C7; color: #92400E; font-weight: bold; "
                f"border-radius: 2px; padding: 0 2px; text-decoration: underline;'>{sub2}</span>"
            )

    return "".join(h1), "".join(h2)


class CandidateCardWidget(QFrame):
    """Card displaying a candidate match from List A with score and diffs."""

    def __init__(
        self,
        candidate_num: int,
        candidate: MatchCandidate | None,
        query_voter_name: str,
        query_rel_name: str,
        voter_col_a: str,
        rel_col_a: str,
        mappings: list[ColumnMapping],
        is_selected: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.candidate_num = candidate_num
        self.candidate = candidate
        self.voter_col_a = voter_col_a
        self.rel_col_a = rel_col_a
        self.query_voter_name = query_voter_name
        self.query_rel_name = query_rel_name
        self.mappings = mappings
        self.is_selected = is_selected
        self.init_ui()

    def init_ui(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        card_border = "#16A34A" if self.is_selected else BORDER_COLOR
        card_bg = "#F0FDF4" if self.is_selected else "#FFFFFF"
        self.setStyleSheet(
            f"QFrame {{ border: 2px solid {card_border}; border-radius: 6px; "
            f"background-color: {card_bg}; padding: 6px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        if not self.candidate:
            lbl_none = QLabel(f"प्रत्याशी {self.candidate_num}: कोई निकटतम प्रत्याशी उपलब्ध नहीं")
            lbl_none.setStyleSheet("color: #94A3B8; font-style: italic;")
            layout.addWidget(lbl_none)
            return

        rec_a = self.candidate.record_a
        score_res = self.candidate.score_result
        score_pct = int(score_res.score * 100)

        # Header Row
        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)

        if score_pct >= 90:
            badge_bg, badge_txt = "#DCFCE7", "#166534"
        elif score_pct >= 72:
            badge_bg, badge_txt = "#FEF3C7", "#92400E"
        else:
            badge_bg, badge_txt = "#FEE2E2", "#991B1B"

        lbl_num = QLabel(f"विकल्प {self.candidate_num} (की: [{self.candidate_num}])")
        lbl_num.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY};")
        hdr.addWidget(lbl_num)

        serial_map = next((m for m in self.mappings if m.role == "serial_no"), None)
        kram_col_a = serial_map.col_a if serial_map else None
        cand_kram = str(rec_a.get(kram_col_a, "")) if kram_col_a and kram_col_a in rec_a else ""
        if cand_kram:
            lbl_kram = QLabel(f"🔢 कागज़ी क्र०: <b>{cand_kram}</b>")
            lbl_kram.setStyleSheet("color: #6D28D9; background-color: #EDE9FE; padding: 2px 8px; border-radius: 4px; font-size: 11px; border: 1px solid #DDD6FE;")
            hdr.addWidget(lbl_kram)

        hdr.addStretch()

        lbl_score = QLabel(f" स्कोर: {score_pct}% ")
        lbl_score.setStyleSheet(
            f"background-color: {badge_bg}; color: {badge_txt}; font-weight: bold; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 12px;"
        )
        hdr.addWidget(lbl_score)
        layout.addLayout(hdr)

        # Names with Character Diff Highlighting
        cand_voter = str(rec_a.get(self.voter_col_a, "") or "")
        cand_rel = str(rec_a.get(self.rel_col_a, "") or "")

        _, diff_voter = highlight_diff_html(self.query_voter_name, cand_voter)
        _, diff_rel = highlight_diff_html(self.query_rel_name, cand_rel)

        lbl_voter = QLabel(f"मतदाता: <span style='font-size: 15px; font-weight: bold;'>{diff_voter}</span>")
        lbl_voter.setTextFormat(Qt.RichText)
        lbl_voter.setStyleSheet("font-size: 12px; color: #0F172A;")
        layout.addWidget(lbl_voter)

        lbl_rel = QLabel(f"सम्बन्धी: <span style='font-size: 14px; font-weight: bold;'>{diff_rel}</span>")
        lbl_rel.setTextFormat(Qt.RichText)
        lbl_rel.setStyleSheet("font-size: 12px; color: #0F172A;")
        layout.addWidget(lbl_rel)

        # Details Grid
        details_list = []
        for m in self.mappings:
            if m.role in {"voter_name", "relative_name"} or not m.col_a:
                continue
            val = str(rec_a.get(m.col_a, "") or "")
            if val:
                details_list.append(f"<b>{m.role}:</b> {val}")

        if details_list:
            lbl_det = QLabel(" | ".join(details_list))
            lbl_det.setTextFormat(Qt.RichText)
            lbl_det.setStyleSheet("font-size: 11px; color: #475569;")
            layout.addWidget(lbl_det)

        # Reasons
        if score_res.reasons:
            reasons_text = " • " + " • ".join(score_res.reasons[:3])
            lbl_reasons = QLabel(reasons_text)
            lbl_reasons.setStyleSheet(
                "color: #475569; font-size: 11px; background-color: #F8FAFC; "
                "padding: 3px 6px; border-radius: 4px; border: 1px solid #E2E8F0;"
            )
            layout.addWidget(lbl_reasons)


class ReviewPage(QWidget):
    """Side-by-Side Review Page for Verification by BLOs."""

    session_updated = Signal()
    save_session_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.session_result: MatchSessionResult | None = None
        self.records: list[MatchRecordB] = []
        self.filtered_indices: list[int] = []
        self.current_pos: int = 0
        self.mappings: list[ColumnMapping] = []
        self.session_id: str = "default_session"
        self.storage = get_default_storage()
        self.alias_mgr = get_default_alias_manager()
        self.init_ui()
        self.setup_shortcuts()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Compact Top Toolbar (Filters + Search + Live Stats + Download Updated Excel)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        lbl_step = QLabel("चरण 4: स्थलीय सत्यापन (Review)")
        lbl_step.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {NAVY_PRIMARY};")
        top_bar.addWidget(lbl_step)

        self.combo_tier = QComboBox()
        self.combo_tier.addItems(["जाँचें (सत्यापन आवश्यक)", "सभी मतदाता", "लापता", "मिला"])
        self.combo_tier.setCurrentText("जाँचें (सत्यापन आवश्यक)")
        self.combo_tier.currentIndexChanged.connect(self.apply_filter)
        top_bar.addWidget(self.combo_tier)

        self.chk_unreviewed_only = QCheckBox("केवल असत्यापित (Pending)")
        self.chk_unreviewed_only.setStyleSheet("font-weight: bold; color: #1E293B; font-size: 12px;")
        self.chk_unreviewed_only.toggled.connect(self.apply_filter)
        top_bar.addWidget(self.chk_unreviewed_only)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 नाम या मकान नं० खोजें...")
        self.txt_search.setMaximumWidth(160)
        self.txt_search.textChanged.connect(self.apply_filter)
        top_bar.addWidget(self.txt_search)

        top_bar.addStretch()

        # Live Review Progress Tracker Badge
        self.lbl_progress_badge = QLabel("📊 सत्यापित: 0 | शेष: 0")
        self.lbl_progress_badge.setStyleSheet(
            f"background-color: {AMBER_BG}; color: {AMBER_TEXT}; font-weight: bold; "
            f"font-size: 12px; padding: 5px 10px; border-radius: 4px; border: 1px solid #FCD34D;"
        )
        top_bar.addWidget(self.lbl_progress_badge)

        # Segment-Leading Power Feature 1: Bulk Auto-Approve High-Confidence Matches
        self.btn_bulk_accept = QPushButton("⚡ उच्च समानता वाले स्वतः स्वीकारें (>85%)")
        self.btn_bulk_accept.setStyleSheet(
            "background-color: #0284C7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px; font-size: 11px;"
        )
        self.btn_bulk_accept.setToolTip("सभी 85% से अधिक स्कोर वाले प्रत्याशियों को एक क्लिक में सत्यापित करें")
        self.btn_bulk_accept.clicked.connect(self.bulk_auto_accept)
        top_bar.addWidget(self.btn_bulk_accept)

        # Star Feature: Download Updated Excel right from the Review Screen!
        self.btn_download_updated = QPushButton("📥 अद्यतन Excel डाउनलोड करें")
        self.btn_download_updated.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 6px 14px; border-radius: 4px; font-size: 12px;"
        )
        self.btn_download_updated.setToolTip("सत्यापन निर्णयों और टिप्पणियों के साथ अद्यतन 5-शीट Excel रिपोर्ट डाउनलोड करें")
        self.btn_download_updated.clicked.connect(self.download_updated_excel)
        top_bar.addWidget(self.btn_download_updated)

        main_layout.addLayout(top_bar)

        # Splitter taking up 85%+ of screen
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # LEFT PANEL: List B Record
        self.box_b = QGroupBox("सूची B (सत्यापन योग्य मतदाता विवरण)")
        self.box_b.setStyleSheet(f"QGroupBox {{ font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY}; }}")
        layout_b = QVBoxLayout(self.box_b)
        layout_b.setContentsMargins(8, 10, 8, 8)
        layout_b.setSpacing(6)

        self.lbl_b_orig_row = QLabel("मूल फ़ाइल पंक्ति: -")
        self.lbl_b_orig_row.setStyleSheet("color: #64748B; font-size: 11px;")
        layout_b.addWidget(self.lbl_b_orig_row)

        self.lbl_b_name = QLabel("नाम: -")
        self.lbl_b_name.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {NAVY_PRIMARY}; margin: 2px 0;")
        layout_b.addWidget(self.lbl_b_name)

        self.lbl_b_rel = QLabel("सम्बन्धी का नाम: -")
        self.lbl_b_rel.setStyleSheet("font-size: 15px; font-weight: bold; color: #334155; margin-bottom: 4px;")
        layout_b.addWidget(self.lbl_b_rel)

        # Compact details row
        self.lbl_b_details = QLabel("विवरण: -")
        self.lbl_b_details.setStyleSheet("font-size: 12px; color: #475569;")
        layout_b.addWidget(self.lbl_b_details)

        layout_b.addSpacing(6)

        # Field Remarks / Notes Box (BLO Field Notes for Excel)
        lbl_rem_title = QLabel("📝 स्थलीय सत्यापन टिप्पणी / कैफियत (Field Remarks):")
        lbl_rem_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #1E293B;")
        layout_b.addWidget(lbl_rem_title)

        self.combo_remarks = QComboBox()
        self.combo_remarks.addItems(COMMON_FIELD_REMARKS)
        self.combo_remarks.currentTextChanged.connect(self.on_remark_selected)
        layout_b.addWidget(self.combo_remarks)

        self.txt_custom_note = QLineEdit()
        self.txt_custom_note.setPlaceholderText("या यहाँ स्वयं कोई विशिष्ट टिप्पणी लिखें...")
        self.txt_custom_note.textChanged.connect(self.on_custom_note_changed)
        layout_b.addWidget(self.txt_custom_note)

        layout_b.addStretch()

        self.lbl_decision_status = QLabel("स्थिति: लंबित")
        self.lbl_decision_status.setStyleSheet("padding: 6px; font-weight: bold; font-size: 12px; border-radius: 4px; background-color: #F1F5F9;")
        layout_b.addWidget(self.lbl_decision_status)

        self.splitter.addWidget(self.box_b)

        # RIGHT PANEL: Candidates from List A
        self.box_a = QGroupBox("सूची A के निकटतम प्रत्याशी (Top Candidates from Reference Roll)")
        self.box_a.setStyleSheet(f"QGroupBox {{ font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY}; }}")
        layout_a = QVBoxLayout(self.box_a)
        layout_a.setContentsMargins(6, 10, 6, 6)

        self.scroll_candidates = QScrollArea()
        self.scroll_candidates.setWidgetResizable(True)
        self.cands_container = QWidget()
        self.cands_layout = QVBoxLayout(self.cands_container)
        self.cands_layout.setContentsMargins(4, 4, 4, 4)
        self.cands_layout.setSpacing(6)
        self.scroll_candidates.setWidget(self.cands_container)
        layout_a.addWidget(self.scroll_candidates)

        self.splitter.addWidget(self.box_a)
        self.splitter.setSizes([400, 600])
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter, stretch=1)

        # BOTTOM ACTION BAR (Large, intuitive action buttons)
        act_box = QHBoxLayout()
        act_box.setContentsMargins(0, 0, 0, 0)
        act_box.setSpacing(6)

        self.btn_prev = QPushButton("◀ पिछला [←]")
        self.btn_prev.clicked.connect(self.navigate_prev)
        act_box.addWidget(self.btn_prev)

        self.lbl_counter = QLabel("0 / 0 मतदाता")
        self.lbl_counter.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY};")
        act_box.addWidget(self.lbl_counter)

        act_box.addStretch()

        self.btn_pick_1 = QPushButton("1️⃣ प्रत्याशी-1 सही है [1]")
        self.btn_pick_1.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_pick_1.clicked.connect(lambda: self.record_decision("accepted_top1", 0))
        act_box.addWidget(self.btn_pick_1)

        self.btn_pick_2 = QPushButton("2️⃣ प्रत्याशी-2 सही है [2]")
        self.btn_pick_2.setStyleSheet(
            "background-color: #0284C7; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_pick_2.clicked.connect(lambda: self.record_decision("accepted_top2", 1))
        act_box.addWidget(self.btn_pick_2)

        self.btn_pick_3 = QPushButton("3️⃣ प्रत्याशी-3 सही है [3]")
        self.btn_pick_3.setStyleSheet(
            "background-color: #475569; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_pick_3.clicked.connect(lambda: self.record_decision("accepted_top3", 2))
        act_box.addWidget(self.btn_pick_3)

        self.btn_missing = QPushButton("❌ कोई नहीं मिला (लापता) [M]")
        self.btn_missing.setStyleSheet(
            f"background-color: {RED_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_missing.clicked.connect(lambda: self.record_decision("missing", None))
        act_box.addWidget(self.btn_missing)

        self.btn_skip = QPushButton("छोड़ें [S]")
        self.btn_skip.clicked.connect(self.navigate_next)
        act_box.addWidget(self.btn_skip)

        act_box.addStretch()

        self.btn_next = QPushButton("अगला [→] ▶")
        self.btn_next.clicked.connect(self.navigate_next)
        act_box.addWidget(self.btn_next)

        main_layout.addLayout(act_box)

    def setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("1"), self, lambda: self.btn_pick_1.click())
        QShortcut(QKeySequence("2"), self, lambda: self.btn_pick_2.click())
        QShortcut(QKeySequence("3"), self, lambda: self.btn_pick_3.click())
        QShortcut(QKeySequence("M"), self, lambda: self.btn_missing.click())
        QShortcut(QKeySequence("m"), self, lambda: self.btn_missing.click())
        QShortcut(QKeySequence("S"), self, lambda: self.btn_skip.click())
        QShortcut(QKeySequence("s"), self, lambda: self.btn_skip.click())
        QShortcut(QKeySequence(Qt.Key_Left), self, self.navigate_prev)
        QShortcut(QKeySequence(Qt.Key_Right), self, self.navigate_next)

    def set_data(
        self,
        records: list[MatchRecordB],
        mappings: list[ColumnMapping],
        session_result: MatchSessionResult | None = None,
        session_id: str = "default_session",
    ) -> None:
        self.records = records
        self.mappings = mappings
        self.session_result = session_result
        self.session_id = session_id
        self.update_progress_tracker()
        self.apply_filter()

    def update_progress_tracker(self) -> None:
        total = len(self.records)
        verified = sum(1 for r in self.records if r.user_decision is not None)
        pending = total - verified

        pct = int((verified / max(1, total)) * 100)
        self.lbl_progress_badge.setText(f"📊 सत्यापित: {verified}/{total} ({pct}%) | लंबित: {pending}")

        if pending == 0 and total > 0:
            self.lbl_progress_badge.setStyleSheet(
                f"background-color: {GREEN_BG}; color: {GREEN_TEXT}; font-weight: bold; "
                f"font-size: 12px; padding: 5px 10px; border-radius: 4px; border: 1px solid #86EFAC;"
            )
            self.lbl_progress_badge.setText("✅ शत-प्रतिशत सत्यापन पूर्ण! Excel डाउनलोड करें")
        else:
            self.lbl_progress_badge.setStyleSheet(
                f"background-color: {AMBER_BG}; color: {AMBER_TEXT}; font-weight: bold; "
                f"font-size: 12px; padding: 5px 10px; border-radius: 4px; border: 1px solid #FCD34D;"
            )

    def apply_filter(self) -> None:
        tier_filter = self.combo_tier.currentText()
        query = self.txt_search.text().strip().lower()
        unreviewed_only = self.chk_unreviewed_only.isChecked()

        self.filtered_indices = []
        for idx, rec in enumerate(self.records):
            if unreviewed_only and rec.user_decision is not None:
                continue

            if "जाँचें" in tier_filter and rec.tier != "जाँचें":
                continue
            if "लापता" in tier_filter and rec.tier != "लापता":
                continue
            if "मिला" in tier_filter and rec.tier != "मिला":
                continue

            if query:
                rec_text = " ".join(str(v) for v in rec.record_b.values()).lower()
                if query not in rec_text:
                    continue

            self.filtered_indices.append(idx)

        self.current_pos = 0
        self.show_current_record()

    def show_current_record(self) -> None:
        total = len(self.filtered_indices)
        if total == 0:
            self.lbl_counter.setText("0 / 0 मतदाता")
            self.lbl_b_orig_row.setText("कोई रिकॉर्ड उपलब्ध नहीं।")
            self.lbl_b_name.setText("नाम: -")
            self.lbl_b_rel.setText("सम्बन्धी का नाम: -")
            self.lbl_b_details.setText("विवरण: -")
            self.txt_custom_note.blockSignals(True)
            self.txt_custom_note.setText("")
            self.txt_custom_note.blockSignals(False)
            self._clear_candidates()
            return

        self.current_pos = max(0, min(self.current_pos, total - 1))
        rec_idx = self.filtered_indices[self.current_pos]
        rec = self.records[rec_idx]

        self.lbl_counter.setText(f"{self.current_pos + 1} / {total} मतदाता")

        rec_b = rec.record_b
        voter_map = next((m for m in self.mappings if m.role == "voter_name"), None)
        rel_map = next((m for m in self.mappings if m.role == "relative_name"), None)

        voter_col_b = voter_map.col_b if voter_map else ""
        rel_col_b = rel_map.col_b if rel_map else ""

        serial_map = next((m for m in self.mappings if m.role == "serial_no"), None)
        kram_col_b = serial_map.col_b if serial_map else None
        b_kram_val = str(rec_b.get(kram_col_b, "")) if kram_col_b and kram_col_b in rec_b else ""

        orig_row = rec_b.get("_orig_row", rec.b_idx + 2)
        if b_kram_val:
            self.lbl_b_orig_row.setText(f"🔢 कागज़ी क्र०: <b style='color:#6D28D9; font-size:13px;'>{b_kram_val}</b> | मूल पंक्ति: #{orig_row} | ID: #{rec.b_idx + 1}")
        else:
            self.lbl_b_orig_row.setText(f"मूल पंक्ति: #{orig_row} | आंतरिक ID: #{rec.b_idx + 1}")

        b_voter_name = str(rec_b.get(voter_col_b, "") or "")
        b_rel_name = str(rec_b.get(rel_col_b, "") or "")

        self.lbl_b_name.setText(f"नाम: {b_voter_name}")
        self.lbl_b_rel.setText(f"सम्बन्धी: {b_rel_name}")

        # Details string
        details_list = []
        for m in self.mappings:
            if m.role in {"voter_name", "relative_name"} or not m.col_b:
                continue
            val = str(rec_b.get(m.col_b, "") or "")
            if val:
                details_list.append(f"<b>{m.role}:</b> {val}")

        self.lbl_b_details.setText(" | ".join(details_list) if details_list else "-")
        self.lbl_b_details.setTextFormat(Qt.RichText)

        # Set Remarks and Notes
        self.txt_custom_note.blockSignals(True)
        self.txt_custom_note.setText(rec.notes or "")
        self.txt_custom_note.blockSignals(False)

        # Status badge
        if rec.user_decision:
            self.lbl_decision_status.setText(f"✓ निर्णय: {rec.user_decision} (सत्यापित)")
            self.lbl_decision_status.setStyleSheet(
                f"padding: 6px; font-weight: bold; font-size: 12px; border-radius: 4px; "
                f"background-color: {GREEN_BG}; color: {GREEN_TEXT}; border: 1px solid #86EFAC;"
            )
        else:
            self.lbl_decision_status.setText(f"स्थिति: {rec.tier} (कंप्यूटर सुझाव)")
            if rec.tier == "जाँचें":
                bg_c, txt_c, brd = AMBER_BG, AMBER_TEXT, "#FCD34D"
            elif rec.tier == "मिला":
                bg_c, txt_c, brd = GREEN_BG, GREEN_TEXT, "#86EFAC"
            else:
                bg_c, txt_c, brd = RED_BG, RED_TEXT, "#FCA5A5"

            self.lbl_decision_status.setStyleSheet(
                f"padding: 6px; font-weight: bold; font-size: 12px; border-radius: 4px; "
                f"background-color: {bg_c}; color: {txt_c}; border: 1px solid {brd};"
            )

        # Populate candidate cards
        self._clear_candidates()
        voter_col_a = voter_map.col_a if voter_map else ""
        rel_col_a = rel_map.col_a if rel_map else ""

        if not rec.top_candidates:
            lbl_none = QLabel("सूची A में कोई निकटतम प्रत्याशी नहीं मिला।")
            lbl_none.setStyleSheet("color: #94A3B8; font-style: italic; padding: 20px;")
            self.cands_layout.addWidget(lbl_none)
        else:
            for c_i, cand in enumerate(rec.top_candidates, start=1):
                is_sel = (rec.assigned_a_idx == cand.a_idx)
                card = CandidateCardWidget(
                    candidate_num=c_i,
                    candidate=cand,
                    query_voter_name=b_voter_name,
                    query_rel_name=b_rel_name,
                    voter_col_a=voter_col_a,
                    rel_col_a=rel_col_a,
                    mappings=self.mappings,
                    is_selected=is_sel,
                    parent=self.cands_container,
                )
                self.cands_layout.addWidget(card)

        self.cands_layout.addStretch()

    def _clear_candidates(self) -> None:
        while self.cands_layout.count():
            item = self.cands_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_remark_selected(self, text: str) -> None:
        if not self.filtered_indices or text.startswith("--"):
            return
        rec_idx = self.filtered_indices[self.current_pos]
        rec = self.records[rec_idx]
        rec.notes = text
        self.txt_custom_note.blockSignals(True)
        self.txt_custom_note.setText(text)
        self.txt_custom_note.blockSignals(False)

    def on_custom_note_changed(self, text: str) -> None:
        if not self.filtered_indices:
            return
        rec_idx = self.filtered_indices[self.current_pos]
        rec = self.records[rec_idx]
        rec.notes = text.strip()

    def record_decision(self, decision_type: str, cand_idx: int | None) -> None:
        if not self.filtered_indices:
            return

        rec_idx = self.filtered_indices[self.current_pos]
        rec = self.records[rec_idx]

        assigned_a_idx = None
        if cand_idx is not None and cand_idx < len(rec.top_candidates):
            chosen_cand = rec.top_candidates[cand_idx]
            assigned_a_idx = chosen_cand.a_idx
            rec.assigned_a_idx = assigned_a_idx
            rec.assigned_record_a = chosen_cand.record_a
            rec.tier = "मिला"
            rec.user_decision = f"प्रत्याशी {cand_idx + 1}"

            voter_map = next((m for m in self.mappings if m.role == "voter_name"), None)
            if voter_map:
                name_b = str(rec.record_b.get(voter_map.col_b, "")).strip()
                name_a = str(chosen_cand.record_a.get(voter_map.col_a, "")).strip()
                if name_b and name_a and name_b != name_a:
                    self.alias_mgr.add_alias(name_b, name_a, source="user_review")
        else:
            rec.assigned_a_idx = None
            rec.assigned_record_a = None
            rec.tier = "लापता"
            rec.user_decision = "लापता (पुष्टि की गई)"

        self.storage.save_decision(
            session_id=self.session_id,
            b_idx=rec.b_idx,
            decision=rec.user_decision,
            assigned_a_idx=assigned_a_idx,
            notes=rec.notes,
        )

        self.update_progress_tracker()
        self.session_updated.emit()
        self.navigate_next()

    def bulk_auto_accept(self) -> None:
        """Bulk auto-accept top candidate for high-confidence review items (> 85%)."""
        pending_high = [
            r for r in self.records
            if r.tier == "जाँचें"
            and r.user_decision is None
            and r.top_candidates
            and r.top_candidates[0].score_result.score >= 0.85
        ]

        if not pending_high:
            QMessageBox.information(
                self,
                "कोई रिकॉर्ड नहीं",
                "85% से अधिक स्कोर वाला कोई भी असत्यापित संशयित रिकॉर्ड नहीं मिला।",
            )
            return

        reply = QMessageBox.question(
            self,
            "पुष्टि करें",
            f"क्या आप {len(pending_high)} उच्च-सटीकता (स्कोर > 85%) वाले प्रत्याशियों को स्वचालित रूप से 'मिला' के रूप में स्वीकार करना चाहते हैं?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        for rec in pending_high:
            chosen_cand = rec.top_candidates[0]
            rec.assigned_a_idx = chosen_cand.a_idx
            rec.assigned_record_a = chosen_cand.record_a
            rec.tier = "मिला"
            rec.user_decision = "स्वतः-स्वीकृत (85%+)"
            rec.notes = "उच्च समानता आधार पर स्वतः सत्यापित"
            self.storage.save_decision(
                session_id=self.session_id,
                b_idx=rec.b_idx,
                decision=rec.user_decision,
                assigned_a_idx=rec.assigned_a_idx,
                notes=rec.notes,
            )

        self.update_progress_tracker()
        self.session_updated.emit()
        self.apply_filter()
        QMessageBox.information(
            self,
            "सफल",
            f"कुल {len(pending_high)} मतदाताओं को सफलतापूर्वक सत्यापित कर 'मिला' में स्थानांतरित कर दिया गया!",
        )

    def download_updated_excel(self) -> None:
        """Direct 1-click download of the updated Excel report reflecting all review decisions."""
        if not self.session_result:
            QMessageBox.warning(self, "सूचना", "कोई सक्रिय मिलान सत्र उपलब्ध नहीं है।")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "सत्यापित अद्यतन Excel रिपोर्ट सहेजें",
            "मतदाता_सत्यापन_अद्यतन_रिपोर्ट.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return

        try:
            exporter = ExcelExporter(self.session_result, self.mappings)
            exporter.export(file_path)
            QMessageBox.information(
                self,
                "रिपोर्ट तैयार",
                f"सत्यापन निर्णयों और टिप्पणियों के साथ अद्यतन Excel फ़ाइल सुरक्षित हो गई है:\n{file_path}\n\n"
                "• 'सारांश' शीट में अद्यतन आँकड़े अपडेट हो चुके हैं।\n"
                "• सत्यापित नाम '3. मिला' शीट में स्थानांतरित हो गए हैं।\n"
                "• आपकी स्थलीय टिप्पणियां (Remarks) संबंधित कॉलम में दर्ज हैं।",
            )
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"Excel रिपोर्ट बनाने में समस्या:\n{e}")

    def navigate_prev(self) -> None:
        if self.current_pos > 0:
            self.current_pos -= 1
            self.show_current_record()

    def navigate_next(self) -> None:
        if self.current_pos < len(self.filtered_indices) - 1:
            self.current_pos += 1
            self.show_current_record()
