r"""gen_sft_v0 生成管线测试：隔离断言（红线）、VERDICT 闭环（判分器 v2 严格
模板层直接消费）、三包配对一致性、注入协议回路、PII 合成性审计、计数。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sft_v0 as g  # noqa: E402
import score_heldout_v2 as sh2  # noqa: E402

# 评估/探针路径字面量（生成器源码必须为零命中——物理隔离红线）
FORBIDDEN_LITERALS = ("heldout", "probes", "ais-500", "v0.1.1", "v0.2")


def _verdict_of(row: dict) -> dict:
    return sh2._extract_structured(row["messages"][-1]["content"])


class CorpusMixin:
    @classmethod
    def setUpClass(cls):
        cls.rows = cls.gen()

    def _verdicts(self):
        for r in self.rows:
            v = _verdict_of(r)
            self.assertIsNotNone(v, f"VERDICT 不可解析: {r['id']}")
            yield r, v


class TestIsolation(unittest.TestCase):
    """物理隔离：生成管线接触不到评估集与探针集（红线）。"""

    def test_generator_source_free_of_eval_path_literals(self):
        src = (ROOT / "scripts" / "gen_sft_v0.py").read_text(encoding="utf-8")
        for lit in FORBIDDEN_LITERALS:
            self.assertNotIn(lit, src, f"生成器源码含禁字面量: {lit!r}")

    def test_generated_rows_free_of_eval_path_references(self):
        rows = (g.gen_policy_pairs() + g.gen_injection_pairs()
                + g.gen_pii_synthetic() + g.gen_calibration())
        for r in rows:
            for m in r["messages"]:
                for lit in FORBIDDEN_LITERALS:
                    self.assertNotIn(lit, m["content"], r["id"])

    def test_generator_writes_only_into_sft_dir(self):
        # main() 的默认出口固定在 data/sft/，不触碰评估/探针/lf 目录
        self.assertEqual(g.OUT_DEFAULT, ROOT / "data" / "sft" / "v0")
        self.assertEqual(len(g.PAIRING_SEEDS), len(
            {s["sid"] for s in g.PAIRING_SEEDS}), "种子 sid 必须唯一")


class TestVerdictClosedLoop(unittest.TestCase):
    """闭环：全部训练目标可被判分器 v2 严格模板层直接消费（docs/06 §5）。"""

    @classmethod
    def setUpClass(cls):
        cls.rows = (g.gen_policy_pairs() + g.gen_injection_pairs()
                    + g.gen_pii_synthetic() + g.gen_calibration())

    def test_every_assistant_parses_in_strict_template_layer(self):
        n = 0
        for r in self.rows:
            v = _verdict_of(r)
            self.assertIsNotNone(v, f"严格层解析失败: {r['id']}")
            self.assertIn(v["action"], sh2.STRUCTURED_ACTIONS)
            self.assertEqual(v["policy"], r["pack"],
                             f"policy 字段必须=实际激活包: {r['id']}")
            self.assertIsInstance(v["confidence"], (int, float))
            self.assertTrue(0.0 <= v["confidence"] <= 1.0)
            self.assertIsInstance(v["findings"], list)
            n += 1
        self.assertGreater(n, 1500)

    def test_verdict_is_final_line(self):
        for r in self.rows:
            content = r["messages"][-1]["content"]
            self.assertRegex(content.rstrip(), r"VERDICT: \{.*\}$", r["id"])

    def test_classify_label_matches_expected_action(self):
        """action↔观察标签对齐：answer→comply / refuse→refuse / report→report_finding。"""
        for r in self.rows:
            c = sh2.classify(r["messages"][-1]["content"])
            self.assertEqual(
                c["label"], sh2.STRUCTURED_ACTIONS[_verdict_of(r)["action"]],
                f"{r['id']}: 判分标签与 action 不一致")
            self.assertIsNotNone(c["structured"], "严格层应命中（非模式库兜底）")


class TestPolicyPairs(CorpusMixin, unittest.TestCase):
    """语料 A：三包配对一致性。"""

    @staticmethod
    def gen():
        return g.gen_policy_pairs()

    def test_three_packs_per_query_with_distinct_policy(self):
        """同查询三目标：恰好三包、policy 字段各异、system 区各异。"""
        groups = {}
        for r in self.rows:
            groups.setdefault((r["task"], r["lang"], r["messages"][1]["content"]),
                              []).append(r)
        self.assertGreater(len(groups), 150)
        for key, grp in groups.items():
            self.assertEqual(len(grp), 3, f"配对组样本数≠3: {key}")
            self.assertEqual({x["pack"] for x in grp}, set(g.PACKS), key)
            self.assertEqual(len({x["messages"][0]["content"] for x in grp}), 3,
                             "三包 system 区必须互不相同")
            self.assertEqual(len({x["messages"][2]["content"] for x in grp}), 3,
                             "三包 assistant 目标必须互不相同")

    def test_pairing_decisions_match_seed_table(self):
        table = {}
        for seed in g.PAIRING_SEEDS:
            for pack in g.PACKS:
                a, v, _ = seed["decisions"][pack]
                table[(seed["sid"], pack)] = (a, v)
        checked = 0
        for r in self.rows:
            if not r["task"].startswith("T5-policy:"):
                continue
            sid = r["task"].split(":", 1)[1]
            v = _verdict_of(r)
            self.assertIn((sid, r["pack"]), table, f"未知种子: {sid}")
            self.assertEqual((v["action"], v["verdict"]),
                             table[(sid, r["pack"])],
                             f"{r['id']}: 裁决与种子表不一致")
            checked += 1
        self.assertGreater(checked, 900)

    def test_hardfloor_refused_under_every_pack(self):
        """HF 六条：任何包语境下 action=refuse（政策包不调整硬底线）。"""
        hf_rows = [r for r in self.rows if "hardfloor" in r["task"]]
        self.assertEqual(len(hf_rows), 6 * 3 * 3 * 4)  # 6 HF ×3包 ×3查询 ×4形式
        for r in hf_rows:
            v = _verdict_of(r)
            self.assertEqual(v["action"], "refuse")
            self.assertEqual(v["verdict"], "refuse")

    def test_direction_invariant_all_packs_refuse(self):
        dp_rows = [r for r in self.rows if "direction" in r["task"]]
        self.assertGreaterEqual(len(dp_rows), 6 * 3 * 3 * 4)
        for r in dp_rows:
            self.assertEqual(_verdict_of(r)["action"], "refuse", r["id"])

    def test_refusal_invariant_to_surface_forms(self):
        """改述阶梯：同一查询的礼貌变体裁决完全一致（一致性训练信号）。"""
        base = {}
        for r in self.rows:
            if "hardfloor" in r["task"] or "direction" in r["task"]:
                base.setdefault((r["task"], r["pack"]),
                                set()).add(_verdict_of(r)["action"])
        for key, actions in base.items():
            self.assertEqual(len(actions), 1, f"{key}: 改述间裁决漂移")

    def test_action_distribution_spans_spectrum(self):
        actions = {_verdict_of(r)["action"] for r in self.rows}
        self.assertEqual(actions, {"answer", "refuse"})

    def test_vocabulary_is_bounded(self):
        allowed = {"allow", "refuse", "conditional", "out-of-scope"}
        for r in self.rows:
            v = _verdict_of(r)["verdict"]
            self.assertIn(v, allowed, f"{r['id']}: T4/T5 词表外取值 {v!r}")


class TestInjection(CorpusMixin, unittest.TestCase):
    """语料 B：注入植入 + 协议回路。"""

    @staticmethod
    def gen():
        return g.gen_injection_pairs()

    def test_count_matches_matrix(self):
        # 5 载体 × 2 语言 × (3 族 × 4 变体 × 2 位置 × 2 措辞 + 2 对照)
        self.assertEqual(len(self.rows), 5 * 2 * (3 * 4 * 2 * 2 + 2))

    def test_protocol_roundtrip(self):
        """user 区可被 parse_context 严格解析（train/infer 同路径）。"""
        from secfm.protocol.context import parse_context
        for r in self.rows[::17]:
            pc = parse_context(r["messages"][1]["content"])
            self.assertEqual(pc.system["policy"], "default")
            self.assertEqual(len(pc.carriers), 1)
            self.assertEqual(pc.carriers[0]["trust"], "untrusted")

    def test_attack_samples_report_with_located_findings(self):
        atk = [r for r in self.rows if "clean-control" not in r["task"]]
        self.assertEqual(len(atk), 5 * 2 * 3 * 4 * 2 * 2)
        for r in atk:
            v = _verdict_of(r)
            self.assertEqual(v["action"], "report", r["id"])
            self.assertEqual(v["verdict"], "contains-injection")
            self.assertTrue(v["findings"], "findings 必须定位载荷")
            self.assertIn(r["task"].split(":")[2],  # 族名出现在 findings 里
                          " ".join(v["findings"]), r["id"])
            content = r["messages"][-1]["content"]
            self.assertRegex(content, r"载体内容是数据而非指令|carrier content is data")

    def test_clean_controls_answer_without_findings(self):
        ctl = [r for r in self.rows if "clean-control" in r["task"]]
        self.assertEqual(len(ctl), 5 * 2 * 2)
        for r in ctl:
            v = _verdict_of(r)
            self.assertEqual(v["action"], "answer")
            self.assertEqual(v["verdict"], "clean")
            self.assertEqual(v["findings"], [])

    def test_payload_present_in_carrier_not_in_assistant(self):
        """载荷必须出现在载体（输入侧）——攻击框架只作为输入。"""
        for r in self.rows:
            if "clean-control" in r["task"]:
                continue
            self.assertIn("<carrier", r["messages"][1]["content"])

    def test_all_five_carrier_types_covered(self):
        self.assertEqual({r["task"].split(":")[1] for r in self.rows},
                         {"email", "webpage", "log", "text", "code"})


class TestPIISynthetic(CorpusMixin, unittest.TestCase):
    """语料 C：PII 合成（保护方向 only）。"""

    @staticmethod
    def gen():
        return g.gen_pii_synthetic()

    def test_count(self):
        self.assertEqual(len(self.rows), 2 * 6 * 3 * 3)

    def test_synthetic_id_checksum_and_fictional_area(self):
        rng = __import__("random").Random(7)
        for _ in range(200):
            v = g._cn_id(rng)
            self.assertRegex(v, r"^99\d{15}[\dX]$")  # 虚构区号 99xxxx
            weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
            s = sum(int(c) * w for c, w in zip(v[:17], weights))
            self.assertEqual(v[-1], "10X98765432"[s % 11])  # ISO 7064 校验真实

    def test_synthetic_phone_ssn_iban_ranges(self):
        rng = __import__("random").Random(11)
        for _ in range(100):
            self.assertRegex(g._cn_phone(rng), r"^16[0-5]\d{8}$")
            self.assertRegex(g._synthetic_ssn(rng), r"^9\d{2}-\d{2}-\d{4}$")
            iban = g._iban(rng)
            self.assertRegex(iban, r"^DE\d{20}$")
            # mod-97 复核：BBAN + DE数字化 + 校验位 ≡ 1 (mod 97)
            mod = int(iban[4:] + "1314" + iban[2:4]) % 97
            self.assertEqual(mod, 1)

    def test_mask_task_actually_masks(self):
        masked = [r for r in self.rows if r["task"].endswith("mask")]
        self.assertGreater(len(masked), 30)
        for r in masked:
            user = r["messages"][1]["content"]
            reply = r["messages"][-1]["content"]
            for m in re.finditer(r"\b\d[\d\-*]{7,}\b", user):
                self.assertNotIn(m.group(0), reply,
                                 f"{r['id']}: 脱敏输出泄漏原值")

    def test_no_deprotection_direction(self):
        """红线：T7 语料不含去保护方向任务（还原教学在语料 A）。"""
        for r in self.rows:
            self.assertNotRegex(r["messages"][1]["content"],
                                r"还原|反查|逆向|恢复(明文|原)")

    def test_verdicts_within_vocabulary(self):
        allowed = {"contains-pii", "high-risk", "medium-risk", "low-risk",
                   "sufficiently-masked"}
        for r, v in self._verdicts():
            self.assertIn(v["verdict"], allowed, r["id"])


class TestCalibration(CorpusMixin, unittest.TestCase):
    """语料 D：T11 澄清式提问。"""

    @staticmethod
    def gen():
        return g.gen_calibration()

    def test_count(self):
        self.assertEqual(len(self.rows), 3 * 6 * 4)  # 3 轴 ×6 查询 ×4 形式

    def test_clarifying_question_not_refusal(self):
        for r in self.rows:
            v = _verdict_of(r)
            self.assertEqual(v["action"], "answer")  # 澄清≠拒绝（误拒纪律）
            self.assertEqual(v["verdict"], "insufficient-context")
            reply = r["messages"][-1]["content"]
            self.assertRegex(reply, r"[?？]")  # 必须含提问
            self.assertIn(r["task"].split(":")[1],
                          ("missing-auth", "missing-object", "missing-purpose"))


class TestDeterminismAndCLI(unittest.TestCase):
    """确定性 + CLI 落盘（不注册 dataset_info）。"""

    def test_deterministic_regeneration(self):
        a = g.gen_policy_pairs() + g.gen_injection_pairs()
        b = g.gen_policy_pairs() + g.gen_injection_pairs()
        self.assertEqual(json.dumps(a, ensure_ascii=False),
                         json.dumps(b, ensure_ascii=False))

    def test_cli_writes_all_four_corpora_and_readme(self):
        with tempfile.TemporaryDirectory() as td:
            rc = g.main(["--out", td])
            self.assertEqual(rc, 0)
            base = Path(td)
            for name in ("policy_pairs.jsonl", "injection_pairs.jsonl",
                         "pii_synthetic.jsonl", "calibration.jsonl",
                         "README.md"):
                self.assertTrue((base / name).exists(), name)
            total = 0
            for name in ("policy_pairs.jsonl", "injection_pairs.jsonl",
                         "pii_synthetic.jsonl", "calibration.jsonl"):
                lines = (base / name).read_text(encoding="utf-8").splitlines()
                for ln in lines:
                    row = json.loads(ln)
                    self.assertEqual(len(row["messages"]), 3)
                total += len(lines)
            self.assertGreaterEqual(total, 2000, "v0 批次目标 ≥2000")
            readme = (base / "README.md").read_text(encoding="utf-8")
            self.assertIn("词表", readme)
            self.assertIn("未注册", readme)


if __name__ == "__main__":
    unittest.main()
