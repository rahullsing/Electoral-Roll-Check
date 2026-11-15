"""Comprehensive Unit Tests for Indic Electoral Roll Fuzzy Matching.

Tests Hindi normalization, phonetic keys, multi-method similarity,
record scoring, sibling guard, and Hungarian optimal matching.
"""

import pytest
from voter_match.core.normalize import normalize_hindi_name, get_default_normalizer
from voter_match.core.phonetic import hindi_phonetic_key
from voter_match.core.similarity import name_similarity
from voter_match.core.learning import AliasManager
from voter_match.core.scorer import (
    RecordScorer,
    ColumnMapping,
    normalize_gender,
    normalize_house_number,
    parse_age,
)
from voter_match.core.matcher import ElectoralRollMatcher


class TestNormalization:
    """Test Devanagari normalization pipeline on real-world voter list pairs."""

    def test_matra_variants(self):
        # जमीलखां vs जमीलखाँ, सुनील vs सुनिल, खॉं vs खाँ
        n1 = normalize_hindi_name("सुनील")
        n2 = normalize_hindi_name("सुनिल")
        assert n1.normalized == n2.normalized

        n_j1 = normalize_hindi_name("जमीलखां")
        n_j2 = normalize_hindi_name("जमीलखाँ")
        assert n_j1.normalized == n_j2.normalized

        n_k1 = normalize_hindi_name("खॉं")
        n_k2 = normalize_hindi_name("खाँ")
        assert n_k1.normalized == n_k2.normalized

    def test_half_letters_and_conjuncts(self):
        # प्रसाद vs प्साद, चन्दन vs चंदन, कृष्ण vs क्रष्ण
        n_p1 = normalize_hindi_name("प्रसाद")
        n_p2 = normalize_hindi_name("प्साद")
        assert n_p1.normalized == n_p2.normalized

        n_c1 = normalize_hindi_name("चन्दन")
        n_c2 = normalize_hindi_name("चंदन")
        assert n_c1.normalized == n_c2.normalized

        n_k1 = normalize_hindi_name("कृष्ण")
        n_k2 = normalize_hindi_name("क्रष्ण")
        assert n_k1.normalized == n_k2.normalized

    def test_letter_swaps_and_nukta(self):
        # श/ष/स, व/ब, ण/न, nukta ग़ vs ग
        n_s1 = normalize_hindi_name("शशि")
        n_s2 = normalize_hindi_name("षसि")
        assert n_s1.normalized == n_s2.normalized

        n_v1 = normalize_hindi_name("विजय")
        n_v2 = normalize_hindi_name("बिजइ")
        assert n_v1.normalized.startswith("ब")

        # ण vs न
        n_n1 = normalize_hindi_name("नारायण")
        n_n2 = normalize_hindi_name("नारायन")
        assert n_n1.normalized == n_n2.normalized

        n_r1 = normalize_hindi_name("रामायण")
        n_r2 = normalize_hindi_name("रामायन")
        assert n_r1.normalized == n_r2.normalized

        n_g1 = normalize_hindi_name("ग़ालिब")
        n_g2 = normalize_hindi_name("गालिब")
        assert n_g1.normalized == n_g2.normalized

    def test_special_singh_khan(self):
        # सिंग -> सिह, खान -> खा
        n_s1 = normalize_hindi_name("अजय सिंह")
        n_s2 = normalize_hindi_name("अजय सिंग")
        assert n_s1.normalized == n_s2.normalized

        n_k1 = normalize_hindi_name("इरफान खान")
        n_k2 = normalize_hindi_name("इरफान खां")
        assert n_k1.normalized == n_k2.normalized

    def test_stopwords_honorifics(self):
        # सुनील vs सुनील कुमार, शीला vs शीला देवी, कु० अंजली, श्रीमती
        n1 = normalize_hindi_name("सुनील कुमार")
        n2 = normalize_hindi_name("सुनील")
        assert n1.core == n2.core

        n_d1 = normalize_hindi_name("शीला देवी")
        n_d2 = normalize_hindi_name("शीला")
        assert n_d1.core == n_d2.core

        n_sh1 = normalize_hindi_name("श्रीमती अंजली")
        n_sh2 = normalize_hindi_name("कु० अंजली")
        assert n_sh1.core == n_sh2.core

    def test_spacing_and_digits(self):
        # योगेश कुमार vs योगेशकुमार
        n1 = normalize_hindi_name("योगेश कुमार")
        n2 = normalize_hindi_name("योगेशकुमार")
        assert n1.space_free == n2.space_free

        norm = get_default_normalizer()
        assert norm.normalize_digits("१२३४५") == "12345"


