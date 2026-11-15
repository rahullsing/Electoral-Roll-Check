# Progress Tracking: Electoral Roll Check (मतदाता सूची मिलान)

Offline Windows Application for Fuzzy Hindi Voter-List Matching (बूथ लेवल अधिकारी / BLO साथी)

## 📌 Status Dashboard
- **Total Modules**: 14 Major Components
- **Completed**: 14 / 14 (100% Complete)
- **Status**: Production Quality, Full Code Written, All 22 Unit, Integration & UI Tests Passing!
- **Real-World Testing**: Verified against actual user rolls `Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx` (649 rows) vs `Chanchpur_Bhatela_Check_List_B.xlsx` (707 rows) in 1.23s!
- **Target Audience**: Booth Level Officers (BLOs) / Primary School Teachers in Uttar Pradesh

---

## 🌟 Key Innovations & Recent Upgrades (Latest Sprint)
1. **Elimination of Duplicate Next Buttons & Clean Forward Workflow**:
   - **Screen 2 ("स्तंभ मिलान")**: Removed redundant `bottom_bar` and duplicate `btn_run_bottom`. Unified into a single prominent `btn_run` ("🚀 मिलान प्रारंभ करें (Start Matching) ➔") in the top action header.
   - **Screen 3 ("मिलान परिणाम")**: Removed duplicate bottom review button. Unified into a single `btn_review` ("🔍 स्थलीय सत्यापन (Review) पर आगे बढ़ें ➔") in the top toolbar alongside Excel and PDF export buttons.
   - Zero ambiguity for non-technical users: each screen now has exactly ONE unambiguous forward action button.
2. **Space-Optimized Screen Proportions (85%+ Dedicated to Data)**:
   - **Screen 3 ("मिलान परिणाम") KPI Proportions**: Replaced oversized 160px vertical stat cards with sleek 32px horizontal `CompactStatPill` widgets in a single neat row. The result preview table now enjoys **85%+ vertical screen real estate**, displaying full voter details without requiring vertical squishing.
   - **Screen 2 ("स्तंभ मिलान") Proportions**: Compacted `RoleCardWidget` margins (padding 6px 10px, grid spacing 4px) and removed the 60px bottom frame. The role mapping area now easily displays 4-5 role cards simultaneously on standard 1366×768 teacher laptops.
3. **Kram Sankhya (Roll Serial Number) Paper Reference System (`कागज़ी क्रम संख्या`)**:
   - Column Mapping (Step 2) now asks for **"🔢 क्रम संख्या / रोल क्रमांक (Roll Serial No.)"** from both sheets, with auto-suggestion for `क्र०`, `क्रमांक`, `अनुक्रमांक`, `Sl No`, etc.
   - Dedicated `Paper Ref` importance (weight 0.0) ensures differing roll serial numbers between reference and verification rolls never penalize matching scores.
   - **Excel Export Prominence**: Every result sheet now prominently features Column 2 (`क्र० [सूची B]`) and Column 3 (`क्र० [सूची A]`) right next to the row counter, enabling BLOs to instantly turn to the exact voter in their physical paper registers.
   - **Review Screen & PDF Integration**: Both the Review screen and printable PDF display the exact paper roll numbers for List B and candidate List A records.
4. **Direct Post-Review Excel Download (`📥 अद्यतन Excel डाउनलोड करें`)**:
   - BLOs can download the complete 5-sheet formatted Excel report right from the "स्थलीय सत्यापन" (Review) screen without navigating back and forth.
   - Live decisions (e.g. `स्वीकृत (प्रत्याशी 1)`, `लापता`) and field remarks (`BLO टिप्पणी`) automatically write to the Excel sheets.
   - Dynamic session recalculation moves verified records into the "3. मिला" sheet and updates summary metrics in real-time.
5. **Bulk Auto-Approve High Confidence (`⚡ उच्च समानता वाले स्वतः स्वीकारें (>85%)`)**:
   - Single-click action that accepts all candidates scoring $\ge 85\%$, dramatically speeding up verification of large rolls.
6. **Universal High-Contrast Theme (No White-on-White)**:
   - Fixed Windows Qt palette glitch by enforcing deep navy headers (`#1E3A8A`) with crisp white bold text (`#FFFFFF`) and dark slate text (`#0F172A`) across all tables.
   - Suppressed benign Qt `QFont::setPointSize: Point size <= 0 (-1)` warnings via Qt message handler in `app.py`.

