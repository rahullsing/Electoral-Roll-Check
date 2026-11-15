"""Script to parse and save user's attached Chanchpur Bhatela datasets into Excel workbooks."""

from pathlib import Path
import pandas as pd
import io

# We will read the raw strings and create the Excel files
DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