class TestPhoneticKey:
    """Test Devanagari Soundex-like phonetic key generation."""

    def test_phonetic_grouping(self):
        # क and ख share 'K'
        assert hindi_phonetic_key("कमल")[0] == "K"
        assert hindi_phonetic_key("खमल")[0] == "K"

        # च and ज share 'C'
        assert hindi_phonetic_key("चन्दन")[0] == "C"
        assert hindi_phonetic_key("जमील")[0] == "C"

        # प, ब, भ, व share 'P'
        assert hindi_phonetic_key("प्रसाद")[0] == "P"
        assert hindi_phonetic_key("बृजेश")[0] == "P"
        assert hindi_phonetic_key("विजय")[0] == "P"


class TestSimilarity:
    """Test multi-method similarity scoring and method attribution."""

    def test_exact_and_normalized(self):
        a = normalize_hindi_name("रमेश")
        b = normalize_hindi_name("रमेश")
        sim, method = name_similarity(a, b)
        assert sim == 1.0

        a = normalize_hindi_name("सुनील")
        b = normalize_hindi_name("सुनिल")
        sim, method = name_similarity(a, b)
        assert sim >= 0.95

    def test_ocr_typing_slips(self):
        # ओमप्काश vs ओमप्रकाश
        a = normalize_hindi_name("ओमप्काश")
        b = normalize_hindi_name("ओमप्रकाश")
        sim, method = name_similarity(a, b)
        assert sim >= 0.90

        # सोरव vs सौरभ
        a = normalize_hindi_name("सोरव")
        b = normalize_hindi_name("सौरभ")
        sim, method = name_similarity(a, b)
        assert sim >= 0.85

    def test_learned_aliases(self):
        # घासू vs धांसू
        alias_mgr = AliasManager()
        a = normalize_hindi_name("घासू")
        b = normalize_hindi_name("धांसू")
        alias_mgr.add_alias(a.normalized, b.normalized)

        sim, method = name_similarity(a, b, alias_mgr)
        assert sim == 0.97
        assert "सीखी गई" in method

    def test_containment(self):
        a = normalize_hindi_name("राम लखन")
        b = normalize_hindi_name("राम लखन सिंह")
        sim, method = name_similarity(a, b)
        assert sim >= 0.90


