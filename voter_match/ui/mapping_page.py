"""Column Mapping and Role Configuration Page (कॉलम मिलान).

Designed for non-technical Government School Teachers and BLOs.
Provides auto-suggestions with live sample previews from the uploaded files,
clear plain-language role explanations, and friendly guidance.
"""

from __future__ import annotations
from typing import Any
import rapidfuzz.fuzz as rf_fuzz
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QGroupBox,
    QMessageBox,
    QInputDialog,
    QScrollArea,
    QFrame,
)

from voter_match.core.scorer import ColumnMapping, IMPORTANCE_WEIGHTS
from voter_match.core.column_suggest import ROLE_KEYWORDS, column_role_score, suggest_columns
from voter_match.storage.db import get_default_storage
from voter_match.ui.i18n import ROLE_NO_I18N, mark_translatable, on_language_changed, skip_translation, tr, trf
from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    TEXT_MUTED,
    GREEN_PRIMARY,
    GREEN_BG,
    GREEN_TEXT,
    BORDER_COLOR,
    AMBER_BG,
    AMBER_TEXT,
    rgba,
    scoped_style,
)

STANDARD_ROLES = [
    {
        "role": "serial_no",
        "label": "🔢 क्रम संख्या / रोल क्रमांक (Roll Serial No.)",
        "badge": "कागज़ी मिलान संदर्भ (Paper Ref)",
        "badge_color": "#7C3AED",
        "type": "text",
        "default_importance": "Paper Ref",
        "keywords": ROLE_KEYWORDS["serial_no"],
    },
    {
        "role": "epic",
        "label": "🆔 EPIC / मतदाता पहचान पत्र संख्या (Voter ID)",
        "badge": "निश्चित पहचान (Exact ID)",
        "badge_color": "#0F766E",
        "type": "text",
        "default_importance": "High",
        "keywords": ROLE_KEYWORDS["epic"],
    },
    {
        "role": "voter_name",
        "label": "👤 मतदाता का नाम (Voter Name)",
        "badge": "अति आवश्यक (Compulsory)",
        "badge_color": "#DC2626",
        "type": "name",
        "default_importance": "High",
        "keywords": ROLE_KEYWORDS["voter_name"],
    },
    {
        "role": "relative_name",
        "label": "👪 पिता / पति / माता का नाम (Relative Name)",
        "badge": "अति आवश्यक (Compulsory)",
        "badge_color": "#DC2626",
        "type": "name",
        "default_importance": "High",
        "keywords": ROLE_KEYWORDS["relative_name"],
    },
    {
        "role": "age",
        "label": "🎂 आयु (Age in Years)",
        "badge": "सहायक (Supporting)",
        "badge_color": "#2563EB",
        "type": "number",
        "default_importance": "Medium",
        "keywords": ROLE_KEYWORDS["age"],
    },
    {
        "role": "gender",
        "label": "👫 लिंग (Gender - पुरुष/महिला)",
        "badge": "सहायक (Supporting)",
        "badge_color": "#2563EB",
        "type": "category",
        "default_importance": "Low",
        "keywords": ROLE_KEYWORDS["gender"],
    },
    {
        "role": "house_no",
        "label": "🏠 मकान संख्या (House No.)",
        "badge": "बोनस (Bonus)",
        "badge_color": "#059669",
        "type": "text",
        "default_importance": "Bonus only",
        "keywords": ROLE_KEYWORDS["house_no"],
    },
    {
        "role": "ward",
        "label": "📍 वार्ड / भाग संख्या (Ward/Part)",
        "badge": "वैकल्पिक (Optional)",
        "badge_color": "#64748B",
        "type": "category",
        "default_importance": "Ignore",
        "keywords": ROLE_KEYWORDS["ward"],
    },
]

IMPORTANCE_OPTIONS = [
    ("Paper Ref", "कागज़ी संदर्भ (Paper Ref - केवल खोजने हेतु)"),
    ("High", "उच्च (High)"),
    ("Must match", "अनिवार्य (Must match)"),
    ("Medium", "मध्यम (Medium)"),
    ("Low", "सामान्य (Low)"),
    ("Bonus only", "केवल बोनस (Bonus only)"),
    ("Ignore", "छोड़ें (Ignore)"),
]


