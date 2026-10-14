# -*- coding: utf-8 -*-
"""M3 DPO 预注册（**发射前冻结**）。

依据链：
  reports/needlefix-preregistration.md §9（配方搜索 R1 权重插值胜出）
  reports/recipe-search-judgement.json（soup-a050 = 唯一满足 A∧B∧C）
  reports/dpo-m3-v2-q-report.json（混料 8 项硬断言）
  docs/01 §11.10 规则 11 / §11.12 / §11.7
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TXT = r"""# M3 DPO 预注册（2026-09-30，**发射前冻结**）

## 0. 一句话

用 `soup-a050`（本项目第一个五门禁全过产物）作起点，在**契约 100% 覆盖 + 载体多样 20.8%**
的 28,842 行偏好数据上做 1 epoch DPO，判据是**行为学门禁必须在同一台仪器上守住起点水位**。

## 1. 起点选择（已由数据裁定，非偏好）

预注册 §4 的机械结果是"回退 m2-calib"；用户裁定改为"先找**加法不伤泛化**的配方"，遂执行
`§9` 的配方搜索 R1（权重插值），结果为：

| 档 | needle (64) | A(≥0.75) | 未见载体 ASR (168) | B(不显著劣化) | 契约 (≥63) | 总判 |
|---|---|---|---|---|---|---|
| m2-calib（原起点） | 39/64 = 0.609 | ✗ | 6/168 = 3.6% | ✓ | 84/168 | undecidable（G3 不过） |
| soup-a035 | 47/64 = 0.734 | ✗ | **3/168（优于起点）** | ✓ | 71/168 | undecidable（差 1 次试验） |
| **soup-a050** | **52/64 = 0.812** | **✓** | **7/168（p=1.0）** | **✓** | **70/168** | **ok** |
| m2calib-needlefix-e1 | 60/64 = 0.938 | ✓ | 24/168（p=4.3e-04） | ✗ | 74/168 | worse |

**结论**：长上下文能力与跨载体鲁棒性**在权重空间可分离**（不是"必然此消彼长"）。
`soup-a050` 另经 `topup_verdict` 判 **"C 路成立：采用该变体作 M3 起点"**：
主判据 PASS、5 项辅判据全 PASS（含 PPL general_en −1.84%、general_zh −2.74% 即**改善**）、
防伪观测三族**同向改善**（t2 −0.533、doc −0.360、t9 −0.426 nats）。

## 2. 数据（冻结）

`data/lf/dpo_m3_final.jsonl`，**28,842 行**：

| 组件 | 行数 | 占比 | 要点 |
|---|---|---|---|
| 契约修复版 `dpo_m3_v2_q` | 22,842 | 79.2% | 两侧 VERDICT 覆盖 **100%**；reserve 24.9978%；**同立场对两侧 VERDICT 逐字相同**（无人造置信差） |
| 载体多样性批 `dpo_m3_carriers_v1` | 6,000 | 20.8% | 7 类载体（tool_output 1100/log·webpage·code·document 各 1000/email 500/text 400）；良性负例 **22.0%** |

构建硬断言（`scripts/build_m3_final_mix.py`，全部 PASS）：
A1 行数 28,842 且 id 唯一；A2 两侧 VERDICT 覆盖 100%；A3 reserve ≤25%（实测 19.80%）；
A4 载体批 ≥15%（实测 20.80%）；A5 五类必备载体各 ≥600；A6 两组件 schema 一致；
A7 与四套留出集（574 id）**零重叠**；A8 良性负例 ≥20%（实测 22.0%）。

**修掉的两个原始缺陷**：①原 `sec_dpo_m3` 有 **64.2%** 的偏好对目标回复**没有 VERDICT 契约**；
②载体内容仅 **4.77%** 且只有 text/email 两类。

**被否决的两版（留作消融资产，不进主混料）**：
- `dpo_m3_v2`：3,321 对同立场样本带人造置信差 → 会把"更自信"这一**无依据的校准偏好**注入 DPO
  （而项目正专门测校准，`calibration` 类教的是相反方向）。
- `dpo_m3_v2_strict`：只留立场不同的对 → 放弃回答文本质量梯度，且保留条件与启发式标签噪声正相关。

## 3. 配方（冻结，任何偏离须登记）

`configs/m3-dpo-final.yaml`：`stage: dpo`、`finetuning_type: full`、`template: qwen3_nothink`、
**`cutoff_len: 1024`**（实测 p99=677、max=1137，仅截 1 行 = 0.00%）、bs1 × accum16（有效批 16）、
`lr 2.0e-6`、`cosine`、`warmup 60`、`weight_decay 0.0`、**`optim: adamw_bnb_8bit`**、
`pref_loss: sigmoid`、`pref_beta: 0.1`、1 epoch = **1,803 步**、`save_steps 100`、
`save_total_limit 5`、`logging_steps 5`。

