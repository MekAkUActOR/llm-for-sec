# -*- coding: utf-8 -*-
r"""T2 机制解释族（scripts/gen_t2_mechanism.py）单测。

覆盖：
  1. schema 合规（m1 契约 {id,task,pack,lang,messages} / 角色顺序 /
     system 区 == 导入的 POLICY_SYSTEM / id 与 (pack,user) 唯一 /
     zh:en 均衡 / zh 行中文 / en 行零 CJK）；
  2. VERDICT 覆盖率 100%（判分器 v2 严格模板层可直接解析、
     policy==pack、action/verdict 在 T2 词表内、findings 带机制类别）；
  3. 无载荷标记断言（0 命中）+ **故意注入的负例**证明断言真的会失败
     （代码块 / curl 载荷 / 缺 VERDICT 三种注入各一）；
  4. 三档差异化（同情境三包的 (action,verdict) 差异比例 ≥ 下限；
     边界情境三包同拒；F4 conservative 拒而 default 答；干净负例不被拒）；
  5. 幂等（同 seed 同输出，逐字节一致）+ CLI 落盘与统计报告；
  6. 隔离红线（生成器源码零评估/探针路径字面量；POLICY_SYSTEM 为导入而非复制）。

运行：.venv\\Scripts\\python.exe -m unittest tests.test_t2_mechanism -v
"""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sft_v0 as g0           # noqa: E402
import gen_t2_mechanism as g      # noqa: E402
import score_heldout_v2 as sh2    # noqa: E402

N_TEST = 600           # 200 情境组：覆盖 15 题材 × zh/en × 5 情境
SEED_TEST = 20261001
FORBIDDEN_LITERALS = ("heldout", "probes", "ais-500", "v0.1.1", "v0.2",
                      "data/lf", "sft_m25.jsonl")
# 情境指纹（用于在测试侧识别 F3 边界 / F4 第三方 / F5 干净负例）
F3_FP = ("操作序列", "executable sequence")
F4_FP = ("没有所有权的第三方系统", "third-party system we do not own")
F5_FP = ("为什么能阻止这类机制", "stop this mechanism class")
REQUIRED_MARKERS = ("```", "python", "bash", "poc", "exploit code", "curl ")

_ROWS = None


def rows():
    global _ROWS
    if _ROWS is None:
        _ROWS = g.generate(N_TEST, SEED_TEST)
    return _ROWS


def report():
    return g.validate_rows(rows(), expect_total=N_TEST,
                           expect_categories=g.planned_coverage(N_TEST)["categories"])


def verdict_of(row):
    return json.loads(row["messages"][2]["content"].rsplit("VERDICT: ", 1)[1])


def user_of(row):
    return next(m["content"] for m in row["messages"] if m["role"] == "user")


def asst_of(row):
    return row["messages"][-1]["content"]


def groups_of(rs):
    out = {}
    for r in rs:
        ref = g._REF_RE.search(user_of(r)).group(0)
        out.setdefault(ref, []).append(r)
    return out


def hit_fp(text, fps):
    return any(fp in text for fp in fps)


def rows_with(fp):
    return [r for r in rows() if hit_fp(user_of(r), fp)]


