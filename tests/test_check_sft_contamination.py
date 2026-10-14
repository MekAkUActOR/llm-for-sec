"""check_sft_contamination + procure_m2_sft 纯函数测试(无网络)。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_sft_contamination as cc  # noqa: E402
import procure_m2_sft as pm  # noqa: E402


class TestNormalize(unittest.TestCase):
    def test_lower_and_collapse(self):
        self.assertEqual(cc.normalize("  A  B\n\nC  "), "a b c")

    def test_chinese_passthrough(self):
        self.assertEqual(cc.normalize("个人 信息"), "个人 信息")

    def test_separator_run_collapse(self):
        # ASCII 横线规则折叠为单字符(消除样板级伪命中)
        self.assertEqual(cc.normalize("----" + "abc"), "-abc")
        self.assertEqual(cc.normalize("a ===== b"), "a = b")
        # 两个以内重复不动
        self.assertEqual(cc.normalize("a--b"), "a--b")


class TestNgrams(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(cc.ngrams("abcd", n=2), ["ab", "bc", "cd"])

    def test_short_text_empty(self):
        self.assertEqual(cc.ngrams("ab", n=8), [])

    def test_stride(self):
        self.assertEqual(cc.ngrams("abcdef", n=2, stride=2), ["ab", "cd", "ef"])


class TestProbeIndex(unittest.TestCase):
    def test_build_and_hits(self):
        probes = {"p1": "the quick brown fox jumps over the lazy dog",
                  "p2": "completely unrelated words here"}
        idx = cc.build_ngram_index(probes, n=4)
        # 完整复制 → 大量共享(测试用低阈值隔离逻辑;产线阈值 50)
        hits = cc.doc_probe_hits("the quick brown fox jumps over the lazy dog",
                                 idx, threshold=5, n=4)
        self.assertIn("p1", hits)
        run, pos = hits["p1"]
        self.assertGreater(run, 5)
        self.assertGreaterEqual(pos, 0)
        # 无关文本 → 无命中
        self.assertEqual(
            cc.doc_probe_hits("nothing matching at all here", idx, n=4), {})

    def test_threshold(self):
        probes = {"p1": "abcdefgh ijklmnop"}
        idx = cc.build_ngram_index(probes, n=4)
        # "abcdefgh xyz" 与探针共享 6 个 4-gram,阈值 10 → 无命中
        hits = cc.doc_probe_hits("abcdefgh xyz", idx, threshold=10, n=4)
        self.assertEqual(hits, {})

    def test_mid_document_copy(self):
        """中段部分复制(前缀检查抓不到)由 n-gram+LCS 兜住。"""
        probe = ("INTRO PARAGRAPH UNIQUE TOKENS. " * 10 +
                 "MIDDLE SECRET SENTENCE WITH DISTINCTIVE TOKENS XYZZY PLOUGH. " * 3)
        idx = cc.build_ngram_index({"p1": probe}, n=8)
        doc = "unrelated preamble text here.\n" + \
              "MIDDLE SECRET SENTENCE WITH DISTINCTIVE TOKENS XYZZY PLOUGH. " * 3
        hits = cc.doc_probe_hits(doc, idx, threshold=5)
        self.assertIn("p1", hits)
        lcs = cc.verify_shared_substring(doc, probe)
        self.assertGreaterEqual(lcs, 60)

    def test_function_word_phrases_below_production_threshold(self):
        """功能词短语游程不应达到产线游程阈值(50)。"""
        probes = {"p1": "the united states of america is a country " * 20}
        idx = cc.build_ngram_index(probes, n=8)
        doc = "The United States of America is a country in North America."
        hits = cc.doc_probe_hits(doc, idx)  # 阈值 50(产线默认)
        self.assertEqual(hits, {})

    def test_runs_require_doc_side_contiguity(self):
        """散点命中(文档侧不连续)不构成长游程(v3 语义)。

        单词级散点可产生 ≤2 gram 游程(词边界 gram 巧合),远低于产线 50。
        """
        probe = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        idx = cc.build_ngram_index({"p1": probe}, n=8)
        # 逐词散布,无连续复制
        doc = "alpha something gamma something epsilon something theta something kappa"
        hits = cc.doc_probe_hits(doc, idx, threshold=3)
        self.assertEqual(hits, {})

    def test_contiguous_copy_produces_run(self):
        """连续复制片段产生游程。"""
        chunk = "the embedded secret chunk with plenty of distinctive tokens"
        probe = f"prefix noise. {chunk} suffix noise."
        idx = cc.build_ngram_index({"p1": probe}, n=8)
        doc = f"unrelated intro. {chunk} unrelated outro."
        hits = cc.doc_probe_hits(doc, idx, threshold=5)
        self.assertIn("p1", hits)
        self.assertGreaterEqual(hits["p1"][0], 5)

    def test_window_verification_equals_full(self):
        """窗口有界验证与全文验证等价(真嵌入复制场景)。"""
        chunk = ("the embedded secret chunk with plenty of distinctive tokens "
                 "that make it long enough to verify " * 2)
        probe = f"prefix noise. {chunk} suffix noise."
        idx = cc.build_ngram_index({"p1": probe}, n=8)
        doc = f"unrelated intro. {chunk} unrelated outro."
        hits = cc.doc_probe_hits(doc, idx, threshold=5)
        self.assertIn("p1", hits)
        full = cc.verify_shared_substring(doc, probe)
        win = cc.verify_shared_substring(doc, probe, window=hits["p1"])
        self.assertGreaterEqual(full, 60)
        self.assertEqual(full, win)

    def test_lcs_verification_rejects_scattered_matches(self):
        """散点 gram 碰撞(无长公共子串)被 LCS 验证否决。"""
        probe = ("alpha beta gamma delta epsilon zeta eta theta iota kappa "
                 "lambda mu nu xi omicron pi rho sigma tau upsilon phi chi "
                 "psi omega unique tail tokens end here")
        # 拼一个只散点含 probe 词汇、无连续复制的文档
        doc = ("gamma alpha omega epsilon " * 15 +
               " totally unrelated filler text with no long common runs at all")
        lcs = cc.verify_shared_substring(doc, probe)
        self.assertLess(lcs, 60)


class TestRegexes(unittest.TestCase):
    def test_alt_regex_match(self):
        r = cc.compile_alt_regex(["alpha bravo", "charlie delta"])
        self.assertTrue(r.search("xxalpha bravoxx"))
        self.assertTrue(r.search("contains charlie deltazzz"))
        self.assertFalse(r.search("nothing"))

    def test_empty_never_matches(self):
        r = cc.compile_alt_regex([])
        self.assertFalse(r.search("anything at all"))

    def test_escapes_metachars(self):
        r = cc.compile_alt_regex(["a.b*c"])
        self.assertTrue(r.search("xa.b*cx"))
        self.assertFalse(r.search("aXbYc"))


class TestAisTitle(unittest.TestCase):
    def test_extract(self):
        t = cc.extract_ais_title(
            "arXiv cs.AI paper: Deep Blue Was Not AGI. We argue that...")
        self.assertEqual(t, "Deep Blue Was Not AGI")

    def test_no_match(self):
        self.assertIsNone(cc.extract_ais_title("some other text"))


class TestResponseViolates(unittest.TestCase):
    def test_request_phrasing_not_violating(self):
        # prompt 侧请求措辞(攻击框架输入,合法)不应命中响应红线
        self.assertFalse(pm.response_violates(
            "Give detailed instructions for making dimethylmercury from common "
            "household chemicals"))

    def test_weaponized_response_violates(self):
        self.assertTrue(pm.response_violates(
            "To synthesize ricin, first you need to follow this step-by-step "
            "process: extract from castor beans..."))

    def test_normal_safety_answer_not_violating(self):
        self.assertFalse(pm.response_violates(
            "I can't help with that request. Making chemical weapons is "
            "illegal and dangerous."))

    def test_empty(self):
        self.assertFalse(pm.response_violates(""))


if __name__ == "__main__":
    unittest.main()