class TestScorerAndSiblingGuard:
    """Test record scorer, penalties, bonuses, and sibling guard."""

    def setup_method(self):
        self.mappings = [
            ColumnMapping(role="voter_name", col_a="name_a", col_b="name_b", importance="High", weight=1.0),
            ColumnMapping(role="relative_name", col_a="rel_a", col_b="rel_b", importance="High", weight=1.0),
            ColumnMapping(role="age", col_a="age_a", col_b="age_b", importance="Medium", col_type="number", tolerance=3),
            ColumnMapping(role="gender", col_a="gen_a", col_b="gen_b", importance="Low", col_type="category"),
            ColumnMapping(role="house_no", col_a="house_a", col_b="house_b", importance="Bonus only"),
        ]
        self.scorer = RecordScorer(self.mappings)

    def test_sibling_guard_negative_cases(self):
        # Sibling guard: शशि देवी vs राशि देवी (father: राम प्रसाद)
        # Sibling guard: सीता देवी vs सुधा देवी (father: मदन लाल)
        rec_a = {"name_a": "शशि देवी", "rel_a": "राम प्रसाद", "age_a": "28", "gen_a": "महिला", "house_a": "12"}
        rec_b = {"name_b": "राशि देवी", "rel_b": "राम प्रसाद", "age_b": "26", "gen_b": "महिला", "house_b": "12"}

        res = self.scorer.score_pair(rec_a, rec_b)
        assert res.is_sibling_guard_applied is True
        assert res.score < 0.85
        assert any("सहोदर" in r for r in res.reasons)

        rec_c = {"name_a": "सीता देवी", "rel_a": "मदन लाल", "age_a": "34", "gen_a": "महिला", "house_a": "45"}
        rec_d = {"name_b": "सुधा देवी", "rel_b": "मदन लाल", "age_b": "30", "gen_b": "महिला", "house_b": "45"}
        res2 = self.scorer.score_pair(rec_c, rec_d)
        assert res2.is_sibling_guard_applied is True
        assert res2.score < 0.85

    def test_age_and_gender_penalty_cap(self):
        # Perfect names should cap age/gender penalty to at most 0.05
        rec_a = {"name_a": "राजेश कुमार", "rel_a": "सुरेश कुमार", "age_a": "25", "gen_a": "पु", "house_a": "10"}
        rec_b = {"name_b": "राजेश कुमार", "rel_b": "सुरेश कुमार", "age_b": "55", "gen_b": "महिला", "house_b": "10"}

        res = self.scorer.score_pair(rec_a, rec_b)
        assert res.score >= 0.90
        assert any("त्रुटि सीमा" in r for r in res.reasons)

    def test_serial_no_does_not_penalize_score(self):
        # Differing paper roll serial numbers (e.g. 142 vs 87) must not penalize match score
        mappings = [
            ColumnMapping(role="serial_no", col_a="kram_a", col_b="kram_b", importance="Paper Ref"),
            ColumnMapping(role="voter_name", col_a="name_a", col_b="name_b", importance="High"),
            ColumnMapping(role="relative_name", col_a="rel_a", col_b="rel_b", importance="High"),
        ]
        scorer = RecordScorer(mappings)
        rec_a = {"kram_a": "142", "name_a": "सुनील कुमार", "rel_a": "राम सेवक"}
        rec_b = {"kram_b": "87", "name_b": "सुनील कुमार", "rel_b": "राम सेवक"}
        res = scorer.score_pair(rec_a, rec_b)
        assert res.score >= 0.95


class TestMatcherOptimalAssignment:
    """Test full Hungarian optimal 1-to-1 matcher."""

    def test_optimal_assignment(self):
        mappings = [
            ColumnMapping(role="voter_name", col_a="नाम", col_b="नाम", importance="High"),
            ColumnMapping(role="relative_name", col_a="पिता", col_b="पिता", importance="High"),
            ColumnMapping(role="age", col_a="आयु", col_b="आयु", importance="Medium", col_type="number"),
        ]

        matcher = ElectoralRollMatcher(mappings)

        # 3 voters in A, 3 in B
        records_a = [
            {"नाम": "सुनील कुमार", "पिता": "राम सेवक", "आयु": "35"},
            {"नाम": "ओमप्रकाश", "पिता": "दीनानाथ", "आयु": "42"},
            {"नाम": "शशि देवी", "पिता": "राम प्रसाद", "आयु": "28"},
        ]

        records_b = [
            {"नाम": "सुनिल", "पिता": "रामसेवक", "आयु": "36"},
            {"नाम": "ओमप्काश", "पिता": "दीना नाथ", "आयु": "40"},
            {"नाम": "राशि देवी", "पिता": "राम प्रसाद", "आयु": "25"},
        ]

        res = matcher.run_matching(records_a, records_b)
        assert len(res.records_b) == 3

        # Sunil should be 'मिला'
        rec_sunil = res.records_b[0]
        assert rec_sunil.tier == "मिला"
        assert rec_sunil.assigned_a_idx == 0

        # Omprakash should be 'मिला' or 'जाँचें'
        rec_omprakash = res.records_b[1]
        assert rec_omprakash.tier in {"मिला", "जाँचें"}
        assert rec_omprakash.assigned_a_idx == 1

        # Rashi Devi (sibling guard) should be 'जाँचें' or 'लापता', NEVER 'मिला'
        rec_rashi = res.records_b[2]
        assert rec_rashi.tier != "मिला"
