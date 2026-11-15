"""Session Save and Load Dialogs (सत्र सहेजें एवं खोलें).

Allows BLOs and teachers to save their current matching progress
and reopen previous sessions seamlessly, without re-uploading files.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QFileDialog,
    QFrame,
    QSizePolicy,
)

from voter_match.storage.session_manager import (
    SavedSessionData,
    get_default_session_manager,
    SESSION_FILE_EXTENSION,
)
from voter_match.ui.theme import (
    NAVY_PRIMARY,
    TEXT_DARK,
    GREEN_PRIMARY,
    BORDER_COLOR,
    RED_PRIMARY,
)


class SaveSessionDialog(QDialog):
    """Dialog to save the current matching session."""

    def __init__(self, current_data: SavedSessionData, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = current_data
        self.session_mgr = get_default_session_manager()
        self.setWindowTitle("💾 सत्र सहेजें (Save Current Session)")
        self.resize(540, 320)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        hdr = QLabel("💾 वर्तमान मिलान सत्र सहेजें (Save Session)")
        hdr.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {NAVY_PRIMARY};")
        layout.addWidget(hdr)

        lbl_desc = QLabel(
            "सत्र सहेजने के बाद आप कभी भी एप्लिकेशन बंद करके पुनः खोल सकते हैं "
            "और आपका सारा मिलान कार्य, निर्णय व टिप्पणियाँ यथावत मिलेंगी।"
        )
        lbl_desc.setStyleSheet("color: #475569; font-size: 12px;")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        # Session Title Input
        lbl_t = QLabel("सत्र का शीर्षक / नाम (Session Name):")
        lbl_t.setStyleSheet("font-weight: bold; font-size: 13px; color: #1E293B;")
        layout.addWidget(lbl_t)

        self.txt_title = QLineEdit()
        self.txt_title.setText(self.data.title or "मतदाता मिलान सत्र")
        self.txt_title.setStyleSheet("font-size: 13px; padding: 6px;")
        layout.addWidget(self.txt_title)

        # Quick stats preview box
        stats_box = QFrame()
        stats_box.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px;"
        )
        sb_layout = QVBoxLayout(stats_box)
        sb_layout.setSpacing(4)

        f_b = Path(self.data.file_b).name if self.data.file_b else "अज्ञात फ़ाइल"
        tot = len(self.data.records_b)
        matched = 0
        review = 0
        missing = 0
        if self.data.session_result and self.data.session_result.stats:
            st = self.data.session_result.stats
            matched = st.get("मिला", 0)
            review = st.get("जाँचें", 0)
            missing = st.get("लापता", 0)

        lbl_summary = QLabel(
            f"📁 <b>सत्यापन सूची:</b> {f_b}<br>"
            f"📋 <b>कुल मतदाता:</b> {tot:,} | 🟢 <b>मिला:</b> {matched:,} | "
            f"🟡 <b>जाँचें:</b> {review:,} | 🔴 <b>लापता:</b> {missing:,}"
        )
        lbl_summary.setTextFormat(Qt.RichText)
        lbl_summary.setStyleSheet("font-size: 12px; color: #334155;")
        sb_layout.addWidget(lbl_summary)
        layout.addWidget(stats_box)

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_save_db = QPushButton("💾 सहेजें (Save in App)")
        self.btn_save_db.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 8px 18px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_save_db.clicked.connect(self.save_to_database)
        btn_layout.addWidget(self.btn_save_db)

        self.btn_export_file = QPushButton("📁 .vsession फ़ाइल में सहेजें...")
        self.btn_export_file.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 8px 14px; border-radius: 6px; font-size: 12px;"
        )
        self.btn_export_file.clicked.connect(self.export_to_file)
        btn_layout.addWidget(self.btn_export_file)

        btn_layout.addStretch()

        btn_cancel = QPushButton("रद्द करें")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def save_to_database(self) -> None:
        title = self.txt_title.text().strip()
        if not title:
            QMessageBox.warning(self, "शीर्षक आवश्यक", "कृपया सत्र का एक नाम दर्ज करें।")
            return
        self.data.title = title
        try:
            self.session_mgr.save_session(self.data)
            QMessageBox.information(
                self,
                "सत्र सहेजा गया",
                f"सत्र '{title}' सफलतापूर्वक सहेजा गया!\n"
                "आप जब चाहें इसे 'सत्र खोलें' मेन्यू से दोबारा खोल सकते हैं।",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"सत्र सहेजने में त्रुटि:\n{e}")

    def export_to_file(self) -> None:
        title = self.txt_title.text().strip()
        self.data.title = title or "मतदाता मिलान सत्र"
        default_name = f"{title.replace(' ', '_')}{SESSION_FILE_EXTENSION}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "सत्र फ़ाइल सहेजें",
            default_name,
            f"Voter Match Session (*{SESSION_FILE_EXTENSION});;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            self.session_mgr.export_session_file(self.data, file_path)
            QMessageBox.information(
                self,
                "फ़ाइल सहेजी गई",
                f"सत्र फ़ाइल सफलतापूर्वक सहेजी गई:\n{file_path}\n\n"
                "इस फ़ाइल को आप पेनड्राइव में लेकर किसी भी कंप्यूटर पर खोल सकते हैं।",
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"सत्र फ़ाइल सहेजने में समस्या:\n{e}")


class OpenSessionDialog(QDialog):
    """Dialog to list saved sessions and restore one, or import from .vsession file."""

    session_loaded = Signal(object)  # SavedSessionData

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.session_mgr = get_default_session_manager()
        self.selected_session_data: SavedSessionData | None = None
        self.setWindowTitle("📂 सहेजे गए सत्र खोलें (Open Saved Session)")
        self.resize(780, 440)
        self.init_ui()
        self.refresh_session_list()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # Top Bar
        top_bar = QHBoxLayout()
        hdr = QLabel("📂 पूर्व सहेजे गए सत्र (Saved Sessions)")
        hdr.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {NAVY_PRIMARY};")
        top_bar.addWidget(hdr)
        top_bar.addStretch()

        self.btn_import_file = QPushButton("📁 .vsession फ़ाइल से खोलें...")
        self.btn_import_file.setStyleSheet(
            f"background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 6px 14px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_import_file.clicked.connect(self.import_from_file)
        top_bar.addWidget(self.btn_import_file)
        layout.addLayout(top_bar)

        # Sessions Table
        self.table_sessions = QTableWidget()
        self.table_sessions.setColumnCount(6)
        self.table_sessions.setHorizontalHeaderLabels([
            "सत्र शीर्षक",
            "सत्यापन सूची (B)",
            "कुल मतदाता",
            "स्थिति (मिला / जाँचें / लापता)",
            "अंतिम अद्यतन",
            "सत्र ID",
        ])
        self.table_sessions.setAlternatingRowColors(True)
        self.table_sessions.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_sessions.setSelectionMode(QTableWidget.SingleSelection)
        self.table_sessions.setStyleSheet(
            f"QTableWidget {{ background-color: #FFFFFF; color: {TEXT_DARK}; "
            f"gridline-color: #E2E8F0; font-size: 12px; border: 1px solid {BORDER_COLOR}; }} "
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; "
            f"font-weight: bold; font-size: 12px; padding: 6px; border: 1px solid #0F2D6B; }} "
            f"QTableWidget::item {{ color: {TEXT_DARK}; padding: 6px; }}"
        )
        self.table_sessions.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_sessions.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_sessions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_sessions.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_sessions.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table_sessions.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table_sessions.itemSelectionChanged.connect(self.on_selection_changed)
        self.table_sessions.doubleClicked.connect(self.load_selected_session)
        layout.addWidget(self.table_sessions, stretch=1)

        # Action Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_load = QPushButton("🚀 सत्र खोलें (Load Session) ➔")
        self.btn_load.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: #FFFFFF; font-weight: bold; "
            f"padding: 8px 22px; border-radius: 6px; font-size: 13px;"
        )
        self.btn_load.setEnabled(False)
        self.btn_load.clicked.connect(self.load_selected_session)
        btn_bar.addWidget(self.btn_load)

        self.btn_delete = QPushButton("🗑️ सत्र हटाएँ (Delete)")
        self.btn_delete.setStyleSheet(
            f"background-color: #EF4444; color: #FFFFFF; font-weight: bold; "
            f"padding: 8px 14px; border-radius: 6px; font-size: 12px;"
        )
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_selected_session)
        btn_bar.addWidget(self.btn_delete)

        btn_bar.addStretch()

        btn_close = QPushButton("बंद करें")
        btn_close.clicked.connect(self.reject)
        btn_bar.addWidget(btn_close)

        layout.addLayout(btn_bar)

    def refresh_session_list(self) -> None:
        sessions = self.session_mgr.list_sessions()
        self.table_sessions.setRowCount(len(sessions))

        bold_font = QFont("Nirmala UI", 10, QFont.Bold)
        center_align = Qt.AlignCenter
        left_align = Qt.AlignVCenter | Qt.AlignLeft

        for row_i, s in enumerate(sessions):
            # 0: Title
            it_t = QTableWidgetItem(s["title"])
            it_t.setFont(bold_font)
            self.table_sessions.setItem(row_i, 0, it_t)

            # 1: File B
            it_fb = QTableWidgetItem(s["file_b"] or "-")
            self.table_sessions.setItem(row_i, 1, it_fb)

            # 2: Total records B
            it_tot = QTableWidgetItem(f"{s['total_records_b']:,}")
            it_tot.setTextAlignment(center_align)
            self.table_sessions.setItem(row_i, 2, it_tot)

            # 3: Status Breakdown
            stat_str = f"🟢 {s['matched_count']} | 🟡 {s['review_count']} | 🔴 {s['missing_count']}"
            it_st = QTableWidgetItem(stat_str)
            it_st.setTextAlignment(center_align)
            self.table_sessions.setItem(row_i, 3, it_st)

            # 4: Date
            it_dt = QTableWidgetItem(s["updated_at"][:16] if s["updated_at"] else "-")
            it_dt.setTextAlignment(center_align)
            self.table_sessions.setItem(row_i, 4, it_dt)

            # 5: Session ID
            it_id = QTableWidgetItem(s["session_id"])
            it_id.setTextAlignment(center_align)
            self.table_sessions.setItem(row_i, 5, it_id)

        self.btn_load.setEnabled(False)
        self.btn_delete.setEnabled(False)

    def on_selection_changed(self) -> None:
        selected_rows = self.table_sessions.selectedItems()
        has_sel = bool(selected_rows)
        self.btn_load.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def get_selected_session_id(self) -> str | None:
        sel_ranges = self.table_sessions.selectedRanges()
        if not sel_ranges:
            return None
        row = sel_ranges[0].topRow()
        item = self.table_sessions.item(row, 5)
        return item.text() if item else None

    def load_selected_session(self) -> None:
        s_id = self.get_selected_session_id()
        if not s_id:
            return
        data = self.session_mgr.load_session(s_id)
        if not data:
            QMessageBox.critical(self, "त्रुटि", "सत्र डेटा लोड नहीं हो सका।")
            return
        self.selected_session_data = data
        self.session_loaded.emit(data)
        self.accept()

    def delete_selected_session(self) -> None:
        s_id = self.get_selected_session_id()
        if not s_id:
            return
        reply = QMessageBox.question(
            self,
            "सत्र हटाएँ",
            "क्या आप वाकई इस सहेजे गए सत्र को हटाना चाहते हैं?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.session_mgr.delete_session(s_id)
            self.refresh_session_list()

    def import_from_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "सत्र फ़ाइल खोलें",
            "",
            f"Voter Match Session (*{SESSION_FILE_EXTENSION});;JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            data = self.session_mgr.import_session_file(file_path)
            self.selected_session_data = data
            self.session_loaded.emit(data)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "त्रुटि", f"सत्र फ़ाइल पढ़ने में समस्या:\n{e}")
