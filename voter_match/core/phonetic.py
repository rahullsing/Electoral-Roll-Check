"""Hindi Devanagari Phonetic Key Generator.

Implements an articulatory Soundex-like algorithm specifically tuned for
Hindi Devanagari phonology and electoral roll naming variations.
"""

from __future__ import annotations
import unicodedata
import re

# Consonant articulation map
# क/ख/ग/घ -> K
# च/छ/ज/झ -> C
# ट/ठ/ड/ढ/त/थ/द/ध -> T
# प/फ/ब/भ/व -> P
# स/श/ष -> S
# न/ण/म -> N
# र/ल -> R
# य -> Y
# ह -> H
PHONETIC_CONSONANT_MAP: dict[str, str] = {
    # Velars -> K
    "क": "K", "ख": "K", "ग": "K", "घ": "K", "ङ": "K",
    "क़": "K", "ख़": "K", "ग़": "K",

    # Palatals -> C
    "च": "C", "छ": "C", "ज": "C", "झ": "C", "ञ": "C",
    "ज़": "C", "झ़": "C",

    # Retroflex & Dentals -> T
    "ट": "T", "ठ": "T", "ड": "T", "ढ": "T", "ड़": "T", "ढ़": "T",
    "त": "T", "थ": "T", "द": "T", "ध": "T",

    # Labials -> P (including 'व')
    "प": "P", "फ": "P", "ब": "P", "भ": "P", "व": "P",
    "फ़": "P",

    # Sibilants -> S
    "स": "S", "श": "S", "ष": "S",

    # Nasals -> N
    "न": "N", "ण": "N", "म": "N",

    # Liquids -> R
    "र": "R", "ल": "R", "ळ": "R",

    # Semivowels -> Y
    "य": "Y",

    # Aspirate -> H
    "ह": "H",
}

# Regex to remove non-Devanagari characters, matras, halants, anusvaras
# Vowels and Matras range from U+0904 to U+0914 (independent vowels)
# and U+093E to U+094C (dependent vowel signs), U+094D (halant), etc.
VOWELS_AND_SIGNS = re.compile(
    r"[\u0904-\u0914\u093E-\u094F\u0901-\u0903\u0951-\u0954\u0962-\u0963\u093C]"
)


def get_first_consonant(text: str) -> str:
    """Extract the first Devanagari consonant found in text."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    for ch in norm:
        if ch in PHONETIC_CONSONANT_MAP:
            return ch
    return ""


def hindi_phonetic_key(text: str, max_length: int = 6) -> str:
    """Generate a Soundex-like phonetic key for Hindi text.

    Steps:
    1. Normalize text to NFC, remove nukta and diacritics.
    2. Map consonants to articulatory group codes (K, C, T, P, S, N, R, Y, H).
    3. Collapse consecutive duplicate codes.
    4. Truncate to max_length (default 6).
    """
    if not text or not isinstance(text, str):
        return ""

    # Normalize Unicode
    norm = unicodedata.normalize("NFC", text.strip())

    # Map characters
    codes: list[str] = []
    i = 0
    while i < len(norm):
        ch = norm[i]
        # Check two-char nukta combination if not decomposed
        if i + 1 < len(norm) and norm[i + 1] == "\u093C":
            comb = norm[i:i + 2]
            code = PHONETIC_CONSONANT_MAP.get(comb, PHONETIC_CONSONANT_MAP.get(ch, ""))
            i += 2
        else:
            code = PHONETIC_CONSONANT_MAP.get(ch, "")
            i += 1

        if code:
            codes.append(code)

    if not codes:
        return ""

    # Collapse consecutive identical codes
    collapsed: list[str] = [codes[0]]
    for c in codes[1:]:
        if c != collapsed[-1]:
            collapsed.append(c)

    key = "".join(collapsed)[:max_length]
    return key