---

## 📋 Task Checklist

### Phase 1: Environment & Project Foundation
- [x] Workspace initialization and package installation (`PySide6`, `pandas`, `openpyxl`, `rapidfuzz`, `scipy`, `reportlab`, `pytest`)
- [x] `progress.md` initialized with full architecture and roadmap
- [x] Default configuration files:
  - [x] `voter_match/data/rules_default.json` (Devanagari normalization rules)
  - [x] `voter_match/data/stopwords_default.json` (Honorifics and common Indian/Hindi titles)

### Phase 2: Core Hindi Processing Engine
- [x] `voter_match/core/normalize.py`:
  - NFC normalization, ZWJ/ZWNJ stripping, Nukta removal, punctuation/abbreviation handling
  - Devanagari digit normalization (०-९ -> 0-9)
  - Half-nasal stripping (न्, म्, ण्, ङ्, ञ्), Anusvara (ं), Chandrabindu (ँ)
  - Halant & conjunct normalizations (्र, ृ, etc.)
  - Matra and vowel normalizations (ी->ि, ू->ु, ै->े, ौ->ो, ॉ->ा, ई->इ, etc.)
  - Consonant phonetic class mapping (श/ष->स, व->ब, ण->न, ढ़->ढ, ड़->ड)
  - Special voter roll variations (सिंग->सिह, खान/खां/खाँ/खॉं->खा)
  - Stopword/honorific stripping (कुमार, कुमारी, देवी, सिंह, शर्मा, etc.)
  - Return `NormalizedName` dataclass (original, normalized, core, skeleton, tokens, space_free, phonetic_key)
- [x] `voter_match/core/phonetic.py`:
  - Custom Devanagari Soundex-like phonetic key (grouping articulatory classes: K, C, T, P, S, N, R, Y, H)
  - Collapse repeats, length-6 key for blocking
- [x] `voter_match/core/similarity.py`:
  - Multi-method similarity calculation:
    - RapidFuzz ratio on space-free form
    - Jaro-Winkler on space-free form
    - token_set_ratio on token list
    - Substring containment (length >= 3 -> 0.92)
    - Core form comparison (exact -> 0.93; 0.92 * ratio)
    - Consonant skeleton ratio (0.90 * ratio)
    - Phonetic key match -> 0.88 (gated behind 0.60 char ratio)
    - Learned alias match -> 0.97
  - Returns `(score, method_used)` for transparency
- [x] `voter_match/core/scorer.py`:
  - Weighted record scoring across roles:
    - Voter Name, Relative Name, Age, Gender, House No., Ward/Section, Custom
  - "Must Match" role penalty cap (< 0.85 -> cap at 0.5)
  - Main name discrepancy penalty (< 0.60 -> -0.10)
  - Sibling guard (relative name >= 0.95 but voter name < 0.80 -> cap at review tier)
  - Age difference bonus/penalty with editable tolerance
  - Gender mismatch penalty (-0.20)
  - Penalty cap (if both names >= 0.95, cap age/gender penalty to 0.05)
  - House number bonus (+0.04)
  - Returns Hindi human-readable explanation reasons list
- [x] `voter_match/core/blocking.py`:
  - Candidate pair generator for high-performance scale (5000 x 5000 in < 60s)
  - Phonetic key prefix blocking, first-consonant dual-name blocking, RapidFuzz process.extract top-20
  - Ward/Section partition blocking
- [x] `voter_match/core/matcher.py`:
  - Exact match fast-path
  - Candidate scoring & Cost matrix creation
  - Optimal 1-to-1 global assignment via `scipy.optimize.linear_sum_assignment`
  - Top-3 candidates preserved per List-B record
  - Tier classification: मिला (Matched), जाँचें (Review), लापता (Missing in A), केवल सूची A में (Only in A)
  - Live review override & dynamic statistics recalculation (`recalculate_stats()`)
- [x] `voter_match/core/duplicates.py`:
  - Intra-list duplicate voter detection (score >= 0.92)
  - Family / Household clustering
- [x] `voter_match/core/learning.py`:
  - Learning alias pairs from user review decisions (e.g. धांसू <-> घासू)
  - JSON import/export for BLO sharing
- [x] `voter_match/core/ocr.py`:
  - Scanned roll card grid extraction (3x10 cards) with Otsu binarization
  - Dual Hindi / English OCR parsing with low confidence flags

