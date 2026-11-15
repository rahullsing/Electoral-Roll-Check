"""File Import and Preview Page (फ़ाइल आयात).

Ultra-compact, space-optimized layout for non-technical Government School Teachers and BLOs.
Eliminates wasted header padding and maximizes vertical table preview area.
"""

from __future__ import annotations
from pathlib import Path
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
    QSpinBox,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QMessageBox,
    QHeaderView,
    QSplitter,
    QSizePolicy,
)

from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    GREEN_PRIMARY,
    GREEN_BG,
    GREEN_TEXT,
    AMBER_BG,
    AMBER_TEXT,
    BORDER_COLOR,
)


class FilePreviewWidget(QGroupBox):
    """Widget handling a single file's selection, sheet, header, and preview with maximum table space."""

    file_loaded = Signal(str, list, list)  # file_path, columns, preview_records

    def __init__(self, title: str, badge_text: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.badge_text = badge_text
        self.file_path: str = ""
        self.df_cleaned: pd.DataFrame | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        # Compact Controls Toolbar in ONE single row to maximize table space
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(6)

        self.btn_browse = QPushButton("📁 फ़ाइल चुनें")
        self.btn_browse.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"font-size: 12px; padding: 6px 12px; border-radius: 4px;"
        )
        self.btn_browse.setToolTip("अपने कंप्यूटर से .xlsx, .xls या .csv फ़ाइल चुनें")
        self.btn_browse.clicked.connect(self.browse_file)
        ctrl_layout.addWidget(self.btn_browse)

        lbl_s = QLabel("शीट:")
        lbl_s.setStyleSheet("font-weight: bold; font-size: 11px;")
        ctrl_layout.addWidget(lbl_s)

        self.combo_sheet = QComboBox()
        self.combo_sheet.setMinimumWidth(100)
        self.combo_sheet.setStyleSheet("font-size: 11px; padding: 3px;")
        self.combo_sheet.currentIndexChanged.connect(self.on_sheet_changed)
        ctrl_layout.addWidget(self.combo_sheet)

        lbl_h = QLabel("पंक्ति:")
        lbl_h.setStyleSheet("font-weight: bold; font-size: 11px;")
        ctrl_layout.addWidget(lbl_h)

        self.spin_header = QSpinBox()
        self.spin_header.setRange(1, 50)
        self.spin_header.setValue(1)
        self.spin_header.setStyleSheet("font-size: 11px;")
        self.spin_header.valueChanged.connect(self.reload_data)
        ctrl_layout.addWidget(self.spin_header)

        # Compact Status Pill right inside the toolbar row
        self.lbl_status = QLabel("⚠️ फ़ाइल लोड नहीं")
        self.lbl_status.setStyleSheet(
            f"background-color: {AMBER_BG}; color: {AMBER_TEXT}; font-weight: bold; "
            f"font-size: 11px; padding: 4px 8px; border-radius: 4px; border: 1px solid #FCD34D;"
        )
        ctrl_layout.addWidget(self.lbl_status)
        ctrl_layout.addStretch()

        layout.addLayout(ctrl_layout)

        # High-Contrast Preview Table (Takes up full remaining height)
        self.table_preview = QTableWidget()
        self.table_preview.setRowCount(0)
        self.table_preview.setColumnCount(0)
        self.table_preview.setAlternatingRowColors(True)
        self.table_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.table_preview.setStyleSheet(
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 4px; }}"
        )
        self.table_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table_preview, stretch=1)

    def browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "मतदाता सूची फ़ाइल चुनें",
            "",
            "Excel / CSV Files (*.xlsx *.xls *.csv);;All Files (*.*)",
        )
        if not file_path:
            return

        self.file_path = file_path
        self.combo_sheet.blockSignals(True)
        self.combo_sheet.clear()

        suffix = Path(file_path).suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            try:
                xl = pd.ExcelFile(file_path)
                self.combo_sheet.addItems(xl.sheet_names)
                self.combo_sheet.setEnabled(True)
            except Exception as e:
                QMessageBox.critical(self, "त्रुटि", f"Excel फ़ाइल पढ़ने में विफल:\n{e}")
                self.combo_sheet.blockSignals(False)
                return
        else:
            self.combo_sheet.addItem("डिफ़ॉल्ट (CSV)")
            self.combo_sheet.setEnabled(False)

        self.combo_sheet.blockSignals(False)
        self.reload_data()

    def reload_data(self) -> None:
        if not self.file_path:
            return

        header_row_idx = self.spin_header.value() - 1
        suffix = Path(self.file_path).suffix.lower()

        try:
            if suffix in {".xlsx", ".xls"}:
                sheet_name = self.combo_sheet.currentText() or 0
                df = pd.read_excel(self.file_path, sheet_name=sheet_name, header=header_row_idx)
            else:
                try:
                    df = pd.read_csv(self.file_path, header=header_row_idx, encoding="utf-8")
                except UnicodeDecodeError:
                    df = pd.read_csv(self.file_path, header=header_row_idx, encoding="latin1")

            df = df.dropna(how="all").dropna(axis=1, how="all")
            df.columns = [str(c).strip() for c in df.columns]
            df["_orig_row"] = df.index + header_row_idx + 2

            for c in df.select_dtypes(include="object").columns:
                df[c] = df[c].astype(str).str.strip().replace("nan", "")

            self.df_cleaned = df
            self.update_preview()

            cols = [c for c in df.columns if c != "_orig_row"]
            records = df.to_dict(orient="records")

            file_name = Path(self.file_path).name
            if len(file_name) > 18:
                file_name = file_name[:15] + "..."

            self.lbl_status.setText(f"✅ {file_name} ({len(df):,} मतदाता)")
            self.lbl_status.setStyleSheet(
                f"background-color: {GREEN_BG}; color: {GREEN_TEXT}; font-weight: bold; "
                f"font-size: 11px; padding: 4px 8px; border-radius: 4px; border: 1px solid #86EFAC;"
            )

            self.file_loaded.emit(self.file_path, cols, records)

        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"डेटा लोड करने में समस्या:\n{e}")

    def on_sheet_changed(self) -> None:
        self.reload_data()

    def update_preview(self) -> None:
        if self.df_cleaned is None:
            return

        df_show = self.df_cleaned.head(50)
        cols = [c for c in df_show.columns if c != "_orig_row"]

        self.table_preview.setColumnCount(len(cols) + 1)
        headers = ["मूल पंक्ति"] + cols
        self.table_preview.setHorizontalHeaderLabels(headers)
        self.table_preview.setRowCount(len(df_show))

        dark_text_color = QColor(15, 23, 42)
        center_align = Qt.AlignCenter
        left_align = Qt.AlignVCenter | Qt.AlignLeft

        for row_i, (_, row_data) in enumerate(df_show.iterrows()):
            orig_row_item = QTableWidgetItem(str(row_data["_orig_row"]))
            orig_row_item.setTextAlignment(center_align)
            orig_row_item.setForeground(QBrush(QColor(71, 85, 105)))
            self.table_preview.setItem(row_i, 0, orig_row_item)

            for col_i, col_name in enumerate(cols, start=1):
                val = str(row_data.get(col_name, "") or "")
                item = QTableWidgetItem(val)
                item.setTextAlignment(left_align)
                item.setForeground(QBrush(dark_text_color))
                self.table_preview.setItem(row_i, col_i, item)

        self.table_preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)


