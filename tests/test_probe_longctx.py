"""probe_longctx 纯函数单测（不碰 GPU/tokenizer，用假 token id 列表）。"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from probe_longctx import (
    assemble_doc,
    assemble_stream,
    code_in_output,
    compare_reports,
    extract_codes,
    make_code,
    needle_position,
    needle_prompt_target,
)


def _ids(n, base=1):
    """造 n 个假 token id（base 起，避开 0/-100 等特殊值）。"""
    return list(range(base, base + n))


class TestMakeCode(unittest.TestCase):
    def test_format_8_lowercase_hex(self):
        rng = random.Random(42)
        for _ in range(20):
            c = make_code(rng)
            self.assertEqual(len(c), 8)
            self.assertTrue(all(ch in "0123456789abcdef" for ch in c))

    def test_same_seed_reproducible(self):
        a = [make_code(random.Random(7)) for _ in range(10)]
        b = [make_code(random.Random(7)) for _ in range(10)]
        self.assertEqual(a, b)

    def test_different_seed_different_codes(self):
        a = {make_code(random.Random(1)) for _ in range(10)}
        b = {make_code(random.Random(2)) for _ in range(10)}
        self.assertNotEqual(a, b)


class TestCodeExtraction(unittest.TestCase):
    def test_0x_prefix_and_case(self):
        self.assertEqual(extract_codes("The code is 0x3F9A2B7C."),
                         {"3f9a2b7c"})

    def test_plain_code(self):
        self.assertEqual(extract_codes("code: deadbeef."), {"deadbeef"})

    def test_two_codes(self):
        self.assertEqual(extract_codes("a 12345678 b abcdef01"),
                         {"12345678", "abcdef01"})

    def test_rejects_non8_hex(self):
        # 7 位与 9 位十六进制串都不应命中（边界 lookaround）
        self.assertEqual(extract_codes("1234567 123456789"), set())
        # 紧跟十六进制字符的 8 位串不算独立 code
        self.assertEqual(extract_codes("12345678a"), set())


class TestCodeInOutput(unittest.TestCase):
    CODE = "3f9a2b7c"

    def test_exact(self):
        self.assertTrue(code_in_output(self.CODE, "the code is 3f9a2b7c."))

    def test_uppercase(self):
        self.assertTrue(code_in_output(self.CODE, "Answer: 3F9A2B7C"))

    def test_0x_prefix(self):
        self.assertTrue(code_in_output(self.CODE, "0x3f9a2b7c"))

    def test_spaced(self):
        # 生成切分空格/标点的宽松匹配
        self.assertTrue(code_in_output(self.CODE, "3f 9a 2b 7c"))
        self.assertTrue(code_in_output(self.CODE, "3f, 9a: 2b - 7c"))

    def test_wrong_code(self):
        self.assertFalse(code_in_output(self.CODE, "the code is deadbeef"))
        self.assertFalse(code_in_output(self.CODE, ""))


class TestNeedlePosition(unittest.TestCase):
    def test_basic_depths(self):
        self.assertEqual(needle_position(100, 0.25), 25)
        self.assertEqual(needle_position(100, 0.5), 50)
        self.assertEqual(needle_position(100, 0.75), 75)

    def test_boundaries(self):
        self.assertEqual(needle_position(100, 0.0), 0)
        self.assertEqual(needle_position(100, 1.0), 100)

    def test_truncation(self):
        self.assertEqual(needle_position(99, 0.25), 24)  # int(24.75)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            needle_position(100, 1.5)
        with self.assertRaises(ValueError):
            needle_position(-1, 0.5)


class TestNeedlePromptTarget(unittest.TestCase):
    def test_reserves_generation_headroom(self):
        self.assertEqual(needle_prompt_target(32768, 32), 32720)
        self.assertEqual(needle_prompt_target(16384, 32), 16336)


class TestAssembleDoc(unittest.TestCase):
    def test_exact_length_and_meta(self):
        tls = [_ids(50), _ids(60, base=51)]
        ids, meta, nxt = assemble_doc(tls, 100)
        self.assertEqual(len(ids), 100)
        self.assertEqual(ids, _ids(100))
        self.assertEqual(meta["first_entry"], 0)
        self.assertEqual(meta["last_entry"], 1)
        self.assertEqual(meta["n_entries"], 2)
        self.assertTrue(meta["last_entry_truncated"])
        self.assertEqual(meta["discarded_tail_tokens"], 10)
        self.assertEqual(nxt, 2)

    def test_exact_boundary_no_truncation(self):
        tls = [_ids(60), _ids(40, base=61)]
        ids, meta, _ = assemble_doc(tls, 100)
        self.assertEqual(len(ids), 100)
        self.assertFalse(meta["last_entry_truncated"])
        self.assertEqual(meta["discarded_tail_tokens"], 0)

    def test_deterministic(self):
        tls = [_ids(30), _ids(45, base=31), _ids(50, base=76)]
        a = assemble_doc(tls, 80)
        b = assemble_doc(tls, 80)
        self.assertEqual(a, b)

    def test_insufficient_raises(self):
        with self.assertRaises(ValueError):
            assemble_doc([_ids(30)], 100)

    def test_skips_empty_entries(self):
        tls = [[], [], _ids(10), []]
        ids, meta, nxt = assemble_doc(tls, 5)
        self.assertEqual(ids, _ids(5))
        self.assertEqual(meta["first_entry"], 2)
        self.assertEqual(meta["last_entry"], 2)
        self.assertEqual(meta["discarded_tail_tokens"], 5)
        self.assertEqual(nxt, 3)  # 尾部空条目未被消费

    def test_large_target(self):
        tls = [_ids(9000), _ids(9000, base=9001)]
        ids, _, _ = assemble_doc(tls, 16384)
        self.assertEqual(len(ids), 16384)


class TestAssembleStream(unittest.TestCase):
    def test_disjoint_docs(self):
        tls = [_ids(30, base=i * 100 + 1) for i in range(5)]
        out = assemble_stream(tls, [("a", 40), ("b", 40)])
        a_ids, a_meta = out["a"]
        b_ids, b_meta = out["b"]
        self.assertEqual(len(a_ids), 40)
        self.assertEqual(len(b_ids), 40)
        # 文档 a 用条目 0-1，b 从条目 2 起（区间不重叠）
        self.assertEqual(a_meta["first_entry"], 0)
        self.assertEqual(b_meta["first_entry"], 2)

    def test_order_and_keys(self):
        tls = [_ids(10, base=i * 10 + 1) for i in range(10)]
        out = assemble_stream(tls, [("x", 25), ("y", 25), ("z", 25)])
        self.assertEqual(list(out), ["x", "y", "z"])
        self.assertEqual(len(out["z"][0]), 25)


class TestCompareReports(unittest.TestCase):
    def _base(self):
        return {"ppl": {"32768": {"en": {"ppl": 20.0}, "zh": {"ppl": 30.0}},
                        "16384": {"en": {"ppl": 15.0}}}}

    def test_pass_within_limit(self):
        other = {"ppl": {"32768": {"en": {"ppl": 21.0}, "zh": {"ppl": 33.0}},
                         "16384": {"en": {"ppl": 18.0}}}}
        res = compare_reports(self._base(), other)
        self.assertTrue(res["verdict"])
        # zh +10% 恰在门禁线上
        self.assertTrue(res["cells"]["32768/zh"]["ok"])
        # 16k 为观察项
        self.assertIsNone(res["cells"]["16384/en"]["ok"])
        self.assertEqual(res["cells"]["16384/en"]["delta"], 0.2)

    def test_fail_beyond_limit(self):
        other = {"ppl": {"32768": {"en": {"ppl": 23.0}, "zh": {"ppl": 30.0}},
                         "16384": {"en": {"ppl": 15.0}}}}
        res = compare_reports(self._base(), other)
        self.assertFalse(res["verdict"])
        self.assertFalse(res["cells"]["32768/en"]["ok"])  # +15%

    def test_missing_32k_fails_conservatively(self):
        other = {"ppl": {"32768": {"en": {"ppl": 20.0}},
                         "16384": {"en": {"ppl": 15.0}}}}
        res = compare_reports(self._base(), other)
        self.assertFalse(res["verdict"])
        self.assertEqual(res["cells"]["32768/zh"]["reason"], "missing")

    def test_improvement_passes(self):
        other = {"ppl": {"32768": {"en": {"ppl": 12.0}, "zh": {"ppl": 20.0}},
                         "16384": {"en": {"ppl": 10.0}}}}
        res = compare_reports(self._base(), other)
        self.assertTrue(res["verdict"])


if __name__ == "__main__":
    unittest.main()
