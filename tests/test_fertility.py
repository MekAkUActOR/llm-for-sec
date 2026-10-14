"""fertility 测量逻辑测试（不依赖 transformers）。"""

import json
import unittest

from secfm.audit.corpora import build_all
from secfm.audit.fertility import fertility_report, measure


class TestMeasure(unittest.TestCase):
    def test_measure(self):
        m = measure(["hello"], lambda t: list(t))
        self.assertEqual(m["bytes"], 5)
        self.assertEqual(m["tokens"], 5)
        self.assertAlmostEqual(m["bytes_per_token"], 1.0)


class TestReport(unittest.TestCase):
    def test_report_thresholds(self):
        encode = lambda t: list(t)  # 字符级假 tokenizer
        baseline = ["你好世界"]              # 12 bytes / 4 tokens = 3.0
        corpora = {
            "hex": ["deadbeef"],              # 8/8 = 1.0 -> ratio 1/3 -> pass
            "chinese": ["更长的中文文本"],      # 3.0 -> ratio 1.0 -> pass
        }
        rep = fertility_report(corpora, baseline, encode, threshold=1.5)
        self.assertTrue(rep["corpora"]["hex"]["pass"])
        self.assertTrue(rep["corpora"]["chinese"]["pass"])
        self.assertTrue(rep["overall_pass"])

    def test_report_fail(self):
        encode = lambda t: list(t)
        baseline = ["aaaaaaaa"]              # 1.0
        corpora = {"cjk": ["你好世界"]}        # 3.0 -> ratio 3.0 -> fail
        rep = fertility_report(corpora, baseline, encode, threshold=1.5)
        self.assertFalse(rep["corpora"]["cjk"]["pass"])
        self.assertFalse(rep["overall_pass"])

    def test_empty(self):
        rep = fertility_report({}, ["x"], lambda t: list(t))
        self.assertIsNone(rep["overall_pass"])


class TestSyntheticCorpora(unittest.TestCase):
    def test_deterministic_and_sized(self):
        a = build_all(target_bytes=4096, seed=7)
        b = build_all(target_bytes=4096, seed=7)
        self.assertEqual(set(a), set(b))
        for name in a:
            self.assertEqual(a[name], b[name], f"{name} 不确定")
            self.assertGreater(len(a[name].encode("utf-8")), 3000)
        # 各组形态抽查
        self.assertIn("CVE-", a["cve_ids"])
        self.assertRegex(a["logs_syslog"], r"\d{2}:\d{2}:\d{2}")
        self.assertIn("0x", a["obfuscated_js"])
        for line in a["logs_json"].split("\n")[:5]:
            json.loads(line)


if __name__ == "__main__":
    unittest.main()
