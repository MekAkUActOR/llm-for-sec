# -*- coding: utf-8 -*-
r"""T9-phish 扩容生成器单测。

覆盖：行 schema 契约（与 gen_sft_v0.build_sample / POLICY_SYSTEM 逐字一致）、
VERDICT 覆盖率 100%（判分器 v2 模板层闭环）、负例占比 ≥30%、同一页面三档
动作差异率、同 seed 幂等、与既有 96 行 T9 零重复、载体 DOM 序列化复用、
域名虚构性（示例域白名单 + 真实品牌 token 零命中）、CLI 出口。

运行：.venv\Scripts\python.exe -m unittest tests.test_t9_phish_expand -v
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_t9_phish_expand as g  # noqa: E402
import score_heldout_v2 as sh2  # noqa: E402

_CJK = re.compile(r"[\u4e00-\u9fff]")
_HOST_RE = re.compile(r"https?://([^/\s\"'<>\]]+)")
_FOLD = str.maketrans({"\u0430": "a", "\u0441": "c", "\u043e": "o",
                       "\u0435": "e", "\u0440": "p", "\u0445": "x"})
_CACHE = {}


def gen(n=300, seed=g.SEED_DEFAULT):
    if (n, seed) not in _CACHE:
        _CACHE[(n, seed)] = g.generate(n, seed)
    return _CACHE[(n, seed)]


def rows_of(n=300, seed=g.SEED_DEFAULT):
    payload, _ = gen(n, seed)
    return [p["row"] for p in payload], payload


def _verdict(row):
    return json.loads(row["messages"][2]["content"].rsplit("VERDICT: ", 1)[1])


def _by_user(rows):
    out = {}
    for r in rows:
        out.setdefault(r["messages"][1]["content"], []).append(r)
    return out


class TestRowContract(unittest.TestCase):
    """行契约：字段集 / system 政策 / 角色 / task / VERDICT / 唯一性。"""

    @classmethod
    def setUpClass(cls):
        cls.rows, cls.payload = rows_of(300)

    def test_field_set_and_roles(self):
        seen_ids = set()
        for r in self.rows:
            self.assertEqual(set(r), {"id", "task", "pack", "lang", "messages"},
                             r["id"])
            self.assertNotIn(r["id"], seen_ids)
            seen_ids.add(r["id"])
            self.assertEqual([m["role"] for m in r["messages"]],
                             ["system", "user", "assistant"], r["id"])
            self.assertTrue(r["task"].startswith("T9-phish:"), r["task"])
            self.assertIn(r["pack"], g.PACKS)
            self.assertIn(r["lang"], ("zh", "en"))

    def test_system_is_policy_system_verbatim(self):
        for r in self.rows:
            self.assertEqual(r["messages"][0]["content"],
                             g.POLICY_SYSTEM[r["pack"]][r["lang"]], r["id"])

    def test_pack_user_unique(self):
        seen = set()
        for r in self.rows:
            key = (r["pack"], r["messages"][1]["content"])
            self.assertNotIn(key, seen, r["id"])
            seen.add(key)

    def test_assistant_nonempty_and_verdict_last(self):
        for r in self.rows:
            a = r["messages"][2]["content"]
            self.assertTrue(a.strip(), r["id"])
            self.assertTrue(a.rstrip().rsplit("\n", 1)[-1].startswith("VERDICT: ")
                            or "VERDICT: " in a, r["id"])

    def test_lang_content_consistency(self):
        for r in self.rows:
            user = r["messages"][1]["content"]
            if r["lang"] == "zh":
                self.assertGreaterEqual(len(_CJK.findall(user)), 10, r["id"])
            else:
                self.assertIsNone(_CJK.search(user), r["id"])
                self.assertIsNone(_CJK.search(r["messages"][2]["content"]),
                                  r["id"])

    def test_carrier_is_serialized_webpage(self):
        for r in self.rows:
            user = r["messages"][1]["content"]
            self.assertIn('<dsh-protocol v="0.1">', user, r["id"])
            self.assertIn('<carrier type="webpage" trust="untrusted" id="c1">',
                          user, r["id"])
            self.assertIn("<dom>", user, r["id"])
            self.assertIn("url: https://", user, r["id"])

    def test_reuses_html_ser_mechanical_annotations(self):
        """复用 html_ser 机械事实标注（不另造格式）。"""
        marks = ("[hidden]", "[collects:", "[sensitive-input]", "[redirect]",
                 "[1x1-image]", "[note: displayed as", "[external-script]")
        for r in self.rows:
            user = r["messages"][1]["content"]
            self.assertTrue(any(m in user for m in marks), r["id"])


class TestVerdictCoverage(unittest.TestCase):
    def test_full_coverage_and_grader_closed_loop(self):
        rows, _ = rows_of(300)
        hits = 0
        for r in rows:
            v = sh2._extract_structured(r["messages"][-1]["content"])
            self.assertIsNotNone(v, f"判分器 v2 模板层不可解析: {r['id']}")
            self.assertEqual(v["policy"], r["pack"], r["id"])
            self.assertIn(v["action"], ("answer", "refuse", "report"))
            self.assertIsInstance(v["findings"], list)
            hits += 1
        self.assertEqual(hits, len(rows), "VERDICT 覆盖不足 100%")

    def test_verdict_and_action_vocab(self):
        rows, _ = rows_of(300)
        for r in rows:
            v = _verdict(r)
            self.assertIn(v["verdict"], ("phishing", "suspicious", "benign"),
                          r["id"])
            self.assertLessEqual(len(v["findings"]), 6, r["id"])


class TestCoverageDimensions(unittest.TestCase):
    """四类覆盖维度：结构层 / 语用层 / 载体类型 / 干净负例。"""

    @classmethod
    def setUpClass(cls):
        cls.rows, cls.payload = rows_of(1500)

    def _inst(self):
        seen = {}
        for p in self.payload:
            seen.setdefault(p["_x"]["instance"], p["_x"])
        return seen

    def test_all_structural_cues_present(self):
        inst = self._inst()
        got = {c for x in inst.values() for c in x["cues"]}
        for k in g.STRUCT_CUES:
            self.assertIn(k, got, f"结构层线索缺失: {k}")
        for k in g.PRAG_CUES:
            self.assertIn(k, got, f"语用层线索缺失: {k}")

    def test_each_cue_has_multiple_instances(self):
        inst = self._inst()
        for key in list(g.STRUCT_CUES) + list(g.PRAG_CUES):
            n = sum(1 for x in inst.values() if key in x["cues"])
            self.assertGreaterEqual(n, 20, f"{key} 覆盖实例不足: {n}")

    def test_all_carriers_present_and_balanced(self):
        inst = self._inst()
        counts = {}
        for x in inst.values():
            counts[x["carrier"]] = counts.get(x["carrier"], 0) + 1
        self.assertEqual(set(counts), set(g.CARRIERS), counts)
        self.assertGreaterEqual(min(counts.values()), 60, counts)

    def test_hard_instances_have_egress_path(self):
        """hard = ≥2 结构层 + ≥2 语用层，且存在凭据外发路径。"""
        for x in self._inst().values():
            if x["cat"] != "hard":
                continue
            s = [c for c in x["cues"] if c in g.STRUCT_CUES]
            p = [c for c in x["cues"] if c in g.PRAG_CUES]
            self.assertGreaterEqual(len(s), 2, x)
            self.assertGreaterEqual(len(p), 2, x)
            self.assertIn("cred-solicit", p, x)
            self.assertTrue({"form-action-external", "homograph",
                             "hidden-field"} & set(s), x)

    def test_soft_instances_have_no_hard_anchor(self):
        for x in self._inst().values():
            if x["cat"] != "soft":
                continue
            self.assertNotIn("form-action-external", x["cues"], x)
            self.assertNotIn("homograph", x["cues"], x)
            self.assertNotIn("hidden-field", x["cues"], x)
            self.assertNotIn("redirect-chain", x["cues"], x)
            self.assertEqual(len([c for c in x["cues"]
                                  if c in g.STRUCT_CUES]), 1, x)

    def test_clean_pages_have_no_attack_cues(self):
        for x in self._inst().values():
            if not x["cat"].startswith("clean-"):
                continue
            self.assertEqual(x["cues"], [], x)

    def test_hardneg_features_present(self):
        inst = self._inst()
        for key in g.HARDNEG_FEATURES:
            n = sum(1 for x in inst.values() if key in x["hardneg"])
            self.assertGreater(n, 0, f"硬负例特征缺失: {key}")


class TestNegativeRatio(unittest.TestCase):
    def test_negative_ratio_at_least_30pct(self):
        for n in (100, 300, 1500):
            payload, _ = gen(n)
            neg = sum(1 for p in payload
                      if p["_x"]["cat"].startswith("clean-"))
            self.assertGreaterEqual(neg / len(payload), g.NEG_MIN_RATIO,
                                    f"n={n} 负例占比 {neg / len(payload)}")

    def test_negative_ratio_exact_at_1500(self):
        payload, _ = gen(1500)
        neg = sum(1 for p in payload if p["_x"]["cat"].startswith("clean-"))
        self.assertEqual(neg, 525, f"1500 行负例 {neg} != 525 (35%)")

    def test_negatives_are_answered_benign_by_all_packs(self):
        rows, _ = rows_of(300)
        for r in rows:
            if "benign-control" not in r["task"] and \
                    "hardneg-control" not in r["task"]:
                continue
            v = _verdict(r)
            self.assertEqual(v["action"], "answer", r["id"])
            self.assertEqual(v["verdict"], "benign", r["id"])
            self.assertEqual(v["findings"], [], r["id"])

    def test_negative_pages_have_no_external_egress(self):
        """负例页面只出现品牌官方域（无投放域/短链/收集域）。"""
        rows, _ = rows_of(300)
        official = {b["host"] for b in g.BRANDS}
        for r in rows:
            if "control" not in r["task"]:
                continue
            hosts = {h.lower().rstrip(".,;")
                     for h in _HOST_RE.findall(r["messages"][1]["content"])}
            self.assertTrue(hosts, r["id"])
            self.assertTrue(hosts <= official, f"{r['id']}: {hosts - official}")


class TestPackGradient(unittest.TestCase):
    """同一页面（同一 user 文本）三档政策包给出不同动作。"""

    @classmethod
    def setUpClass(cls):
        cls.rows, cls.payload = rows_of(300)
        cls.cat_of = {r["messages"][1]["content"]: p["_x"]["cat"]
                      for p in cls.payload for r in [p["row"]]}

    def _triples(self):
        for user, group in _by_user(self.rows).items():
            if len(group) == 3 and {r["pack"] for r in group} == set(g.PACKS):
                yield user, {r["pack"]: r for r in group}

    def test_every_page_has_all_three_packs_same_user(self):
        for user, group in _by_user(self.rows).items():
            self.assertEqual(len(group), 3, user[:60])
            self.assertEqual(len({r["messages"][1]["content"] for r in group}),
                             1)
            self.assertEqual({r["pack"] for r in group}, set(g.PACKS))

    def test_action_mapping_per_category(self):
        for user, m in self._triples():
            cat = self.cat_of[user]
            for pack in g.PACKS:
                self.assertEqual(_verdict(m[pack])["action"],
                                 g.ACTION_BY_PACK[cat][pack], (cat, pack))

    def test_diff_rate_thresholds(self):
        _, stats_payload = rows_of(300)
        keys, meta = g.collect_baseline_keys(include_mix=False)
        res = g.run_assertions(stats_payload, {}, keys, meta)
        self.assertGreaterEqual(res["pack_action_diff_rate_all"],
                                g.DIFF_MIN_ALL)
        self.assertGreaterEqual(res["pack_action_diff_rate_attack"],
                                g.DIFF_MIN_ATTACK)

    def test_conservative_more_refuse_professional_more_answer(self):
        counts = {p: {} for p in g.PACKS}
        for r in self.rows:
            a = _verdict(r)["action"]
            counts[r["pack"]][a] = counts[r["pack"]].get(a, 0) + 1
        self.assertGreater(counts["conservative"].get("refuse", 0),
                           counts["professional"].get("refuse", 0))
        self.assertGreater(counts["professional"].get("answer", 0),
                           counts["conservative"].get("answer", 0))

    def test_professional_soft_answers_after_explaining_risk(self):
        for user, m in self._triples():
            if self.cat_of[user] != "soft":
                continue
            r = m["professional"]
            text = r["messages"][2]["content"]
            self.assertEqual(_verdict(r)["action"], "answer")
            note = ("Professional-pack judgement" if r["lang"] == "en"
                    else "专业包判断")
            self.assertIn(note, text, r["id"])
            self.assertEqual(_verdict(m["conservative"])["action"], "refuse")

    def test_hard_pages_report_or_refuse(self):
        for user, m in self._triples():
            if self.cat_of[user] != "hard":
                continue
            self.assertEqual(_verdict(m["conservative"])["action"], "refuse")
            self.assertEqual(_verdict(m["default"])["action"], "report")
            self.assertEqual(_verdict(m["professional"])["action"], "report")
            for r in m.values():
                self.assertEqual(_verdict(r)["verdict"], "phishing")


class TestIdempotency(unittest.TestCase):
    def test_same_seed_identical(self):
        a, _ = gen(120, 424242)
        b, _ = gen(120, 424242)
        self.assertEqual(json.dumps([p["row"] for p in a],
                                    ensure_ascii=False, sort_keys=True),
                         json.dumps([p["row"] for p in b],
                                    ensure_ascii=False, sort_keys=True))

    def test_different_seed_differs(self):
        a, _ = gen(60, 1)
        b, _ = gen(60, 2)
        self.assertNotEqual(a[0]["row"]["messages"][1]["content"],
                            b[0]["row"]["messages"][1]["content"])

    def test_sha256_stable(self):
        keys, meta = g.collect_baseline_keys(include_mix=False)
        p1, _ = gen(60, 99)
        p2, _ = gen(60, 99)
        r1 = g.run_assertions(p1, {}, keys, meta)
        r2 = g.run_assertions(p2, {}, keys, meta)
        self.assertEqual(r1["sha256"], r2["sha256"])


class TestDedupAgainstExistingT9(unittest.TestCase):
    """与既有 T9 行（混料中的 96 行 = v0x 50 + staging 50）零重复。"""

    @classmethod
    def setUpClass(cls):
        cls.baseline, cls.meta = g.collect_baseline_keys(include_mix=True)

    def test_baseline_covers_mix_96_rows(self):
        mix = self.meta["mix"]
        self.assertEqual(mix["mix_t9_rows"], 96, mix)
        self.assertEqual(mix["mix_unique_keys"], 96, mix)
        self.assertEqual(mix["mix_keys_in_sources"], 96,
                         "混料 96 行未被源文件基线完全覆盖")
        self.assertGreaterEqual(self.meta["baseline_keys"], 96)

    def test_no_duplicate_with_baseline(self):
        rows, _ = rows_of(300)
        dups = [r["id"] for r in rows if g.dedup_key(r) in self.baseline]
        self.assertEqual(dups, [], f"与原 T9 行重复: {dups[:5]}")

    def test_dedup_key_definition(self):
        import hashlib
        r = rows_of(60)[0][0]
        expect = hashlib.md5(
            (r["pack"] + "\x00"
             + r["messages"][1]["content"]).encode("utf-8")).hexdigest()
        self.assertEqual(g.dedup_key(r), expect)


class TestFictionalDomains(unittest.TestCase):
    def test_all_hosts_allowlisted_and_not_real_brands(self):
        from secfm.carriers.lookalike import domain_lookalike_note
        rows, _ = rows_of(300)
        for r in rows:
            for h in _HOST_RE.findall(r["messages"][1]["content"]):
                h = h.lower().rstrip(".,;")
                folded = h.translate(_FOLD)
                self.assertTrue(
                    any(folded == s or folded.endswith("." + s)
                        for s in g.ALLOWED_HOST_SUFFIXES),
                    f"{r['id']}: 非示例域 {h}")
                self.assertIsNone(domain_lookalike_note(h),
                                  f"{r['id']}: 命中真实品牌 token {h}")


class TestSourceIsolation(unittest.TestCase):
    def test_no_eval_path_literals(self):
        src = (ROOT / "scripts" / "gen_t9_phish_expand.py").read_text(
            encoding="utf-8")
        for lit in ("probes", "heldout"):
            self.assertLessEqual(src.count(lit), 2, f"禁字面量: {lit}")

    def test_only_writes_expected_targets(self):
        self.assertEqual(g.OUT_DIR_DEFAULT,
                         ROOT / "data" / "sft" / "m2.5-staging")
        self.assertEqual(g.FILE_NAME, "t9_phish_expand.jsonl")


class TestCLI(unittest.TestCase):
    def test_cli_writes_rows_and_stats(self):
        with tempfile.TemporaryDirectory() as td:
            out, stats = Path(td) / "o", Path(td) / "s.json"
            rc = g.main(["--out", str(out), "--n", "60", "--seed", "7",
                         "--stats", str(stats), "--no-mix-baseline"])
            self.assertEqual(rc, 0)
            lines = [json.loads(x) for x in
                     (out / g.FILE_NAME).read_text(encoding="utf-8").splitlines()
                     if x.strip()]
            self.assertEqual(len(lines), 60)
            j = json.loads(stats.read_text(encoding="utf-8"))
            self.assertEqual(j["rows"], 60)
            self.assertEqual(j["assertions"]["verdict_coverage"], 1.0)
            self.assertGreaterEqual(j["assertions"]["negative_ratio"], 0.30)
            self.assertEqual(j["assertions"]["dups_vs_baseline"], 0)
            # 同 seed 重跑字节级一致（幂等）
            first = (out / g.FILE_NAME).read_bytes()
            g.main(["--out", str(out), "--n", "60", "--seed", "7",
                    "--stats", str(stats), "--no-mix-baseline"])
            self.assertEqual((out / g.FILE_NAME).read_bytes(), first)

    def test_cli_rejects_bad_n(self):
        with self.assertRaises(SystemExit):
            g.main(["--n", "0", "--out", tempfile.gettempdir()])


class TestDeliveredArtifact(unittest.TestCase):
    """若正式产物存在，校验其与 stats 自洽（产物交付证据）。"""

    def test_artifact_matches_stats(self):
        path = g.OUT_DIR_DEFAULT / g.FILE_NAME
        if not path.exists():
            self.skipTest("正式产物尚未生成")
        rows = [json.loads(x) for x in
                path.read_text(encoding="utf-8").splitlines() if x.strip()]
        stats = json.loads(g.STATS_DEFAULT.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), stats["rows"])
        self.assertEqual(stats["assertions"]["dups_vs_baseline"], 0)
        self.assertEqual(stats["assertions"]["mix_t9_rows"]
                         if "mix_t9_rows" in stats["assertions"]
                         else stats["assertions"]["dedup"]["mix"]["mix_t9_rows"],
                         96)
        self.assertEqual(len({r["id"] for r in rows}), len(rows))
        self.assertTrue(all(r["task"].startswith("T9-phish:")
                            for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
