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
    excludes=["tkinter", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ElectoralRollCheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "voter_match" / "data" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ElectoralRollCheck",
)
