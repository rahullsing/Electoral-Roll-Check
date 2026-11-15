"""Column -> role auto-suggestion shared by the mapping screen and batch mode.

Scoring per (role, column):
  * exact keyword == header           -> strongest
  * keyword contained in header       -> strong, tighter headers preferred
                                          ('नाम' beats 'अनुभाग संख्या और नाम')
  * fuzzy similarity (>= 70)           -> weak fallback
  * an exclusion word in the header    -> column is never suggested for that role
Columns are then assigned greedily by score so one column serves one role only.
"""

from __future__ import annotations
import rapidfuzz.fuzz as rf_fuzz

ROLE_KEYWORDS: dict[str, list[str]] = {
    "serial_no": ["क्रम", "क्रमांक", "क्र०", "क्र.", "अनुक्रमांक", "serial", "sl", "sr", "sno", "s.no"],
    "epic": ["epic", "एपिक", "पहचान", "पहचान पत्र", "voter id", "card"],
    "voter_name": ["नाम", "मतदाता", "निर्वाचक", "voter", "name"],
    "relative_name": ["पिता", "पति", "माता", "सम्बन्धी", "relative", "father", "husband"],
    "age": ["आयु", "उम्र", "age"],
    "gender": ["लिंग", "gender", "sex"],
    "house_no": ["मकान", "गृह", "house", "hno", "h.no"],
    "ward": ["वार्ड", "भाग", "अनुभाग", "ward", "part", "section"],
}

ROLE_EXCLUDE: dict[str, list[str]] = {
    "serial_no": ["पृष्ठ", "पीडीएफ", "page", "pdf", "वार्ड", "मकान", "epic", "पहचान", "अनुभाग", "भाग"],
    "epic": ["पृष्ठ", "page"],
    "voter_name": ["पिता", "पति", "माता", "सम्बन्धी", "संबंध", "relative", "father", "husband",
                   "अनुभाग", "section", "भाग", "कारण", "टिप्पणी", "file", "फ़ाइल"],
    "relative_name": ["संबंध प्रकार", "relation type"],
    "age": [],
    "gender": [],
    "house_no": ["पृष्ठ", "page", "वार्ड", "epic", "पहचान"],
    "ward": ["पृष्ठ", "page"],
}

MIN_SCORE = 60.0


def column_role_score(role: str, col: str, keywords: list[str] | None = None) -> float:
    col_l = col.lower().strip()
    if not col_l:
        return 0.0
    if any(x in col_l for x in ROLE_EXCLUDE.get(role, [])):
        return 0.0
    best = 0.0
    for kw in keywords or ROLE_KEYWORDS.get(role, [role]):
        kw = kw.lower()
        if col_l == kw:
            score = 300.0
        elif kw in col_l:
            # Contained: longer keyword = more specific; extra header text = less specific
            score = 150.0 + 10.0 * len(kw) - 2.0 * (len(col_l) - len(kw))
            score = max(score, 100.0)
        else:
            r = rf_fuzz.ratio(kw, col_l)
            score = r * 0.8 if r >= 70 else 0.0
        best = max(best, score)
    return best


def suggest_columns(
    cols: list[str],
    roles: list[str],
    keywords: dict[str, list[str]] | None = None,
) -> dict[str, str]:
    """Return role -> column, each column used at most once."""
    kw_map = keywords or ROLE_KEYWORDS
    scored: list[tuple[float, int, str, str]] = []
    for r_i, role in enumerate(roles):
        for col in cols:
            sc = column_role_score(role, col, kw_map.get(role))
            if sc >= MIN_SCORE:
                scored.append((sc, -r_i, role, col))
    scored.sort(reverse=True)
    out: dict[str, str] = {}
    used: set[str] = set()
    for _sc, _r, role, col in scored:
        if role in out or col in used:
            continue
        out[role] = col
        used.add(col)
    return out