class TestSchemaAndStructure(unittest.TestCase):
    def test_field_contract_and_task(self):
        for r in rows():
            self.assertEqual(set(r), {"id", "task", "pack", "lang", "messages"},
                             r["id"])
            self.assertEqual(r["task"], "T2-mechanism")

    def test_message_roles_and_system_policy_block(self):
        for r in rows():
            roles = [m["role"] for m in r["messages"]]
            self.assertEqual(roles, ["system", "user", "assistant"], r["id"])
            sysmsg = r["messages"][0]["content"]
            # system 区逐字等于导入的政策系统提示（证明未复制字面量）
            self.assertEqual(sysmsg, g0.POLICY_SYSTEM[r["pack"]][r["lang"]])
            self.assertIn("pack:", sysmsg)
            self.assertIn("@0.1", sysmsg)
            self.assertIn("P-DUALUSE-GRANULARITY", sysmsg)

    def test_ids_and_pack_user_unique(self):
        ids, pack_user = set(), set()
        for r in rows():
            self.assertNotIn(r["id"], ids)
            ids.add(r["id"])
            key = (r["pack"], user_of(r))
            self.assertNotIn(key, pack_user)
            pack_user.add(key)
        self.assertEqual(len(ids), N_TEST)

    def test_three_packs_per_group(self):
        for ref, entries in groups_of(rows()).items():
            self.assertEqual({e["pack"] for e in entries}, set(g.PACKS), ref)
            self.assertEqual(len(entries), 3, ref)

    def test_lang_balance_and_cjk_discipline(self):
        zh = [r for r in rows() if r["lang"] == "zh"]
        en = [r for r in rows() if r["lang"] == "en"]
        self.assertEqual(len(zh) + len(en), N_TEST)
        self.assertLessEqual(abs(len(zh) - len(en)), max(1, N_TEST // 20))
        for r in zh:
            self.assertGreaterEqual(len(g._CJK.findall(user_of(r))), 10, r["id"])
        for r in en:
            self.assertIsNone(g._CJK.search(user_of(r)), r["id"])
            self.assertIsNone(g._CJK.search(asst_of(r)), r["id"])
            bad = [c for c in (user_of(r) + asst_of(r)) if ord(c) > 127]
            self.assertEqual(bad, [], "%s 非 ASCII: %s" % (r["id"], bad))

    def test_category_and_topic_coverage_both_langs(self):
        seen_cat, seen_topic = set(), set()
        for r in rows():
            v = verdict_of(r)
            blob = " ".join(str(x) for x in v["findings"])
            tid = next((t for t in g.TID2CAT if t in blob), None)
            self.assertIsNotNone(tid, r["id"])
            seen_cat.add((g.TID2CAT[tid], r["lang"]))
            seen_topic.add((tid, r["lang"]))
        for cat, _zh in g.CATS:
            for lang in g.LANGS:
                self.assertIn((cat, lang), seen_cat, "%s/%s 缺行" % (cat, lang))
        self.assertEqual(len({c for c, _l in seen_cat}), 5)
        self.assertEqual(len(seen_topic), 2 * len(g.TOPICS))
        for topic in g.TOPICS:
            for lang in g.LANGS:
                self.assertIn((topic["tid"], lang), seen_topic,
                              "%s/%s 缺行" % (topic["tid"], lang))

    def test_default_output_path(self):
        self.assertEqual(g.OUT_DEFAULT,
                         ROOT / "data" / "sft" / "m2.5-staging"
                         / "t2_mechanism.jsonl")


class TestVerdictClosedLoop(unittest.TestCase):
    def test_verdict_coverage_100pct(self):
        for r in rows():
            self.assertTrue(asst_of(r).rstrip().endswith("}"), r["id"])
            self.assertIn("VERDICT: ", asst_of(r), r["id"])

    def test_strict_template_layer_parses_every_row(self):
        for r in rows():
            parsed = sh2._extract_structured(asst_of(r))
            self.assertIsNotNone(parsed, r["id"])
            self.assertEqual(parsed["policy"], r["pack"], r["id"])
            self.assertIn(parsed["action"], ("answer", "refuse", "report"))
            self.assertIn(parsed["verdict"], g.VOCAB)
            self.assertGreater(parsed["confidence"], 0.0)
            self.assertLessEqual(parsed["confidence"], 1.0)
            self.assertEqual(len(parsed["findings"]), 3, r["id"])

    def test_verdict_vocabulary_and_action_pairing(self):
        for r in rows():
            v = verdict_of(r)
            if v["action"] == "refuse":
                self.assertEqual(v["verdict"], g.V_REFUSE, r["id"])
            elif r["pack"] == "professional":
                self.assertEqual(v["verdict"], g.V_MECH_PLUS, r["id"])
            elif v["action"] == "answer":
                self.assertEqual(v["verdict"], g.V_MECH, r["id"])


class TestNoPayloadMarkers(unittest.TestCase):
    def test_marker_list_covers_required_terms(self):
        for m in REQUIRED_MARKERS:
            self.assertIn(m, g.PAYLOAD_MARKERS, m)
        self.assertGreaterEqual(len(g.PAYLOAD_MARKERS), 30)

    def test_zero_marker_hits_in_generated_rows(self):
        rep = report()
        self.assertEqual(rep["checks"]["payload_marker_hits"], 0)
        for r in rows():
            self.assertEqual(g.find_payload_markers(asst_of(r)), [], r["id"])
            self.assertEqual(g.find_payload_markers(user_of(r)), [], r["id"])

    def test_finder_detects_known_payload_shapes(self):
        for bad in ("```python\nprint(1)\n```",
                    "run this: curl http://x/y",
                    "a POC for the overflow",
                    "here is the exploit code",
                    "bash -c id"):
            self.assertTrue(g.find_payload_markers(bad), bad)
        self.assertEqual(g.find_payload_markers(
            "Mechanism explanation with no executable content."), [])

    def test_injected_negative_makes_assertion_fail(self):
        """故意注入负例：证明断言真的会失败（不是恒真）。"""
        base = rows()[0]
        cases = {
            "code_block": asst_of(base) + "\n```python\nprint('owned')\n```",
            "curl_payload": asst_of(base) + "\ncurl http://example.invalid/x",
            "missing_verdict": asst_of(base).split("VERDICT: ")[0].strip(),
        }
        for name, poisoned in cases.items():
            with self.subTest(case=name):
                bad = json.loads(json.dumps(base, ensure_ascii=False))
                bad["messages"][-1]["content"] = poisoned
                rep = g.validate_rows([bad])
                self.assertFalse(rep["ok"], name)
                self.assertTrue(rep["errors"], name)
                if name != "missing_verdict":
                    self.assertGreater(rep["checks"]["payload_marker_hits"], 0)
                else:
                    self.assertEqual(rep["checks"]["payload_marker_hits"], 0)
                    self.assertTrue(any("缺 VERDICT" in e for e in rep["errors"]))

    def test_marker_scan_covers_user_side_too(self):
        base = rows()[0]
        bad = json.loads(json.dumps(base, ensure_ascii=False))
        bad["messages"][1]["content"] = user_of(base) + "\npython exploit.py"
        rep = g.validate_rows([bad])
        self.assertFalse(rep["ok"])
        self.assertGreater(rep["checks"]["payload_marker_hits"], 0)


class TestTriPackDifferentiation(unittest.TestCase):
    def test_diff_ratio_meets_floor(self):
        rep = report()
        self.assertGreaterEqual(rep["checks"]["tri_pack_diff_ratio"],
                                g.TRI_PACK_DIFF_FLOOR)
        self.assertGreater(rep["checks"]["tri_pack_diff_groups"], 0)

    def test_professional_adds_detection_points_not_operational(self):
        prof = [r for r in rows() if r["pack"] == "professional"
                and verdict_of(r)["action"] == "answer"]
        self.assertTrue(prof)
        for r in prof:
            self.assertIn(g.V_MECH_PLUS, asst_of(r))
            self.assertIn("- ", asst_of(r))          # 检测要点为条目级

    def test_boundary_groups_refuse_in_all_packs(self):
        grp = groups_of(rows_with(F3_FP))
        self.assertTrue(grp, "缺 F3 边界情境")
        for ref, entries in grp.items():
            for e in entries:
                v = verdict_of(e)
                self.assertEqual(v["action"], "refuse", ref)
                self.assertEqual(v["verdict"], g.V_REFUSE, ref)
            # 拒绝教学：必须有边界理由 + 替代路径（与 T7 同形，不复用 T7 内容）
            text = asst_of(entries[0])
            self.assertTrue(("操作增量" in text) or ("operational uplift" in text),
                            ref)
        ratio = len(grp) / len(groups_of(rows()))
        self.assertLessEqual(ratio, 0.15, "边界组应为少数对照行")
        rep = report()
        self.assertLessEqual(rep["checks"]["refuse_ratio"], g.REFUSE_RATIO_CAP)

    def test_third_party_framing_splits_packs(self):
        grp = groups_of(rows_with(F4_FP))
        self.assertTrue(grp, "缺 F4 第三方情境")
        for ref, entries in grp.items():
            by_pack = {e["pack"]: verdict_of(e) for e in entries}
            self.assertEqual(by_pack["conservative"]["action"], "refuse", ref)
            for p in ("default", "professional"):
                self.assertEqual(by_pack[p]["action"], "answer", ref)
                self.assertIn("P-CONTEXT-THRESHOLD", asst_of(
                    next(e for e in entries if e["pack"] == p)), ref)

    def test_clean_negatives_answered_not_refused(self):
        """F5 防御侧机理 = 干净负例：三包都不应因'问机理'而拒（误拒纪律）。"""
        grp = groups_of(rows_with(F5_FP))
        self.assertTrue(grp, "缺 F5 干净负例情境")
        for ref, entries in grp.items():
            for e in entries:
                self.assertEqual(verdict_of(e)["action"], "answer", ref)

    def test_conservative_and_default_stay_textbook(self):
        for r in rows():
            if r["pack"] in ("conservative", "default"):
                if verdict_of(r)["action"] == "answer":
                    self.assertIn("textbook", asst_of(r), r["id"])


class TestIdempotency(unittest.TestCase):
    def test_same_seed_same_rows(self):
        a = g.generate(N_TEST, SEED_TEST)
        b = g.generate(N_TEST, SEED_TEST)
        self.assertEqual(len(a), len(b))
        for ra, rb in zip(a, b):
            self.assertEqual(json.dumps(ra, ensure_ascii=False, sort_keys=True),
                             json.dumps(rb, ensure_ascii=False, sort_keys=True))

    def test_cli_writes_file_and_stats_report(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "t2.jsonl"
            stats = Path(td) / "stats.json"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = g.main(["--n", "100", "--seed", str(SEED_TEST),
                             "--out", str(out), "--stats-out", str(stats)])
            self.assertEqual(rc, 0)
            lines = [ln for ln in out.read_text(encoding="utf-8").splitlines()
                     if ln.strip()]
            self.assertEqual(len(lines), 100)
            rep = json.loads(stats.read_text(encoding="utf-8"))
            self.assertTrue(rep["assert_ok"], rep["errors"])
            self.assertEqual(rep["n"], 100)
            self.assertEqual(rep["payload_marker_hits"], 0)
            self.assertEqual(rep["sha256"],
                             hashlib.sha256(out.read_bytes()).hexdigest())
            # 同参数重跑 → 同 sha256（幂等）
            out2 = Path(td) / "t2b.jsonl"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g.main(["--n", "100", "--seed", str(SEED_TEST),
                                         "--out", str(out2)]), 0)
            self.assertEqual(hashlib.sha256(out2.read_bytes()).hexdigest(),
                             rep["sha256"])

    def test_non_multiple_of_three_row_count(self):
        rs = g.generate(100, SEED_TEST)
        rep = g.validate_rows(rs, expect_total=100,
                              expect_categories=g.planned_coverage(100)["categories"])
        self.assertEqual(len(rs), 100)
        self.assertTrue(rep["ok"], rep["errors"])
        self.assertEqual(rep["checks"]["partial_groups"], 1)


class TestIsolationAndReuse(unittest.TestCase):
    def test_policy_system_is_imported_not_copied(self):
        self.assertIs(g.POLICY_SYSTEM, g0.POLICY_SYSTEM)
        src = (ROOT / "scripts" / "gen_t2_mechanism.py").read_text(encoding="utf-8")
        for literal in ("你是安全感知助手", "You are a security-perception assistant",
                        "HF-001 儿童性剥削内容"):
            self.assertNotIn(literal, src, "政策字面量被复制：%s" % literal)
        self.assertIn("from gen_sft_v0 import", src)

    def test_generator_source_free_of_eval_path_literals(self):
        src = (ROOT / "scripts" / "gen_t2_mechanism.py").read_text(encoding="utf-8")
        for lit in FORBIDDEN_LITERALS:
            self.assertNotIn(lit, src, "生成器源码含禁字面量：%r" % lit)

    def test_rows_free_of_eval_path_references(self):
        for r in rows()[:80]:
            for m in r["messages"]:
                for lit in FORBIDDEN_LITERALS:
                    self.assertNotIn(lit, m["content"], r["id"])


class TestStagingCheckerReuse(unittest.TestCase):
    """复用既有暂存校验器 check_m25_staging 的结构/语种/唯一性规则跑 T2

    （该脚本的文件清单是固定的、不允许改动，故此处直接调用它的规则函数，
    等价于把 T2 产物送进同一条硬闸。）
    """

    def test_checker_structure_rules_pass_on_t2_rows(self):
        import check_m25_staging as chk
        errors = []
        stats = chk.check_structure_lang_uniqueness(
            list(enumerate(rows())), "t2_mechanism", errors,
            prefixes=("T2-mechanism",))
        self.assertEqual(errors, [], errors[:5])
        self.assertEqual(sum(stats["lang"].values()), N_TEST)
        self.assertLessEqual(abs(stats["lang"]["zh"] - stats["lang"]["en"]), 5)
        for p in g.PACKS:
            self.assertGreater(stats["pack"].get(p, 0), 0)
        self.assertEqual(stats["action"].get("refuse"),
                         report()["checks"]["refuse_rows"])
        for k in g.VOCAB:
            self.assertGreater(stats["verdict"].get(k, 0), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
