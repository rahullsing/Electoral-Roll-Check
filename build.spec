# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Electoral Roll Check Windows desktop app."""

import sys
from pathlib import Path

block_cipher = None

project_dir = Path(SPECPATH).resolve() if "SPECPATH" in globals() else Path.cwd().resolve()

datas = [
    (str(project_dir / "voter_match" / "data" / "rules_default.json"), "voter_match/data"),
    (str(project_dir / "voter_match" / "data" / "stopwords_default.json"), "voter_match/data"),
    (str(project_dir / "voter_match" / "data" / "icon.png"), "voter_match/data"),
    (str(project_dir / "voter_match" / "data" / "icon.ico"), "voter_match/data"),
    (str(project_dir / "voter_match" / "data" / "rules_default.json"), "data"),
    (str(project_dir / "voter_match" / "data" / "stopwords_default.json"), "data"),
    (str(project_dir / "voter_match" / "data" / "icon.png"), "data"),
    (str(project_dir / "voter_match" / "data" / "icon.ico"), "data"),
]

hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "pandas",
    "openpyxl",
    "rapidfuzz",
    "rapidfuzz.fuzz",
    "rapidfuzz.process",
    "rapidfuzz.distance.JaroWinkler",
    "scipy.optimize",
    "scipy.optimize.linear_sum_assignment",
    "reportlab",
    "reportlab.lib",
    "reportlab.platypus",
    "sqlite3",
    "voter_match",
    "voter_match.core",
    "voter_match.core.normalize",
    "voter_match.core.phonetic",
    "voter_match.core.similarity",
    "voter_match.core.scorer",
    "voter_match.core.blocking",
    "voter_match.core.matcher",
    "voter_match.core.duplicates",
    "voter_match.core.learning",
    "voter_match.core.ocr",
    "voter_match.core.assignment",
    "voter_match.core.transliterate",
    "voter_match.core.column_suggest",
    "voter_match.core.forms",
    "voter_match.core.evaluation",
    "voter_match.core.batch",
    "voter_match.storage",
    "voter_match.storage.db",
    "voter_match.storage.session_manager",
    "voter_match.export",
    "voter_match.export.excel_export",
    "voter_match.export.pdf_export",
    "voter_match.ui",
    "voter_match.ui.theme",
    "voter_match.ui.import_page",
    "voter_match.ui.mapping_page",
    "voter_match.ui.settings_page",
    "voter_match.ui.review_page",
    "voter_match.ui.results_page",
    "voter_match.ui.duplicates_page",
    "voter_match.ui.search_page",
    "voter_match.ui.session_dialog",
    "voter_match.ui.main_window",
    "voter_match.ui.batch_dialog",
    "voter_match.ui.tts",
    "PySide6.QtTextToSpeech",
]

a = Analysis(
    [str(project_dir / "voter_match" / "app.py")],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # jinja2: only used by pandas DataFrame.style (never used here; not installed).
    # scipy.special._cdflib: listed by PyInstaller's SciPy-1.13 hook, but SciPy >= 1.15
    # no longer ships it as a separate module. Excluding both only silences
    # "Hidden import not found" warnings; nothing the app uses is removed.
    excludes=["tkinter", "matplotlib", "jinja2", "scipy.special._cdflib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ElectoralRollCheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "voter_match" / "data" / "icon.ico"),
)
