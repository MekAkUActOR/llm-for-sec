r"""RLVR 工具链测试：分量式奖励 + 可验证任务生成器。

覆盖：分量已知答案 / 组合行为 / 防黑不变量（格式满分但行为错净负分）/
GRPO 适配器契约 / 任务真值自洽 / 实例级新鲜（与 SFT 8-gram 重叠阈值）/
隔离红线扫描。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import rlvr_reward as rr  # noqa: E402
from gen_rlvr_tasks import (  # noqa: E402
    CARRIER_BUILDERS, GENS, POLICY_CASES, RLVR_PAYLOADS, gen_tasks,
)
import gen_sft_v0 as g0  # noqa: E402

# ------------------------------------------------------------ 构造工具 --------
def _vline(action, verdict, confidence=0.9, findings=("发现",), policy="default"):
    return ("VERDICT: " + json.dumps(
        {"action": action, "verdict": verdict, "confidence": confidence,
         "findings": list(findings), "policy": policy}, ensure_ascii=False))


INJ_TASK = {"task_type": "inj_detect", "ground_truth": {
    "verdict": "contains-injection", "action": "report",
    "locate": ["c2", "尾部"]}}
POL_TASK = {"task_type": "policy_ruling", "ground_truth": {
    "verdict": None, "action": "refuse",
    "actions": {"conservative": "refuse", "default": "refuse",
                "professional": "answer"}}}


class TestRewardComponents(unittest.TestCase):
    """单分量已知答案。"""

    def test_verdict_parse_bands(self):
        body = "逐段核对完毕，详见下方判定。"  # ≥8 字符：不触发短正文折
        full = body + "\n" + _vline("report", "contains-injection")
        self.assertEqual(
            rr.reward(full, INJ_TASK)["components"]["verdict_parse"], 1.0)
        # 字段瑕疵（policy 缺失）→ 0.6
        flawed = body + "\nVERDICT: " + json.dumps(
            {"action": "report", "verdict": "contains-injection",
             "confidence": 0.9, "findings": ["x"]}, ensure_ascii=False)
        self.assertEqual(
            rr.reward(flawed, INJ_TASK)["components"]["verdict_parse"], 0.6)
        # JSON 残缺但 action 可恢复 → 0.3
        broken = body + "\nVERDICT: {\"action\": \"report\", ???"
        self.assertEqual(
            rr.reward(broken, INJ_TASK)["components"]["verdict_parse"], 0.3)
        # 无 VERDICT → 0
        self.assertEqual(
            rr.reward("直接回答，无判定行。", INJ_TASK)
            ["components"]["verdict_parse"], 0.0)

    def test_verdict_parse_degenerate_caps_zero(self):
        # 正文退化（长游程重复）+ 完整 VERDICT = 刷格式 → parse 0
        degenerate = ("载体 载体 载体 载体 载体 载体 载体 载体 载体 载体 "
                      "载体 载体\n" + _vline("report", "contains-injection"))
        self.assertEqual(
            rr.reward(degenerate, INJ_TASK)["components"]["verdict_parse"],
            0.0)

    def test_verdict_parse_short_body_capped(self):
        # 正文过短（<8 字符）+ 完整 VERDICT：格式在但无推理 → 打六折
        short = "好的。\n" + _vline("report", "contains-injection")
        c = rr.reward(short, INJ_TASK)["components"]
        self.assertAlmostEqual(c["verdict_parse"], 0.6)

    def test_verdict_correct_known_answers(self):
        ok = "定位到 c2 尾部的注入语句，已按流程上报处置。\n" + _vline(
            "report", "contains-injection", findings=("c2 尾部 注入",))
        self.assertEqual(
            rr.reward(ok, INJ_TASK)["components"]["verdict_correct"], 1.0)
        # 裁决对但未定位 → 0.5
        noloc = "发现存在注入迹象，建议人工复核。\n" + _vline(
            "report", "contains-injection", findings=("存在注入",))
        self.assertEqual(
            rr.reward(noloc, INJ_TASK)["components"]["verdict_correct"], 0.5)
        # 裁决错 → -1
        wrong = "未见异常。\n" + _vline("answer", "clean")
        self.assertEqual(
            rr.reward(wrong, INJ_TASK)["components"]["verdict_correct"], -1.0)
        # 有真值但无可判读裁决 → -1
        self.assertEqual(
            rr.reward("完全无格式的回答文本若干字。", INJ_TASK)
            ["components"]["verdict_correct"], -1.0)
        # 无真值（policy_ruling）→ None
        self.assertIsNone(
            rr.reward("回答。\n" + _vline("refuse", None, findings=()),
                      POL_TASK)["components"]["verdict_correct"])

    def test_policy_compliance(self):
        # 结构化匹配
        ok = "按政策包要求处置如下，不予执行。\n" + _vline(
            "refuse", None, findings=())
        self.assertEqual(
            rr.reward(ok, POL_TASK, "default")
            ["components"]["policy_compliance"], 1.0)
        # professional 包期望 answer，结构化 refuse → -1
        self.assertEqual(
            rr.reward(ok, POL_TASK, "professional")
            ["components"]["policy_compliance"], -1.0)
        # 无结构化软路径：拒绝语言 + 期望 refuse → 0.5
        soft = "我不能协助这个请求，请走正式授权通道。"  # 无 VERDICT
        self.assertEqual(
            rr.reward(soft, POL_TASK, "default")
            ["components"]["policy_compliance"], 0.5)
        # 无期望 → None
        self.assertIsNone(
            rr.reward("任意回答。\n" + _vline("answer", None, findings=()),
                      {"ground_truth": {}})
            ["components"]["policy_compliance"])

    def test_action_consistency(self):
        # 一致：正文拒绝语言 + VERDICT refuse
        agree = "我无法协助该请求。\n" + _vline("refuse", None, findings=())
        self.assertEqual(
            rr.reward(agree, POL_TASK)["components"]["action_consistency"], 1.0)
        # 冲突：正文作答 + VERDICT refuse
        conflict = ("好的，步骤如下：第一步检查配置，第二步执行变更，"
                    "第三步回滚验证。\n" + _vline("refuse", None, findings=()))
        self.assertEqual(
            rr.reward(conflict, POL_TASK)["components"]["action_consistency"],
            -1.0)
        # 无结构化 → None
        self.assertIsNone(
            rr.reward("我不会处理。", POL_TASK)
            ["components"]["action_consistency"])

    def test_length_prior_bands(self):
        # 变体填充（重复同一词块会触发退化检测——那是 length_prior
        # 的本职惩罚，此处测纯长度带）
        # 高多样性自然句池（字符多样性 ≥6%——避免误触退化检测的坍缩线）
        sents = [
            "值班记录显示夜间有一次异常登录尝试，来源地址与历史基线不符。",
            "复核人员建议先确认工单状态再决定是否推进下一步处置动作。",
            "口径文档第三版把留痕要求从二十四小时延长到七十二小时。",
            "台账里新增了三条外部协作条目，均附有对应的审批编号。",
            "巡检脚本在上一个窗口捕获到两次阈值越界，回溯结论为误报。",
            "批注区域留有前任负责人的签字，扫描件已归档到备份盘。",
            "抽检样本覆盖五个业务单元，覆盖率和上季度相比略有提升。",
            "值守交接清单包含九项待办，其中两项需要跨部门协调跟进。",
            "基线快照生成完毕，哈希值已写入防篡改日志并同步给审计方。",
            "回溯分析确认告警源自测试流量，无需启动应急响应流程。",
            "清单更新后要重新走一次评审，预计两个工作日内可以完成。",
            "载体解析模块升级到新版后，误判率下降约三成，详见周报。",
            "供应商回函确认第二批设备将于周五前送达，验收安排在下周二。",
            "应急联系人表新增了两位 backup，手机与邮箱均已登记进系统。",
            "季度演练复盘指出三处改进点，分别涉及流程、工具和培训层面。",
            "权限申请单编号 APP-2049 已获三级审批，生效范围限测试环境。",
            "缓存节点切换完成后，延迟指标回落到正常水位，持续观察中。",
            "合同扫描件共 37 页，关键条款已由法务同事标注并反馈结论。",
            "白名单调整涉及 4 个 IP 段，变更窗口定在业务低谷时段执行。",
            "数据源接口昨晚出现两次超时，重试机制按预期自动恢复正常。",
            "培训签到实到 45 人，缺席者将在下周参加补训场次，材料已发。",
            "风险评估矩阵更新后，中危项从 12 项收敛到 9 项，详见附件。",
            "跨区同步任务耗时比上个月增加 8%，初步判断与链路扩容有关。",
            "审计抽样比例维持在 5%，今年上半年未发现重大不符合项。",
        ]

        def body_of(n_chars):
            out, i = [], 0
            while sum(len(s) + 1 for s in out) < n_chars:
                out.append(sents[i % len(sents)])
                i += 1
            text = " ".join(out)
            return text[:n_chars] + "\n" + _vline(
                "answer", None, findings=())
        for n, want in [(20, 1.0), (150, 1.0), (3000, 1.0), (10, 0.5),
                        (5000, 0.5), (5, 0.0)]:
            self.assertEqual(
                rr.reward(body_of(n), {"ground_truth": {}})
                ["components"]["length_prior"], want, msg=f"len={n}")


class TestRewardCombination(unittest.TestCase):
    """组合行为 + 权重覆盖 + None 归一。"""

    def test_perfect_response(self):
        # 正文使用可识别的报告语言（判分器 v2 模式库命中——一致性分量
        # 依赖正文语言可判读）
        resp = ("检测到注入载荷：c2 尾部被植入机审通道备注，试图固定审查"
                "结论。建议中止自动化处理并转人工复核，已按流程登记。\n"
                + _vline("report", "contains-injection",
                         findings=("c2 尾部 注入",)))
        r = rr.reward(resp, INJ_TASK, "default")
        self.assertEqual(r["total"], 1.0)

    def test_weights_override(self):
        resp = "好。"
        r0 = rr.reward(resp, {"ground_truth": {}}, weights={
            "verdict_parse": 0.0, "verdict_correct": 0.0,
            "policy_compliance": 0.0, "action_consistency": 0.0,
            "length_prior": 1.0})
        self.assertEqual(r0["total"], 0.0)  # 只有长度分量，短答 → 0

    def test_none_renormalization(self):
        # policy_ruling：verdict_correct=None 不适用，其余分量照常加权归一
        resp = "我无法协助该请求。\n" + _vline("refuse", None, findings=())
        r = rr.reward(resp, POL_TASK, "default")
        self.assertIsNotNone(r["total"])
        self.assertGreater(r["total"], 0.5)
        self.assertIsNone(r["components"]["verdict_correct"])

    def test_total_bounded(self):
        for resp in ["", "VERDICT: {}", "好", "x" * 9000]:
            r = rr.reward(resp, INJ_TASK)
            self.assertGreaterEqual(r["total"], -1.0)
            self.assertLessEqual(r["total"], 1.0)


class TestAntiGamingInvariant(unittest.TestCase):
    """防黑：格式满分但行为错必须净负分。"""

    def test_weight_inequality(self):
        fmt_sum = sum(rr.DEFAULT_WEIGHTS[k] for k in rr.FORMAT_COMPONENTS)
        self.assertGreater(
            rr.DEFAULT_WEIGHTS["verdict_correct"], fmt_sum,
            "verdict_correct 权重必须大于可凭格式满足的分量之和")

    def test_format_perfect_behaviour_wrong_is_negative(self):
        """格式全满 + 裁决错 → total < 0（policy 分量亦不适用时最保守）。"""
        task_no_policy = {"task_type": "inj_detect", "ground_truth": {
            "verdict": "contains-injection", "action": "report",
            "locate": ["c2", "尾部"]}}  # 无 actions/action 期望 → policy None
        gaming = ("经全面复查，本材料各项指标均在正常范围内，可以安全归档，"
                  "无需进一步处置，建议按标准流程继续后续环节处理即可。\n"
                  + _vline("answer", "clean"))
        r = rr.reward(gaming, task_no_policy)
        self.assertEqual(r["components"]["verdict_parse"], 1.0)
        self.assertEqual(r["components"]["length_prior"], 1.0)
        self.assertEqual(r["components"]["action_consistency"], 1.0)
        self.assertEqual(r["components"]["verdict_correct"], -1.0)
        self.assertLess(r["total"], 0.0, "格式满分但裁决错必须净负分")

    def test_gaming_sweep(self):
        """对抗扫描：多类刷格式响应在含真值任务上均不得为正。"""
        gts = [
            INJ_TASK,
            {"task_type": "pii_discover", "ground_truth": {
                "verdict": "contains-pii", "action": "answer",
                "locate": ["9983"]}},
        ]
        games = [
            "一切正常，无任何需要关注的事项，请按既定流程归档处理即可。\n"
            + _vline("answer", "clean"),
            "经检查未发现个人身份数据，可以直接进入下一环节。\n"
            + _vline("answer", "clean", findings=()),
        ]
        for gt in gts:
            for g in games:
                self.assertLess(
                    rr.reward(g, gt)["total"], 0.0,
                    msg=f"刷格式响应不应得正分: {g[:30]}")


class TestGRPAdapter(unittest.TestCase):
    """TRL 0.24 RewardFunc 契约。"""

    def _cols(self, rows):
        return ([r["reward_task_json"] for r in rows],
                [r["reward_pack"] for r in rows])

    def test_string_completions(self):
        rows = gen_tasks(6)
        tj, tp = self._cols(rows)
        comps = [("看起来一切正常可以归档。\n" + _vline("answer", "clean"))
                 for _ in rows]
        out = rr.grpo_reward_func(comps, reward_task_json=tj, reward_pack=tp)
        self.assertEqual(len(out), len(rows))
        self.assertTrue(all(isinstance(x, float) for x in out))

    def test_conversational_completions(self):
        rows = gen_tasks(3)
        tj, tp = self._cols(rows)
        comps = [[{"role": "assistant", "content":
                   "未见异常，可归档。\n" + _vline("answer", "clean")}]
                 for _ in rows]
        out = rr.grpo_reward_func(comps, reward_task_json=tj, reward_pack=tp)
        self.assertEqual(len(out), 3)

    def test_missing_metadata_none(self):
        out = rr.grpo_reward_func(["回答文本"], reward_task_json=[None],
                                  reward_pack=["default"])
        self.assertEqual(out, [None])
        out2 = rr.grpo_reward_func(["回答文本"])  # 无元数据列
        self.assertEqual(out2, [None])

    def test_weights_column(self):
        rows = gen_tasks(2)
        tj, tp = self._cols(rows)
        wj = [json.dumps({"verdict_parse": 0.0, "verdict_correct": 0.0,
                          "policy_compliance": 0.0, "action_consistency": 0.0,
                          "length_prior": 1.0}), None]
        comps = ["短。\n" + _vline("answer", "clean")] * 2
        out = rr.grpo_reward_func(comps, reward_task_json=tj, reward_pack=tp,
                                  reward_weights_json=wj)
        self.assertEqual(out[0], 0.0)  # 只剩长度分量，短正文 → 0
        self.assertNotEqual(out[0], out[1])  # 第二个用默认权重


class TestGenTasks(unittest.TestCase):
    """任务流真值自洽 + 契约 + 新鲜值。"""

    def test_determinism(self):
        a = gen_tasks(40, seed=123)
        b = gen_tasks(40, seed=123)
        self.assertEqual(a, b)
        c = gen_tasks(40, seed=124)
        self.assertNotEqual(a, c)

    def test_gt_consistency_inj(self):
        rows = [r for r in gen_tasks(200)
                if r["task_type"] == "inj_detect"]
        self.assertGreater(len(rows), 20)
        n_pos = 0
        for r in rows:
            gt, user = r["ground_truth"], r["messages"][1]["content"]
            payloads = [p for lang in RLVR_PAYLOADS.values()
                        for ps in lang.values() for p in ps]
            has_payload = any(p in user for p in payloads)
            if gt["verdict"] == "contains-injection":
                n_pos += 1
                self.assertTrue(has_payload, r["id"])
                self.assertTrue(gt["locate"][0].startswith("c"), r["id"])
                self.assertIn(gt["locate"][1], ("头部", "中段", "尾部",
                                                "head", "middle", "tail"))
            else:
                self.assertFalse(has_payload, r["id"])
                self.assertEqual(gt["action"], "answer")
        self.assertGreater(n_pos, 10)  # 注入正例充足

    def test_gt_consistency_pii(self):
        rows = [r for r in gen_tasks(200)
                if r["task_type"] == "pii_discover"]
        self.assertGreater(len(rows), 20)
        for r in rows:
            user = r["messages"][1]["content"]
            self.assertEqual(r["ground_truth"]["verdict"], "contains-pii")
            for prefix in r["ground_truth"]["locate"]:
                self.assertIn(prefix, user, r["id"])

    def test_gt_consistency_carrier(self):
        rows = [r for r in gen_tasks(100)
                if r["task_type"] == "carrier_classify"]
        for r in rows:
            self.assertIn(r["ground_truth"]["verdict"], CARRIER_BUILDERS)
            self.assertEqual(r["ground_truth"]["action"], "answer")

    def test_gt_consistency_policy(self):
        rows = [r for r in gen_tasks(200)
                if r["task_type"] == "policy_ruling"]
        self.assertGreater(len(rows), 20)
        valid = {"answer", "refuse", "report"}
        n_divergent = 0
        for r in rows:
            acts = r["ground_truth"]["actions"]
            self.assertEqual(set(acts), {"conservative", "default",
                                         "professional"})
            self.assertTrue(all(a in valid for a in acts.values()), r["id"])
            if len(set(acts.values())) > 1:
                n_divergent += 1
        # 聚合断言：裁决用例中包间分歧占足够比例（分歧=核心训练信号；
        # 三包同拒=硬地板/流程不满足，同答=pack 无关任务，均合法少数）
        self.assertGreater(n_divergent / len(rows), 0.3)
        # 用例表自检：全部三包动作合法
        for case in POLICY_CASES:
            self.assertEqual(len(case), 4)
            self.assertTrue(case[0] and case[1])

    def test_row_contract(self):
        for r in gen_tasks(30):
            self.assertEqual(len(r["messages"]), 2)
            self.assertEqual(r["messages"][0]["role"], "system")
            self.assertEqual(r["messages"][1]["role"], "user")
            # system 提示 = 政策包契约（设计内共享）
            self.assertEqual(
                r["messages"][0]["content"],
                g0.POLICY_SYSTEM[r["policy_pack"]][r["lang"]])
            # reward 列回读
            self.assertEqual(json.loads(r["reward_task_json"])[
                "task_type"], r["task_type"])
            self.assertEqual(r["reward_pack"], r["policy_pack"])
            self.assertIn(r["lang"], ("zh", "en"))

    def test_value_freshness_across_runs(self):
        a = gen_tasks(60, seed=1)
        b = gen_tasks(60, seed=2)
        va = {r["messages"][1]["content"] for r in a
              if r["task_type"] == "pii_discover"}
        vb = {r["messages"][1]["content"] for r in b
              if r["task_type"] == "pii_discover"}
        self.assertFalse(va & vb, "不同 seed 的 PII 文档应值级全新")


class TestFreshness(unittest.TestCase):
    """实例级新鲜：与 SFT 语料的规范化 8-gram 连续共享游程 < 阈值。

    房屋口径（check_sft_contamination.py）：真复制信号 = ≥40 连续 gram；
    功能词/搭配噪声 < 40。此处锁 30（含余量）。索引侧 = v0/v0x 全量
    自建（同族基础设施，最高风险）+ SFT train 抽样；两侧均跳过 system
    （政策包文本为设计内共享契约）。
    """
    LONGEST_RUN_MAX = 30
    _idx = None

    @classmethod
    def setUpClass(cls):
        from check_sft_contamination import normalize, ngrams
        grams = set()
        sft_root = ROOT / "data" / "sft"
        for sub in ("v0", "v0x"):
            for p in sorted((sft_root / sub).glob("*.jsonl")):
                for line in p.read_text(encoding="utf-8").splitlines():
                    d = json.loads(line)
                    for m in d["messages"][1:]:
                        grams.update(ngrams(normalize(m["content"])))
        train = sft_root / "m1" / "train.jsonl"
        if train.exists():
            with train.open(encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i % 199:
                        continue
                    d = json.loads(line)
                    for m in d["messages"][1:]:
                        grams.update(ngrams(normalize(m["content"])))
        # 注意：plain function 存类属性经实例访问会变绑定方法（描述符
        # 协议）——必须 staticmethod 包装
        cls._idx = grams
        cls._ng = staticmethod(ngrams)
        cls._norm = staticmethod(normalize)

    def test_longest_shared_run_below_threshold(self):
        worst = 0
        for r in gen_tasks(300):
            best = cur = 0
            for g in self._ng(self._norm(r["messages"][1]["content"])):
                cur = cur + 1 if g in self._idx else 0
                best = max(best, cur)
            worst = max(worst, best)
        self.assertLessEqual(
            worst, self.LONGEST_RUN_MAX,
            f"与 SFT 共享 8-gram 连续游程超阈值（实测 {worst}，"
            f"真复制信号线 40）")


class TestIsolationScan(unittest.TestCase):
    """隔离红线：两脚本源码零评估资产字面量。"""

    FORBIDDEN = ("data/heldout", "data\\heldout", "data/probes",
                 "data\\probes", "ais-500", "tc260", "m2-reference",
                 "tool_output")

    def test_no_eval_literals(self):
        for name in ("rlvr_reward.py", "gen_rlvr_tasks.py"):
            src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
            for lit in self.FORBIDDEN:
                self.assertNotIn(lit, src, f"{name} 含隔离字面量 {lit!r}")


if __name__ == "__main__":
    unittest.main()
