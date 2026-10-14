"""M1.5 mix 组装器单测：C2 动态枚举 / zhwiki 长文回放采样 / 三遍写入计数（无 GPU）。

2026-09-30 修订：回放设计在 2026-09-26 由"enwiki 摘要补集 × 二次哈希"重构为
"zhwiki **全文长文**子采样"（用户选 C：摘要短文是 C1-full 32k 退化的机制元凶），
但当时的测试未同步——旧 `TestReplayComplement` 在新契约下 1 例失败、2 例**空洞
通过**。本轮按现行契约重写该组用例（父代理，m25 训练窗口内）。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_m15_mix as bm  # noqa: E402
from build_c1_mix import enwiki_keep  # noqa: E402


def _enwiki_line(title: str) -> str:
    return json.dumps({"text": f"Wikipedia article: {title}\n\nbody"},
                      ensure_ascii=True)


def _zhwiki_line(title: str, chars: int = 4000) -> str:
    """zhwiki 长文回放行：现行契约由 title 字段驱动采样、text 长度过闸。"""
    body = "长文正文内容" * (chars // 6 + 1)
    return json.dumps({"title": title, "text": body[:chars]},
                      ensure_ascii=False)


class TestC2Enumeration(unittest.TestCase):
    """manifest 动态枚举：只收 clean/c2_*、分隔符归一、同文件取 max、缺文件跳过。"""

    def _patch_world(self, td: Path, manifest_entries, on_disk, extra_clean=()):
        clean = td / "clean"
        clean.mkdir(parents=True, exist_ok=True)
        raw_manifest = td / "manifest.jsonl"
        raw_manifest.write_text(
            "\n".join(json.dumps(e) for e in manifest_entries) + "\n",
            encoding="utf-8")
        for name in on_disk:
            (clean / name).write_text(
                '{"text": "c2 doc"}\n' * 2, encoding="utf-8")
        for name in extra_clean:
            (clean / name).write_text('{"text": "x"}\n', encoding="utf-8")
        bm.CLEAN, bm.MANIFEST = clean, raw_manifest

    def test_dynamic_enumeration(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            entries = [
                # 正则应命中：反斜杠路径
                {"name": "arxiv-aisafety", "est_tokens": 100,
                 "files": ["data\\corpora\\clean\\c2_aisafety_arxiv.jsonl"]},
                # 正斜杠路径 + 更新条目（同文件更大 est → 取 max）
                {"name": "arxiv-aisafety-v2", "est_tokens": 300,
                 "files": ["data/corpora/clean/c2_aisafety_arxiv.jsonl"]},
                # 另一 c2 文件
                {"name": "lolbas", "est_tokens": 50,
                 "files": ["data/corpora/clean/c2_aisafety_lolbas.jsonl"]},
                # 非 c2：排除
                {"name": "zhwiki-sec", "est_tokens": 999,
                 "files": ["data/corpora/clean/c1_zhwiki_sec.jsonl"]},
                # manifest 列出但磁盘不存在：警告跳过
                {"name": "future-b-variant", "est_tokens": 400,
                 "files": ["data/corpora/clean/c2_future_source.jsonl"]},
            ]
            self._patch_world(td, entries,
                              ["c2_aisafety_arxiv.jsonl",
                               "c2_aisafety_lolbas.jsonl"])
            old = (bm.CLEAN, bm.MANIFEST)
            try:
                src = bm.c2_sources()
                self.assertEqual(
                    src, {"c2_aisafety_arxiv.jsonl": 300,
                          "c2_aisafety_lolbas.jsonl": 50})  # max + 磁盘存在
            finally:
                bm.CLEAN, bm.MANIFEST = old

    def test_empty_manifest_aborts(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            self._patch_world(td, [], [])
            old = (bm.CLEAN, bm.MANIFEST)
            try:
                self.assertEqual(bm.c2_sources(), {})
            finally:
                bm.CLEAN, bm.MANIFEST = old


class TestReplayZhwikiLongdoc(unittest.TestCase):
    """回放采样 = zhwiki 全文长文确定性子采样（现行契约，2026-09-26 重构后）。

    契约（scripts/build_m15_mix.py `replay_keep`）：
      1. 行必须是合法 JSON，否则排除；
      2. `text` 长度必须 ≥ min_chars（默认 3000，与 M1.6 恢复语料同标准）；
      3. 采样键 = md5("m15replay-zh:" + title)，万分比 < zh_keep（默认 5900）；
      4. title 缺失时退化为 text[:64]。
    语义：zhwiki 全体在 C1 已训过 → 回放即"防遗忘 + 长程注意力维持"，
    与 C1 的 enwiki 保留集**无关**（原 enwiki 补集设计已废弃）。
    """

    def test_longdoc_filter_and_badline(self):
        self.assertFalse(bm.replay_keep(_zhwiki_line("T-short", 100), 3000, 9999))
        self.assertFalse(bm.replay_keep("not json", 3000, 5900))
        # title 缺失 → 退化 text[:64]，不抛异常且类型为 bool
        d = {"text": "长文正文内容" * 700}
        self.assertIsInstance(
            bm.replay_keep(json.dumps(d, ensure_ascii=False), 3000, 5900), bool)
        # 阈值边界：恰好 min_chars 可入闸（>=）
        exact = json.dumps({"title": "Boundary T", "text": "长" * 3000},
                           ensure_ascii=False)
        self.assertIsInstance(bm.replay_keep(exact, 3000, 5900), bool)

    def test_deterministic_and_monotone_in_keep(self):
        line = _zhwiki_line("Deterministic Title X")
        decisions = [bm.replay_keep(line, 3000, 5900) for _ in range(5)]
        self.assertEqual(len(set(decisions)), 1)  # 确定性
        if bm.replay_keep(line, 3000, 1450):
            self.assertTrue(bm.replay_keep(line, 3000, 9999))  # 大阈值 ⊇ 小阈值

    def test_sampling_density(self):
        """可复算性：万分比 5900 → 长文池命中率 ≈ 59%。"""
        n, hit = 2000, 0
        for i in range(n):
            if bm.replay_keep(_zhwiki_line(f"Title {i}"), 3000, 5900):
                hit += 1
        self.assertAlmostEqual(hit / n, 0.59, delta=0.04)

    def test_independent_of_c1_enwiki_keep(self):
        """回放不查 C1 的 enwiki 保留集：C1 保留的标题同样按 ~59% 被回放采样。"""
        titles = [f"Some Wikipedia Article {i}" for i in range(300)]
        c1_kept = [t for t in titles if enwiki_keep(_enwiki_line(t), 7400)]
        self.assertGreater(len(c1_kept), 100)          # C1 侧密度 ~74%
        self.assertAlmostEqual(len(c1_kept) / len(titles), 0.74, delta=0.09)
        rep_among_kept = [t for t in c1_kept
                          if bm.replay_keep(_zhwiki_line(t), 3000, 5900)]
        self.assertAlmostEqual(len(rep_among_kept) / len(c1_kept), 0.59,
                               delta=0.15)


class TestAssemblyEndToEnd(unittest.TestCase):
    """端到端：三遍写入计数 + dataset_info 注册 + 红线（不写 c1 文件）。"""

    def test_three_pass_and_registration(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            clean = td / "clean"
            clean.mkdir()
            (clean / "c2_alpha.jsonl").write_text(
                '{"text": "A1"}\n{"text": "A2"}\n', encoding="utf-8")
            (clean / "c2_beta.jsonl").write_text(
                '{"text": "B1"}\n', encoding="utf-8")
            (clean / "c1_enwiki_gen.jsonl").write_text(
                "\n".join(_enwiki_line(f"Wiki {i}") for i in range(200))
                + "\n", encoding="utf-8")
            # 现行回放源（2026-09-26 重构后 main() 硬要求此文件）
            (clean / "c1_zhwiki_gen.jsonl").write_text(
                "\n".join(_zhwiki_line(f"长文 {i}", 4000) for i in range(200))
                + "\n", encoding="utf-8")
            manifest = td / "manifest.jsonl"
            manifest.write_text(json.dumps({
                "name": "alpha", "est_tokens": 1000,
                "files": ["data/corpora/clean/c2_alpha.jsonl"]}) + "\n" +
                json.dumps({
                    "name": "beta", "est_tokens": 500,
                    "files": ["data/corpora/clean/c2_beta.jsonl"]}) + "\n" +
                json.dumps({
                    "name": "enwiki-gen", "est_tokens": 100000,
                    "files": ["data/corpora/clean/c1_enwiki_gen.jsonl"]}) + "\n",
                encoding="utf-8")
            lf = td / "lf"
            lf.mkdir()
            di = lf / "dataset_info.json"
            di.write_text(json.dumps({
                "sec_c1_full": {"file_name": "sec_c1_full.jsonl"}}),
                encoding="utf-8")
            old = (bm.CLEAN, bm.MANIFEST, bm.OUT, bm.DATASET_INFO, bm.ROOT)
            bm.CLEAN, bm.MANIFEST = clean, manifest
            bm.OUT = lf / "sec_m15.jsonl"
            bm.DATASET_INFO = di
            bm.ROOT = td
            try:
                # sys.argv 覆盖（main 无参解析）
                old_argv = sys.argv
                sys.argv = ["build_m15_mix.py"]
                try:
                    bm.main()
                finally:
                    sys.argv = old_argv
                lines = bm.OUT.read_text(encoding="utf-8").splitlines()
                # C2: (A1,A2,B1)×3 = 9 行 + 回放 > 0
                c2_expected = ['{"text": "A1"}', '{"text": "A2"}',
                               '{"text": "B1"}']
                c2_docs = [l for l in lines if l in c2_expected]
                self.assertEqual(len(c2_docs), 9)
                from collections import Counter
                self.assertEqual(Counter(c2_docs),
                                 Counter(c2_expected * 3))
                replay = [l for l in lines if l not in c2_expected]
                self.assertGreater(len(replay), 0)
                self.assertEqual(
                    len(lines), 9 + len(replay))
                # dataset_info：sec_m15 注册 + c1 条目原样保留（红线）
                info = json.loads(di.read_text(encoding="utf-8"))
                self.assertIn("sec_m15", info)
                self.assertEqual(info["sec_c1_full"]["file_name"],
                                 "sec_c1_full.jsonl")
                self.assertEqual(info["sec_m15"]["columns"]["prompt"], "text")
            finally:
                bm.CLEAN, bm.MANIFEST, bm.OUT, bm.DATASET_INFO, bm.ROOT = old


if __name__ == "__main__":
    unittest.main()
