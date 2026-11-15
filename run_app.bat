@echo off
title Electoral Roll Check — Offline Windows App for Fuzzy Hindi Voter-List Matching (BLO Saathi)
echo Starting Electoral Roll Check (मतदाता सूची मिलान — BLO साथी)...

if exist "dist\ElectoralRollCheck\ElectoralRollCheck.exe" (
    echo Launching compiled executable...
    start "" "dist\ElectoralRollCheck\ElectoralRollCheck.exe"
) else (
    echo Launching via Python...
    python voter_match\app.py
)
