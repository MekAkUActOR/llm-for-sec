# 第 24 轮报告：全长跑在飞 + 配比「先量后修」否决 + objective ② 阻断项定性

**日期**：2026-10-06。**全长跑**：`configs/m4-capfix-full.yaml`（1,803 步 / 1 epoch ✓，预计 ~88 分钟 ✓，21:34 起 ✓）

> ## ⚠️⚠️⚠️ 顶部更正横幅（2026-10-14 追加）—— 请先读本节再看 §二
>
> **本报告 §二 的核心结论「方向性过半（53.6%）⇒ 判别信号不构成瓶颈 ⇒ 否决改配比」
> 已被推翻/修正** ✗✓——这是「**多数 ≠ 有效**」陷阱：方向性度量**忽略了 39.4%
> 梯度质量是纯风格对** ✗，且全混料 `VERDICT:` 标记对比度实测 = **0.00%**
> （标记轴零梯度信号 ✗）。
>
> **见 `reports\retrospective-41.md`**：§一#2（时间线审计对本结论判「错 ✗，
> 此错直接塑造了 M4 的错误设计」）+ §二①（标记对比度审计）+ §三（修法轴修订：
> rebal 对 MUST-B 无效，损失函数/预算轴才对症）。
>
> **★ §二 保留为过程记录** ✓（**不得删 ✗——错误本身是证据 ✓**），但
> **不得被引用为结论** ✗✓；本报告其余各节（全长跑发射/objective ②③ 定性）未被动摇 ✓。

---

## 一、★★★★★★ 本轮主体：发射**全长跑**（最大残留风险的验证 ✓）

**★ 为什么这是最后一道闸**：第 23 轮探针只到 **300 / 1,803 步 = 1/6 epoch** ✓，
而 M3 的病态**在 1,803 步末最重**（`rewards/rejected` −12.46 ✗）
⇒ **「1/6 epoch 无病态」不能推出「全程无病态」** ✗✓。

**★★ 配方与 M3 逐点可比** ✓：超参**逐字相同** ✓，`num_train_epochs: 1` ⇒ 自然得到 **1,803 步** ✓（与 M3 同步数 ✓）。

**★★★ 可证伪预测（已写进配置注释 ✓）**：
- **`rewards/chosen` 应全程保持 +1 以上** ✓（M3 只有 **+0.34** ✗）
- **若末段 chosen 掉回 ~0 且 rejected 独降到 −10 以下** ✗ ⇒ **过优化全程重现** ✗ ⇒ **capfix 不足，须改配比** ✓

**★★★★ 进度（21:35）**：训练中 ✓（GPU 16.5 GB / 55% ✓），日志在变长 ✓，首个 checkpoint 在 100 步 ✓。
**守望 agent `8dddbb93` 已派** ✓（★已明确告知它**看不到父会话的 job** ✗，必须靠读日志+查进程 ✓）。

## 二、★★★★★ 配比度量：**先量后修，结果是否决** ✓（本轮最重要的判断 ✓）

**★ 起因**：第 23 轮发现 `policy` 族占 **50.9%** 对数 / **30.3%** 梯度质量 ✓，且 **76.4% 逐对动作相同** ✗
⇒ 疑为「政策条件化稀释安全判断」✗ —— **本能反应是改配比** ✗。

**★★ 我先量**（`scripts/action_directionality.py` ✓，**方向性对 = chosen 动作 ≠ rejected 动作** ✓）：

| 类 | n | 中性对占比 | 方向质量 ✓ | 中性质量 ✗ |
|---|---|---|---|---|
| `policy` | 14,688 | **76.4%** | 616,652 | 1,935,076 |
| `reserve` | 5,710 | **69.9%** | 717,113 | 1,900,960 |
| `carrier_inject_obedient` | 2,360 | **0%** ✓ | **880,196** ✓ | 0 |
| `carrier_inject_hollow` | 2,320 | **0%** ✓ | **927,294** ✓ | 0 |
| `bt330_refusal` | 1,904 | 0.5% | **917,289** ✓ | 4,052 |
| `carrier_clean_overrefusal` | 1,320 | **0%** ✓ | **446,595** ✓ | 0 |
| `refusal_quality` | 300 | **100%** ✗ | **0** ✗ | 45,546 |
| `calibration` | 240 | 60% | 16,640 | 24,192 |

