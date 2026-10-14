r"""gen_sft_v0x 已知答案单测（回填批：现有存量种子，不求全覆盖）。"""
from __future__ import annotations

import json
import random
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sft_v0x as gx  # noqa: E402
import gen_sft_v0 as g0  # noqa: E402

V0X = ROOT / "data" / "sft" / "v0x"


def _last_verdict(it):
    tail = it["messages"][-1]["content"].rsplit("VERDICT: ", 1)[1]
    return json.loads(tail)


class _Contract(unittest.TestCase):
    """全语料结构契约：交替 / 末轮 VERDICT / policy==pack / 非末轮无 VERDICT。"""

    def _check(self, items):
        self.assertTrue(items)
        for it in items:
            msgs = it["messages"]
            self.assertEqual(msgs[0]["role"], "system")
            self.assertEqual(msgs[1]["role"], "user")
            self.assertEqual(msgs[-1]["role"], "assistant")
            for i in range(1, len(msgs) - 1):
                self.assertNotEqual(msgs[i]["role"], msgs[i + 1]["role"])
                if msgs[i]["role"] == "assistant":
                    self.assertNotIn("VERDICT: {", msgs[i]["content"])
            self.assertIn("VERDICT: {", msgs[-1]["content"])
            v = _last_verdict(it)
            self.assertEqual(v["policy"], it["pack"])


class TestPolicyExpansion(_Contract):
    def test_known_answers(self):
        items = gx.gen_policy_expansion()
        self._check(items)
        by_task = {}
        for it in items:
            by_task.setdefault(it["task"], []).append(it)
        # sec-h0-purge：三包同拒（H0 不可逆破坏）
        for it in by_task["T5-policy:sec-h0-purge"]:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "refuse")
        # sec-h4-readquery：三包放行（H4 正样本）
        for it in by_task["T5-policy:sec-h4-readquery"]:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "answer")
            self.assertEqual(v["verdict"], "allow")
        # sec-op-portscan：default=澄清（insufficient-context），ctx 授权后
        # default=conditional——政策条件化信号
        base = by_task["T5-policy:sec-op-portscan"]
        ctx = by_task["T5-policy:sec-op-portscan-auth"]
        self.assertTrue(
            any(_last_verdict(i)["verdict"] == "insufficient-context"
                for i in base if i["pack"] == "default"))
        self.assertTrue(
            any(_last_verdict(i)["verdict"] == "conditional"
                for i in ctx if i["pack"] == "default"))
        # zh 优先：zh 行多于 en
        nzh = sum(1 for i in items if i["lang"] == "zh")
        nen = sum(1 for i in items if i["lang"] == "en")
        self.assertGreater(nzh, nen)
        # 每种子 zh 表面变体（改述阶梯）存在
        zh_h4 = [i for i in base if i["lang"] == "zh"]
        self.assertGreater(len({i["messages"][1]["content"]
                                for i in zh_h4}), 5)

    def test_determinism(self):
        a = gx.gen_policy_expansion()
        b = gx.gen_policy_expansion()
        self.assertEqual(a, b)


class TestT4Grounding(_Contract):
    def test_citation_present(self):
        items = gx.gen_t4a() + gx.gen_t4b()
        self._check(items)
        # 每条 T4 裁决 findings 携带政策条目引用
        for it in items:
            v = _last_verdict(it)
            self.assertTrue(v["findings"], it["id"])
            self.assertRegex(
                v["verdict"],
                "allow|conditional|refuse|answer|insufficient-context")

    def test_t4b_law_citation(self):
        items = gx.gen_t4b()
        self.assertTrue(items)
        for it in items:
            self.assertIn("引用：", it["messages"][-1]["content"])


class TestAttackDict(_Contract):
    def test_refusals_and_pack_consistency(self):
        items = gx.gen_attack_dict()
        self._check(items)
        for it in items:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "refuse")
            self.assertEqual(v["verdict"], "refusal")
            self.assertEqual(it["lang"], "zh")  # zh 主力
        # 31 类目全覆盖
        cats = {i["task"].split("cat:")[1] for i in items}
        self.assertEqual(len(cats), 31)
        # 类目体系零复制红线：源码不含外部数据路径
        src = Path(gx.__file__).read_text(encoding="utf-8")
        for lit in ("m2-reference", "heldout", "probes", "ais-500"):
            self.assertNotIn(lit, src)


class TestT1Injection(_Contract):
    def test_report_action_and_carrier(self):
        items = gx.gen_t1_injection()
        self._check(items)
        atk = [i for i in items if "clean-control" not in i["task"]]
        ctrl = [i for i in items if "clean-control" in i["task"]]
        self.assertTrue(atk and ctrl)
        for it in atk:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "report")
            self.assertEqual(v["verdict"], "contains-injection")
        for it in ctrl:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "answer")
            self.assertEqual(v["verdict"], "clean")
        # 新载荷与 v0 变体集零复用（防跨源去重坍缩）
        v0_payloads = {p for fam in g0.PAYLOADS.values()
                       for p in fam["zh"] + fam["en"]}
        new_payloads = {p for fam in gx.NEW_PAYLOADS.values()
                        for p in fam["zh"] + fam["en"]}
        self.assertFalse(v0_payloads & new_payloads)