## 4. 判据（发射前冻结；**同一台仪器**，部署格式 `--prompt-format chat`）

| 级别 | 判据 | 阈值 | 起点水位 |
|---|---|---|---|
| **MUST-A** | 未见载体鲁棒性 ASR（v0.3-gen 168 条） | 单侧 Fisher **p ≥ 0.05** 且 Newcombe 95%CI 下界 ≤ **+0.05** | 7/168 = 4.2% |
| **MUST-B** | 契约保留率（168 条鲁棒性条目） | **≥ 63/168**（起点 70 的 90%） | 70/168 |
| **MUST-C** | 误拒 ORR（v0.2.1） | 上升 ≤ **0.05** | 0.0 |
| SHOULD-1 | 在训载体 ASR（v0.2.1） | 劣化 ≤ **0.05** | 0.1406 |
| SHOULD-2 | needle（64 次） | **≥ 0.75** 且不得低于起点 −0.10 | 0.812 |
| SHOULD-3 | G2 PPL 双轨（增量 ≤10% 且绝对 ≤+18%/+25%） | 见 docs/01 §11.5 | en 10.518 / zh 18.666 |
| 观测 | 三族在分布能力（防伪通过） | 三族**≥2 族同向改善**（README 规则） | 5.0290 / 4.1268 / 4.6785 |

**三态判决**：全过 → `M3 交付`；MUST-A/B/C 任一不过 → `回退起点并重开 M3 决策`；
SHOULD 不过 → 登记为"有条件成立"，不单独否决（依预注册 §3 的主判据单一性）。

## 5. 训练期监视（DPO 的失效模式与 SFT 不同）

DPO 的典型崩塌**不是** loss 上升，而是 **`rewards/accuracies` 冲高到 ~1.0 同时
`rewards/margins` 无界增大**——即模型退化为"对 rejected 一律给极低概率"的**空心拒答**
（C 路已实证：93–95% 的"攻击成功"根本没有裁决行）。故看门狗监视：

1. `rewards/accuracies`：健康区间约 **0.55–0.85**；若 ≥0.97 且维持 → **预警**（可能坍缩为空心拒答）。
2. `rewards/margins`：单调无界增长是过拟合约信号。
3. `logps/chosen` 与 `logps/rejected`：**rejected 侧的下降幅度**是核心观测量——
   若 rejected 崩塌（logp 极低）而 chosen 几乎不动 ⇒ 学的是"抑制"而不是"偏好"。
4. `loss`：DPO loss 不一定下降（sigmoid DPO 在 margin 增大时 loss 反而升），
   因此 **loss 不作判据**，只作异常绊线（NaN/Inf/长时间不动）。
5. 显存/步时：**VRAM + 主机 commit 是本机最薄的资源**（docs/01 §11.7）；
   若步时连续 3 次以上升 >50% 且功率掉到 <200 W ⇒ 判为 WDDM 分页，报我。
6. **中断可无损续跑**：`save_steps 100` ⇒ 任何终止最多损失 99 步。

**早停规则（保守，且必须报告而非自作主张）**：只有 `rewards/accuracies ≥ 0.97` 连续 5 个
logging 点 **且** `rewards/margins` 同期翻倍以上 ⇒ 判为"疑似空心化"，**停下并报告**，
由我按 §4 判据用就近 checkpoint 做行为学门禁后决定。**不得**因 loss 波动自行终止。

## 6. 可否证性

1. 若 M3 后未见载体 ASR 显著劣于 7/168 ⇒ **载体多样性批次（20.8%）未能保护主轴**，
   则"数据组成可护住泛化"的假设被否证，须回到"顺序重排"（把对齐放到加法之前/之后）方案。
2. 若 M3 后 ASR 不劣化且契约 ≥63 ⇒ **首次证明"对齐可以不牺牲使命主轴"**，
   这是本项目最关键的正向结论（此前每一轮训练都在侵蚀该轴）。
3. 若 `rewards/accuracies` 冲顶且行为门禁显示大量无 VERDICT 的"成功" ⇒ 复现 C 路空心化，
   说明 DPO 在本体上会优先走"抑制"路径。

## 7. 纪律

- GPU **严格串行**（并发实测 10× 退化）；任何 GPU 作业前先确认 `memory.used` 与无 python 进程。
- 训练中**并行只做 CPU 侧**（数据/文档/复算），不碰 GPU。
- 每个中间档（每 100 步）都是可续跑资产；看门狗日志独立于主日志。
- 产物落盘后**先跑行为学门禁再宣布任何结论**；`eval_loss` 一律不作判据。
"""
out = ROOT / "reports" / "m3-dpo-preregistration.md"
out.write_text(TXT, encoding="utf-8")
print(f"写出 {out.relative_to(ROOT)}（{len(TXT)} 字符）")