**★ 总盘子（28,842 对 ✓）**：**动作方向性质量 = 53.6%** ✓ / 中性 = 46.4% ✗

**★★★ 裁决：★否决改配比** ✗** ✓
- **方向性过半（53.6% ✓）⇒ 判别信号不构成瓶颈** ✓
- **中性质量由 `policy`(49.1%) + `reserve`(48.2%) 构成** ✓ —— **它们教**格式/细节** ✓，不必然有害** ✓
- **按推论 42.4：不得据此动手改数据** ✗
- **病根已被第 22–23 轮因果钉在 `report`-as-rejected 压制** ✓，**不是配比** ✓

**★★★★ 本轮因此**省下了一次高风险数据改动** ✓ —— 这就是「先量后修」的价值 ✓✓。**
（★ 若我当时直接删掉 11,216 条中性对 ✗，会同时破坏格式/细节能力 ✗ 且**无从归因** ✗。）

**★ 仅登记为线索** ✓：`refusal_quality` 300 对 **100% 动作中性** ✗（真正零信号 ✓，量小 ✓）。

## 三、★★★★★ objective ②：阻断项**定性为真缺失**，不是命名问题 ✗

**★ 线索**：仓库里有 `scripts/check_toolout_naming.py` ✓，其自述是
「若结构一致 ⇒ m25full/m2full 的『缺 toolout』阻断项系**命名不匹配**，而非数据缺失」✓。

**★★ 实测（本轮 ✓，`scored-chat-*tooloutput-v2.json` 与 `scored-chat-to-m3-dpo-v2.json` 并列核）**：

| 产物 | 条目数 | kind 分布 |
|---|---|---|
| `scored-chat-to-m3-dpo-v2.json`【**新命名**】 | **70** ✓ | robustness **46** / alignment 24 ✓ |
| `scored-chat-m25full-tooloutput-v2.json`【旧】 | **8** ✗ | capability 4 / robustness **4** ✗ |
| `scored-chat-m2full-tooloutput-v2.json`【旧】 | **8** ✗ | capability 4 / robustness **4** ✗ |

**★★★ 结构**不一致**** ✗ —— 旧命名只有 **8 条** ✓，
**正是 objective ① 里「tool_output 门禁 8→≥32」要替换掉的那个 8 条旧仪器** ✓✓

**⇒ m25full/m2full **从未在新 70 条仪器上评测过**** ✗ ⇒ **阻断项是真数据缺失** ✓
**⇒ 完成 objective ② 必须**在新仪器上重跑它们**（GPU 工作 ✓，本轮 GPU 被全长跑占用 ✗）。**

**★ 附带**：objective ① 的「≥32 且含真·未见载体」✓ —— 新仪器鲁棒性 **46 条 ≥ 32** ✓；
但 `tool_output` **是**在训载体**** ✗ ⇒ **「真·未见载体」须由 `v0.5-toolout-reg/carrier_extra.jsonl`（载体拓宽层 ✓）承担** ✓，**不得**把 toolout 轴说成未见载体泛化（规则 24 ✓）。

## 四、★★★★ objective ③ 现状：named 交付物**都已有产物** ✓

| 项 | 产物 |
|---|---|
| document 载体 | `docs/08-carrier-ontology.md` ✓、训练 1,000+ 行 ✓、`v0.6-document` 门已登记 ✓ |
| 结构/行为层样本 | `s1-three-families-structural-audit.md` ✓ |
| T2 机制解释族 | `reports/t2-mechanism-gen-stats.json` ✓ |
| T9 扩容 | `reports/t9-phish-expand-stats.json` ✓ |
| manifest 结账 | `reports/staging-manifest-reconciliation.md`（26.6 KB ✓）、`carrier-ontology-report.md` ✓ |
| 本体论裁决 | `s1-ontology-adjudication.md` ✓、`s1-ontology-items-verification.md` ✓ |

