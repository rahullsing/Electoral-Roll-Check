# Progress Tracking: Electoral Roll Check (मतदाता सूची मिलान)

Offline Windows Application for Fuzzy Hindi Voter-List Matching (बूथ लेवल अधिकारी / BLO साथी)

## 📌 Status Dashboard
- **Total Modules**: 14 Major Components
- **Completed**: 14 / 14 (100% Complete)
- **Status**: Production Quality, Full Code Written, All 57 Unit, Integration, UI, i18n & Benchmark Tests Passing!
- **Real-World Testing**: Verified against actual user rolls `Chanchpur_Bhatela_Voter_List_2026_Hindi.xlsx` (649 rows) vs `Chanchpur_Bhatela_Check_List_B.xlsx` (707 rows) in ~0.9s — Matched 400 / Review 165 / Missing 142
- **Interface Languages**: हिंदी and English (switchable from the banner or Settings, remembered across restarts)
- **Target Audience**: Booth Level Officers (BLOs) / Primary School Teachers in Uttar Pradesh
- **GitHub Repository**: [rahullsing/Electoral-Roll-Check](https://github.com/rahullsing/Electoral-Roll-Check.git) (Synced & Pushed to `main`)
- **Executable**: Single-file standalone Windows executable at `dist/ElectoralRollCheck.exe` + 1-click launcher `run_app.bat`

---

## 🧭 Sprint: Matching Accuracy, Bilingual UI, Copy-to-Excel & Data Safety (2026-11-15, later)

### Matching accuracy (`core/assignment.py`, `core/matcher.py`, `core/scorer.py`)
1. **Assignment objective fixed** — the 1-to-1 solver used to maximise the *number* of pairs first, so it broke 100% matches apart to form two weak 55–60% pairs (genuine voters ended up "Missing"). It now maximises total confidence above the threshold; leaving a voter unassigned costs nothing.
2. **Strong candidate taken elsewhere → Review**, not Missing (usually a duplicate entry in List B).
3. **Age-gap guard** — same name + same relative with an age gap > 2× tolerance (namesakes, uncle/nephew) is never auto-"मिला"; it goes to Review (`ScoreResult.age_conflict`).
4. Chanchpur real data: **Matched 384 → 400, Review 104 → 165, Missing 219 → 142**; 15/15 sampled newly-matched records verified genuine.

### Duplicate detection (`core/duplicates.py`, `ui/duplicates_page.py`)
1. Page now uses the **Step-2 column mapping** (List A → col_a, List B → col_b) instead of guessing; it previously missed relative columns such as "संबंधी का नाम", so duplicates were judged on the voter name alone.
2. Strict pair rule: voter ≥ 90% **and** relative ≥ 85% (voter ≥ 97% when no relative column); typing-slip exception (voter ≥ 85%, identical relative, age ±1); siblings / large age gaps excluded.
3. **Complete-linkage grouping** — a voter joins a group only if it matches every member (no A~B~C chaining).
4. "🧩 Columns used" line shows exactly which columns were compared. Chanchpur List B: 16 mostly-false groups → 3 plausible ones.

### Bilingual interface (`ui/i18n.py`, `ui/i18n_en.py`)
1. Whole UI switchable **हिंदी ⇄ English** (banner toggle + Settings), persisted with QSettings; ~500 strings incl. dynamic templates, message boxes, file dialogs and the status bar.
2. **User data is never translated**: names, relatives, column names, sample values, search text, serial numbers, file/profile/session names are protected (`skip_translation`, `trf`, `mark_headers_only`, `mark_data_columns`, `keep_item`, `ROLE_NO_I18N`). Logic that used to read on-screen text now uses item data / indexes.
3. Fixed: a diff-highlighting fragment "म" was translated to "F" (name shown as "अनाFका"); Step-2 gender sample "महिला" shown as "Female"; accuracy dialog / progress line partly untranslated.
4. Guards: coverage test (every UI string has English), adversarial whole-app test (voters named "मकान", "सूची", "सफल"…, relative "मतदाता", gender "महिला" stay unchanged on every screen).

### UI quality
1. Container styles leaked onto every child label (QLabel is a QFrame) → every label boxed; styles now scoped per widget. Mapping badges rendered dark (`#RRGGBBAA` read as `#AARRGGBB`) — fixed with `rgba()`.
2. **Quick Search rebuilt**: one compact toolbar, results fill the screen, live search, search by name / relative / both / serial-EPIC, shows serial, relative, age, gender, house, row; follows the live Step-2 mapping; serial numbers stored as floats (1349.0) now found and shown correctly.
3. Results pills no longer truncated; long reason columns fit the screen; Review shows Hindi field labels; matras no longer split from consonants in diff highlighting (no dotted circles).
4. **Copy to Excel** (`ui/copy_support.py`): Excel-style cell selection, Ctrl+C / Ctrl+Shift+C (with headings), right-click copy menu on every table; Field Verification "📋 Copy details" (Ctrl+Shift+C) and per-candidate "📋 Copy" buttons copy the original record as one Excel row; voter-detail labels selectable.
5. **PDF Hindi fixed**: Windows ships Nirmala UI as `Nirmala.ttc`; exporter looked for `.ttf` and fell back to Helvetica (Hindi printed as black squares). Now loads the TTC (with Mangal/Aparajita/Kokila fallbacks), reorders the short-i matra when no shaping engine is present, and enables HarfBuzz shaping automatically if `uharfbuzz` is installed.

---

## 🚀 Sprint: Performance + BLO Workflow Features (2026-11-15)

### Optimizations
1. **Sparse optimal assignment** (`core/assignment.py`): union-find splits the candidate graph into connected components and runs `linear_sum_assignment` per component. Same global optimum as the old dense (n_b × n_a) solve (verified objective-equal on random graphs and row-identical on the Chanchpur real data), without the ~100 MB matrix.
2. **Vectorised blocking** (`core/blocking.py`): one multi-threaded `rapidfuzz.process.cdist` call per 512-row chunk replaces a Python-level `extract()` per row; ties broken by lowest index exactly like `extract`, so candidate sets are identical.
3. **Memoisation**: `HindiNormalizer.normalize()` cache; per-run similarity / age / gender / house / EPIC caches in `RecordScorer`; deleted-row flags and role lookups precomputed once.
4. **Benchmark** (`scripts/benchmark.py`, guarded by `test_benchmark_large_roll_speed`): 5,000 × 5,000 synthetic rolls **78.4 s → 21.8 s**; real Chanchpur roll 2.3 s → 0.9 s with identical results.
5. **Debounced review**: autosave runs 2 s after the last decision (flushed on close) and the Results table rebuilds only when visible; per-decision rows are still written immediately.
6. **Session format v2**: records stored once and referenced by index; `.vsession` gzip-compressed; SQLite payload zlib-compressed; v1 files still load.

### Features
1. **EPIC role**: exact EPIC → definite match (score ≥ 0.97, bypasses sibling guard); mismatch → −15 % and never auto-"मिला"; EPIC candidates injected into blocking; OCR slip repair (O→0, I→1).
2. **Roll-year age offset**: roll year A / B on the age card → `ColumnMapping.year_offset`.
3. **Undo (Ctrl+Z)** on the Review screen, incl. bulk auto-approve groups, alias/rejection side effects and stored decisions (`StorageManager.delete_decision`).
4. **Rejection learning**: passed-over / "missing" candidates stored in `rejected_pairs`; future runs cap those pairs at 0.54 (visible, never auto-assigned). Learned aliases are now persisted to the app DB (previously in-memory only).
5. **Cross-list duplicate detection**: B rows strongly matching the same A voter are flagged (`conflict_b_indices`) and warned on accept.
6. **Form 6/7/8 work list** (`core/forms.py`): Excel (sheet per form, tick column) + PDF checklist; BLO remarks override.
7. **Accuracy & threshold tuning** (`core/evaluation.py`): precision/recall from manual decisions, grid-searched thresholds minimising 5×errors + reviews; `MatchSessionResult.retier()` applies new thresholds instantly to undecided records (also used by Settings).
8. **Roman → Devanagari transliteration** (`core/transliterate.py`) before normalisation.
9. **Offline name read-aloud** (`ui/tts.py`): Hindi voice when installed, romanised fallback for English voices.
10. **Multi-booth batch mode** (`core/batch.py`, `ui/batch_dialog.py`): queue / folder-pair discovery, per-pair reports, combined summary, error isolation.
11. **ETA** on the matching progress panel.

### Fixes found along the way
* `recalculate_stats()` treated A voters held by "जाँचें" rows as "only in A" (29 → 262 on real data after any decision); now consistent with matching-time semantics.
* Column auto-suggest picked "अनुभाग संख्या और नाम" for voter name and "पृष्ठ संख्या" for serial/house; new shared `core/column_suggest.py` (exact-match bonus, exclusion words, one column per role).

---

## 🌟 Key Innovations & Recent Upgrades (Previous Sprint)
1. **NumPy / Pandas Scalar JSON Serialization Guard (Fixed `int64` error)**:
   - Fixed `TypeError: Object of type int64 is not JSON serializable` when saving sessions or exporting `.vsession` files.
   - Built recursive `clean_value_for_json()` and `json_default_fallback()` in `voter_match/storage/session_manager.py` that automatically maps NumPy integers (`np.int64`, `np.int32`), floats (`np.float64`), booleans (`np.bool_`), and Pandas null values (`pd.NA`, `np.nan`) to native Python types.
   - Added unit test `test_session_numpy_int64_serialization` ensuring permanent regression protection.
2. **Criteria Filter Dropdown & Clickable KPI Pills (Screen 3 - मिलान परिणाम)**:
   - Added criteria filter dropdown (`combo_criteria`):
     - `📋 सभी परिणाम (All Results)`
     - `🟢 केवल मिला (Matched Only)`
     - `🟡 केवल जाँचें (Needs Review Only)`
     - `🔴 केवल नहीं मिला / लापता (Missing in A Only)`
     - `🔵 केवल सूची A में (Only in List A)`: Displays all unmatched reference records with soft blue badge, row number, paper roll serial number, voter name, relative name, and explanation.
   - **Direct Pill Click Filtering**: Clicking any KPI pill (`CompactStatPill`) immediately filters the results table to that criteria.
   - **Live Text Search**: Added real-time search box (`txt_search`) filtering by voter name, relative name, or paper roll serial number.
   - **Filtered Count Badge**: Live counter (`दिखाए गए: X / Y`).
2. **Complete Session Persistence & Reopening (`💾 सत्र सहेजें / 📂 सत्र खोलें`)**:
   - Built `voter_match/storage/session_manager.py` with lossless serialization of source records, column mappings, candidates, verification decisions, field remarks, and statistics.
   - Dual storage engines: Local SQLite database (`saved_sessions` table) and portable `.vsession` files for easy sharing via USB pen drives.
   - Intuitive dialogs: `SaveSessionDialog` and `OpenSessionDialog` accessible from the top banner, Results page, and Review page.
   - Reopen any existing session with 1 click: all files, mappings, decisions, and results are restored without re-uploading files!
   - Background auto-save to `__autosave_latest__` for crash protection and automatic recovery.
3. **Comprehensive Bilingual User Guide (`USER_GUIDE.md`)**:
   - Detailed operational instructions tailored for BLOs and government teachers.
   - Covers file loading, sheet selection, Devanagari column mapping, paper roll numbers, criteria filtering, side-by-side review, keyboard shortcuts, field notes, session saving/loading, and 5-sheet Excel / printable PDF reports.
4. **Standalone Windows Executable (`.exe`) Compilation**:
   - Resolved PyInstaller spec pathing (`Path(SPECPATH)`).
   - Compiled complete distribution into `dist\ElectoralRollCheck\ElectoralRollCheck.exe` (20.2 MB).
   - Created double-click batch launcher `run_app.bat`.
5. **Git Repository Setup & Sync**:
   - Initialized Git repository, configured `.gitignore` (safely ignoring caches, logs, databases, and build artifacts).
   - Configured remote `origin https://github.com/rahullsing/Electoral-Roll-Check.git`.
   - Rebased on top of remote initial commit and pushed cleanly to `main` branch.
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
- [x] Test suite status: **57/57 tests passing** (core, e2e, UI, features, i18n data-safety, 3,000×3,000 benchmark)
- [x] `requirements.txt`
- [x] `build.spec` (PyInstaller Windows configuration)
- [x] `installer/setup.iss` (Inno Setup script for offline Windows deployment)
- [x] `README.md` (Bilingual Hindi + English guide with detailed operational steps)
- [x] Real-world attached Excel files and reports (`sample_data/`)
