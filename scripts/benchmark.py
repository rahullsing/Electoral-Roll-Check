"""Synthetic large-roll benchmark: python scripts/benchmark.py [N]

Generates two N-row Hindi voter lists with realistic spelling noise and times
the full matching pipeline. Used by the regression test in tests/test_features.py.
"""

from __future__ import annotations
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIRST = ["राम", "श्याम", "सुनील", "अनिल", "राजेश", "महेश", "सुरेश", "रमेश", "दिनेश", "मुकेश",
         "सीता", "गीता", "सुनीता", "अनीता", "रेखा", "पूजा", "शशि", "चन्दन", "योगेश", "विजय",
         "अजय", "संजय", "मनोज", "अशोक", "ओमप्रकाश", "नारायण", "कृष्ण", "गोपाल", "हरि", "मोहन",
         "सोहन", "जमील", "अहमद", "ग़ालिब", "अशरफ", "राधा", "कमला", "उर्मिला", "पुष्पा", "लक्ष्मी"]
MIDDLE = ["", "", "", "कुमार", "प्रसाद", "लाल", "चन्द्र", "नाथ", "देवी", "सिंह"]
LAST = ["", "", "यादव", "शर्मा", "वर्मा", "गुप्ता", "पाल", "मौर्य", "चौहान", "खान", "मिश्रा", "तिवारी"]
NOISE = [("ी", "ि"), ("ू", "ु"), ("ं", "न्"), ("व", "ब"), ("श", "स"), ("ण", "न"), ("्र", ""), (" ", "")]


def _name(rng: random.Random) -> str:
    return " ".join(p for p in (rng.choice(FIRST), rng.choice(MIDDLE), rng.choice(LAST)) if p)


def _noisy(rng: random.Random, s: str) -> str:
    if rng.random() < 0.5:
        a, b = rng.choice(NOISE)
        s = s.replace(a, b, 1)
    return s


def generate(n: int, seed: int = 7) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    recs_a, recs_b = [], []
    for i in range(n):
        voter, rel = _name(rng), _name(rng)
        age = rng.randint(18, 90)
        house = str(rng.randint(1, n // 4 + 1))
        recs_a.append({"क्र०": i + 1, "नाम": voter, "पिता": rel, "आयु": age, "मकान": house})
        if rng.random() < 0.9:  # 90 % of A appear in B, with noise
            recs_b.append({"क्र०": len(recs_b) + 1, "नाम": _noisy(rng, voter), "पिता": _noisy(rng, rel),
                           "आयु": age + rng.choice([0, 0, 1, -1]), "मकान": house})
    while len(recs_b) < n:  # new voters only in B
        recs_b.append({"क्र०": len(recs_b) + 1, "नाम": _name(rng), "पिता": _name(rng),
                       "आयु": rng.randint(18, 90), "मकान": str(rng.randint(1, n // 4 + 1))})
    rng.shuffle(recs_b)
    return recs_a, recs_b


def mappings():
    from voter_match.core.scorer import ColumnMapping
    return [
        ColumnMapping(role="serial_no", col_a="क्र०", col_b="क्र०", importance="Paper Ref"),
        ColumnMapping(role="voter_name", col_a="नाम", col_b="नाम", importance="High"),
        ColumnMapping(role="relative_name", col_a="पिता", col_b="पिता", importance="High"),
        ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium", col_type="number"),
        ColumnMapping(role="house_no", col_a="मकान", col_b="मकान", importance="Bonus only"),
    ]


def run(n: int) -> tuple[float, dict]:
    from voter_match.core.matcher import ElectoralRollMatcher
    from voter_match.core.learning import AliasManager

    recs_a, recs_b = generate(n)
    t0 = time.perf_counter()
    res = ElectoralRollMatcher(mappings(), alias_manager=AliasManager()).run_matching(recs_a, recs_b)
    return time.perf_counter() - t0, res.stats


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    elapsed, stats = run(n)
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{n} x {n}: {elapsed:.1f}s  {stats}")