class RoleCardWidget(QFrame):
    """An intuitive card representing a single mapped role with live sample preview."""

    def __init__(
        self,
        role: str,
        label: str,
        badge_text: str,
        badge_color: str,
        col_type: str,
        default_importance: str,
        cols_a: list[str],
        cols_b: list[str],
        sample_rec_a: dict[str, Any] | None = None,
        sample_rec_b: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.role = role
        self.role_label = label
        self.badge_text = badge_text
        self.badge_color = badge_color
        self.col_type = col_type
        self.default_importance = default_importance
        self.cols_a = [tr("-- चयन न करें --")] + cols_a
        self.cols_b = [tr("-- चयन न करें --")] + cols_b
        self.sample_rec_a = sample_rec_a or {}
        self.sample_rec_b = sample_rec_b or {}
        self.init_ui()

    def init_ui(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        scoped_style(self, f"background-color: #FFFFFF; border: 1px solid {BORDER_COLOR}; border-radius: 6px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(4)

        # Header: Role Title + Requirement Badge
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        lbl_name = QLabel(self.role_label)
        lbl_name.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {NAVY_PRIMARY};")
        top_row.addWidget(lbl_name)

        lbl_badge = QLabel(f" {self.badge_text} ")
        lbl_badge.setStyleSheet(
            f"background-color: {rgba(self.badge_color, 0.10)}; color: {self.badge_color}; "
            f"border: 1px solid {rgba(self.badge_color, 0.35)}; border-radius: 4px; font-size: 10px; "
            f"font-weight: bold; padding: 1px 6px;"
        )
        top_row.addWidget(lbl_badge)
        top_row.addStretch()

        # Age Tolerance (if age role)
        if self.role == "age":
            lbl_tol = QLabel("सहनशीलता (Tolerance):")
            lbl_tol.setStyleSheet("color: #475569; font-size: 11px;")
            top_row.addWidget(lbl_tol)

            self.spin_tol = QSpinBox()
            self.spin_tol.setRange(0, 15)
            self.spin_tol.setValue(3)
            self.spin_tol.setPrefix("± ")
            self.spin_tol.setSuffix(" वर्ष")
            self.spin_tol.setToolTip("कितने वर्ष तक के अंतर को स्वीकार्य माना जाए")
            top_row.addWidget(self.spin_tol)

            # Roll years: lists from different years need an age shift (2023 vs 2026 -> +3)
            lbl_years = QLabel("  नामावली वर्ष A / B:")
            lbl_years.setStyleSheet("color: #475569; font-size: 11px;")
            lbl_years.setToolTip("यदि सूची A और सूची B अलग-अलग वर्ष की हैं, तो आयु का अंतर स्वतः समायोजित होगा")
            top_row.addWidget(lbl_years)
            self.spin_year_a = QSpinBox()
            self.spin_year_a.setRange(1990, 2100)
            self.spin_year_a.setValue(2026)
            self.spin_year_a.setToolTip("सूची A (संदर्भ) किस वर्ष की नामावली है")
            top_row.addWidget(self.spin_year_a)
            self.spin_year_b = QSpinBox()
            self.spin_year_b.setRange(1990, 2100)
            self.spin_year_b.setValue(2026)
            self.spin_year_b.setToolTip("सूची B (सत्यापन) किस वर्ष की नामावली है")
            top_row.addWidget(self.spin_year_b)
            self.lbl_offset = QLabel("")
            self.lbl_offset.setStyleSheet("color: #0F766E; font-size: 11px; font-weight: bold;")
            top_row.addWidget(self.lbl_offset)
            self.spin_year_a.valueChanged.connect(self._update_offset_label)
            self.spin_year_b.valueChanged.connect(self._update_offset_label)
        elif self.role == "serial_no":
            lbl_tip = QLabel("💡 <i>कागज़ी सूची में मतदाता को तुरंत खोजने हेतु (यह स्कोरिंग को प्रभावित नहीं करेगा)</i>")
            lbl_tip.setStyleSheet("color: #7C3AED; font-size: 11px;")
            top_row.addWidget(lbl_tip)
            self.spin_tol = None
        elif self.role == "epic":
            lbl_tip = QLabel("💡 <i>EPIC समान हो तो नाम में अंतर होने पर भी निश्चित मिलान</i>")
            lbl_tip.setStyleSheet("color: #0F766E; font-size: 11px;")
            top_row.addWidget(lbl_tip)
            self.spin_tol = None
        else:
            self.spin_tol = None
        if self.role != "age":
            self.spin_year_a = None
            self.spin_year_b = None

        layout.addLayout(top_row)

        # Dropdowns Grid
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        # List A selector
        grid.addWidget(QLabel("सूची A (संदर्भ) कॉलम:"), 0, 0)
        self.combo_a = QComboBox()
        self.combo_a.addItems(self.cols_a)
        self.combo_a.currentTextChanged.connect(self.update_sample_previews)
        grid.addWidget(self.combo_a, 0, 1)

        # List B selector
        grid.addWidget(QLabel("सूची B (सत्यापन) कॉलम:"), 0, 2)
        self.combo_b = QComboBox()
        self.combo_b.addItems(self.cols_b)
        self.combo_b.currentTextChanged.connect(self.update_sample_previews)
        grid.addWidget(self.combo_b, 0, 3)

        # Importance Selector
        grid.addWidget(QLabel("महत्व (Importance):"), 0, 4)
        self.combo_importance = mark_translatable(QComboBox())
        for key, val in IMPORTANCE_OPTIONS:
            self.combo_importance.addItem(val, key)
        # Select default
        idx = next((i for i, (k, _) in enumerate(IMPORTANCE_OPTIONS) if k == self.default_importance), 0)
        self.combo_importance.setCurrentIndex(idx)
        grid.addWidget(self.combo_importance, 0, 5)

        layout.addLayout(grid)

        # Live Sample Preview Chips (Gives teacher instant visual confidence!)
        self.lbl_sample_a = skip_translation(QLabel(tr("नमूना मान (A): -")))
        self.lbl_sample_a.setStyleSheet("color: #059669; font-size: 11px; font-style: italic;")

        self.lbl_sample_b = skip_translation(QLabel(tr("नमूना मान (B): -")))
        self.lbl_sample_b.setStyleSheet("color: #059669; font-size: 11px; font-style: italic;")

        sample_row = QHBoxLayout()
        sample_row.setContentsMargins(0, 0, 0, 0)
        sample_row.addWidget(self.lbl_sample_a)
        sample_row.addSpacing(25)
        sample_row.addWidget(self.lbl_sample_b)
        sample_row.addStretch()
        layout.addLayout(sample_row)

    def _update_offset_label(self) -> None:
        off = self.year_offset()
        self.lbl_offset.setText(f"(आयु समायोजन {off:+d} वर्ष)" if off else "")

    def year_offset(self) -> int:
        if not self.spin_year_a or not self.spin_year_b:
            return 0
        return self.spin_year_b.value() - self.spin_year_a.value()

    def update_sample_previews(self) -> None:
        col_a = self.combo_a.currentText()
        col_b = self.combo_b.currentText()

        if col_a and self.combo_a.currentIndex() > 0 and col_a in self.sample_rec_a:
            val_a = str(self.sample_rec_a.get(col_a, "") or "")
            self.lbl_sample_a.setText(trf('✓ सूची A पहली पंक्ति: "{}"', val_a))
            self.lbl_sample_a.setStyleSheet("color: #166534; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_sample_a.setText(tr("नमूना मान (A): -"))
            self.lbl_sample_a.setStyleSheet("color: #94A3B8; font-size: 11px;")

        if col_b and self.combo_b.currentIndex() > 0 and col_b in self.sample_rec_b:
            val_b = str(self.sample_rec_b.get(col_b, "") or "")
            self.lbl_sample_b.setText(trf('✓ सूची B पहली पंक्ति: "{}"', val_b))
            self.lbl_sample_b.setStyleSheet("color: #166534; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_sample_b.setText(tr("नमूना मान (B): -"))
            self.lbl_sample_b.setStyleSheet("color: #94A3B8; font-size: 11px;")

    def get_mapping(self) -> ColumnMapping:
        col_a = self.combo_a.currentText()
        col_b = self.combo_b.currentText()
        imp_key = self.combo_importance.currentData() or self.default_importance

        # index 0 is the "not selected" placeholder (its text may be translated)
        final_a = col_a if self.combo_a.currentIndex() > 0 else None
        final_b = col_b if self.combo_b.currentIndex() > 0 else None
        tol = self.spin_tol.value() if self.spin_tol else 3

        return ColumnMapping(
            role=self.role,
            col_a=final_a,
            col_b=final_b,
            importance=imp_key,
            weight=IMPORTANCE_WEIGHTS.get(imp_key, 1.0),
            col_type=self.col_type,
            tolerance=tol,
            year_offset=self.year_offset(),
        )

    def set_mapping(
        self, col_a: str | None, col_b: str | None, imp: str, tol: int = 3, year_offset: int = 0
    ) -> None:
        if col_a and col_a in self.cols_a:
            self.combo_a.setCurrentText(col_a)
        if col_b and col_b in self.cols_b:
            self.combo_b.setCurrentText(col_b)
        idx = next((i for i, (k, _) in enumerate(IMPORTANCE_OPTIONS) if k == imp), -1)
        if idx >= 0:
            self.combo_importance.setCurrentIndex(idx)
        if self.spin_tol:
            self.spin_tol.setValue(tol)
        if self.spin_year_a and self.spin_year_b:
            self.spin_year_b.setValue(self.spin_year_a.value() + int(year_offset or 0))
        self.update_sample_previews()


class MappingPage(QWidget):
    """Main Column Mapping screen."""

    start_matching = Signal(list, bool)  # list[ColumnMapping], match_within_ward

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.cols_a: list[str] = []
        self.cols_b: list[str] = []
        self.sample_rec_a: dict[str, Any] = {}
        self.sample_rec_b: dict[str, Any] = {}
        self.role_cards: list[RoleCardWidget] = []
        self.storage = get_default_storage()
        self.init_ui()
        on_language_changed(lambda _lang: [c.update_sample_previews() for c in self.role_cards])

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Single Unified Top Header Bar: Title + Compact Tip + SINGLE Start Button
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        header_lbl = QLabel("चरण 2: स्तंभ एवं भूमिका मिलान (Step 2: Column Mapping)")
        header_lbl.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {NAVY_PRIMARY};")
        top_bar.addWidget(header_lbl)

        # Compact Teacher Tip Pill
        lbl_tip = QLabel("💡 <b>निर्देश:</b> हरे रंग के नमूना मान देखकर पुष्टि करें कि कॉलम सही चुने गए हैं।")
        lbl_tip.setTextFormat(Qt.RichText)
        lbl_tip.setStyleSheet(
            "background-color: #F1F5F9; color: #334155; font-size: 11px; "
            "padding: 4px 10px; border-radius: 4px; border: 1px solid #CBD5E1;"
        )
        top_bar.addWidget(lbl_tip)

        top_bar.addStretch()

        # SINGLE Next Button on Screen 2 (No duplicate buttons!)
        self.btn_run = QPushButton("🚀 मिलान प्रारंभ करें (Start Matching) ➔")
        self.btn_run.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 7px 20px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_run.clicked.connect(self.on_start_matching)
        top_bar.addWidget(self.btn_run)

        # Legacy compatibility aliases so tests and other callers succeed seamlessly
        self.btn_run_top = self.btn_run
        self.btn_run_bottom = self.btn_run

        main_layout.addLayout(top_bar)

        # Compact Profile Selection & Ward Filter Bar (~36px height)
        profile_bar = QFrame()
        scoped_style(profile_bar, "background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px;")
        pb_layout = QHBoxLayout(profile_bar)
        pb_layout.setContentsMargins(6, 2, 6, 2)
        pb_layout.setSpacing(8)

        lbl_prof = QLabel("सहेजी गई प्रोफ़ाइल:")
        lbl_prof.setStyleSheet("font-weight: bold; font-size: 11px; color: #334155;")
        pb_layout.addWidget(lbl_prof)

        self.combo_profile = QComboBox()
        self.combo_profile.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.combo_profile.setMinimumWidth(160)
        self.refresh_profiles()
        pb_layout.addWidget(self.combo_profile)

        self.btn_load_prof = QPushButton("लोड करें")
        self.btn_load_prof.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.btn_load_prof.clicked.connect(self.load_selected_profile)
        pb_layout.addWidget(self.btn_load_prof)

        self.btn_save_prof = QPushButton("नई प्रोफ़ाइल सहेजें...")
        self.btn_save_prof.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.btn_save_prof.clicked.connect(self.save_current_profile)
        pb_layout.addWidget(self.btn_save_prof)

        pb_layout.addSpacing(16)
        sep = QLabel("|")
        sep.setStyleSheet("color: #CBD5E1; font-weight: bold;")
        pb_layout.addWidget(sep)
        pb_layout.addSpacing(16)

        self.chk_ward = QCheckBox("केवल समान वार्ड/भाग में तुलना करें (Match within same ward)")
        self.chk_ward.setToolTip("यदि दोनों फाइलों में वार्ड नंबर बिल्कुल समान हैं, तो इसे टिक करें")
        self.chk_ward.setStyleSheet("font-weight: bold; font-size: 11px; color: #1E293B;")
        pb_layout.addWidget(self.chk_ward)

        pb_layout.addStretch()
        main_layout.addWidget(profile_bar)

        # Scroll area for Role Cards (Now takes 90%+ of the screen height!)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(2, 2, 2, 2)
        self.cards_layout.setSpacing(6)
        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area, stretch=1)

    def set_columns(
        self,
        cols_a: list[str],
        cols_b: list[str],
        sample_a: dict[str, Any] | None = None,
        sample_b: dict[str, Any] | None = None,
    ) -> None:
        self.cols_a = cols_a
        self.cols_b = cols_b
        self.sample_rec_a = sample_a or {}
        self.sample_rec_b = sample_b or {}

        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.role_cards.clear()

        # Build cards for standard roles
        for info in STANDARD_ROLES:
            card = RoleCardWidget(
                role=info["role"],
                label=info["label"],
                badge_text=info["badge"],
                badge_color=info["badge_color"],
                col_type=info["type"],
                default_importance=info["default_importance"],
                cols_a=cols_a,
                cols_b=cols_b,
                sample_rec_a=self.sample_rec_a,
                sample_rec_b=self.sample_rec_b,
                parent=self.cards_container,
            )
            self.role_cards.append(card)
            self.cards_layout.addWidget(card)

        # Check for saved profile match
        matched_prof = self.storage.find_matching_profile(cols_a, cols_b)
        if matched_prof:
            self._select_profile(matched_prof)
            self.load_selected_profile()
        else:
            self.auto_suggest()

        self.cards_layout.addStretch()

    def auto_suggest(self) -> None:
        """Auto-suggest mappings based on Devanagari and English keywords."""
        roles = [info["role"] for info in STANDARD_ROLES]
        kw = {info["role"]: info["keywords"] for info in STANDARD_ROLES}
        best_a = suggest_columns(self.cols_a, roles, kw)
        best_b = suggest_columns(self.cols_b, roles, kw)
        for card in self.role_cards:
            if card.role in best_a:
                card.combo_a.setCurrentText(best_a[card.role])
            if card.role in best_b:
                card.combo_b.setCurrentText(best_b[card.role])
            card.update_sample_previews()

    def _find_best_match(self, cols: list[str], keywords: list[str]) -> str | None:
        """Best single column for a keyword list (kept for compatibility)."""
        best_col, best = None, 0.0
        for col in cols:
            sc = column_role_score("", col, keywords)
            if sc > best and sc >= 60.0:
                best_col, best = col, sc
        return best_col

    def refresh_profiles(self) -> None:
        self.combo_profile.clear()
        profs = self.storage.list_profiles()
        if profs:
            for name in profs:
                self.combo_profile.addItem(name, name)  # data = real profile name
                self.combo_profile.setItemData(self.combo_profile.count() - 1, True, ROLE_NO_I18N)
        else:
            self.combo_profile.addItem("-- कोई प्रोफ़ाइल नहीं --", None)
        mark_translatable(self.combo_profile)

    def _select_profile(self, name: str) -> None:
        idx = self.combo_profile.findData(name)
        if idx >= 0:
            self.combo_profile.setCurrentIndex(idx)

    def load_selected_profile(self) -> None:
        p_name = self.combo_profile.currentData()
        if not p_name:
            return
        mappings = self.storage.get_profile(p_name)
        if not mappings:
            return

        map_dict = {m.role: m for m in mappings}
        for card in self.role_cards:
            if card.role in map_dict:
                m = map_dict[card.role]
                card.set_mapping(m.col_a, m.col_b, m.importance, m.tolerance, getattr(m, "year_offset", 0))

    def save_current_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "प्रोफ़ाइल सहेजें", "प्रोफ़ाइल का नाम दर्ज करें (उदा० पंचायत vs विधानसभा):")
        if not ok or not name.strip():
            return
        mappings = [c.get_mapping() for c in self.role_cards]
        self.storage.save_profile(name.strip(), mappings)
        self.refresh_profiles()
        self._select_profile(name.strip())
        QMessageBox.information(self, "सफल", f"प्रोफ़ाइल '{name.strip()}' सफलतापूर्वक सहेजी गई!")

    def on_start_matching(self) -> None:
        mappings = [c.get_mapping() for c in self.role_cards]
        voter_map = next((m for m in mappings if m.role == "voter_name" and m.is_active()), None)
        if not voter_map:
            QMessageBox.warning(
                self,
                "अनिवार्य कॉलम छूटा है",
                "कृपया 'मतदाता का नाम' (Voter Name) के लिए दोनों सूचियों के कॉलम अवश्य चुनें।",
            )
            return

        match_ward = self.chk_ward.isChecked()
        self.start_matching.emit(mappings, match_ward)
