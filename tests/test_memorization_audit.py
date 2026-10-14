r"""memorization_audit.py 单测：采样确定性/训练侧一致/已知答案指标/截断/stub 闭环。

GPU 分离纪律：本文件绝不 import torch / transformers——所有审计逻辑经
stub generate_fn + stub tokenizer 验证；真实三模型跑由人工在 GPU 空窗执行。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from build_c1_mix import enwiki_keep  # noqa: E402
import memorization_audit as ma  # noqa: E402


# ------------------------------------------------------------ 合成语料 ---

def _line_en(title: str, n_words: int) -> str:
    body = " ".join(f"w{i}" for i in range(n_words))
    return json.dumps({"text": f"Wikipedia article: {title}\n\n{body}"})


def _line_zh(n_chars: int, tag: str) -> str:
    return json.dumps({"text": f"维基百科条目：{tag}\n\n" + "字" * n_chars},
                      ensure_ascii=False)


def _find_titles(n_keep: int, n_drop: int):
    """暴力搜索 enwiki_keep 判定已知（True/False）的标题。"""
    keep, drop = [], []
    for i in range(10000):
        t = f"Synthetic Keep Article {i}"
        if enwiki_keep(_line_en(t, 10), 7400):
            if len(keep) < n_keep:
                keep.append(t)
        elif len(drop) < n_drop:
            drop.append(t)
        if len(keep) == n_keep and len(drop) == n_drop:
            break
    assert len(keep) == n_keep and len(drop) == n_drop
    return keep, drop


def _synthetic_dir(keep, drop, n_zh_long=12, n_zh_short=3):
    d = Path(tempfile.mkdtemp())
    # en：交替排布 keep/drop 长文（合格）+ 2 条 keep 长标题短文
    # （训练侧 True 但正文不足——测资格过滤的身体长度维度）
    with open(d / ma.EN_FILE, "w", encoding="utf-8") as g:
        for i in range(max(len(keep), len(drop))):
            if i < len(drop):
                g.write(_line_en(drop[i], 320) + "\n")
            if i < len(keep):
                g.write(_line_en(keep[i], 320) + "\n")
            if i < 2 and len(keep) > i + 2:
                g.write(_line_en(keep[-(i + 1)], 100) + "\n")
    with open(d / ma.ZH_FILE, "w", encoding="utf-8") as g:
        for i in range(n_zh_long):
            g.write(_line_zh(600, f"合成{i}") + "\n")
        for i in range(n_zh_short):
            g.write(_line_zh(100, f"短{i}") + "\n")
    return d


class TestMetrics(unittest.TestCase):
    """已知答案：纯 token 列表上的指标计算。"""

    def test_common_prefix(self):
        self.assertEqual(ma.common_prefix_len([1, 2, 3, 4], [1, 2, 3, 9]), 3)
        self.assertEqual(ma.common_prefix_len([1, 2], [1, 2]), 2)
        self.assertEqual(ma.common_prefix_len([], [1]), 0)
        self.assertEqual(ma.common_prefix_len([5, 6], [1, 2]), 0)

    def test_ngram_rate_known(self):
        # ref=range(20) 的 10-gram 共 11 个；gen=range(10,30) 的 11 个
        # 10-gram 中仅 (10..19) 与 ref 重合 → 1/11
        ref, gen = list(range(20)), list(range(10, 30))
        self.assertEqual(len(ma.ngram_set(ref)), 11)
        rate = len(ma.ngram_set(gen) & ma.ngram_set(ref)) / len(
            ma.ngram_set(gen))
        self.assertAlmostEqual(rate, 1 / 11, places=6)

    def test_evaluate_full_repro_threshold(self):
        ref = list(range(200, 400))
        m = ma.evaluate_span(ref[:60], ref)
        self.assertEqual(m["lcp"], 60)
        self.assertTrue(m["full_repro"])
        m = ma.evaluate_span(ref[:49], ref)
        self.assertEqual(m["lcp"], 49)
        self.assertFalse(m["full_repro"])

    def test_scrambled_memorization(self):
        """乱序记忆化：lcp=0 但 10-gram 重合率高（不同记忆化形态）。"""
        ref = list(range(200))
        gen = list(range(100, 150)) + list(range(0, 50)) + [999]
        m = ma.evaluate_span(gen, ref)
        self.assertEqual(m["lcp"], 0)
        self.assertGreater(m["ngram10_rate"], 0.5)
        self.assertFalse(m["full_repro"])


class TestSamplingSynthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keep, cls.drop = _find_titles(8, 8)
        cls.dir = _synthetic_dir(cls.keep, cls.drop)

    def test_en_spans_from_trained_eligible_lines_only(self):
        spans = ma.sample_spans(en_quota=6, zh_quota=3, corpus_dir=self.dir)
        en = [s for s in spans if s["lang"] == "en"]
        self.assertEqual(len(en), 6)
        # 严格核验：读原行 → 训练侧 keep=True + 正文长度合格（短文行必被排除）
        lines = (self.dir / ma.EN_FILE).read_text(encoding="utf-8").splitlines()
        for s in en:
            self.assertTrue(enwiki_keep(lines[s["line_idx"]], 7400))
            body = json.loads(lines[s["line_idx"]])["text"].split("\n", 1)[1]
            self.assertGreaterEqual(len(body.split()), ma.EN_MIN_WORDS)

    def test_determinism(self):
        a = ma.sample_spans(en_quota=5, zh_quota=4, corpus_dir=self.dir)
        b = ma.sample_spans(en_quota=5, zh_quota=4, corpus_dir=self.dir)
        self.assertEqual(a, b)

    def test_window_shape(self):
        spans = ma.sample_spans(en_quota=4, zh_quota=4, corpus_dir=self.dir)
        for s in spans:
            if s["lang"] == "en":
                self.assertEqual(len(s["window_text"].split()),
                                 ma.EN_WINDOW_WORDS)
            else:
                self.assertEqual(len(s["window_text"]), ma.ZH_WINDOW_CHARS)

    def test_quota_respected(self):
        spans = ma.sample_spans(en_quota=7, zh_quota=4, corpus_dir=self.dir)
        self.assertEqual(sum(1 for s in spans if s["lang"] == "en"), 7)
        self.assertEqual(sum(1 for s in spans if s["lang"] == "zh"), 4)

    def test_sparse_corpus_expansion(self):
        """资格稀疏：候选集自动扩容直至取满配额；取不满则如实返回。"""
        keep2, drop2 = _find_titles(2, 30)
        d = _synthetic_dir(keep2, drop2, n_zh_long=1, n_zh_short=0)
        spans = ma.sample_spans(en_quota=2, zh_quota=1, corpus_dir=d)
        self.assertEqual(len([s for s in spans if s["lang"] == "en"]), 2)
        # 配额 5 > 可用 2：返回全部可用（不虚报）
        spans = ma.sample_spans(en_quota=5, zh_quota=0, corpus_dir=d)
        self.assertEqual(len([s for s in spans if s["lang"] == "en"]), 2)


class TestRealCorpusIntegration(unittest.TestCase):
    """真实训练侧语料（只读）：74% 一致性 + 确定性 + 结构。"""

    def test_real_sampling_trained_side_and_determinism(self):
        a = ma.sample_spans(en_quota=12, zh_quota=8)
        b = ma.sample_spans(en_quota=12, zh_quota=8)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 20)
        lines_en = None
        for s in a:
            self.assertIn(s["lang"], ("en", "zh"))
            self.assertTrue(s["window_text"].strip())
        # en span 逐条核验：训练侧 keep=True（74% 子采样内）
        en = [s for s in a if s["lang"] == "en"]
        self.assertEqual(len(en), 12)
        wanted = {s["line_idx"] for s in en}
        got = {}
        with open(ma.CORPUS / ma.EN_FILE, encoding="utf-8") as g:
            for i, line in enumerate(g):
                if i in wanted:
                    got[i] = line
        for s in en:
            self.assertIn(s["line_idx"], got)
            self.assertTrue(enwiki_keep(got[s["line_idx"]], 7400),
                            f"span line {s['line_idx']} not in trained set")


class _StubTok:
    """词→id 线性映射的假 tokenizer（w{i} ↔ i）。"""

    def __call__(self, text):
        return {"input_ids": [int(w[1:]) for w in text.split()]}

    def decode(self, ids):
        return " ".join(f"w{i}" for i in ids)


class TestRunAuditStub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = _StubTok()

    @staticmethod
    def _span(lang="en", n=300, start=0):
        return {"file": ma.EN_FILE if lang == "en" else ma.ZH_FILE,
                "line_idx": 0, "lang": lang,
                "window_text": " ".join(f"w{i}"
                                        for i in range(start, start + n))}

    def test_stub_closed_loop_known_answers(self):
        """四种形态各一 span：全对/部分/乱序/全错 → 聚合读数已知。
        以窗口起始 token（prompt[0]）分发 stub 行为——同 tokenizer 下
        prompt=ids[:50]，start 不同则 prompt 可区分。"""
        def gen(prompt, max_new):
            s0 = prompt[0]
            if s0 == 0:       # 全对：lcp=200, full_repro
                return list(range(50, 50 + max_new))
            if s0 == 1000:    # 部分：lcp=30
                return (list(range(1050, 1080))
                        + [9000 + i for i in range(max_new - 30)])
            if s0 == 2000:    # 乱序：lcp=0, ngram>0
                return (list(range(2150, 2200)) + list(range(2050, 2100))
                        + [9999])
            return [8000 + i for i in range(max_new)]  # 全错：lcp=0

        spans = [self._span(n=300, start=0),
                 self._span(n=290, start=1000),
                 self._span(n=280, start=2000),
                 self._span(n=270, start=3000)]
        rep = ma.run_audit(spans, gen, self.tok, "stub")
        self.assertEqual(rep["n_spans"], 4)
        self.assertEqual(rep["n_evaluated"], 4)
        self.assertEqual(rep["n_degenerate"], 0)
        m = rep["metrics"]
        self.assertEqual(m["lcp_mean"], (200 + 30 + 0 + 0) / 4)
        self.assertAlmostEqual(m["full_reproduction_rate"], 0.25, places=6)
        self.assertEqual(m["lcp_max"], 200)
        # 乱序 span 的 ngram 重合应抬高均值（全错 span 为 0）
        self.assertGreater(m["ngram10_rate_mean"], 0)
        # worst_cases 按 lcp 降序，首名 = 全对 span
        self.assertEqual(rep["worst_cases"][0]["lcp"], 200)
        # by_file 汇总齐全
        self.assertIn(ma.EN_FILE, rep["by_file"])
        self.assertEqual(rep["by_file"][ma.EN_FILE]["n"], 4)

    def test_preview_truncation(self):
        """生成预览截 60 token（防意外复现长敏感文本）。"""
        ref = list(range(50, 250))

        def gen(prompt, max_new):
            return ref[:max_new]

        rep = ma.run_audit([self._span(n=300)], gen, self.tok, "stub")
        wc = rep["worst_cases"][0]
        self.assertLessEqual(len(wc["gen_preview"].split()),
                             ma.PREVIEW_TOKENS)
        self.assertLessEqual(len(wc["prompt_preview"].split()), 30)

    def test_degenerate_spans_skipped(self):
        """窗口 token 不足（< prompt+20）→ 记退化，不入读数。"""
        def gen(prompt, max_new):
            return [1] * max_new

        spans = [self._span(n=300), self._span(n=60)]  # 60 < 50+20
        rep = ma.run_audit(spans, gen, self.tok, "stub")
        self.assertEqual(rep["n_evaluated"], 1)
        self.assertEqual(rep["n_degenerate"], 1)

    def test_ref_shorter_than_max_new(self):
        """窗口 token 少于 prompt+200：参考截断，lcp 以参考长度为上限。"""
        def gen(prompt, max_new):
            return list(range(50, 50 + max_new))  # 恰为参考全文

        rep = ma.run_audit([self._span(n=150)], gen, self.tok, "stub")
        # prompt=0..49, ref=50..149（100 token）；gen 前 100 与 ref 全同
        wc = rep["worst_cases"][0]
        self.assertEqual(wc["lcp"], 100)
        self.assertEqual(wc["ref_len"], 100)


class TestCompare(unittest.TestCase):
    @staticmethod
    def _report(name, lcp, repro, ngram):
        return {"name": name, "n_spans": 200,
                "metrics": {"lcp_mean": lcp, "full_reproduction_rate": repro,
                            "ngram10_rate_mean": ngram}}

    def test_known_deltas(self):
        base = self._report("base", 3.0, 0.10, 0.05)
        m15 = self._report("m15", 5.5, 0.30, 0.12)
        d = ma.compare_reports(base, [m15])
        self.assertEqual(d["base"], "base")
        self.assertEqual(len(d["rows"]), 1)
        r = d["rows"][0]
        self.assertEqual(r["d_lcp_mean"], 2.5)
        self.assertEqual(r["d_full_reproduction_rate"], 0.2)
        self.assertEqual(r["d_ngram10_rate_mean"], 0.07)

    def test_compare_cli(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            b = td / "base.json"
            o = td / "m15.json"
            b.write_text(json.dumps(self._report("base", 3.0, 0.1, 0.05)))
            o.write_text(json.dumps(self._report("m15", 5.5, 0.3, 0.12)))
            out = td / "delta.json"
            rc = ma.main(["compare", str(b), str(o), "--out", str(out)])
            self.assertEqual(rc, 0)
            d = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(d["rows"][0]["name"], "m15")
            self.assertEqual(d["rows"][0]["d_lcp_mean"], 2.5)


if __name__ == "__main__":
    unittest.main()
