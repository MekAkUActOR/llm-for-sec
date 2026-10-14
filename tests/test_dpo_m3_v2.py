# -*- coding: utf-8 -*-
r"""data/lf/dpo_m3_v2.jsonl 与 build/check 脚本的单测（unittest，含故意做坏的反例）。

覆盖：行数=期望、VERDICT 覆盖 100%、键序/值域、policy==pack（含 policy 类
rejected_pack 例外）、chosen≠rejected、id 唯一、reserve 占比≤25%、丢弃率≤5%、
协议类逐字一致、reserve/bt330 仅追加、源文件未被改动、源 bt330 rejected 侧
确实无 VERDICT（审计纠正证据）、分类器 6 条规则 + 丢弃、渲染/追加、定容公式、
分层抽样确定性、构建器自断言反例、校验器反例（缺 VERDICT/policy 不符/键序错/
相同 VERDICT/非法 JSON/action 越界/reserve 超比）。

运行：J:\Projects\llm_for_sec\.venv\Scripts\python.exe -m unittest tests.test_dpo_m3_v2 -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_dpo_m3_v2 as B            # noqa: E402
import check_dpo_m3_v2 as C            # noqa: E402

V2 = ROOT / "data" / "lf" / "dpo_m3_v2.jsonl"
STRICT = ROOT / "data" / "lf" / "dpo_m3_v2_strict.jsonl"
Q = ROOT / "data" / "lf" / "dpo_m3_v2_q.jsonl"
SRC = ROOT / "data" / "lf" / "dpo_m3.jsonl"
REPORT = ROOT / "reports" / "dpo-m3-v2-report.json"
STRICT_REPORT = ROOT / "reports" / "dpo-m3-v2-strict-report.json"
Q_REPORT = ROOT / "reports" / "dpo-m3-v2-q-report.json"

EXPECTED_TOTAL = 22842
EXPECTED_BY_CLASS = {"policy": 14688, "bt330_refusal": 1904,
                     "refusal_quality": 300, "calibration": 240,
                     "reserve": 5710}


# ---------------------------------------------------------------- 测试原料
def _line(action, verdict, conf, pack):
    return "正文。" + "\n" + B.render_verdict_line(
        {"action": action, "verdict": verdict, "confidence": conf,
         "findings": [], "policy": pack})


def good_row(rid="t-1", pack="default", cls="reserve",
             act=("refuse", "refuse"), act2=("answer", "allow"),
             conf=(0.9, 0.8)) -> dict:
    return {"id": rid, "dpo_class": cls, "pack": pack, "lang": "zh",
            "conversations": [{"from": "system", "value": "s"},
                              {"from": "human", "value": "q"}],
            "chosen": {"from": "gpt", "value": _line(*act, conf[0], pack)},
            "rejected": {"from": "gpt", "value": _line(*act2, conf[1], pack)}}


def _write_jsonl(path: Path, rows) -> Path:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def _clone(r: dict) -> dict:
    return json.loads(json.dumps(r, ensure_ascii=False))


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _v2_rows() -> dict:
    return {r["id"]: r for r in _iter_jsonl(V2)}


# ------------------------------------------------- 1) 交付文件结构不变量
class TestV2File(unittest.TestCase):
    def test_01_line_count_equals_expected(self):
        by_class = Counter(r["dpo_class"] for r in _iter_jsonl(V2))
        n_protocol = sum(v for k, v in by_class.items() if k in C.PROTOCOL_CLASSES)
        cap = C.solve_reserve_cap(n_protocol)
        self.assertEqual(sum(by_class.values()), n_protocol + cap)
        self.assertEqual(sum(by_class.values()), EXPECTED_TOTAL)
        self.assertEqual(by_class["reserve"], cap)
        self.assertEqual(dict(by_class), EXPECTED_BY_CLASS)

    def test_02_verdict_coverage_100pct_and_parsable(self):
        n = 0
        for r in _iter_jsonl(V2):
            n += 1
            for side in ("chosen", "rejected"):
                pre, js = C.split_verdict(r[side]["value"])
                self.assertIsNotNone(js, f"{r['id']}:{side} 缺 VERDICT")
                self.assertIsInstance(json.loads(js), dict)
                self.assertTrue(pre.endswith("\n"))
        self.assertEqual(n, EXPECTED_TOTAL)
        self.assertEqual(2 * n, 45684)

    def test_03_key_order_types_and_ranges(self):
        for r in _iter_jsonl(V2):
            for side in ("chosen", "rejected"):
                v = json.loads(C.split_verdict(r[side]["value"])[1])
                self.assertEqual(list(v), C.VERDICT_KEYS)
                self.assertIn(v["action"], C.ACTION_VOCAB)
                if v["verdict"] not in C.VERDICT_VOCAB:
                    self.assertEqual(r["dpo_class"], "calibration")
                    self.assertIsNone(v["verdict"])
                self.assertIsInstance(v["findings"], list)
                self.assertIsInstance(v["confidence"], (int, float))
                self.assertTrue(0.0 <= v["confidence"] <= 1.0)
                self.assertIn(r["pack"], C.PACK_VOCAB)

    def test_04_policy_equals_pack_with_documented_exception(self):
        """口径（父代理 2026-10-06 裁定）：
        chosen.policy == row.pack（严格，所有行）；
        rejected.policy == row.rejected_pack（有该字段时 = 对照设计，计数备查）；
        rejected.policy == row.pack（其余行，严格）。"""
        exc = 0
        for r in _iter_jsonl(V2):
            ch = json.loads(C.split_verdict(r["chosen"]["value"])[1])
            rj = json.loads(C.split_verdict(r["rejected"]["value"])[1])
            self.assertEqual(ch["policy"], r["pack"], r["id"])
            if "rejected_pack" in r:
                self.assertEqual(r["dpo_class"], "policy", r["id"])
                self.assertEqual(rj["policy"], r["rejected_pack"], r["id"])
                self.assertNotEqual(rj["policy"], r["pack"], r["id"])
                exc += 1
            else:
                self.assertEqual(rj["policy"], r["pack"], r["id"])
        self.assertEqual(exc, 14688)
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(rep["rejected_pack_exception_count"], exc)

    def test_05_chosen_rejected_verdict_differ(self):
        conf_only = Counter()
        for r in _iter_jsonl(V2):
            ch = json.loads(C.split_verdict(r["chosen"]["value"])[1])
            rj = json.loads(C.split_verdict(r["rejected"]["value"])[1])
            self.assertNotEqual(json.dumps(ch, ensure_ascii=False),
                                json.dumps(rj, ensure_ascii=False), r["id"])
            a = {k: v for k, v in ch.items() if k != "confidence"}
            b = {k: v for k, v in rj.items() if k != "confidence"}
            if a == b:
                conf_only[r["dpo_class"]] += 1
        self.assertEqual(conf_only["reserve"], 3065)

    def test_06_ids_unique_and_subset_of_source(self):
        ids = [r["id"] for r in _iter_jsonl(V2)]
        self.assertEqual(len(ids), len(set(ids)))
        src_ids = {r["id"] for r in _iter_jsonl(SRC)}
        self.assertTrue(set(ids) <= src_ids)

    def test_07_reserve_ratio_and_drop_rate(self):
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertLessEqual(rep["reserve_share"], 0.25)
        self.assertAlmostEqual(rep["reserve_share"], 5710 / 22842, places=12)
        self.assertLessEqual(rep["reserve_drop_rate_of_pool"], 0.05)
        self.assertEqual(rep["dropped_by_class"]["reserve"], 368)
        self.assertAlmostEqual(rep["reserve_drop_rate_of_pool"], 368 / 30807,
                               places=12)
        self.assertEqual(rep["dropped_by_class"]["bt330_refusal"], 9)
        self.assertEqual(rep["protocol_dropped"], 9)

    def test_08_protocol_texts_verbatim_and_render_append_only(self):
        v2 = _v2_rows()
        changed, appended_bad, matched = [], [], 0
        for s in _iter_jsonl(SRC):
            o = v2.get(s["id"])
            if o is None:
                continue
            matched += 1
            self.assertEqual(o["conversations"], s["conversations"])
            sides = C.NEEDS_RENDER.get(s["dpo_class"], ())
            for side in ("chosen", "rejected"):
                sv, ov = s[side]["value"], o[side]["value"]
                if side not in sides:
                    if ov != sv:
                        changed.append((s["id"], side))
                else:
                    pre, js = C.split_verdict(ov)
                    if pre != sv + "\n" or js is None:
                        appended_bad.append((s["id"], side))
        self.assertEqual(changed, [])
        self.assertEqual(appended_bad, [])
        self.assertEqual(matched, EXPECTED_TOTAL)

    def test_09_source_untouched_baseline(self):
        cls = Counter()
        n = 0
        for r in _iter_jsonl(SRC):
            n += 1
            cls[r["dpo_class"]] += 1
        self.assertEqual(n, C.SRC_BASELINE_TOTAL)
        self.assertEqual(dict(cls), C.SRC_BASELINE_CLASSES)

    def test_10_source_bt330_rejected_side_had_no_verdict(self):
        miss = have = 0
        for r in _iter_jsonl(SRC):
            if r["dpo_class"] == "bt330_refusal":
                if C.split_verdict(r["rejected"]["value"])[1] is None:
                    miss += 1
                else:
                    have += 1
        self.assertEqual(miss, 1913)
        self.assertEqual(have, 0)

    def test_11_report_matches_file(self):
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        by_class = Counter(r["dpo_class"] for r in _iter_jsonl(V2))
        self.assertEqual(rep["total"], EXPECTED_TOTAL)
        self.assertEqual(rep["by_class"], {k: by_class.get(k, 0)
                                           for k in rep["by_class"]})
        self.assertEqual(rep["verdict_coverage_overall"], 1.0)
        self.assertEqual(rep["reserve_cap"], 5710)
        self.assertEqual(rep["seed"], 20261001)
        self.assertEqual(rep["policy_mismatch_rows"], {})
        self.assertEqual(rep["rejected_pack_exception_count"], 14688)

    def test_12_full_checker_exits_zero(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = C.main([])
        self.assertEqual(rc, 0, buf.getvalue()[-2000:])
        self.assertIn("CHECK_PASS", buf.getvalue())


# --------------------------------------------- 2) 分类器 / 渲染器 纯函数
class TestClassifier(unittest.TestCase):
    CASES = [
        ("我不能提供任何关于制作爆炸物的指导，因为这是违法的。", "R1",
         "refuse", "refuse"),
        ("I cannot help with that request, it violates policy.", "R1",
         "refuse", "refuse"),
        ("如果你确认已获得书面授权，我可以继续提供该流程。", "R2",
         "propose", "conditional"),
        ("Can you tell me more about your end goal?", "R3",
         "answer", "insufficient-context"),
        ("这是违法行为，建议你遵守法律并寻求律师帮助。", "R4",
         "answer", "conditional"),
        ("Dogs can learn to dance with clicker training and treats.", "R5",
         "answer", "allow"),
    ]

    def test_13_classifier_rules_and_determinism(self):
        for text, rule, action, verdict in self.CASES:
            with self.subTest(text=text[:16]):
                c = B.classify_reserve_text(text)
                self.assertIsNotNone(c)
                self.assertEqual(c["rule"], rule)
                self.assertEqual(c["action"], action)
                self.assertEqual(c["verdict"], verdict)
                self.assertTrue(0.0 <= c["confidence"] <= 1.0)
                self.assertEqual(c, B.classify_reserve_text(text))

    def test_14_classifier_drops_unstable(self):
        for text in ("", "   ", "?!...", "Hey", "fart", "Why, yes."):
            with self.subTest(text=text):
                self.assertIsNone(B.classify_reserve_text(text))

    def test_15_render_and_append_preserve_text(self):
        v = {"action": "refuse", "verdict": "refuse", "confidence": 0.9,
             "findings": [], "policy": "conservative"}
        line = B.render_verdict_line(v)
        self.assertTrue(line.startswith("VERDICT: "))
        self.assertEqual(list(json.loads(line[len("VERDICT: "):])),
                         list(B.VERDICT_KEYS))
        src = "原文一句。\n第二句。"
        out = B.append_verdict(src, v)
        self.assertEqual(out, src + "\n" + line)
        pre, js = C.split_verdict(out)
        self.assertEqual(pre, src + "\n")
        self.assertEqual(json.loads(js), v)

    def test_16_cap_formula_boundary(self):
        for n in (0, 1, 100, 17132, 17141):
            cap = B.solve_reserve_cap(n)
            if n + cap > 0:
                self.assertLessEqual(cap / (n + cap), 0.25)
            self.assertGreater((cap + 1) / (n + cap + 1), 0.25)
        self.assertEqual(B.solve_reserve_cap(17132), 5710)
        self.assertEqual(C.solve_reserve_cap(17132), 5710)

    def test_17_stratified_sample_deterministic_and_capped(self):
        rows = [{"id": f"r{i:05d}", "lang": "zh" if i % 3 else "en",
                 "pack": "default"} for i in range(1000)]
        a, sa = B.stratified_sample(rows, 250, seed=7)
        b, _ = B.stratified_sample(rows, 250, seed=7)
        c, _ = B.stratified_sample(rows, 250, seed=8)
        self.assertEqual([r["id"] for r in a], [r["id"] for r in b])
        self.assertNotEqual([r["id"] for r in a], [r["id"] for r in c])
        self.assertEqual(len(a), 250)
        self.assertEqual(sum(sa["by_stratum"].values()), 250)
        self.assertEqual(len({r["id"] for r in a}), 250)

    def test_18_fix_row_renders_only_missing_side(self):
        chosen = "I can't help with that.\n" + B.render_verdict_line(
            {"action": "refuse", "verdict": "refuse", "confidence": 0.95,
             "findings": [], "policy": "default"})
        r = {"id": "bt-1", "dpo_class": "bt330_refusal", "pack": "default",
             "lang": "en", "conversations": [{"from": "system", "value": "s"},
                                            {"from": "human", "value": "q"}],
             "chosen": {"from": "gpt", "value": chosen},
             "rejected": {"from": "gpt", "value":
                          "I can look her up in public records and ask around."}}
        out = B.fix_row(r)
        self.assertIsNotNone(out)
        self.assertEqual(out["chosen"]["value"], chosen)
        pre, js = C.split_verdict(out["rejected"]["value"])
        self.assertEqual(pre, r["rejected"]["value"] + "\n")
        self.assertEqual(json.loads(js)["policy"], "default")
        r2 = dict(r, rejected={"from": "gpt", "value": "fart"})
        self.assertIsNone(B.fix_row(r2))


# --------------------------------------------------- 3) 反例：构建器自断言
class TestBuilderSelfCheckCounterexamples(unittest.TestCase):
    def setUp(self):
        self.good = good_row()
        self.rep = {"verdict_coverage_overall": 1.0, "reserve_share": 0.2,
                    "reserve_drop_rate_of_pool": 0.01}

    def _errs(self, rows, rep=None):
        return B.self_check(rows, rep or self.rep)

    def test_19_clean_row_passes(self):
        self.assertEqual(self._errs([self.good]), [])

    def test_20_missing_verdict_flagged(self):
        bad = _clone(self.good)
        bad["rejected"]["value"] = "没有契约的散文。"
        self.assertTrue(any("missing VERDICT" in e for e in self._errs([bad])))

    def test_21_policy_mismatch_flagged(self):
        bad = _clone(self.good)
        bad["rejected"]["value"] = B.append_verdict(
            "正文。", {"action": "answer", "verdict": "allow", "confidence": 0.8,
                     "findings": [], "policy": "professional"})
        self.assertTrue(any("rejected policy != pack" in e
                            for e in self._errs([bad])))

    def test_22_wrong_key_order_flagged(self):
        bad = _clone(self.good)
        bad["rejected"]["value"] = ("正文。\nVERDICT: " + json.dumps(
            {"verdict": "allow", "action": "answer", "confidence": 0.8,
             "findings": [], "policy": "default"}, ensure_ascii=False))
        self.assertTrue(any("bad key order" in e for e in self._errs([bad])))

    def test_23_identical_verdicts_flagged(self):
        bad = _clone(self.good)
        bad["rejected"]["value"] = bad["chosen"]["value"]
        self.assertTrue(any("chosen VERDICT == rejected VERDICT" in e
                            for e in self._errs([bad])))

    def test_24_duplicate_id_and_ratio_flagged(self):
        dup = [_clone(self.good), _clone(self.good)]
        self.assertTrue(any("duplicate ids" in e for e in self._errs(dup)))
        over = dict(self.rep, reserve_share=0.30)
        self.assertTrue(any("reserve share" in e for e in self._errs([self.good],
                                                                    over)))
        drop = dict(self.rep, reserve_drop_rate_of_pool=0.06)
        self.assertTrue(any("drop rate" in e for e in self._errs([self.good],
                                                                drop)))


# ----------------------------------------------------- 4) 反例：校验器
class TestCheckerCounterexamples(unittest.TestCase):
    def _errors_for(self, row) -> list:
        with tempfile.TemporaryDirectory() as td:
            p = _write_jsonl(Path(td) / "rows.jsonl", [row])
            ck = C.Check()
            C.check_structure(ck, p)
            return ck.errors

    def test_25_missing_verdict(self):
        r = good_row("bad-1")
        r["rejected"]["value"] = "无契约散文。"
        self.assertTrue(any("缺 VERDICT" in e for e in self._errors_for(r)))

    def test_26_policy_mismatch(self):
        r = good_row("bad-2", pack="default")
        r["chosen"]["value"] = B.append_verdict(
            "正文。", {"action": "refuse", "verdict": "refuse", "confidence": 0.9,
                     "findings": [], "policy": "professional"})
        self.assertTrue(any("policy != pack" in e for e in self._errors_for(r)))

    def test_27_wrong_key_order(self):
        r = good_row("bad-3")
        r["chosen"]["value"] = ("正文。\nVERDICT: " + json.dumps(
            {"verdict": "refuse", "action": "refuse", "confidence": 0.9,
             "findings": [], "policy": "default"}, ensure_ascii=False))
        self.assertTrue(any("键序" in e for e in self._errors_for(r)))

    def test_28_identical_verdicts(self):
        r = good_row("bad-4")
        r["rejected"]["value"] = r["chosen"]["value"]
        self.assertTrue(any("chosen VERDICT == rejected VERDICT" in e
                            for e in self._errors_for(r)))

    def test_29_bad_json_and_action_vocab(self):
        r = good_row("bad-5")
        r["chosen"]["value"] = "正文。\nVERDICT: {not json}"
        self.assertTrue(any("非法 JSON" in e for e in self._errors_for(r)))
        r2 = good_row("bad-6")
        r2["chosen"]["value"] = B.append_verdict(
            "正文。", {"action": "report", "verdict": "allow", "confidence": 0.9,
                     "findings": [], "policy": "default"})
        self.assertTrue(any("action 越界" in e for e in self._errors_for(r2)))

    def test_30_confidence_and_findings_type(self):
        r = good_row("bad-7")
        r["chosen"]["value"] = B.append_verdict(
            "正文。", {"action": "refuse", "verdict": "refuse",
                     "confidence": 1.7, "findings": "x", "policy": "default"})
        errs = self._errors_for(r)
        self.assertTrue(any("confidence 越界" in e for e in errs))
        self.assertTrue(any("findings 非 list" in e for e in errs))

    def test_31_reserve_ratio_counterexample(self):
        ok = C.Check()
        self.assertEqual(C.check_reserve_ratio(ok, 25, 100), 0.25)
        self.assertEqual(ok.errors, [])
        bad = C.Check()
        C.check_reserve_ratio(bad, 26, 100)
        self.assertTrue(bad.errors and "reserve 占比" in bad.errors[0])
        edge = C.Check()
        self.assertLess(C.check_reserve_ratio(edge, 5710, 22842), 0.25)
        self.assertEqual(edge.errors, [])
        over = C.Check()
        C.check_reserve_ratio(over, 5711, 22842)
        self.assertTrue(over.errors)


# ------------------------------------------- 5) 严格版（两侧立场必须不同）
class TestStrictVariant(unittest.TestCase):
    """data/lf/dpo_m3_v2_strict.jsonl + reports/dpo-m3-v2-strict-report.json"""

    def test_32_strict_is_v2_subset_and_100pct_stance_signal(self):
        self.assertTrue(STRICT.exists(), f"缺 {STRICT}")
        v2 = _v2_rows()
        st_rows = {r["id"]: r for r in _iter_jsonl(STRICT)}
        self.assertTrue(set(st_rows) <= set(v2))
        self.assertEqual(len(st_rows), 19521)
        self.assertEqual(len(st_rows), len(set(st_rows)))
        no_signal = []
        for rid, r in st_rows.items():                    # 逐字相同 + 立场不同
            self.assertEqual(json.dumps(r, ensure_ascii=False, sort_keys=True),
                             json.dumps(v2[rid], ensure_ascii=False,
                                        sort_keys=True), rid)
            ch = json.loads(C.split_verdict(r["chosen"]["value"])[1])
            rj = json.loads(C.split_verdict(r["rejected"]["value"])[1])
            if not B.has_stance_signal(ch, rj):
                no_signal.append(rid)
        self.assertEqual(no_signal, [])
        # 与校验器口径一致
        self.assertEqual(tuple(B.STANCE_FIELDS), tuple(C.STANCE_FIELDS))

    def test_33_strict_report_diff_counts_and_ratios(self):
        srep = json.loads(STRICT_REPORT.read_text(encoding="utf-8"))
        v2 = _v2_rows()
        st_rows = {r["id"]: r for r in _iter_jsonl(STRICT)}
        by_class = Counter(r["dpo_class"] for r in st_rows.values())
        rem = Counter(r["dpo_class"] for rid, r in v2.items()
                      if rid not in st_rows)
        self.assertEqual(srep["total"], len(st_rows))
        self.assertEqual(srep["diff_vs_v2"]["v2_total"], len(v2))
        self.assertEqual(srep["diff_vs_v2"]["strict_total"], len(st_rows))
        self.assertEqual(srep["diff_vs_v2"]["v2_only_rows"],
                         len(v2) - len(st_rows))
        self.assertEqual(srep["diff_vs_v2"]["strict_only_rows"], 0)
        self.assertEqual({k: rem.get(k, 0)
                          for k in srep["diff_vs_v2"]["removed_by_class"]},
                         srep["diff_vs_v2"]["removed_by_class"])
        # 期望的按类剔除数（与父代理 2026-10-06 裁定口径一致）
        self.assertEqual(dict(rem), {"reserve": 3065, "refusal_quality": 246,
                                     "bt330_refusal": 10})
        self.assertEqual(dict(by_class),
                         {"policy": 14688, "bt330_refusal": 1894,
                          "refusal_quality": 54, "calibration": 240,
                          "reserve": 2645})
        self.assertEqual(srep["verdict_coverage_overall"], 1.0)
        self.assertAlmostEqual(srep["reserve_share"], 2645 / 19521, places=12)
        self.assertLessEqual(srep["reserve_share"], 0.25)
        self.assertEqual(srep["strict_fields"], list(B.STANCE_FIELDS))
        self.assertEqual(srep["seed"], 20261001)

    def test_34_strict_filter_drops_only_no_signal(self):
        rows = [good_row("s-1", act=("refuse", "refuse"), act2=("answer", "allow")),
                good_row("s-2", act=("answer", "allow"), act2=("answer", "allow"),
                         conf=(0.9, 0.8)),          # 仅置信度不同 → 应剔除
                good_row("s-3", act=("answer", "allow"), act2=("answer", "allow"),
                         conf=(0.9, 0.9))]          # 连置信度都相同 → 也剔除
        kept, removed = B.strict_filter(rows)
        self.assertEqual([r["id"] for r in kept], ["s-1"])
        self.assertEqual([r["id"] for r in removed], ["s-2", "s-3"])
        # 字面口径（仅 action,verdict）会把 policy 类视为同立场
        pol = good_row("s-4", cls="policy", pack="default",
                       act=("refuse", "refuse"), act2=("refuse", "refuse"))
        pol["rejected_pack"] = "professional"
        pol["rejected"]["value"] = B.append_verdict(
            "正文。", {"action": "refuse", "verdict": "refuse", "confidence": 0.9,
                     "findings": [], "policy": "professional"})
        self.assertEqual(len(B.strict_filter([pol])[0]), 1)          # 默认口径保留
        lit_kept, lit_rem = B.strict_filter([pol], ("action", "verdict"))
        self.assertEqual(lit_kept, [])
        self.assertEqual([r["id"] for r in lit_rem], ["s-4"])

    def test_35_strict_row_errors_counterexample_same_stance_kept(self):
        """反例：两侧立场相同却被保留 → 校验器必须报错。"""
        r = good_row("strict-bad", act=("answer", "allow"),
                     act2=("answer", "allow"), conf=(0.88, 0.86))
        self.assertTrue(C.strict_row_errors(r))
        ok = good_row("strict-ok", act=("refuse", "refuse"),
                      act2=("answer", "allow"))
        self.assertEqual(C.strict_row_errors(ok), [])
        # 端到端：临时 strict 文件 + 临时报告
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            sp = _write_jsonl(tdp / "strict.jsonl", [r, ok])
            v2rows = {"strict-bad": _clone(r), "strict-ok": _clone(ok)}
            srep = {"strict_fields": list(C.STANCE_FIELDS), "total": 2,
                    "by_class": {"reserve": 2}, "reserve_share": 1.0,
                    "verdict_coverage_overall": 1.0, "seed": 20261001,
                    "reserve_drop_rate_of_pool": 0.0,
                    "diff_vs_v2": {"v2_total": 2, "strict_total": 2,
                                   "v2_only_rows": 0, "strict_only_rows": 0,
                                   "removed_by_class": {"reserve": 0}}}
            rp = tdp / "strict-report.json"
            rp.write_text(json.dumps(srep, ensure_ascii=False), encoding="utf-8")
            ck = C.Check()
            C.check_strict(ck, v2rows, strict_path=sp, report_path=rp)
            joined = " | ".join(ck.errors)
            self.assertIn("两侧立场相同", joined)
            # 反例 2：严格版出现 v2 里没有的行
            extra = good_row("strict-extra", act=("refuse", "refuse"),
                             act2=("answer", "allow"))
            sp2 = _write_jsonl(tdp / "strict2.jsonl", [r, ok, extra])
            ck2 = C.Check()
            C.check_strict(ck2, v2rows, strict_path=sp2, report_path=rp)
            self.assertIn("不在 v2 中", " | ".join(ck2.errors))

    def test_36_strict_resample_projection_is_consistent(self):
        srep = json.loads(STRICT_REPORT.read_text(encoding="utf-8"))
        p = srep["resample_projection"]
        self.assertEqual(p["protocol_kept"], 16876)
        self.assertEqual(p["cap_if_resampled"],
                         C.solve_reserve_cap(p["protocol_kept"]))
        self.assertLessEqual(p["projected_reserve"], p["cap_if_resampled"])
        self.assertLessEqual(p["projected_reserve"],
                             p["reserve_pool_with_stance_signal"])
        self.assertAlmostEqual(p["projected_reserve_share"],
                               p["projected_reserve"] / p["projected_total"],
                               places=12)
        self.assertLessEqual(p["projected_reserve_share"], 0.25)
        self.assertEqual(p["projected_total"],
                         p["protocol_kept"] + p["projected_reserve"])
        self.assertEqual(p["projected_rows_gain"],
                         p["projected_total"] - srep["total"])


# ------------------------- 6) q 版（同立场对两侧 VERDICT 必须逐字相同）
class TestQVariant(unittest.TestCase):
    """data/lf/dpo_m3_v2_q.jsonl + reports/dpo-m3-v2-q-report.json"""

    def test_37_q_same_stance_pairs_share_identical_verdict(self):
        self.assertTrue(Q.exists(), f"缺 {Q}")
        q_rows = list(_iter_jsonl(Q))
        self.assertEqual(len(q_rows), EXPECTED_TOTAL)
        same = Counter()
        bad_same, bad_diff = [], []
        for r in q_rows:
            ch = json.loads(C.split_verdict(r["chosen"]["value"])[1])
            rj = json.loads(C.split_verdict(r["rejected"]["value"])[1])
            cs, rs = B.render_verdict_line(ch), B.render_verdict_line(rj)
            if B.has_stance_signal(ch, rj):
                if cs == rs:
                    bad_diff.append(r["id"])
            else:
                same[r["dpo_class"]] += 1
                if cs != rs:
                    bad_same.append(r["id"])
        self.assertEqual(bad_same, [])          # 不得留任何人造置信差
        self.assertEqual(bad_diff, [])          # 立场不同者不得相同
        self.assertEqual(sum(same.values()), 3321)
        self.assertEqual({k: same.get(k, 0) for k in EXPECTED_BY_CLASS},
                         {"policy": 0, "bt330_refusal": 10,
                          "refusal_quality": 246, "calibration": 0,
                          "reserve": 3065})

    def test_38_q_diff_vs_v2_is_confidence_digits_only(self):
        v2 = _v2_rows()
        q_rows = {r["id"]: r for r in _iter_jsonl(Q)}
        self.assertEqual(set(q_rows), set(v2))
        changed, by_class = [], Counter()
        for rid, qr in q_rows.items():
            b = v2[rid]
            self.assertEqual(qr["chosen"]["value"], b["chosen"]["value"], rid)
            if qr["rejected"]["value"] == b["rejected"]["value"]:
                continue
            changed.append(rid)
            by_class[qr["dpo_class"]] += 1
            pre_o, _ = C.split_verdict(b["rejected"]["value"])
            pre_n, _ = C.split_verdict(qr["rejected"]["value"])
            self.assertEqual(pre_o, pre_n, rid)         # 原文前缀逐字不动
            a = json.loads(C.split_verdict(b["rejected"]["value"])[1])
            z = json.loads(C.split_verdict(qr["rejected"]["value"])[1])
            self.assertEqual([k for k in C.VERDICT_KEYS if a.get(k) != z.get(k)],
                             ["confidence"], rid)
            self.assertEqual(z["confidence"],
                             json.loads(C.split_verdict(
                                 qr["chosen"]["value"])[1])["confidence"], rid)
        self.assertEqual(len(changed), 3321)
        self.assertEqual(dict(by_class), {"reserve": 3065,
                                          "refusal_quality": 246,
                                          "bt330_refusal": 10})
        rep = json.loads(Q_REPORT.read_text(encoding="utf-8"))
        # 与 v2 的差异必须精确等于"那 2,149 对 + 另外 1,172 对"的置信度数字
        w = rep["diff_vs_v2"]["changed_writer_dist"]
        self.assertEqual(w["artificial_tiebreak_0.02"], 2149)
        self.assertEqual(w["natural_confidence_diff"], 1172)
        self.assertEqual(sum(w.values()), len(changed))
        self.assertEqual(rep["diff_vs_v2"]["side_diff_counts"],
                         {"chosen_side_changed": 0, "rejected_side_changed": 3321,
                          "rejected_prefix_changed": 0, "row_added": 0,
                          "row_removed": 0})
        self.assertEqual(rep["diff_vs_v2"]["changed_field_sets"],
                         {"confidence": 3321})

    def test_39_q_row_errors_counterexample(self):
        """反例：同立场对仍带 −0.02 修正 → 必须报错。"""
        still_fixed = good_row("q-bad", act=("answer", "allow"),
                               act2=("answer", "allow"), conf=(0.88, 0.86))
        errs = C.q_row_errors(still_fixed)
        self.assertTrue(errs and "人造置信差" in errs[0], errs)
        fixed = good_row("q-ok", act=("answer", "allow"),
                         act2=("answer", "allow"), conf=(0.88, 0.88))
        self.assertEqual(C.q_row_errors(fixed), [])
        # 立场不同的对：必须不同（若被改成逐字相同则立场也随之相同 ⇒ 落入上一条）
        diff_ok = good_row("q-ok2", act=("refuse", "refuse"),
                           act2=("answer", "allow"))
        self.assertEqual(C.q_row_errors(diff_ok), [])
        self.assertTrue(C.q_row_errors(still_fixed)[0].startswith("q-bad:"))
        # 端到端：临时 q 文件 + 临时报告 ⇒ check_q 必须报"人造置信差"
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            qp = _write_jsonl(tdp / "q.jsonl", [still_fixed])
            rows = {"q-bad": _clone(still_fixed)}
            qrep = {"stance_fields": list(C.STANCE_FIELDS), "total": 1,
                    "by_class": {"reserve": 1}, "reserve_share": 1.0,
                    "verdict_coverage_overall": 1.0, "seed": 20261001,
                    "same_stance_pairs": {"total": 1},
                    "identical_verdict_pairs": {"total": 0},
                    "diff_vs_v2": {"rows_changed": 0, "rows_identical": 1,
                                   "changed_ids": [], "side_diff_counts": {},
                                   "changed_writer_dist": {}}}
            rp = tdp / "q-report.json"
            rp.write_text(json.dumps(qrep, ensure_ascii=False), encoding="utf-8")
            ck = C.Check()
            C.check_q(ck, rows, q_path=qp, report_path=rp)
            joined = " | ".join(ck.errors)
            self.assertIn("人造置信差", joined)          # 核心反例
            self.assertTrue(any("改动行数" in e or "同立场对" in e
                                for e in ck.errors), ck.errors)

    def test_40_q_report_consistency(self):
        rep = json.loads(Q_REPORT.read_text(encoding="utf-8"))
        v2rep = json.loads(REPORT.read_text(encoding="utf-8"))
        q_rows = list(_iter_jsonl(Q))
        by_class = Counter(r["dpo_class"] for r in q_rows)
        self.assertEqual(rep["variant"], "q")
        self.assertEqual(rep["total"], len(q_rows))
        self.assertEqual({k: by_class.get(k, 0) for k in rep["by_class"]},
                         rep["by_class"])
        self.assertEqual(rep["by_class"], EXPECTED_BY_CLASS)
        self.assertEqual(rep["verdict_coverage_overall"], 1.0)
        self.assertAlmostEqual(rep["reserve_share"], 5710 / 22842, places=12)
        self.assertEqual(rep["same_stance_pairs"]["total"], 3321)
        self.assertEqual(rep["identical_verdict_pairs"]["total"], 3321)
        self.assertEqual(rep["diff_vs_v2"]["rows_changed"], 3321)
        self.assertEqual(rep["diff_vs_v2"]["rows_identical"], 22842 - 3321)
        self.assertEqual(rep["reasoning"]["tiebreak_removed"], 2149)
        # q 的置信度差分布里不应再有"只有 −0.02"的人造信号占多数：
        # 2,395 对 delta=0.02 属 chosen 与该文本原置信度的真实差
        self.assertEqual(rep["diff_vs_v2"]["confidence_delta_dist"]["0.02"], 2395)
        # 消融资产：strict 由 v2 或由 q 生成必须相同
        st_v2, _ = B.strict_filter(list(_v2_rows().values()))
        st_q, _ = B.strict_filter(q_rows)
        self.assertEqual(sorted(r["id"] for r in st_v2),
                         sorted(r["id"] for r in st_q))
        # v2 报告的 tiebreak 数 = q 报告里被去掉的人造修正数
        self.assertEqual(sum(v2rep["output_pairs_confidence_tiebreak_by_class"]
                             .values()), rep["reasoning"]["tiebreak_removed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)