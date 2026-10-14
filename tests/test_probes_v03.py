"""探针 v0.3 脚本单测：排除逻辑 / 验证标记 / 组装前置（无网络，合成语料）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_probes_v03 as fp3  # noqa: E402

MINI_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry><id>http://arxiv.org/abs/2501.00001v2</id>
  <title>  Prompt Injection   Defenses </title>
  <summary> We study defenses against prompt injection attacks in depth. </summary></entry>
 <entry><id>http://arxiv.org/abs/2501.00002v1</id>
  <title>Malware Family Classification</title>
  <summary>A study of malware family behavior with static features.</summary></entry>
</feed>
"""


class TestQueryDesign(unittest.TestCase):
    def test_category_disjointness(self):
        """新域查询类目必须与训练 CATS 互补（设计不变量）。"""
        self.assertEqual(fp3.check_query_disjointness(), [])

    def test_every_domain_has_queries_and_label(self):
        for dom, spec in fp3.DOMAINS.items():
            self.assertGreaterEqual(len(spec["queries"]), 2, dom)
            self.assertTrue(spec["label"], dom)
            for expr, cats in spec["queries"]:
                self.assertIn("cat:", cats)
                self.assertTrue(expr.startswith("abs:"), expr)

    def test_url_encoding(self):
        url = fp3.query_url('abs:"prompt injection"', "(cat:cs.CY)", 0)
        self.assertIn("search_query=", url)
        self.assertIn("%22", url)          # 引号编码
        self.assertIn("%28cat:cs.CY%29", url)  # 括号编码
        self.assertIn("start=0", url)
        self.assertIn("max_results=200", url)


class TestExclusionLogic(unittest.TestCase):
    """excluded() 判定与 build_exclusion 的层间协作（合成 fixture）。"""

    def setUp(self):
        self.excl = {
            "ids": {"2501.00001"},
            "titles": {"malware family classification"},
            "probe_titles": {"existing probe paper"},
        }

    def test_id_layer(self):
        self.assertEqual(fp3.excluded("2501.00001", "Novel Title", self.excl),
                         "id-in-train")

    def test_title_layer_normalization(self):
        # 大小写/空白差异不影响标题层命中
        self.assertEqual(
            fp3.excluded("9999.99999", "Malware  FAMILY\nclassification",
                         self.excl),
            "title-in-train")

    def test_probe_title_layer(self):
        self.assertEqual(
            fp3.excluded("9999.99998", "Existing PROBE paper", self.excl),
            "title-in-existing-probe")

    def test_clean_kept(self):
        self.assertEqual(
            fp3.excluded("9999.99997", "Brand New Held-out Paper", self.excl),
            "")


