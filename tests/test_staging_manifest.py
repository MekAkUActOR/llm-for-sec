"""check_staging_manifest 结账不变量测试（纯 CPU、无网络、不触碰真实语料）。

只跑纯函数与 tmp_path 夹具；唯一只读真实目录的用例是
`TestRealStaging.test_closed`（关掉 data/lf 扫描，约 1 秒）。
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_staging_manifest as csm  # noqa: E402


def make_row(rid, pack="default", lang="en", verdict="clean", action="answer",
             task="T1-injection:tail:fake_context:pos"):
    asst = "answer body\nVERDICT: " + json.dumps(
        {"action": action, "verdict": verdict, "confidence": 0.9,
         "findings": [], "policy": pack}, ensure_ascii=False)
    return {"id": rid, "task": task, "pack": pack, "lang": lang,
            "messages": [{"role": "system", "content": "policy pack: @0.1"},
                         {"role": "user", "content": f"{rid} user text"},
                         {"role": "assistant", "content": asst}]}


class Fixture:
    """最小 staging 夹具：两个族，可按需破坏 README / stats.json。"""

    def __init__(self, root: Path):
        self.dir = root / "stage"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.files = {"alpha": 3, "beta": 2}
        for name, n in self.files.items():
            with open(self.dir / f"{name}.jsonl", "w", encoding="utf-8") as f:
                for i in range(n):
                    f.write(json.dumps(make_row(f"{name}-{i:03d}"),
                                       ensure_ascii=False) + "\n")
        self.readme = self.dir / "README.md"
        self.stats = self.dir / "stats.json"
        self.write_readme()
        self.write_stats()

    def write_readme(self, *, count_alpha=None, extra="", drop=()):
        lines = ["# fixture", ""]
        for name, n in self.files.items():
            if name in drop:
                continue
            shown = n if count_alpha is None or name != "alpha" else count_alpha
            lines.append(f"| {name}.jsonl | {shown} | fixture row |")
        lines.append(extra)
        self.readme.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_stats(self, *, drop=(), families=True):
        blob = {"files": {"alpha": 3}, "t1_by_lang": {"en": 3},
                "t1_by_pack": {"default": 3},
                "t1_by_verdict": {"clean": 3}, "t9_by_lang": {"en": 0},
                "t9_by_pack": {"default": 0}, "t9_by_verdict": {},
                "seed": 1}
        if families:
            blob["families"] = {
                name: {"rows": n} for name, n in self.files.items()
                if name not in drop}
        self.stats.write_text(json.dumps(blob, ensure_ascii=False),
                              encoding="utf-8")

    def run(self):
        return csm.reconcile(stage=self.dir, readme=self.readme,
                             stats=self.stats, lf_mix=self.dir / "nope.jsonl",
                             do_lf=False, log=lambda *a, **k: None)


def codes(report):
    return " ".join(report["errors"])


class TestFamilyStats(unittest.TestCase):
    def test_rows_lang_pack_verdict_keys(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            st = csm.family_stats(fx.dir / "alpha.jsonl")
            self.assertEqual(st["rows"], 3)
            self.assertEqual(st["by_lang"], {"en": 3})
            self.assertEqual(st["by_pack"], {"default": 3})
            self.assertEqual(st["by_verdict"], {"clean": 3})
            self.assertEqual(st["by_action"], {"answer": 3})
            self.assertEqual(st["ids_unique"], 3)
            self.assertEqual(st["pack_user_unique"], 3)
            self.assertEqual(st["schema_violation_rows"], 0)
            self.assertEqual(st["no_verdict_rows"], 0)

    def test_schema_violation_and_missing_verdict_counted(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.jsonl"
            rows = [dict(make_row("x-1"), extra=1),
                    {"id": "x-2", "task": "t", "pack": "default", "lang": "en",
                     "messages": [{"role": "system", "content": "s"},
                                  {"role": "user", "content": "u"},
                                  {"role": "assistant", "content": "no verdict"}]}]
            p.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                         encoding="utf-8")
            errs = []
            st = csm.family_stats(p, errors=errs)
            self.assertEqual(st["schema_violation_rows"], 1)
            self.assertEqual(st["no_verdict_rows"], 1)
            self.assertTrue(errs)


class TestClosure(unittest.TestCase):
    def test_clean_fixture_passes(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            report = fx.run()
            self.assertEqual(report["errors"], [], report["errors"])
            self.assertEqual(report["verdict"], "PASS")
            self.assertEqual(report["family_count"], 2)
            self.assertEqual(report["rows_total"], 5)

    def test_forward_closure_missing_readme_record(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(drop=("beta",))
            rep = fx.run()
            self.assertIn("[I1] beta.jsonl 缺 README 结账记录", codes(rep))

    def test_forward_closure_missing_stats_family(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_stats(drop=("alpha",))
            rep = fx.run()
            self.assertIn("[I1] stats.json 未结账 alpha.jsonl", codes(rep))

    def test_forward_closure_missing_families_block(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_stats(families=False)
            rep = fx.run()
            self.assertIn("无 `families`", codes(rep))

    def test_reverse_closure_deleted_file(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            (fx.dir / "beta.jsonl").unlink()
            rep = fx.run()
            self.assertIn("[I2] README 结账了不存在的族 `beta.jsonl`",
                          codes(rep))
            self.assertIn("[I2] stats.json 结账了不存在的族 `beta.jsonl`",
                          codes(rep))

    def test_reverse_closure_dangling_readme_reference(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(extra="| ghost.jsonl | 7 | stale |")
            rep = fx.run()
            self.assertIn("[I2] README 引用了不存在的族文件 `ghost.jsonl`",
                          codes(rep))

    def test_stale_readme_row_count(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(count_alpha=99)
            rep = fx.run()
            self.assertIn("[I4] alpha.jsonl README 行数过期", codes(rep))

    def test_stale_readme_count_can_be_disabled(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(count_alpha=99)
            rep = csm.reconcile(stage=fx.dir, readme=fx.readme,
                                stats=fx.stats,
                                lf_mix=fx.dir / "nope.jsonl", do_lf=False,
                                check_readme_counts=False,
                                log=lambda *a, **k: None)
            self.assertEqual(rep["errors"], [], rep["errors"])

    def test_stats_rows_must_match_disk(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            blob = json.loads(fx.stats.read_text(encoding="utf-8"))
            blob["families"]["alpha"]["rows"] = 4
            fx.stats.write_text(json.dumps(blob), encoding="utf-8")
            rep = fx.run()
            self.assertIn("[I3] alpha.jsonl stats.json 行数过期", codes(rep))

    def test_legacy_keys_dropped_is_error(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            blob = json.loads(fx.stats.read_text(encoding="utf-8"))
            del blob["t9_by_pack"]
            fx.stats.write_text(json.dumps(blob), encoding="utf-8")
            rep = fx.run()
            self.assertIn("[I5] stats.json 旧键丢失", codes(rep))

    def test_template_placeholder_is_not_a_record(self):
        """`<stem>.jsonl` 这类占位符不得被当成结账记录（防假闭合）。"""
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(drop=("beta",), extra="见 `<stem>.jsonl` 一节。")
            rep = fx.run()
            self.assertIn("[I1] beta.jsonl 缺 README 结账记录", codes(rep))


class TestMarkers(unittest.TestCase):
    def test_marker_pairing_errors(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(extra="\n<!-- X SECTION BEGIN -->\n\n无标题\n")
            rep = fx.run()
            self.assertIn("未闭合", codes(rep))

    def test_marker_block_needs_heading(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            fx.write_readme(extra="\n<!-- X SECTION BEGIN -->\n\n正文\n\n"
                                  "<!-- X SECTION END -->\n")
            rep = fx.run()
            self.assertIn("块内无 ## 标题", codes(rep))

    def test_marker_mismatch(self):
        blocks, errs = csm.readme_markers(
            "<!-- A SECTION BEGIN -->\n## h\n<!-- B SECTION END -->\n")
        self.assertEqual(blocks, [])
        self.assertTrue(errs)


class TestStatsBuilder(unittest.TestCase):
    def test_legacy_keys_preserved_verbatim_and_added_block(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            rep = fx.run()
            old = {"files": {"t1_injection": 375}, "t1_by_lang": {"en": 1},
                   "t1_by_pack": {"default": 1}, "t1_by_verdict": {"x": 1},
                   "t9_by_lang": {"en": 1}, "t9_by_pack": {"default": 1},
                   "t9_by_verdict": {"y": 1}, "seed": 42}
            blob = csm.build_stats(rep, old)
            for k, v in old.items():
                self.assertEqual(blob[k], v)
            self.assertEqual(blob["families"]["alpha"]["rows"], 3)
            self.assertIn("overlap_with_lf_mix", blob)
            self.assertIn("_meta", blob)
            self.assertEqual(blob["_meta"]["family_count"], 2)

    def test_built_stats_satisfy_closure(self):
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            rep = fx.run()
            old = json.loads(fx.stats.read_text(encoding="utf-8"))
            fx.stats.write_text(
                json.dumps(csm.build_stats(rep, old), ensure_ascii=False),
                encoding="utf-8")
            rep2 = fx.run()
            self.assertEqual(rep2["errors"], [], rep2["errors"])

    def test_empty_old_cannot_invent_legacy_keys(self):
        """旧 stats.json 缺失/损坏时 build_stats 不会凭空造旧键 —— 产物会
        I5 报错（宁可响，不静默丢下游可能在读的键）。"""
        with TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp))
            rep = fx.run()
            fx.stats.write_text(
                json.dumps(csm.build_stats(rep, {}), ensure_ascii=False),
                encoding="utf-8")
            rep2 = fx.run()
            self.assertIn("[I5] stats.json 旧键丢失", codes(rep2))


class TestRealStaging(unittest.TestCase):
    def test_closed(self):
        """真实目录必须满足结账不变量（关掉 data/lf 扫描，约 1 秒）。"""
        if not csm.STAGE.exists():
            self.skipTest("data/sft/m2.5-staging 不存在")
        rep = csm.reconcile(do_lf=False, log=lambda *a, **k: None)
        self.assertEqual(rep["errors"], [], rep["errors"][:10])
        files = {p.stem for p in csm.STAGE.glob("*.jsonl")}
        self.assertEqual(set(rep["families"]), files)
        self.assertTrue(files)


if __name__ == "__main__":
    unittest.main()
