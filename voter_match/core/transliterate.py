"""Offline Roman (English) -> Devanagari transliteration for Indian names.

Some rolls / BLO check-lists type names in Roman script ("Ram Prasad"). To
allow cross-script matching against Hindi rolls we convert Roman tokens to
Devanagari *before* normalization. No ML, no network: a dictionary of very
common name tokens is tried first, and everything else falls back to a
greedy longest-match phoneme table with Hindi schwa conventions.

The output does not need to be perfect spelling: it only needs to land close
enough that the downstream Devanagari normalizer + fuzzy/skeleton/phonetic
similarity can do the rest (e.g. "Ram" -> "रम" shares the skeleton of "राम").
"""

from __future__ import annotations
import re

HALANT = "्"

# Frequent name tokens in UP electoral rolls -> canonical Devanagari spelling.
COMMON_WORDS: dict[str, str] = {
    "singh": "सिंह", "kumar": "कुमार", "kumari": "कुमारी", "devi": "देवी", "ram": "राम",
    "prasad": "प्रसाद", "lal": "लाल", "sharma": "शर्मा", "yadav": "यादव", "khan": "खान",
    "mohammad": "मोहम्मद", "mohammed": "मोहम्मद", "mohd": "मोहम्मद", "md": "मोहम्मद",
    "ali": "अली", "chand": "चन्द", "chandra": "चन्द्र", "nath": "नाथ", "shri": "श्री",
    "sri": "श्री", "smt": "श्रीमती", "shrimati": "श्रीमती", "babu": "बाबू", "ahmad": "अहमद",
    "ahmed": "अहमद", "verma": "वर्मा", "gupta": "गुप्ता", "pal": "पाल", "maurya": "मौर्य",
    "chauhan": "चौहान", "pandey": "पाण्डेय", "mishra": "मिश्रा", "tiwari": "तिवारी",
    "shukla": "शुक्ला", "das": "दास", "bai": "बाई", "begum": "बेगम", "khatoon": "खातून",
    "khatun": "खातून", "husain": "हुसैन", "hussain": "हुसैन", "raj": "राज", "kishan": "किशन",
    "krishna": "कृष्ण", "krishan": "कृष्ण", "shiv": "शिव", "om": "ओम", "prakash": "प्रकाश",
    "narayan": "नारायण", "sunil": "सुनील", "anil": "अनिल", "sanjay": "संजय", "vijay": "विजय",
    "ajay": "अजय", "mahesh": "महेश", "suresh": "सुरेश", "ramesh": "रमेश", "dinesh": "दिनेश",
    "rakesh": "राकेश", "mukesh": "मुकेश", "rajesh": "राजेश", "santosh": "संतोष",
    "ashok": "अशोक", "manoj": "मनोज", "pooja": "पूजा", "puja": "पूजा", "sita": "सीता",
    "geeta": "गीता", "gita": "गीता", "sunita": "सुनीता", "anita": "अनीता", "rekha": "रेखा",
    "rani": "रानी", "laxmi": "लक्ष्मी", "lakshmi": "लक्ष्मी", "savitri": "सावित्री",
    "shanti": "शान्ति", "kamla": "कमला", "kamala": "कमला", "urmila": "उर्मिला",
    "pushpa": "पुष्पा", "radha": "राधा", "munni": "मुन्नी", "sevak": "सेवक",
    "sewak": "सेवक", "bahadur": "बहादुर", "dutt": "दत्त", "datt": "दत्त", "kant": "कान्त",
    "pratap": "प्रताप", "shankar": "शंकर", "shyam": "श्याम", "mohan": "मोहन",
    "sohan": "सोहन", "rohan": "रोहन", "jai": "जय", "jay": "जय", "gopal": "गोपाल",
    "hari": "हरि", "har": "हर", "dev": "देव", "pati": "पति", "wati": "वती", "vati": "वती",
    "rajput": "राजपूत", "kushwaha": "कुशवाहा", "nishad": "निषाद", "jatav": "जाटव",
    "rawat": "रावत", "thakur": "ठाकुर", "saxena": "सक्सेना", "srivastava": "श्रीवास्तव",
}

# Longest match first.
CONSONANTS: list[tuple[str, str]] = [
    ("chh", "छ"), ("ksh", "क्ष"), ("shh", "ष"),
    ("kh", "ख"), ("gh", "घ"), ("ch", "च"), ("jh", "झ"), ("th", "थ"), ("dh", "ध"),
    ("ph", "फ"), ("bh", "भ"), ("sh", "श"), ("gy", "ज्ञ"),
    ("k", "क"), ("g", "ग"), ("c", "क"), ("j", "ज"), ("t", "त"), ("d", "द"), ("n", "न"),
    ("p", "प"), ("b", "ब"), ("m", "म"), ("y", "य"), ("r", "र"), ("l", "ल"), ("v", "व"),
    ("w", "व"), ("s", "स"), ("h", "ह"), ("f", "फ"), ("z", "ज"), ("q", "क"), ("x", "क्स"),
]