class TestBuildExclusionSources(unittest.TestCase):
    """raw Atom 页 + 清洗文件头部内嵌 id 两源的汇聚（临时目录注入）。"""

    def test_sources_merged(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            raw = td / "raw" / "arxiv-test"
            raw.mkdir(parents=True)
            (raw / "page0.xml").write_text(MINI_ATOM, encoding="utf-8")
            clean = td / "clean"
            clean.mkdir()
            (clean / "c2_fake_arxiv.jsonl").write_text(
                '{"text": "arXiv AI safety research paper 2501.00003: '
                'Third Paper. Body."}\n', encoding="utf-8")
            old_raw, old_clean = fp3.RAW, fp3.CLEAN
            old_v011, old_ais500 = fp3.V011, fp3.AIS500
            fp3.RAW, fp3.CLEAN = raw.parent, clean
            fp3.V011, fp3.AIS500 = td / "v011", td / "ais500"
            try:
                excl = fp3.build_exclusion()
                self.assertIn("2501.00001", excl["ids"])   # raw atom（v2 剥离）
                self.assertIn("2501.00002", excl["ids"])
                self.assertIn("2501.00003", excl["ids"])   # jsonl 头部兜底
                self.assertIn("prompt injection defenses",
                              excl["titles"])               # 标题规范化
                self.assertEqual(excl["raw_pages"], 1)
            finally:
                fp3.RAW, fp3.CLEAN = old_raw, old_clean
                fp3.V011, fp3.AIS500 = old_v011, old_ais500

    def test_skip_probe_dirs(self):
        """验证 ais-500 时跳过其目录——自比对不误报。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            raw = td / "raw"
            raw.mkdir()
            ais500 = td / "ais500"
            ais500.mkdir()
            (ais500 / "ais.jsonl").write_text(
                '{"text": "arXiv cs.AI paper: Self Check Title\\n\\nbody"}\n',
                encoding="utf-8")
            old_raw, old_v011, old_ais500 = fp3.RAW, fp3.V011, fp3.AIS500
            fp3.RAW, fp3.V011 = raw, td / "v011"
            fp3.AIS500 = ais500
            try:
                excl = fp3.build_exclusion(skip_probe_dirs=(ais500,))
                self.assertNotIn("self check title", excl["probe_titles"])
                excl2 = fp3.build_exclusion()
                self.assertIn("self check title", excl2["probe_titles"])
            finally:
                fp3.RAW, fp3.V011, fp3.AIS500 = old_raw, old_v011, old_ais500


class TestVerifyAndAssemble(unittest.TestCase):
    """ais-500 验证 → 晋升标记 → 组装前置链（合成端到端）。"""

    def _setup(self, td: Path, *, ais_contaminated: bool):
        """搭合成世界：raw/clean/probes 目录 + 可选污染 ais-500。"""
        raw = td / "raw" / "arxiv-cscr-full" / "y2026"
        raw.mkdir(parents=True)
        # 训练语料含 2501.00001（Prompt Injection Defenses）
        (raw / "page0.xml").write_text(MINI_ATOM, encoding="utf-8")
        clean = td / "clean"
        clean.mkdir()
        (clean / "c1_arxiv_full.jsonl").write_text(
            '{"text": "arXiv security research paper 2501.00001: '
            'Prompt Injection Defenses. Body."}\n', encoding="utf-8")
        ais500 = td / "ais500"
        ais500.mkdir()
        lines = ['{"text": "arXiv cs.AI paper: Clean Held-out Study\\n\\n'
                 'A long enough abstract body text. "}',
                 '{"text": "arXiv cs.AI paper: Another Clean Study\\n\\n'
                 'More body text here for length."}']
        if ais_contaminated:
            lines.append('{"text": "arXiv cs.AI paper: Prompt Injection '
                         'Defenses\\n\\ncontaminated body"}')
        (ais500 / "ais.jsonl").write_text("\n".join(lines) + "\n",
                                          encoding="utf-8")
        v011 = td / "v011"
        v011.mkdir()
        for name in fp3.FIVE:
            (v011 / f"{name}.jsonl").write_text(
                '{"text": "frozen v0.1.1 content"}\n', encoding="utf-8")
        return raw.parent.parent, clean, ais500, v011

    def _patch(self, td, raw_root, clean, ais500, v011, v03):
        olds = (fp3.RAW, fp3.CLEAN, fp3.AIS500, fp3.V011, fp3.V03)
        fp3.RAW, fp3.CLEAN = raw_root, clean
        fp3.AIS500, fp3.V011, fp3.V03 = ais500, v011, v03
        return olds

    def test_verify_clean_then_assemble_blocks_then_passes(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            raw_root, clean, ais500, v011 = self._setup(td, ais_contaminated=False)
            v03 = td / "v0.3"
            olds = self._patch(td, raw_root, clean, ais500, v011, v03)
            try:
                # 组装前置 1：缺新域 → 拒绝
                v = fp3.verify_ais500(fp3._clean_arxiv_corpora())
                self.assertEqual(v["overlap"], [])
                self.assertEqual(v["n"], 2)
                self.assertTrue(fp3.promote_ais500(v))
                self.assertTrue((v03 / "ais.jsonl").exists())
                self.assertTrue((v03 / ".ais500-verified.json").exists())
                rc = fp3.assemble()
                self.assertEqual(rc, 1)  # 缺三新域 → BLOCKED

                # 补齐三新域 → 组装成功，v0.1.1 五域字节相同
                for d in ("aisafety", "malware", "content"):
                    (v03 / f"{d}.jsonl").write_text(
                        '{"text": "new domain probe"}\n', encoding="utf-8")
                rc = fp3.assemble()
                self.assertEqual(rc, 0)
                for name in fp3.FIVE:
                    self.assertEqual(
                        (v03 / f"{name}.jsonl").read_bytes(),
                        (v011 / f"{name}.jsonl").read_bytes(), name)
                self.assertTrue((v03 / "README.md").exists())

                # 语料漂移 → 验证标记失效 → 组装拒绝
                with open(clean / "c1_arxiv_full.jsonl", "a",
                          encoding="utf-8") as f:
                    f.write('{"text": "arXiv security research paper '
                            '2701.99999: New Doc. Body."}\n')
                self.assertEqual(fp3.assemble(), 1)
            finally:
                fp3.RAW, fp3.CLEAN, fp3.AIS500, fp3.V011, fp3.V03 = olds

    def test_verify_contaminated_blocks_then_prunes(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            raw_root, clean, ais500, v011 = self._setup(td, ais_contaminated=True)
            v03 = td / "v0.3"
            olds = self._patch(td, raw_root, clean, ais500, v011, v03)
            try:
                v = fp3.verify_ais500(fp3._clean_arxiv_corpora())
                self.assertEqual(len(v["overlap"]), 1)
                self.assertIn("title-in-train", v["overlap"][0]["reason"])
                # 不带 --prune：拒绝晋升
                self.assertFalse(fp3.promote_ais500(v))
                self.assertFalse((v03 / "ais.jsonl").exists())
                # 带 --prune：剪除污染出净版（2 条干净）
                self.assertTrue(fp3.promote_ais500(v, prune=True))
                lines = (v03 / "ais.jsonl").read_text(
                    encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 2)
                for ln in lines:
                    self.assertNotIn("Prompt Injection Defenses", ln)
                marker = json.loads(
                    (v03 / ".ais500-verified.json").read_text(encoding="utf-8"))
                self.assertEqual(marker["pruned"], 1)
                self.assertEqual(marker["overlap"], [])
            finally:
                fp3.RAW, fp3.CLEAN, fp3.AIS500, fp3.V011, fp3.V03 = olds


if __name__ == "__main__":
    unittest.main()