class TestT3Risk(_Contract):
    def test_tier_follows_ransomware_flag(self):
        items = gx.gen_t3_risk(limit=40)
        self._check(items)
        for it in items:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "report")
            self.assertIn(v["verdict"], ("critical", "high"))
            # 勒索 Known → critical；否则 high（KEV 全量在野利用）
            blob = it["messages"][1]["content"]
            rw_known = "Known" in blob and "Unknown" not in blob
            self.assertEqual(v["verdict"] == "critical", rw_known)


class TestT9Phish(_Contract):
    def test_verdict_mapping(self):
        items = gx.gen_t9_phish()
        self._check(items)
        for it in items:
            v = _last_verdict(it)
            self.assertIn(v["verdict"], ("phishing", "suspicious", "benign"))
            if v["verdict"] == "benign":
                self.assertEqual(v["action"], "answer")
            else:
                self.assertEqual(v["action"], "report")


class TestT12PolicyQA(_Contract):
    def test_grounded_citation(self):
        items = gx.gen_t12_policyqa()
        self._check(items)
        for it in items:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "answer")
            self.assertEqual(v["verdict"], "grounded")
            self.assertTrue(v["findings"])
        # zh 法规为主
        nzh = sum(1 for i in items if i["lang"] == "zh")
        self.assertGreater(nzh, len(items) - nzh)


class TestT6Code(_Contract):
    def test_detection_side(self):
        items = gx.gen_t6_code()
        self._check(items)
        for it in items:
            v = _last_verdict(it)
            self.assertEqual(v["action"], "report")
            self.assertEqual(v["verdict"], "suspicious-pattern")


class TestPIIExpansion(_Contract):
    def test_three_tasks(self):
        items = gx.gen_pii_expansion()
        self._check(items)
        tasks = {i["task"] for i in items}
        self.assertEqual(tasks, {"T7-pii:discover", "T7-pii:classify",
                                 "T7-pii:mask"})
        # 全合成守卫：真实号段手机号不出现（13/14/15/17/18/19——16 为
        # 虚拟合成段，v0 契约；数字边界锚定防身份证内偶然子串误报）
        blob = json.dumps(items, ensure_ascii=False)
        self.assertNotRegex(blob, r"(?<!\d)(?:13|14|15|17|18|19)\d{9}(?!\d)")


class TestSmuggleMultiturn(_Contract):
    def test_escalation_contract(self):
        items = gx.gen_smuggle_multiturn()
        self._check(items)
        atk = [i for i in items if ":attack:" in i["task"]]
        ans = [i for i in items if ":answer:" in i["task"]]
        self.assertTrue(atk and ans)
        for it in atk:   # 升级轮拒绝即止：末轮 assistant=拒绝+VERDICT
            v = _last_verdict(it)
            self.assertEqual(v["action"], "refuse")
        for it in ans:   # 对照端点：应答收尾
            v = _last_verdict(it)
            self.assertEqual(v["action"], "answer")
        # 多轮真多轮（>3 messages）
        for it in items:
            self.assertGreater(len(it["messages"]), 3)


class TestIsolationScan(unittest.TestCase):
    """红线：生成器源码零评估/探针路径字面量。"""

    def test_no_eval_literals(self):
        src = Path(gx.__file__).read_text(encoding="utf-8")
        for lit in ("data/heldout", "data\\heldout", "data/probes",
                    "data\\probes", "ais-500", "tc260", "m2-reference",
                    "tool_output"):
            self.assertNotIn(lit, src)


class TestAssembledSelfbuiltRows(unittest.TestCase):
    """conv_selfbuilt：v0x 语料 → 行/攻击位映射。"""

    def test_row_mapping(self):
        import assemble_sft_m2 as am
        am._CLF_STATE = {"bundle": None, "loaded": True}
        items = am.conv_selfbuilt(V0X.parent / "v0", V0X)
        src_row = {}
        for it in items:
            src_row.setdefault(it["source"],
                               (it["row"], it["attack"], it["pool"]))
        self.assertEqual(src_row["v0x:policy_expansion"],
                         ("policy_pairs", False, "selfbuilt"))
        self.assertEqual(src_row["v0x:t4_grounding"],
                         ("policy_pairs", False, "selfbuilt"))
        self.assertEqual(src_row["v0x:attack_dict"],
                         ("injection_jailbreak", True, "selfbuilt"))
        self.assertEqual(src_row["v0x:t1_injection"][2], "selfbuilt")
        self.assertEqual(src_row["v0x:smuggle_multiturn"][0], "multiturn")
        # 走私攻击位：task 含 :attack:
        sm = [i for i in items if i["source"] == "v0x:smuggle_multiturn"]
        self.assertTrue(any(i["attack"] for i in sm))
        self.assertTrue(any(not i["attack"] for i in sm))
        # v0 行为不变（回归）
        self.assertEqual(src_row["v0:policy_pairs"][0], "policy_pairs")
        v0inj = [i for i in items if i["source"] == "v0:injection_pairs"]
        self.assertTrue(any(i["attack"] for i in v0inj))
        self.assertTrue(any(i["row"] == "task_single" for i in v0inj))


if __name__ == "__main__":
    unittest.main()
