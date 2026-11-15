"""Main Application Window for Electoral Roll Check.

Provides a Hindi-first user interface with font fallbacks (Nirmala UI, Mangal),
background QThread execution with live progress reporting, step-by-step workflow navigation,
and local error logging.
"""

from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QPushButton,
    QLabel,
    QProgressBar,
    QMessageBox,
    QStatusBar,
    QFrame,
    QDialog,
)

from voter_match.ui.import_page import ImportPage
from voter_match.ui.mapping_page import MappingPage
from voter_match.ui.results_page import ResultsPage
from voter_match.ui.review_page import ReviewPage
from voter_match.ui.settings_page import SettingsPage
from voter_match.ui.duplicates_page import DuplicatesPage
from voter_match.ui.search_page import SearchPage

from voter_match.core.matcher import (
    ElectoralRollMatcher,
    MatchSessionResult,
)
from voter_match.core.scorer import ColumnMapping
from voter_match.core.learning import get_default_alias_manager
from voter_match.storage.db import APP_DATA_DIR, get_default_storage
from voter_match.storage.session_manager import (
    SavedSessionData,
    get_default_session_manager,
)
from voter_match.ui.session_dialog import SaveSessionDialog, OpenSessionDialog
from voter_match.ui.theme import GLOBAL_QSS, NAVY_PRIMARY

