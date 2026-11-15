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
if hasattr(sys, "_MEIPASS"):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _resolve_resource_path(relative_path: str) -> Path | None:
    """Safely resolve bundled resource in PyInstaller _MEIPASS or source tree."""
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.append(meipass / relative_path)
        candidates.append(meipass / "voter_match" / relative_path)
        if relative_path.startswith("voter_match/"):
            candidates.append(meipass / relative_path[len("voter_match/"):])
    pkg_root = Path(__file__).resolve().parent.parent
    candidates.append(pkg_root / relative_path)
    candidates.append(Path.cwd() / relative_path)
    for c in candidates:
        if c.exists():
            return c
    return None

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
    icon_path = _resolve_resource_path("voter_match/data/icon.ico")
    if not icon_path or not icon_path.exists():
        icon_path = _resolve_resource_path("voter_match/data/icon.png")
    if icon_path and icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Set Indic Hindi font family priority
    font = QFont()
    font.setFamilies(["Nirmala UI", "Mangal", "Noto Sans Devanagari", "Segoe UI", "sans-serif"])
    font.setPointSize(10)
    app.setFont(font)

    # Allow automated self-check / headless launch verification
    if "--test-launch" in sys.argv or "--check" in sys.argv:
        print("Launch self-check OK: App initialized successfully.")
        return 0

    from voter_match.ui import i18n

    i18n.install()  # loads the saved language (हिंदी / English)
    window = MainWindow()
    window.show()
    i18n.set_language(i18n.current_language(), persist=False)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