# (roman, independent vowel, matra). The inherent 'a' has an empty matra.
VOWELS: list[tuple[str, str, str]] = [
    ("aa", "आ", "ा"), ("ai", "ऐ", "ै"), ("au", "औ", "ौ"), ("ee", "ई", "ी"), ("ii", "ई", "ी"),
    ("oo", "ऊ", "ू"), ("uu", "ऊ", "ू"), ("ei", "ए", "े"), ("ou", "औ", "ौ"),
    ("a", "अ", ""), ("i", "इ", "ि"), ("u", "उ", "ु"), ("e", "ए", "े"), ("o", "ओ", "ो"),
]

_LATIN_RE = re.compile(r"[A-Za-z]")
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_TOKEN_RE = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


def has_latin(text: str) -> bool:
    return bool(text) and bool(_LATIN_RE.search(text))


def _match(table, word: str, pos: int):
    for entry in table:
        key = entry[0]
        if word.startswith(key, pos):
            return entry
    return None


def transliterate_word(word: str) -> str:
    """Transliterate a single lowercase Roman word into Devanagari."""
    w = word.lower()
    if not w:
        return ""
    if w in COMMON_WORDS:
        return COMMON_WORDS[w]

    out: list[str] = []
    pos = 0
    n = len(w)
    prev_consonant = False

    while pos < n:
        cons = _match(CONSONANTS, w, pos)
        if cons:
            if prev_consonant:
                out.append(HALANT)  # cluster: previous consonant had no vowel
            out.append(cons[1])
            pos += len(cons[0])
            prev_consonant = True

            vow = _match(VOWELS, w, pos)
            if vow:
                roman, _indep, matra = vow
                pos += len(roman)
                if roman == "a" and pos == n and n > 2:
                    matra = "ा"  # word-final 'a' is usually long: Sharma, Rama, Sita
                out.append(matra)
                prev_consonant = False
            continue

        vow = _match(VOWELS, w, pos)
        if vow:
            out.append(vow[1])
            pos += len(vow[0])
            prev_consonant = False
            continue

        pos += 1  # unknown character: drop it

    return "".join(out)


def transliterate_roman_to_devanagari(text: str) -> str:
    """Transliterate every Roman-script token in text, leaving Devanagari untouched."""
    if not has_latin(text):
        return text
    parts = []
    for tok in _TOKEN_RE.findall(text):
        if tok[0].isascii() and tok[0].isalpha():
            parts.append(transliterate_word(tok))
        else:
            parts.append(tok)
    return "".join(parts)


# --- Devanagari -> Roman (for reading names aloud with an English TTS voice) ---

_DEV_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j",
    "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t",
    "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh",
    "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s",
    "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
}
_DEV_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e",
    "ऐ": "ai", "ओ": "o", "औ": "au",
}
_DEV_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai",
    "ो": "o", "ौ": "au", "ॉ": "o",
}
_NUKTA = "\u093C"


def devanagari_to_roman(text: str) -> str:
    """Rough phonetic romanization so an English voice can pronounce Hindi names."""
    import unicodedata

    if not text or not _DEVANAGARI_RE.search(text):
        return text or ""
    s = unicodedata.normalize("NFC", text)
    words_out = []
    for word in re.split(r"(\s+)", s):
        if not word.strip():
            words_out.append(word)
            continue
        out: list[str] = []
        pending_a = False  # inherent vowel of the last consonant not yet emitted
        i = 0
        while i < len(word):
            ch = word[i]
            if i + 1 < len(word) and word[i + 1] == _NUKTA and (ch + _NUKTA) in _DEV_CONS:
                ch = ch + _NUKTA
                i += 1
            if ch in _DEV_CONS:
                if pending_a:
                    out.append("a")
                out.append(_DEV_CONS[ch])
                pending_a = True
            elif ch in _DEV_MATRAS:
                out.append(_DEV_MATRAS[ch])
                pending_a = False
            elif ch == HALANT:
                pending_a = False
            elif ch in ("ं", "ँ"):
                if pending_a:
                    out.append("a")
                    pending_a = False
                out.append("n")
            elif ch == "ः":
                out.append("h")
            elif ch in _DEV_VOWELS:
                if pending_a:
                    out.append("a")
                    pending_a = False
                out.append(_DEV_VOWELS[ch])
            else:
                if pending_a:
                    out.append("a")
                    pending_a = False
                out.append(ch)
            i += 1
        # Hindi schwa deletion: the final inherent 'a' is silent (राम -> Ram)
        words_out.append("".join(out).capitalize())
    return "".join(words_out)