### Phase 3: Storage & Persistence
- [x] `voter_match/storage/db.py`:
  - SQLite database with fallback directory protection for restricted Windows school PCs:
    - Mapping profiles (e.g. "पंचायत vs विधानसभा")
    - Custom normalization rules & weights
    - Learned aliases
    - Session state & review decisions (auto-save / resume)
    - Audit trail log

### Phase 4: Export Engine
- [x] `voter_match/export/excel_export.py`:
  - Formatted multi-sheet Excel output using `openpyxl`:
    - सारांश (Summary & statistics)
    - 1. लापता मतदाता (Missing)
    - 2. जाँचें (Needs Review side-by-side with reasons)
    - 3. मिला (Matched, including live user-verified additions)
    - 4. केवल सूची A में (Only in reference list)
    - 5. पूरी सूची (Full Master list)
    - Two-level comparative headers, A4 Landscape print setups, freeze panes, auto-fit column widths, `BLO निर्णय` and `स्थलीय टिप्पणी (Remarks)` columns
- [x] `voter_match/export/pdf_export.py`:
  - Clean printable Hindi PDF export with Nirmala UI / Devanagari font embedding

### Phase 5: GUI Application (PySide6)
- [x] `voter_match/ui/theme.py`:
  - Centralized high-contrast stylesheet (`GLOBAL_QSS`)
  - Deep Navy (`#1E3A8A`) headers with crisp white text (`#FFFFFF`)
  - High-contrast typography and explicit dark text foregrounds (`#0F172A`)
- [x] `voter_match/ui/main_window.py`:
  - Main window shell with numbered 4-step wizard navigation, status bar, and background QThread execution
  - Real-time signal connection syncing Review decisions with Results dashboard
- [x] `voter_match/ui/import_page.py`:
  - Maximized preview table (85%+ vertical height), compact 34px toolbar, sheet selector, and clear forward flow
- [x] `voter_match/ui/mapping_page.py`:
  - Column to Role mapping cards with **live sample value previews** from uploaded files, plain-language explanations, and auto-suggestion
- [x] `voter_match/ui/review_page.py`:
  - Side-by-side verification interface with colored diff legend (🟢 green identical, 🔴 red difference)
  - 1-click updated Excel download button
  - Bulk auto-approve high confidence button
  - Preset field remarks dropdown
  - Full keyboard shortcuts (`1`, `2`, `3`, `M`, `S`, `Left`, `Right`)
- [x] `voter_match/ui/results_page.py`:
  - Plain-language KPI cards and high-contrast result preview with 1-click Excel and PDF export
- [x] `voter_match/ui/settings_page.py`:
  - Normalization rule editor with interactive test box, threshold sliders, and learned aliases manager
- [x] Advanced Features Implemented:
  - Global Fuzzy Search Tab across both lists (`voter_match/ui/search_page.py`)
  - Household / Family grouping view (`voter_match/ui/duplicates_page.py`)
  - Character-level Devanagari diff highlighting

### Phase 6: Testing & Packaging
- [x] Comprehensive unit tests (`voter_match/tests/test_core.py`):
  - Normalization test cases (जमीलखां/जमीलखाँ, प्रसाद/प्साद, कृष्ण/क्रष्ण, etc.)
  - Phonetic key test cases
  - Similarity test cases (positive & sibling/negative tests)
  - Scorer & Matcher test cases
- [x] Integration & E2E tests (`voter_match/tests/test_e2e.py`):
  - End-to-end matching, Excel export, PDF export, Household clustering
  - Live review decision override and dynamic Excel report generation test
  - **Real-world Chanchpur Bhatela dataset test (`Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx` vs `Chanchpur_Bhatela_Check_List_B.xlsx`)**: 707 vs 649 records in 1.23s
- [x] UI headless tests (`voter_match/tests/test_ui.py`):
  - Main window instantiation, contrast verification, mapping auto-suggestions, single button workflow, and screen proportions
- [x] Test suite status: **22/22 tests passing**
- [x] `requirements.txt`
- [x] `build.spec` (PyInstaller Windows configuration)
- [x] `installer/setup.iss` (Inno Setup script for offline Windows deployment)
- [x] `README.md` (Bilingual Hindi + English guide with detailed operational steps)
- [x] Real-world attached Excel files and reports (`sample_data/`)
