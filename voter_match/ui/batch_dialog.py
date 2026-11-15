"""Multi-Booth Batch Matching Dialog (बहु-बूथ बैच मिलान)."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from voter_match.core.batch import BatchJob, run_batch
from voter_match.core.scorer import ColumnMapping
from voter_match.ui.copy_support import enable_table_copy, make_selectable
from voter_match.ui.i18n import mark_headers_only, skip_translation, tr, translate_keep_args
from voter_match.ui.theme import GREEN_PRIMARY, NAVY_PRIMARY

FILE_FILTER = "Excel / CSV Files (*.xlsx *.xls *.csv);;All Files (*.*)"


class BatchWorker(QThread):
    progress = Signal(int, int, str)
    finished_batch = Signal(object, str)  # outcomes, summary path
    error_occurred = Signal(str)

    def __init__(self, jobs, template, out_dir, matcher_kwargs, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.template = template
        self.out_dir = out_dir
        self.matcher_kwargs = matcher_kwargs
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            outcomes, summary = run_batch(
                self.jobs,
                self.template,
                self.out_dir,
                self.matcher_kwargs,
                progress=lambda i, n, msg: self.progress.emit(i, n, msg),
                is_cancelled=lambda: self._cancel,
            )
            self.finished_batch.emit(outcomes, summary)
        except Exception as e:
            self.error_occurred.emit(str(e))


class BatchDialog(QDialog):
    """Queue several List A / List B file pairs and match them all at once."""

    def __init__(
        self,
        template: list[ColumnMapping],
        matcher_kwargs: dict[str, Any],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.template = template
        self.matcher_kwargs = matcher_kwargs
        self.jobs: list[BatchJob] = []
        self.worker: BatchWorker | None = None
        self.setWindowTitle("📦 बहु-बूथ बैच मिलान (Multi-Booth Batch Matching)")
        self.resize(980, 560)
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)

        intro = QLabel(
            "<b>एक साथ कई भाग/बूथ का मिलान करें।</b> प्रत्येक जोड़ी (सूची A + सूची B) के लिए अलग Excel रिपोर्ट "
            "और सभी का एक <b>संयुक्त सारांश</b> बनेगा। चरण 2 की वर्तमान कॉलम मैपिंग उपयोग होगी — "
            "अलग नाम वाले कॉलम स्वतः पहचाने जाएंगे। (प्रत्येक फ़ाइल की पहली शीट, पंक्ति 1 = शीर्षक)"
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        intro.setStyleSheet("background:#F1F5F9; padding:8px; border-radius:6px; color:#1E293B;")
        layout.addWidget(intro)

        bar = QHBoxLayout()
        self.btn_add = QPushButton("➕ जोड़ी जोड़ें (A + B)")
        self.btn_add.clicked.connect(self.add_pair)
        bar.addWidget(self.btn_add)
        self.btn_add_folder = QPushButton("📂 फ़ोल्डर से जोड़ियाँ")
        self.btn_add_folder.setToolTip(
            "एक फ़ोल्डर चुनें जिसमें '..._A.xlsx' और '..._B.xlsx' नाम की फ़ाइल-जोड़ियाँ हों"
        )
        self.btn_add_folder.clicked.connect(self.add_folder)
        bar.addWidget(self.btn_add_folder)
        self.btn_remove = QPushButton("🗑️ चयनित हटाएँ")
        self.btn_remove.clicked.connect(self.remove_selected)
        bar.addWidget(self.btn_remove)
        bar.addStretch()
        layout.addLayout(bar)

        self.table = mark_headers_only(QTableWidget(0, 3))  # part names / file names are user data
        self.table.setHorizontalHeaderLabels(["भाग / बूथ नाम", "सूची A (संदर्भ) फ़ाइल", "सूची B (सत्यापन) फ़ाइल"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        enable_table_copy(self.table)
        self.table.setStyleSheet(
            f"QHeaderView::section {{ background-color: {NAVY_PRIMARY}; color: #FFFFFF; font-weight: bold; padding: 5px; }}"
        )
        layout.addWidget(self.table, stretch=1)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("रिपोर्ट फ़ोल्डर:"))
        self.txt_out = QLineEdit(str(Path.home() / "Documents" / "बैच_मिलान_रिपोर्ट"))
        out_row.addWidget(self.txt_out, stretch=1)
        btn_out = QPushButton("बदलें...")
        btn_out.clicked.connect(self.choose_output)
        out_row.addWidget(btn_out)
        layout.addLayout(out_row)

        prog_row = QHBoxLayout()
        self.lbl_status = skip_translation(QLabel(tr("तैयार")))
        self.lbl_status.setStyleSheet("font-weight: bold; color: #334155;")
        prog_row.addWidget(self.lbl_status, stretch=1)
        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        prog_row.addWidget(self.pbar, stretch=1)
        layout.addLayout(prog_row)

        act = QHBoxLayout()
        act.addStretch()
        self.btn_cancel = QPushButton("रद्द करें")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_batch)
        act.addWidget(self.btn_cancel)
        self.btn_start = QPushButton("▶ बैच मिलान शुरू करें")
        self.btn_start.setStyleSheet(
            f"background-color: {GREEN_PRIMARY}; color: white; font-weight: bold; padding: 8px 18px; border-radius: 6px;"
        )
        self.btn_start.clicked.connect(self.start_batch)
        act.addWidget(self.btn_start)
        btn_close = QPushButton("बंद करें")
        btn_close.clicked.connect(self.close)
        act.addWidget(btn_close)
        layout.addLayout(act)

    # --- Queue management ---

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.jobs))
        for i, job in enumerate(self.jobs):
            self.table.setItem(i, 0, QTableWidgetItem(job.display_name()))
            self.table.setItem(i, 1, QTableWidgetItem(Path(job.file_a).name))
            self.table.setItem(i, 2, QTableWidgetItem(Path(job.file_b).name))
            self.table.item(i, 1).setToolTip(job.file_a)
            self.table.item(i, 2).setToolTip(job.file_b)

    def add_pair(self) -> None:
        fa, _ = QFileDialog.getOpenFileName(self, "सूची A (संदर्भ) फ़ाइल चुनें", "", FILE_FILTER)
        if not fa:
            return
        fb, _ = QFileDialog.getOpenFileName(self, "सूची B (सत्यापन) फ़ाइल चुनें", str(Path(fa).parent), FILE_FILTER)
        if not fb:
            return
        self.jobs.append(BatchJob(file_a=fa, file_b=fb, label=Path(fb).stem))
        self._refresh_table()

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "फ़ाइल-जोड़ियों वाला फ़ोल्डर चुनें")
        if not folder:
            return
        files = [f for f in Path(folder).iterdir() if f.suffix.lower() in {".xlsx", ".xls", ".csv"}]
        by_stem: dict[str, dict[str, Path]] = {}
        for f in files:
            stem = f.stem
            for sep in ("_", "-", " "):
                for tag in ("A", "B", "a", "b"):
                    suffix = f"{sep}{tag}"
                    if stem.endswith(suffix):
                        by_stem.setdefault(stem[: -len(suffix)], {})[tag.upper()] = f
        added = 0
        for base, pair in sorted(by_stem.items()):
            if "A" in pair and "B" in pair:
                self.jobs.append(BatchJob(file_a=str(pair["A"]), file_b=str(pair["B"]), label=base))
                added += 1
        self._refresh_table()
        if not added:
            QMessageBox.information(
                self,
                "कोई जोड़ी नहीं मिली",
                "फ़ाइलों के नाम इस प्रकार रखें: 'भाग12_A.xlsx' और 'भाग12_B.xlsx'",
            )

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.jobs):
                del self.jobs[r]
        self._refresh_table()

    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "रिपोर्ट फ़ोल्डर चुनें", self.txt_out.text())
        if folder:
            self.txt_out.setText(folder)

    # --- Running ---

    def start_batch(self) -> None:
        if not self.jobs:
            QMessageBox.warning(self, "सूचना", "कृपया पहले कम से कम एक फ़ाइल-जोड़ी जोड़ें।")
            return
        # Update labels from any edits in the name column
        for i, job in enumerate(self.jobs):
            item = self.table.item(i, 0)
            if item and item.text().strip():
                job.label = item.text().strip()
        self._set_running(True)
        self.worker = BatchWorker(self.jobs, self.template, self.txt_out.text().strip(), self.matcher_kwargs, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_batch.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()

    def cancel_batch(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.lbl_status.setText("वर्तमान जोड़ी पूरी होने के बाद रोका जाएगा...")

    def _set_running(self, running: bool) -> None:
        for b in (self.btn_add, self.btn_add_folder, self.btn_remove, self.btn_start):
            b.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    def on_progress(self, i: int, n: int, msg: str) -> None:
        # the part name inside the message is user data: keep it, translate the wording
        self.lbl_status.setText(translate_keep_args(msg))
        self.pbar.setValue(int(100 * i / max(1, n)))

    def on_finished(self, outcomes, summary_path: str) -> None:
        self._set_running(False)
        self.pbar.setValue(100)
        ok = [o for o in outcomes if not o.error]
        bad = [o for o in outcomes if o.error]
        msg = f"सफल: {len(ok)} | त्रुटि: {len(bad)}\n\nसंयुक्त सारांश:\n{summary_path}"
        if bad:
            msg += "\n\nत्रुटि वाली जोड़ियाँ:\n" + "\n".join(f"• {o.job.display_name()}: {o.error}" for o in bad[:8])
        QMessageBox.information(self, "बैच मिलान पूर्ण", msg)
        try:
            os.startfile(str(Path(summary_path).parent))  # open the report folder (Windows)
        except Exception:
            pass

    def on_error(self, err: str) -> None:
        self._set_running(False)
        QMessageBox.critical(self, "त्रुटि", f"बैच मिलान में त्रुटि:\n{err}")
