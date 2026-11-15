"""Application Entry Point.

Electoral Roll Check — Offline Windows App for Fuzzy Hindi Voter-List Matching.
(मतदाता सूची मिलान — बी०एल०ओ० साथी)
"""

from __future__ import annotations
import sys
import os
import traceback
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, qInstallMessageHandler, QtMsgType
from PySide6.QtGui import QFont, QIcon

from voter_match.ui.main_window import MainWindow, LOG_FILE


def qt_message_handler(mode, context, message):
    """Filter benign Qt stylesheet/font-pointSize diagnostic warnings on Windows."""
    if "Point size <= 0" in message:
        return
    if mode == QtMsgType.QtWarningMsg:
        logging.warning(f"Qt Warning: {message}")
    elif mode == QtMsgType.QtCriticalMsg:
        logging.error(f"Qt Critical: {message}")
    elif mode == QtMsgType.QtFatalMsg:
        logging.critical(f"Qt Fatal: {message}")


def exception_hook(exctype, value, tb):
    """Global unhandled exception hook logging to file and showing friendly Hindi prompt."""
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    logging.critical(f"Unhandled Exception: {err_msg}")

    # Show friendly message
    msg = (
        "अनुप्रयोग में एक अप्रत्याशित समस्या उत्पन्न हुई है।\n\n"
        f"त्रुटि: {value}\n\n"
        f"विस्तृत लॉग यहाँ सुरक्षित है:\n{LOG_FILE}"
    )
    QMessageBox.critical(None, "गंभीर त्रुटि (Unexpected Error)", msg)
    sys.__excepthook__(exctype, value, tb)


def main():
    # Set Windows App User Model ID so taskbar groups properly
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ECI.VoterRollCheck.IndicFuzzyMatcher.1.0"
            )
        except Exception:
            pass

    sys.excepthook = exception_hook
    qInstallMessageHandler(qt_message_handler)

    app = QApplication(sys.argv)
    app.setApplicationName("Electoral Roll Check")
    app.setOrganizationName("ECI UP BLO Tools")

    # Set Application Window Icon
    icon_path = PROJECT_ROOT / "voter_match" / "data" / "icon.ico"
    if not icon_path.exists():
        icon_path = PROJECT_ROOT / "voter_match" / "data" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Set Indic Hindi font family priority
    font = QFont()
    font.setFamilies(["Nirmala UI", "Mangal", "Noto Sans Devanagari", "Segoe UI", "sans-serif"])
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