class ImportPage(QWidget):
    """Full Import Page maximizing table view height and minimizing wasted header space."""

    ready_to_map = Signal(list, list, list, list)  # cols_a, cols_b, recs_a, recs_b

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.cols_a: list[str] = []
        self.cols_b: list[str] = []
        self.recs_a: list[dict[str, Any]] = []
        self.recs_b: list[dict[str, Any]] = []
        self.init_ui()

    def init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Single Compact Header Row (Step title + Compact Teacher Tip + Proceed Button)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        lbl_step = QLabel("चरण 1: मतदाता सूची आयात (Import Lists)")
        lbl_step.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {NAVY_PRIMARY};")
        top_bar.addWidget(lbl_step)

        # Compact Teacher Tip Pill
        lbl_tip = QLabel("💡 <b>निर्देश:</b> बाईं ओर संदर्भ सूची A और दाईं ओर सत्यापन सूची B चुनें।")
        lbl_tip.setTextFormat(Qt.RichText)
        lbl_tip.setStyleSheet(
            "background-color: #F1F5F9; color: #334155; font-size: 11px; "
            "padding: 4px 10px; border-radius: 4px; border: 1px solid #CBD5E1;"
        )
        top_bar.addWidget(lbl_tip)

        top_bar.addStretch()

        self.btn_proceed = QPushButton("कॉलम मिलाएँ (Step 2) पर आगे बढ़ें ➔")
        self.btn_proceed.setStyleSheet(
            "background-color: #94A3B8; color: #FFFFFF; font-weight: bold; "
            "padding: 7px 18px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_proceed.setEnabled(False)
        self.btn_proceed.clicked.connect(self.on_proceed)
        top_bar.addWidget(self.btn_proceed)

        main_layout.addLayout(top_bar)

        # Splitter for List A and List B (Takes up all remaining vertical space)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.widget_a = FilePreviewWidget(
            title="सूची A: मुख्य संदर्भ मतदाता सूची (Reference Roll)",
            badge_text="विधानसभा रोल",
        )
        self.widget_a.file_loaded.connect(self.on_file_a_loaded)
        self.splitter.addWidget(self.widget_a)

        self.widget_b = FilePreviewWidget(
            title="सूची B: सत्यापन योग्य मतदाता सूची (Target Roll to Verify)",
            badge_text="पंचायत रोल / SIR",
        )
        self.widget_b.file_loaded.connect(self.on_file_b_loaded)
        self.splitter.addWidget(self.widget_b)

        self.splitter.setSizes([500, 500])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self.splitter, stretch=1)

    def on_file_a_loaded(self, path: str, cols: list[str], records: list[dict[str, Any]]) -> None:
        self.cols_a = cols
        self.recs_a = records
        self.check_readiness()

    def on_file_b_loaded(self, path: str, cols: list[str], records: list[dict[str, Any]]) -> None:
        self.cols_b = cols
        self.recs_b = records
        self.check_readiness()

    def check_readiness(self) -> None:
        ready = bool(self.recs_a and self.recs_b)
        self.btn_proceed.setEnabled(ready)

        if ready:
            self.btn_proceed.setStyleSheet(
                f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; "
                f"padding: 7px 20px; border-radius: 6px; font-size: 13px;"
            )
            self.btn_proceed.setText("✅ दोनों फ़ाइलें तैयार! कॉलम मिलाएँ (Step 2) ➔")
        else:
            self.btn_proceed.setStyleSheet(
                "background-color: #94A3B8; color: #FFFFFF; font-weight: bold; "
                "padding: 7px 18px; border-radius: 6px; font-size: 13px;"
            )
            self.btn_proceed.setText("कॉलम मिलाएँ (Step 2) पर आगे बढ़ें ➔")

    def on_proceed(self) -> None:
        if not self.recs_a or not self.recs_b:
            QMessageBox.warning(self, "अधूरी जानकारी", "कृपया दोनों सूचियाँ (सूची A और B) लोड करें।")
            return
        self.ready_to_map.emit(self.cols_a, self.cols_b, self.recs_a, self.recs_b)
