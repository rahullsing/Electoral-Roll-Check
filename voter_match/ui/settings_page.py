"""Settings and Rules Configuration Page (नियम एवं सेटिंग्स).

Allows live editing and testing of Devanagari normalization rules,
threshold slider adjustments, and management of learned alias pairs (JSON import/export).
Designed with high contrast and teacher-friendly layout.
"""

from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSlider,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QTabWidget,
    QInputDialog,
    QFrame,
)

from voter_match.core.normalize import (
    get_default_normalizer,
    normalize_hindi_name,
    DEFAULT_RULES_PATH,
)
from voter_match.core.learning import get_default_alias_manager
from PySide6.QtWidgets import QFrame, QRadioButton
from voter_match.ui.copy_support import enable_table_copy, make_selectable
from voter_match.ui.i18n import (
    LANG_EN,
    LANG_HI,
    current_language,
    on_language_changed,
    set_language,
    skip_translation,
)
from voter_match.ui.theme import scoped_style
from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    BORDER_COLOR,
    GREEN_PRIMARY,
)


class SettingsPage(QWidget):
    """Configuration page for thresholds, rules, and learned aliases."""

    thresholds_changed = Signal(float, float, float, float)  # matched, review, min_voter, min_rel

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.normalizer = get_default_normalizer()
        self.alias_mgr = get_default_alias_manager()
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_lbl = QLabel("नियम एवं सिस्टम सेटिंग्स (System Settings & Indic Rules)")
        header_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {NAVY_PRIMARY};")
        header_row.addWidget(header_lbl)
        header_row.addStretch()

        # Interface language (always shown bilingually so anyone can find it)
        lang_box = QFrame()
        scoped_style(lang_box, "background-color: #EFF6FF; border: 2px solid #1E3A8A; border-radius: 8px;")
        lb = QHBoxLayout(lang_box)
        lb.setContentsMargins(12, 6, 12, 6)
        lb.setSpacing(10)
        lbl_lang = skip_translation(QLabel("🌐 भाषा / Language:"))
        lbl_lang.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {NAVY_PRIMARY};")
        lb.addWidget(lbl_lang)
        self.radio_hi = skip_translation(QRadioButton("हिंदी"))
        self.radio_en = skip_translation(QRadioButton("English"))
        for r in (self.radio_hi, self.radio_en):
            r.setStyleSheet("font-size: 14px; font-weight: bold;")
            lb.addWidget(r)
        self.radio_en.setChecked(current_language() == LANG_EN)
        self.radio_hi.setChecked(current_language() != LANG_EN)
        self.radio_hi.toggled.connect(lambda on: on and set_language(LANG_HI))
        self.radio_en.toggled.connect(lambda on: on and set_language(LANG_EN))
        on_language_changed(self._sync_language_radios)
        header_row.addWidget(lang_box)
        main_layout.addLayout(header_row)

        # Tab Widget
        tabs = QTabWidget()

        tab_thresh = self.create_thresholds_tab()
        tabs.addTab(tab_thresh, "🎚️ मिलान सीमाएँ (Thresholds)")

        tab_rules = self.create_rules_tab()
        tabs.addTab(tab_rules, "🔤 देवनागरी नियम सम्पादक (Rules Editor)")

        tab_aliases = self.create_aliases_tab()
        tabs.addTab(tab_aliases, "📒 सीखे गए उपनाम / वर्तनी (Learned Aliases)")

        main_layout.addWidget(tabs)

    def create_thresholds_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(16)

        box_thresh = QGroupBox("मिलान श्रेणी सीमा निर्धारण (Matching Tier Thresholds)")
        b_layout = QGridLayout(box_thresh)
        b_layout.setSpacing(12)

        b_layout.addWidget(QLabel("मिला (Matched) न्यूनतम स्कोर:"), 0, 0)
        self.slider_matched = QSlider(Qt.Horizontal)
        self.slider_matched.setRange(75, 99)
        self.slider_matched.setValue(90)
        self.lbl_v_matched = QLabel("90%")
        self.lbl_v_matched.setStyleSheet("font-weight: bold; min-width: 40px;")
        self.slider_matched.valueChanged.connect(lambda v: self.lbl_v_matched.setText(f"{v}%"))
        b_layout.addWidget(self.slider_matched, 0, 1)
        b_layout.addWidget(self.lbl_v_matched, 0, 2)

        b_layout.addWidget(QLabel("जाँचें (Needs Review) न्यूनतम स्कोर:"), 1, 0)
        self.slider_review = QSlider(Qt.Horizontal)
        self.slider_review.setRange(50, 85)
        self.slider_review.setValue(72)
        self.lbl_v_review = QLabel("72%")
        self.lbl_v_review.setStyleSheet("font-weight: bold; min-width: 40px;")
        self.slider_review.valueChanged.connect(lambda v: self.lbl_v_review.setText(f"{v}%"))
        b_layout.addWidget(self.slider_review, 1, 1)
        b_layout.addWidget(self.lbl_v_review, 1, 2)

        b_layout.addWidget(QLabel("मतदाता नाम न्यूनतम समानता:"), 2, 0)
        self.slider_voter = QSlider(Qt.Horizontal)
        self.slider_voter.setRange(70, 99)
        self.slider_voter.setValue(90)
        self.lbl_v_voter = QLabel("90%")
        self.lbl_v_voter.setStyleSheet("font-weight: bold; min-width: 40px;")
        self.slider_voter.valueChanged.connect(lambda v: self.lbl_v_voter.setText(f"{v}%"))
        b_layout.addWidget(self.slider_voter, 2, 1)
        b_layout.addWidget(self.lbl_v_voter, 2, 2)

        b_layout.addWidget(QLabel("सम्बन्धी नाम न्यूनतम समानता:"), 3, 0)
        self.slider_rel = QSlider(Qt.Horizontal)
        self.slider_rel.setRange(60, 95)
        self.slider_rel.setValue(80)
        self.lbl_v_rel = QLabel("80%")
        self.lbl_v_rel.setStyleSheet("font-weight: bold; min-width: 40px;")
        self.slider_rel.valueChanged.connect(lambda v: self.lbl_v_rel.setText(f"{v}%"))
        b_layout.addWidget(self.slider_rel, 3, 1)
        b_layout.addWidget(self.lbl_v_rel, 3, 2)

        layout.addWidget(box_thresh)

        btn_apply = QPushButton("सीमा परिवर्तन लागू करें (Apply Thresholds)")
        btn_apply.setStyleSheet(f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 10px 18px; border-radius: 6px;")
        btn_apply.clicked.connect(self.apply_thresholds)
        layout.addWidget(btn_apply)

        layout.addStretch()
        return w

    def create_rules_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        test_box = QGroupBox("🔍 लाइव देवनागरी टेस्ट बॉक्स (Interactive Hindi Normalization Tester)")
        t_layout = QGridLayout(test_box)

        t_layout.addWidget(QLabel("मूल नाम टाइप करें:"), 0, 0)
        self.txt_test_in = QLineEdit()
        self.txt_test_in.setPlaceholderText("उदा० जमीलखां, ओमप्काश, प्रसाद, कृष्ण...")
        self.txt_test_in.setStyleSheet("font-size: 14px; padding: 6px;")
        self.txt_test_in.textChanged.connect(self.run_live_test)
        t_layout.addWidget(self.txt_test_in, 0, 1)

        t_layout.addWidget(QLabel("सामान्यीकृत रूप (Normalized):"), 1, 0)
        self.lbl_test_norm = QLabel("-")
        self.lbl_test_norm.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {NAVY_PRIMARY};")
        t_layout.addWidget(self.lbl_test_norm, 1, 1)

        t_layout.addWidget(QLabel("मूल रूप (Core form):"), 2, 0)
        self.lbl_test_core = QLabel("-")
        self.lbl_test_core.setStyleSheet("font-size: 14px; font-weight: bold; color: #16A34A;")
        t_layout.addWidget(self.lbl_test_core, 2, 1)

        t_layout.addWidget(QLabel("ध्वनि कोड (Phonetic Key):"), 3, 0)
        self.lbl_test_pkey = QLabel("-")
        self.lbl_test_pkey.setStyleSheet("font-size: 14px; font-weight: bold; color: #7C3AED;")
        t_layout.addWidget(self.lbl_test_pkey, 3, 1)

        layout.addWidget(test_box)

        table_qss = (
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 4px; }}"
        )

        self.table_rules = QTableWidget()
        self.table_rules.setColumnCount(4)
        self.table_rules.setHorizontalHeaderLabels(["सक्रिय", "नियम का नाम", "पैटर्न (Regex)", "विवरण"])
        self.table_rules.setStyleSheet(table_qss)
        self.table_rules.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.populate_rules_table()
        enable_table_copy(self.table_rules)
        layout.addWidget(self.table_rules)

        return w

    def create_aliases_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        act_box = QHBoxLayout()

        self.btn_add_alias = QPushButton("➕ नया उपनाम जोड़ें")
        self.btn_add_alias.clicked.connect(self.add_alias_dialog)
        act_box.addWidget(self.btn_add_alias)

        self.btn_del_alias = QPushButton("🗑️ चयनित हटाएँ")
        self.btn_del_alias.clicked.connect(self.delete_selected_alias)
        act_box.addWidget(self.btn_del_alias)

        act_box.addStretch()

        self.btn_export_alias = QPushButton("📤 JSON में निर्यात करें")
        self.btn_export_alias.clicked.connect(self.export_aliases)
        act_box.addWidget(self.btn_export_alias)

        self.btn_import_alias = QPushButton("📥 JSON से आयात करें")
        self.btn_import_alias.clicked.connect(self.import_aliases)
        act_box.addWidget(self.btn_import_alias)

        layout.addLayout(act_box)

        table_qss = (
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 4px; }}"
        )

        self.table_aliases = QTableWidget()
        self.table_aliases.setColumnCount(2)
        self.table_aliases.setHorizontalHeaderLabels(["शब्द 1 (Term 1)", "शब्द 2 (Term 2)"])
        self.table_aliases.setStyleSheet(table_qss)
        self.table_aliases.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_aliases.setSelectionBehavior(QTableWidget.SelectRows)
        enable_table_copy(self.table_aliases, read_only=True)
        self.refresh_aliases_table()
        layout.addWidget(self.table_aliases)

        return w

    def run_live_test(self, text: str) -> None:
        if not text.strip():
            self.lbl_test_norm.setText("-")
            self.lbl_test_core.setText("-")
            self.lbl_test_pkey.setText("-")
            return
        res = normalize_hindi_name(text)
        for lbl in (self.lbl_test_norm, self.lbl_test_core, self.lbl_test_pkey):
            skip_translation(lbl)  # normalised forms of the typed name are data
        self.lbl_test_norm.setText(res.normalized)
        self.lbl_test_core.setText(res.core)
        self.lbl_test_pkey.setText(res.phonetic_key)

    def populate_rules_table(self) -> None:
        self.table_rules.setRowCount(len(self.normalizer.rules))
        dark_text = QColor(15, 23, 42)
        for idx, r in enumerate(self.normalizer.rules):
            item_chk = QTableWidgetItem()
            item_chk.setCheckState(Qt.Checked if r.get("enabled", True) else Qt.Unchecked)
            self.table_rules.setItem(idx, 0, item_chk)

            for col_i, text in [(1, r.get("name", "")), (2, str(r.get("pattern", ""))), (3, r.get("description", ""))]:
                item = QTableWidgetItem(text)
                item.setForeground(QBrush(dark_text))
                self.table_rules.setItem(idx, col_i, item)

    def _sync_language_radios(self, lang: str) -> None:
        for r, want in ((self.radio_en, lang == LANG_EN), (self.radio_hi, lang != LANG_EN)):
            if r.isChecked() != want:
                r.blockSignals(True)
                r.setChecked(want)
                r.blockSignals(False)

    def set_threshold_values(self, m: float, r: float) -> None:
        """Move the sliders to new values (e.g. accepted accuracy suggestion)."""
        self.slider_matched.setValue(int(round(m * 100)))
        self.slider_review.setValue(int(round(r * 100)))

    def apply_thresholds(self) -> None:
        m = self.slider_matched.value() / 100.0
        r = self.slider_review.value() / 100.0
        v = self.slider_voter.value() / 100.0
        rel = self.slider_rel.value() / 100.0
        self.thresholds_changed.emit(m, r, v, rel)
        QMessageBox.information(self, "सफल", "मिलान सीमाएँ सफलतापूर्वक अपडेट कर दी गई हैं।")

    def refresh_aliases_table(self) -> None:
        aliases = self.alias_mgr.get_all_aliases()
        self.table_aliases.setRowCount(len(aliases))
        dark_text = QColor(15, 23, 42)
        for idx, item in enumerate(aliases):
            it1 = QTableWidgetItem(item["term1"])
            it1.setForeground(QBrush(dark_text))
            it2 = QTableWidgetItem(item["term2"])
            it2.setForeground(QBrush(dark_text))
            self.table_aliases.setItem(idx, 0, it1)
            self.table_aliases.setItem(idx, 1, it2)

    def add_alias_dialog(self) -> None:
        t1, ok1 = QInputDialog.getText(self, "उपनाम जोड़ें", "प्रथम शब्द दर्ज करें (उदा० घासू):")
        if not ok1 or not t1.strip():
            return
        t2, ok2 = QInputDialog.getText(self, "उपनाम जोड़ें", "द्वितीय शब्द दर्ज करें (उदा० धांसू):")
        if not ok2 or not t2.strip():
            return

        norm1 = normalize_hindi_name(t1.strip()).normalized
        norm2 = normalize_hindi_name(t2.strip()).normalized
        self.alias_mgr.add_alias(norm1, norm2, source="manual_settings")
        self.refresh_aliases_table()

    def delete_selected_alias(self) -> None:
        selected = self.table_aliases.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        t1 = self.table_aliases.item(row, 0).text()
        t2 = self.table_aliases.item(row, 1).text()
        self.alias_mgr.remove_alias(t1, t2)
        self.refresh_aliases_table()

    def export_aliases(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "उपनाम JSON फ़ाइल सहेजें",
            "voter_aliases.json",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        self.alias_mgr.export_to_json(file_path)
        QMessageBox.information(self, "सफल", f"उपनाम सफलतापूर्वक निर्यात किए गए:\n{file_path}")

    def import_aliases(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "उपनाम JSON फ़ाइल चुनें",
            "",
            "JSON Files (*.json)",
        )
        if not file_path:
            return
        cnt = self.alias_mgr.import_from_json(file_path)
        self.refresh_aliases_table()
        QMessageBox.information(self, "सफल", f"सफलतापूर्वक {cnt} नए उपनाम जोड़े गए!")
