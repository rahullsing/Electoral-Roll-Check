"""Duplicate Detection and Family / Household Clustering Page (डुप्लिकेट एवं परिवार क्लस्टर).

Identifies duplicate voters in a single list and clusters families by house number and lineage.
Designed with high-contrast styling and clear Hindi guidance.
"""

from __future__ import annotations
from typing import Any
import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QFrame,
)

from voter_match.core.duplicates import DuplicateDetector, DuplicateCluster, HouseholdGroup
from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    GREEN_PRIMARY,
    BORDER_COLOR,
)


class DuplicatesPage(QWidget):
    """Page for analyzing intra-list duplicates and family household units."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.records_a: list[dict[str, Any]] = []
        self.records_b: list[dict[str, Any]] = []
        self.cols_a: list[str] = []
        self.cols_b: list[str] = []
        self.clusters: list[DuplicateCluster] = []
        self.households: list[HouseholdGroup] = []
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 12, 15, 12)
        main_layout.setSpacing(12)

        header_lbl = QLabel("डुप्लिकेट मतदाता एवं पारिवारिक क्लस्टर (Duplicates & Household Clustering)")
        header_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {NAVY_PRIMARY};")
        main_layout.addWidget(header_lbl)

        # Guidance Banner
        help_card = QFrame()
        help_card.setStyleSheet(
            f"background-color: #FFFFFF; border: 1px solid #BFDBFE; "
            f"border-left: 5px solid {NAVY_PRIMARY}; border-radius: 6px; padding: 8px 12px;"
        )
        hc_layout = QHBoxLayout(help_card)
        hc_layout.setContentsMargins(6, 4, 6, 4)
        lbl_h = QLabel(
            "💡 <b>यह सुविधा क्या करती है?</b><br>"
            "1. <b>डुप्लिकेट खोजें:</b> एक ही सूची में दो बार दर्ज हो गए समान मतदाताओं (फर्जी/दोहरी प्रविष्टि) को खोजती है।<br>"
            "2. <b>मकान क्लस्टर:</b> एक ही मकान नंबर के सभी परिवारजनों को एक साथ समूह बनाकर दिखाती है।"
        )
        lbl_h.setTextFormat(Qt.RichText)
        lbl_h.setStyleSheet("color: #1E293B; font-size: 12px; line-height: 1.3;")
        hc_layout.addWidget(lbl_h)
        main_layout.addWidget(help_card)

        # Control Bar
        ctrl_bar = QFrame()
        ctrl_bar.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 12px;")
        ctrl_box = QHBoxLayout(ctrl_bar)
        ctrl_box.setContentsMargins(6, 4, 6, 4)

        lbl_target = QLabel("जाँच हेतु सूची चुनें:")
        lbl_target.setStyleSheet("font-weight: bold; color: #1E293B;")
        ctrl_box.addWidget(lbl_target)

        self.combo_target_list = QComboBox()
        self.combo_target_list.addItems(["सूची B (सत्यापन सूची)", "सूची A (संदर्भ सूची)"])
        ctrl_box.addWidget(self.combo_target_list)

        self.btn_run_dup = QPushButton("🔍 डुप्लिकेट खोजें (Find Duplicates)")
        self.btn_run_dup.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px;"
        )
        self.btn_run_dup.clicked.connect(self.run_duplicate_detection)
        ctrl_box.addWidget(self.btn_run_dup)

        self.btn_run_house = QPushButton("🏠 परिवार / मकान क्लस्टर बनाएँ")
        self.btn_run_house.setStyleSheet(
            "background-color: #0284C7; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px;"
        )
        self.btn_run_house.clicked.connect(self.run_household_grouping)
        ctrl_box.addWidget(self.btn_run_house)

        ctrl_box.addStretch()

        self.btn_export = QPushButton("📊 Excel में निर्यात करें")
        self.btn_export.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 8px 16px; border-radius: 6px;"
        )
        self.btn_export.clicked.connect(self.export_results)
        ctrl_box.addWidget(self.btn_export)

        main_layout.addWidget(ctrl_bar)

        # Tab Widget: Duplicates vs Households
        self.tabs = QTabWidget()

        table_qss = (
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 4px; }}"
        )

        # TAB 1: Duplicates
        self.table_duplicates = QTableWidget()
        self.table_duplicates.setAlternatingRowColors(True)
        self.table_duplicates.setStyleSheet(table_qss)
        self.tabs.addTab(self.table_duplicates, "⚠️ संभावित डुप्लिकेट मतदाता")

        # TAB 2: Households
        self.table_households = QTableWidget()
        self.table_households.setAlternatingRowColors(True)
        self.table_households.setStyleSheet(table_qss)
        self.tabs.addTab(self.table_households, "🏠 पारिवारिक / मकान क्लस्टर")

        main_layout.addWidget(self.tabs)

    def set_data(self, recs_a: list[dict[str, Any]], recs_b: list[dict[str, Any]], cols_a: list[str], cols_b: list[str]) -> None:
        self.records_a = recs_a
        self.records_b = recs_b
        self.cols_a = cols_a
        self.cols_b = cols_b

    def run_duplicate_detection(self) -> None:
        use_b = "सूची B" in self.combo_target_list.currentText()
        records = self.records_b if use_b else self.records_a
        cols = self.cols_b if use_b else self.cols_a

        if not records:
            QMessageBox.warning(self, "सूचना", "कृपया पहले मतदाता सूची आयात करें।")
            return

        voter_col = next((c for c in cols if any(k in c.lower() for k in ["नाम", "voter", "name"])), cols[0])
        rel_col = next((c for c in cols if any(k in c.lower() for k in ["पिता", "पति", "माता", "relative"])), None)
        house_col = next((c for c in cols if any(k in c.lower() for k in ["मकान", "गृह", "house"])), None)

        detector = DuplicateDetector(voter_col=voter_col, rel_col=rel_col, house_col=house_col)
        self.clusters = detector.find_duplicates(records)

        self.table_duplicates.setColumnCount(6)
        self.table_duplicates.setHorizontalHeaderLabels([
            "क्लस्टर ID", "मतदाता नाम", "सम्बन्धी का नाम", "मकान नं०", "समानता स्कोर", "मिलान विवरण"
        ])

        total_rows = sum(len(c.records) for c in self.clusters)
        self.table_duplicates.setRowCount(total_rows)

        dark_text = QColor(15, 23, 42)
        row_idx = 0
        for c in self.clusters:
            for rec in c.records:
                for c_i, val in enumerate([
                    f"समूह #{c.cluster_id}",
                    str(rec.get(voter_col, "")),
                    str(rec.get(rel_col, "") if rel_col else ""),
                    str(rec.get(house_col, "") if house_col else ""),
                    f"{int(c.similarity_score * 100)}%",
                    "; ".join(c.reasons[:2]),
                ]):
                    item = QTableWidgetItem(val)
                    item.setForeground(QBrush(dark_text))
                    if c_i in {0, 4}:
                        item.setTextAlignment(Qt.AlignCenter)
                    self.table_duplicates.setItem(row_idx, c_i, item)
                row_idx += 1

        self.table_duplicates.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabs.setCurrentIndex(0)
        QMessageBox.information(self, "सफल", f"कुल {len(self.clusters)} संभावित डुप्लिकेट समूह मिले।")

    def run_household_grouping(self) -> None:
        use_b = "सूची B" in self.combo_target_list.currentText()
        records = self.records_b if use_b else self.records_a
        cols = self.cols_b if use_b else self.cols_a

        if not records:
            QMessageBox.warning(self, "सूचना", "कृपया पहले मतदाता सूची आयात करें।")
            return

        house_col = next((c for c in cols if any(k in c.lower() for k in ["मकान", "गृह", "house"])), None)
        if not house_col:
            QMessageBox.warning(self, "कॉलम नहीं मिला", "सूची में 'मकान संख्या' (House No.) कॉलम नहीं मिला।")
            return

        rel_col = next((c for c in cols if any(k in c.lower() for k in ["पिता", "पति", "माता", "relative"])), None)
        voter_col = next((c for c in cols if any(k in c.lower() for k in ["नाम", "voter", "name"])), cols[0])

        self.households = DuplicateDetector.group_by_household(records, house_col=house_col, rel_col=rel_col)

        self.table_households.setColumnCount(5)
        self.table_households.setHorizontalHeaderLabels([
            "मकान नं०", "परिवार सदस्य संख्या", "मुखिया / मुख्य सम्बन्धी", "मतदाता सदस्य सूची", "विवरण"
        ])

        self.table_households.setRowCount(len(self.households))
        dark_text = QColor(15, 23, 42)

        for idx, h in enumerate(self.households):
            member_names = ", ".join(str(m.get(voter_col, "")) for m in h.members[:5])
            if len(h.members) > 5:
                member_names += f" (+{len(h.members) - 5} अन्य)"

            vals = [
                h.original_house_no,
                f"{h.member_count} मतदाता",
                h.family_head_or_relative or "-",
                member_names,
                f"मानक संख्या: {h.house_no_clean}",
            ]
            for c_i, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setForeground(QBrush(dark_text))
                if c_i in {0, 1}:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table_households.setItem(idx, c_i, item)

        self.table_households.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabs.setCurrentIndex(1)
        QMessageBox.information(self, "सफल", f"कुल {len(self.households)} पारिवारिक/मकान क्लस्टर तैयार किए गए।")

    def export_results(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "क्लस्टर रिपोर्ट सहेजें",
            "डुप्लिकेट_एवं_परिवार_क्लस्टर.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            if self.clusters:
                dup_rows = []
                for c in self.clusters:
                    for rec in c.records:
                        row = dict(rec)
                        row["_क्लस्टर_ID"] = c.cluster_id
                        row["_समानता_स्कोर"] = f"{int(c.similarity_score * 100)}%"
                        dup_rows.append(row)
                pd.DataFrame(dup_rows).to_excel(writer, sheet_name="डुप्लिकेट मतदाता", index=False)

            if self.households:
                house_rows = []
                for h in self.households:
                    house_rows.append({
                        "मकान संख्या": h.original_house_no,
                        "सदस्य संख्या": h.member_count,
                        "मुखिया / सम्बन्धी": h.family_head_or_relative,
                    })
                pd.DataFrame(house_rows).to_excel(writer, sheet_name="मकान क्लस्टर", index=False)

        QMessageBox.information(self, "सफल", f"रिपोर्ट सफलतापूर्वक सहेजी गई:\n{file_path}")