**★ 回归核查**：`CARRIER-ONTOLOGY-CHECK=PASS errors=0` ✓、`STAGING-MANIFEST=PASS` ✓、`DOCUMENT-GATE=PASS` ✓

## 五、★ 本轮结论与下一步

**★★ 已确证（不变）**：capfix 在 1/6 epoch 上 **MUST-A PASS（非劣性 ✓）**、未见代价 ✓

**★★★ 待全长跑回答（唯一未决的关键问题 ✓）**：
**病态是否在 1,803 步重现** ✗ —— **这是发射全量 M4 的最后一道闸** ✓

**★ 下一步（25 轮）**：
1. **读全长跑曲线** ✓ —— 重点看**末段 `rewards/chosen` 是否守住 +1** ✓
2. **在**同一模型**上跑完整门禁集** ✓（needle@chat ✓ + PPL en/zh ✓ + toolout ✓，一次跑齐 ✓）
3. **补 `soup-a050` 的 needle@chat** ✓（裁决需要它 ✓）
4. **重跑 m25full/m2full 于新 70 条仪器** ✓（objective ② ✓）

## 六、★★★★ 已备好「跑完即补齐」的一键门禁脚本 ✓

**★ 产物**：`scripts/gate_m4_full.ps1` ✓（`PS-SYNTAX=PASS` ✓、BOM 已加 ✓ 4397→4400 B ✓）

**★★ 依据（逐条按源码核实 ✓）**：
- `eval_needlefix.ps1` 的**非** `-DecisiveOnly` 路径**一次跑齐**：
  MUST-3/2 v0.3-gen(chat) → MUST-1 needle(`$NeedlePromptFormat`) →
  SHOULD v0.2.1(chat) → SHOULD v0.4-toolout(chat) → SHOULD v0.4 PPL ✓
- 末尾 `Stop-IfFailed 'ALL'` ⇒ **任何一步失败即非零退出** ✓（不再无条件 exit 0 ✓）
- **`-NeedlePromptFormat chat` ⇒ 产出 `reports/longctx-$Tag-chat.json`** ✓
  —— 与 `raw` 的 `longctx-$Tag.json` **不同名** ⇒ **零覆盖** ✓（第 23 轮的 raw 读数**保留** ✓）
- **`-MaxNewTokens 512` ⇒ 产物名带 `-mnt512`** ✓ ⇒ 与 96 历史读数**互不覆盖** ✓
- **脚本对已存在的产物会**跳过**** ✓ ⇒ 用 `-Tag soup-a050` 复跑**只补缺失的 needle@chat** ✓，
  既有 `scored/heldout` 产物**不动** ✓✓

**★★★ 脚本自身先做并发守卫** ✓（`stop_eval_procs.ps1 -Guard` ✓，非 PASS 即 **exit 3 拒跑** ✓，不静默继续 ✓）

**★ 一条运维事实**：训练日志被 `Tee-Object` **独占锁定** ✗ ⇒
**进度只能靠 `checkpoint-N` 目录判** ✓（`Get-Item`/`Get-ChildItem` 可用 ✓，`ReadAllText` 会 IOException ✗）。

## 七、★ 复核路径

```
configs/m4-capfix-full.yaml       ← 全长配方（含可证伪预测 ✓）
reports/logs/m4-capfix-full.log   ← 训练日志（在飞 ✓）
scripts/action_directionality.py  ← §二 方向性度量 ✓
scripts/update_m4_hypothesis_r24.py ← §二 记入 m4-hypothesis.json ✓
reports/m4-hypothesis.json        ← mix_measured_round24 段 ✓
scripts/check_toolout_naming.py   ← §三 命名/结构核查 ✓
```