# Setup local file logging safely
LOG_DIR = APP_DATA_DIR / "logs"
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOG_DIR / "voter_match.log"
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )
except Exception:
    LOG_FILE = Path.cwd() / "voter_match.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class MatcherWorker(QThread):
    """Background worker thread for high-speed Hungarian fuzzy matching."""

    progress = Signal(str, int, int)      # message, current, total
    finished_matching = Signal(object)    # MatchSessionResult
    error_occurred = Signal(str)

    def __init__(
        self,
        matcher: ElectoralRollMatcher,
        records_a: list[dict[str, Any]],
        records_b: list[dict[str, Any]],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.matcher = matcher
        self.records_a = records_a
        self.records_b = records_b
        self.is_cancelled = False

    def run(self) -> None:
        try:
            def on_progress(msg: str, cur: int, tot: int) -> None:
                if self.is_cancelled:
                    raise InterruptedError("प्रक्रिया उपयोगकर्ता द्वारा रद्द कर दी गई।")
                self.progress.emit(msg, cur, tot)

            res = self.matcher.run_matching(self.records_a, self.records_b, on_progress)
            self.finished_matching.emit(res)
        except Exception as e:
            logging.exception("Matching failed")
            self.error_occurred.emit(str(e))

    def cancel(self) -> None:
        self.is_cancelled = True


class MainWindow(QMainWindow):
    """Main Application Window for Electoral Roll Check."""

    def __init__(self):
        super().__init__()
        self.records_a: list[dict[str, Any]] = []
        self.records_b: list[dict[str, Any]] = []
        self.cols_a: list[str] = []
        self.cols_b: list[str] = []
        self.mappings: list[ColumnMapping] = []
        self.session_result: MatchSessionResult | None = None
        self.worker: MatcherWorker | None = None

        # Thresholds
        self.thresh_matched = 0.90
        self.thresh_review = 0.72
        self.min_voter = 0.90
        self.min_rel = 0.80

        self.init_window()
        self.init_ui()

    def init_window(self) -> None:
        self.setWindowTitle("Electoral Roll Check — Offline Windows App for Fuzzy Hindi Voter-List Matching (मतदाता सूची मिलान — BLO साथी)")
        self.resize(1220, 820)
        self.setMinimumSize(960, 680)

        # Set Window Icon
        icon_path = Path(__file__).resolve().parent.parent / "data" / "icon.ico"
        if not icon_path.exists():
            icon_path = Path(__file__).resolve().parent.parent / "data" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def init_ui(self) -> None:
        # Apply Universal High-Contrast Theme
        self.setStyleSheet(GLOBAL_QSS)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top Application Banner
        banner = QFrame()
        banner.setStyleSheet("background-color: #1F4E79; color: white; padding: 4px;")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(15, 6, 15, 6)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        app_title = QLabel("🇮🇳 मतदाता सूची मिलान — बी०एल०ओ० साथी (Electoral Roll Check)")
        app_title.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        app_subtitle = QLabel("उत्तर प्रदेश निर्वाचन नामावली एवं पंचायत सूची शुद्धिकरण प्रणाली (पूर्णतः ऑफलाइन एवं सुरक्षित)")
        app_subtitle.setStyleSheet("font-size: 11px; color: #D0E1FD;")
        title_vbox.addWidget(app_title)
        title_vbox.addWidget(app_subtitle)
        banner_layout.addLayout(title_vbox)

        banner_layout.addStretch()

        # Session Persistence Buttons in Banner
        self.btn_save_session = QPushButton("💾 सत्र सहेजें (Save)")
        self.btn_save_session.setStyleSheet(
            "background-color: #4F46E5; color: white; font-weight: bold; "
            "padding: 5px 12px; border-radius: 5px; font-size: 12px; border: 1px solid #4338CA;"
        )
        self.btn_save_session.setToolTip("वर्तमान मिलान सत्र को सहेजें ताकि बाद में कभी भी यहीं से जारी रख सकें")
        self.btn_save_session.clicked.connect(self.open_save_session_dialog)
        banner_layout.addWidget(self.btn_save_session)

        self.btn_open_session = QPushButton("📂 सत्र खोलें (Open)")
        self.btn_open_session.setStyleSheet(
            "background-color: #0284C7; color: white; font-weight: bold; "
            "padding: 5px 12px; border-radius: 5px; font-size: 12px; border: 1px solid #0369A1;"
        )
        self.btn_open_session.setToolTip("पूर्व में सहेजे गए सत्र को खोलें और अपना कार्य जारी रखें")
        self.btn_open_session.clicked.connect(self.open_open_session_dialog)
        banner_layout.addWidget(self.btn_open_session)

        # Offline & Security Badge
        badge_lbl = QLabel("🛡️ 100% ऑफलाइन (डेटा सुरक्षित)")
        badge_lbl.setStyleSheet(
            "background-color: #16A34A; color: white; font-weight: bold; "
            "padding: 5px 10px; border-radius: 5px; font-size: 11px;"
        )
        badge_lbl.setToolTip("इंटरनेट की कोई आवश्यकता नहीं है। आपका कोई भी डेटा बाहर नहीं जाता।")
        banner_layout.addWidget(badge_lbl)

        main_layout.addWidget(banner)

        # Workflow Navigation Bar (Step-by-Step for Teachers)
        nav_bar = QFrame()
        nav_bar.setStyleSheet("background-color: #E2E8F0; border-bottom: 2px solid #CBD5E1;")
        self.nav_layout = QHBoxLayout(nav_bar)
        self.nav_layout.setContentsMargins(10, 6, 10, 6)
        self.nav_layout.setSpacing(6)

        self.btn_nav_import = self._create_nav_btn("1️⃣ फ़ाइलें आयात करें", 0)
        self.btn_nav_map = self._create_nav_btn("2️⃣ कॉलम मिलाएँ", 1)
        self.btn_nav_results = self._create_nav_btn("3️⃣ मिलान परिणाम", 2)
        self.btn_nav_review = self._create_nav_btn("4️⃣ स्थलीय सत्यापन", 3)

        self.nav_layout.addWidget(self.btn_nav_import)
        self.nav_layout.addWidget(self.btn_nav_map)
        self.nav_layout.addWidget(self.btn_nav_results)
        self.nav_layout.addWidget(self.btn_nav_review)

        self.nav_layout.addSpacing(15)
        sep = QLabel("|")
        sep.setStyleSheet("color: #94A3B8; font-weight: bold;")
        self.nav_layout.addWidget(sep)
        self.nav_layout.addSpacing(15)

        self.btn_nav_duplicates = self._create_nav_btn("⚠️ डुप्लिकेट व परिवार", 4)
        self.btn_nav_search = self._create_nav_btn("🔍 त्वरित खोज", 5)
        self.btn_nav_settings = self._create_nav_btn("⚙️ सेटिंग्स", 6)

        self.nav_layout.addWidget(self.btn_nav_duplicates)
        self.nav_layout.addWidget(self.btn_nav_search)
        self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.btn_nav_settings)

        main_layout.addWidget(nav_bar)

        # Progress Bar Panel (Hidden by default, shown during matching)
        self.progress_panel = QFrame()
        self.progress_panel.setStyleSheet("background-color: #FEF3C7; border-bottom: 2px solid #FCD34D; padding: 6px;")
        self.progress_panel.setVisible(False)
        p_layout = QHBoxLayout(self.progress_panel)
        p_layout.setContentsMargins(15, 6, 15, 6)

        self.lbl_progress_status = QLabel("प्रगति विवरण...")
        self.lbl_progress_status.setStyleSheet("font-weight: bold; color: #92400E; font-size: 13px;")
        p_layout.addWidget(self.lbl_progress_status)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setStyleSheet(
            "QProgressBar { border: 1px solid #D97706; border-radius: 4px; text-align: center; height: 20px; font-weight: bold; }"
            "QProgressBar::chunk { background-color: #16A34A; }"
        )
        p_layout.addWidget(self.pbar)

        self.btn_cancel = QPushButton("रद्द करें (Cancel)")
        self.btn_cancel.setStyleSheet("background-color: #DC2626; color: white; padding: 4px 12px; font-weight: bold; border-radius: 4px;")
        self.btn_cancel.clicked.connect(self.cancel_matching)
        p_layout.addWidget(self.btn_cancel)

        main_layout.addWidget(self.progress_panel)

        # Stacked Pages
        self.stack = QStackedWidget()

        self.page_import = ImportPage()
        self.page_import.ready_to_map.connect(self.on_files_ready_to_map)
        self.stack.addWidget(self.page_import)

        self.page_mapping = MappingPage()
        self.page_mapping.start_matching.connect(self.start_matching_pipeline)
        self.stack.addWidget(self.page_mapping)

        self.page_results = ResultsPage()
        self.page_results.go_to_review.connect(lambda: self.switch_page(3))
        self.page_results.save_session_requested.connect(self.open_save_session_dialog)
        self.stack.addWidget(self.page_results)

        self.page_review = ReviewPage()
        self.page_review.session_updated.connect(self.on_review_session_updated)
        self.page_review.save_session_requested.connect(self.open_save_session_dialog)
        self.stack.addWidget(self.page_review)

        self.page_duplicates = DuplicatesPage()
        self.stack.addWidget(self.page_duplicates)

        self.page_search = SearchPage()
        self.stack.addWidget(self.page_search)

        self.page_settings = SettingsPage()
        self.page_settings.thresholds_changed.connect(self.on_thresholds_changed)
        self.stack.addWidget(self.page_settings)

        main_layout.addWidget(self.stack)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("तैयार | कृपया पहले चरण 1 में दोनों सूचियाँ (A और B) चुनें।")

        self.switch_page(0)

    def _create_nav_btn(self, text: str, index: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 8px 16px; border: 1px solid #CBD5E1; "
            "border-radius: 6px; background-color: #FFFFFF; color: #1E293B; font-size: 13px; }"
            "QPushButton:hover { background-color: #F1F5F9; border-color: #94A3B8; }"
        )
        btn.clicked.connect(lambda: self.switch_page(index))
        return btn

    def switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        buttons = [
            self.btn_nav_import,
            self.btn_nav_map,
            self.btn_nav_results,
            self.btn_nav_review,
            self.btn_nav_duplicates,
            self.btn_nav_search,
            self.btn_nav_settings,
        ]
        for i, b in enumerate(buttons):
            if i == index:
                b.setStyleSheet(
                    "font-weight: bold; padding: 8px 16px; border-radius: 6px; "
                    "background-color: #1E3A8A; color: #FFFFFF; font-size: 13px; border: 1px solid #0F2D6B;"
                )
            else:
                b.setStyleSheet(
                    "font-weight: bold; padding: 8px 16px; border: 1px solid #CBD5E1; "
                    "border-radius: 6px; background-color: #FFFFFF; color: #1E293B; font-size: 13px;"
                )

    def on_files_ready_to_map(
        self,
        cols_a: list[str],
        cols_b: list[str],
        recs_a: list[dict[str, Any]],
        recs_b: list[dict[str, Any]],
    ) -> None:
        self.cols_a = cols_a
        self.cols_b = cols_b
        self.records_a = recs_a
        self.records_b = recs_b

        sample_a = recs_a[0] if recs_a else None
        sample_b = recs_b[0] if recs_b else None

        # Send to Mapping, Duplicates and Search pages
        self.page_mapping.set_columns(cols_a, cols_b, sample_a, sample_b)
        self.page_duplicates.set_data(recs_a, recs_b, cols_a, cols_b)
        self.page_search.set_data(recs_a, recs_b, cols_a, cols_b)

        self.switch_page(1)
        self.status_bar.showMessage(f"फ़ाइलें लोड हुईं: सूची A ({len(recs_a):,} मतदाता), सूची B ({len(recs_b):,} मतदाता)")

    def start_matching_pipeline(self, mappings: list[ColumnMapping], match_within_ward: bool) -> None:
        self.mappings = mappings

        matcher = ElectoralRollMatcher(
            mappings=mappings,
            threshold_matched=self.thresh_matched,
            threshold_review=self.thresh_review,
            min_voter_sim=self.min_voter,
            min_relative_sim=self.min_rel,
            match_within_ward=match_within_ward,
            alias_manager=get_default_alias_manager(),
        )

        self.progress_panel.setVisible(True)
        self.pbar.setValue(0)
        self.lbl_progress_status.setText("मिलान प्रक्रिया आरंभ हो रही है...")

        self.worker = MatcherWorker(matcher, self.records_a, self.records_b, self)
        self.worker.progress.connect(self.on_matching_progress)
        self.worker.finished_matching.connect(self.on_matching_finished)
        self.worker.error_occurred.connect(self.on_matching_error)
        self.worker.start()

    def on_matching_progress(self, msg: str, cur: int, tot: int) -> None:
        self.lbl_progress_status.setText(msg)
        pct = int((cur / max(1, tot)) * 100)
        self.pbar.setValue(pct)
        self.status_bar.showMessage(msg)

    def on_matching_finished(self, result: MatchSessionResult) -> None:
        self.progress_panel.setVisible(False)
        self.session_result = result

        self.page_results.set_results(result, self.mappings)
        self.page_review.set_data(result.records_b, self.mappings, session_result=result, session_id="session_current")

        self.switch_page(2)
        matched = result.stats.get("मिला", 0)
        review = result.stats.get("जाँचें", 0)
        missing = result.stats.get("लापता", 0)
        self.status_bar.showMessage(f"मिलान पूर्ण! मिला: {matched}, जाँचें: {review}, लापता: {missing}")

        # Auto-save session for crash recovery
        try:
            sm = get_default_session_manager()
            sm.auto_save(SavedSessionData(
                session_id="__autosave_latest__",
                title="स्वतः-सहेजा गया सत्र",
                file_a=getattr(self.page_import.widget_a, "file_path", ""),
                file_b=getattr(self.page_import.widget_b, "file_path", ""),
                cols_a=self.cols_a,
                cols_b=self.cols_b,
                records_a=self.records_a,
                records_b=self.records_b,
                mappings=self.mappings,
                session_result=result,
            ))
        except Exception:
            pass

    def on_review_session_updated(self) -> None:
        if hasattr(self, "session_result") and self.session_result:
            self.session_result.recalculate_stats()
            self.page_results.set_results(self.session_result, self.mappings)
            matched = self.session_result.stats.get("मिला", 0)
            review = self.session_result.stats.get("जाँचें", 0)
            missing = self.session_result.stats.get("लापता", 0)
            self.status_bar.showMessage(f"सत्यापन अपडेट हुआ! मिला: {matched}, जाँचें: {review}, लापता: {missing}")

            # Update auto-saved session
            try:
                sm = get_default_session_manager()
                sm.auto_save(SavedSessionData(
                    session_id="__autosave_latest__",
                    title="स्वतः-सहेजा गया सत्र",
                    file_a=getattr(self.page_import.widget_a, "file_path", ""),
                    file_b=getattr(self.page_import.widget_b, "file_path", ""),
                    cols_a=self.cols_a,
                    cols_b=self.cols_b,
                    records_a=self.records_a,
                    records_b=self.records_b,
                    mappings=self.mappings,
                    session_result=self.session_result,
                ))
            except Exception:
                pass

    def on_matching_error(self, err_msg: str) -> None:
        self.progress_panel.setVisible(False)
        QMessageBox.critical(self, "त्रुटि", f"मिलान प्रक्रिया के दौरान त्रुटि उत्पन्न हुई:\n{err_msg}\n\nविवरण लॉग फ़ाइल में लिखा गया है।")
        self.status_bar.showMessage("त्रुटि के कारण प्रक्रिया रुक गई।")

    def cancel_matching(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_bar.showMessage("प्रक्रिया रद्द की जा रही है...")

    def on_thresholds_changed(self, m: float, r: float, v: float, rel: float) -> None:
        self.thresh_matched = m
        self.thresh_review = r
        self.min_voter = v
        self.min_rel = rel
        self.status_bar.showMessage("नई मिलान सीमाएँ सहेजी गईं।")

    def open_save_session_dialog(self) -> None:
        if not self.records_b and not self.session_result:
            QMessageBox.information(
                self,
                "सत्र सहेजें",
                "सत्र सहेजने के लिए पहले मतदाता सूची लोड करें या मिलान शुरू करें।",
            )
            return

        file_a_path = getattr(self.page_import.widget_a, "file_path", "")
        file_b_path = getattr(self.page_import.widget_b, "file_path", "")

        default_title = "मतदाता मिलान सत्र"
        if file_b_path:
            default_title = f"{Path(file_b_path).stem} मिलान सत्र"

        data = SavedSessionData(
            session_id="",
            title=default_title,
            file_a=file_a_path,
            file_b=file_b_path,
            cols_a=self.cols_a,
            cols_b=self.cols_b,
            records_a=self.records_a,
            records_b=self.records_b,
            mappings=self.mappings,
            session_result=self.session_result,
        )
        dlg = SaveSessionDialog(data, self)
        dlg.exec()

    def open_open_session_dialog(self) -> None:
        dlg = OpenSessionDialog(self)
        dlg.session_loaded.connect(self.restore_session)
        dlg.exec()

    def restore_session(self, data: SavedSessionData) -> None:
        self.cols_a = data.cols_a
        self.cols_b = data.cols_b
        self.records_a = data.records_a
        self.records_b = data.records_b
        self.mappings = data.mappings
        self.session_result = data.session_result

        sample_a = self.records_a[0] if self.records_a else None
        sample_b = self.records_b[0] if self.records_b else None

        self.page_mapping.set_columns(data.cols_a, data.cols_b, sample_a, sample_b)
        self.page_duplicates.set_data(data.records_a, data.records_b, data.cols_a, data.cols_b)
        self.page_search.set_data(data.records_a, data.records_b, data.cols_a, data.cols_b)

        if data.session_result:
            self.page_results.set_results(data.session_result, data.mappings)
            self.page_review.set_data(
                data.session_result.records_b,
                data.mappings,
                session_result=data.session_result,
                session_id=data.session_id,
            )
            self.switch_page(2)  # Switch to Results page
            QMessageBox.information(
                self,
                "सत्र लोड हुआ",
                f"सत्र '{data.title}' सफलतापूर्वक पुनः आरंभ किया गया!\n"
                f"कुल {len(data.records_b):,} मतदाताओं का डेटा और आपके पिछले सत्यापन निर्णय उपलब्ध हैं।",
            )
            self.status_bar.showMessage(f"सत्र '{data.title}' सक्रिय है।")
        else:
            self.switch_page(1)  # Switch to Mapping page
            self.status_bar.showMessage(f"सत्र '{data.title}' के कॉलम लोड हुए।")
