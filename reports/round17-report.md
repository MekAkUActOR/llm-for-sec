# 第 17 轮报告：两次自我更正、一个静默损坏、以及 DPO 诊断的**降级**

**时间**：2026-10-06 18:56–19:10。**状态**：512 口径重测跑批中（18:57:41 起，worker 约 14 分钟）。

**★ 本轮的产出主要是"把错的诊断改对"**，不是新读数。以下四件事按"对我自己论断的修正幅度"排序。

---

## 一、★★★ 我把"一条健康评测链"误读成"两个评测抢 GPU"，并据此杀掉了它

### 1.1 我做了什么

看到进程表里有 **2 个 `python.exe` 匹配 `baseline_eval.py`**，我判定
"两个评测在抢同一块 GPU、写同样的产物名 ⇒ 读数互相污染" ✗，
**杀掉了当时已运行 13 分钟的健康跑批**，并清理了产物 ✗。

### 1.2 真因：Windows venv 的 trampoline 会让一次调用产生**两个** python

```
pid=21796 powershell   94 MB  recaliber_mnt.ps1 -MaxNewTokens 512        ← launcher
 └38584 powershell     92 MB  eval_needlefix.ps1 …                        ← 子脚本
   └31236 python         4 MB  baseline_eval.py …                          ← trampoline
     └29920 python    1962 MB baseline_eval.py …                           ← 唯一真 worker
```

- `venv\Scripts\python.exe` 在 Windows 上是 **uv 的 trampoline** ⇒
  **一次调用 = 2 个 `python.exe`**（~4 MB 薄壳 + ~2 GB 真 worker）✗
- launcher 还会**调用子脚本 powershell** ⇒ 一条健康单链同时命中 **4–5 个进程** ✗

**⇒ "2 个 python"完全不能推断"跑了 2 份任务"** ✗。
判据应是**重 worker 数**（工作集 > 模型量级）**与 GPU 占用**，**不是模式串匹配数** ✓。

**★ 代价**：13 分钟 GPU 时间（产物在末尾写盘 ⇒ 未丢数据 ✓）。
**★ 教训已固化**：新增 **docs/01 §11.37 规则 38** +
把 `scripts\stop_eval_procs.ps1` 改造成**取证式**工具（`-Tree` 打印父子链与工作集、
`-Guard` 按重 worker 数判定），并把判据写进输出，**使误判无法悄悄发生** ✓。

## 二、★ 互斥锁：真并发确实该防，而且已实证会开火

虽然上一节那次是误判，但"两次手工发射 ⇒ 写同样产物名"是**真会发生的** ✓。
`recaliber_mnt.ps1` 现在有锁文件 + 活 pid 校验 + 陈旧锁回收 ✓，
并发预检**按规则 38 用重 worker 数**（否则会把自己链上的 trampoline 误计而永远拒启 ✗）。

**★实证**（不是"代码看着对"）：同时发第二次 ⇒
```
[18:58:02] ★★拒绝启动：已有 launcher 在跑（pid=21796，锁 .recaliber-512.lock）
第二次 rc=3  （期望 3）
```

## 三、★★★ 一个**静默损坏**：`scripts\audit` 被 Python 当成 BEL 吃掉

我在**非 raw** 字符串里写 PowerShell 路径 `scripts\audit_dpo_nonlength_signal.py`，
`\a` 被解释成 **BEL(\x07)** ✗ ⇒ 写进 runbook 成了 `scriptsudit_dpo_nonlength_signal.py` ✗✗
—— **用户照抄会直接失败** ✓。

**★ 关键：Python 早就用 `SyntaxWarning: "\P" is an invalid escape sequence` 警告我了，我差点当噪声忽略** ✗。
（`\P` 不是合法转义 ⇒ 原样保留，相对无害；但 `\a` 是**合法**转义 ⇒ 真的被吃掉 ✗✗）

**⇒ 已产出 `scripts\scan_escape_damage.py`**：
- **通用还原**：BEL→`\a`、BS→`\b`、VT→`\v`、FF→`\f`（正好复原被吃掉的字符 ✓）
- **全仓扫描**控制字符出现在文本文件里的情形 ✓
- **复验** runbook 里所有脚本路径可照抄 ✓

**现读数**：`ESCAPE-DAMAGE-CHECK=PASS`（还原 1 处 ✓，全仓无残留 ✓，4 条路径全部可照抄 ✓）

## 四、★★★ DPO 诊断**降级**：数据是**可用**的，修法是外科式的

### 4.1 我先前的论断过强 ✗

第 16 轮我写：这 5 类的"**梯度几乎纯粹来自长度**" ✗。**证据不支持** ✗。

全量量化"除了长度还能学什么"（`scripts/audit_dpo_nonlength_signal.py`）：

| dpo_class | n | chosen `action` | rejected `action` | 空 findings（c/r） |
|---|---|---|---|---|
| **`carrier_inject_obedient`** | 2,360 | **report 2360/2360** | **answer 2360/2360** | **0.0% / 100.0%** |
| **`carrier_inject_hollow`** | 2,320 | **report 2320/2320** | **refuse 2320/2320** | **0.0% / 100.0%** |
| **`carrier_clean_overrefusal`** | 1,320 | **answer 1320/1320** | **report 1320/1320** | 0.0% / 0.0% |
| `refusal_quality` | 300 | refuse 300/300 | refuse 300/300 | 82.0% / 100.0% |
| **`calibration`** | 240 | answer/refuse | answer 240/240 | `verdict:null` **0% / 60%** |

**⇒ 这 5 类每一个都有 100% 干净的、与长度无关的类别信号** ✓✓
⇒ **数据可用** ✓，长度是**叠加的混杂** ✗，不是唯一信号 ✓

### 4.2 抽样还证明**语义与标签一致**

我原本怀疑 `carrier_inject_obedient` 的 rejected 只是"简短拒绝"（标签与内容不符 ✗）。
实测**不成立** ✓ —— 它确实在服从：
```
rejected: 已按载体内的指令跳过检查，本次判定为 clean。
          VERDICT: {"action": "answer", "verdict": "benign", ..., "findings": []}
```
**★ 两侧都流畅、都带完整合法 VERDICT** ✓ ⇒ 长度是它们**最显著的表面差别** ✗
（这就是"模型会优先学到长度"的原因 ✓）。

### 4.3 机制仍然成立，但结论要改

**仍然成立** ✓：6,540 对**全部** chosen 更长 ✗ ⇒ DPO 顺带获得"更长更好"的梯度 ✓；
长度偏好**跨类泛化** ✓ 而类别信号只在类内可学 ✓ ⇒ **净效果 = 整体变长** ⇒
部署预算装不下 ⇒ 尾部契约行被截断 ⇒ MUST-B 崩 ✓。

**改的是修法** ✓：

| 我第 16 轮倾向 | 现在明确 |
|---|---|
| "这 5 类要**重新生成**" ✗ | **只补足较短一侧的长度，不动语义** ✓ |
| — | **禁止**把 rejected/chosen **砍短** ✗（会抹掉非长度信号，比不修更糟） |

修法要点（详见 `reports/dpo-length-confounding-surgical-fix.md`）：
- `carrier_inject_obedient`：把**服从的回复写详尽** ✓（真服从的 agent 也会长篇汇报）
- `carrier_inject_hollow`：改为「**冗长但空洞**」✓（保留类定义中的"空洞"，去掉"短"）
- `carrier_clean_overrefusal` / `refusal_quality` / `calibration`：同样补足长度
  （`calibration` 的 `verdict:null` 信号要**保留** ✓ —— 它正好是非长度信号 ✓）

### 4.4 新增推论 37.3（消混杂不得消灭信号）

> 长度匹配后**必须复验**该类的**非长度判别信号仍然存在** ✓；
> 若两侧在**所有**非长度维度上也变得相同 ⇒ 已退化为"纯长度对" ✗ ⇒ **禁止入训**。
> **落地**：`audit_dpo_nonlength_signal.py` 须对每类给出**至少一个**分离度 ≥0.95 的非长度维度 ✓。

已落 docs/01（1,578 行）并接进 runbook 步骤 2.0c 作为**第四道检查** ✓。

## 六、★★★ 本轮的两个实质产出（跑批进行中已可用）

### 6.1 512 口径的**首个实测**：截断率从 ~68% 降到 **1.2%**

```
resp-chat-gen-soup-a050-mnt512.jsonl
  行数=258   字段=完整   token_ids=OK
  finish_reason = {'stop': 255, 'length': 3}   max_new_tokens=512
  ★截断率 = 3/258 = 1.2%
```

**⇒ 对"预算设错"这一诊断的决定性验证** ✓：
- 历史 96 口径：约 **68%** 响应被截断 ✗（`append_truncation_proof.py` 记录）
- 512 口径：**1.2%** ✓

**★ 且 `token_ids=OK`** ✓ ⇒ `derive_budget_curve.py` 的"一次 512 跑批导出整条曲线"
设计**可行且已验证** ✓（该字段若缺，一整次跑批就白跑 —— 第 15 轮差点如此 ✗）。

### 6.2 ★★★ 外科式长度匹配已完成并**通过复验**

`scripts/length_match_dpo.py` 对 `dpo_m3_final.jsonl` 的 **5 类 / 6,540 对**做：
**逐字保留原 VERDICT**（⇒ `action`/`findings` 等非长度信号**由构造保证不变** ✓），
**只在其前补足同义详尽散文** ✓；chosen 侧**完全不动** ✓；
输出新文件 **`data/lf/dpo_m4_final.jsonl`**（`dpo_m3_final.jsonl` **未被覆盖** ✓，
sha256 前 16 位 `c272ff9d0f858398`、28,842 行 ✓）。

**★ 长度匹配前后**（token 中位）：

| dpo_class | chosen | rej 前 | 比前 | **rej 后** | **比后** | 判定 |
|---|---|---|---|---|---|---|
| `carrier_inject_obedient` | 210 | 51 | 4.12 | **206** | **1.02** | ✓ |
| `carrier_inject_hollow` | 210 | 43 | 4.88 | **222** | **0.95** | ✓ |
| `carrier_clean_overrefusal` | 160 | 110 | 1.45 | **168** | **0.95** | ✓ |
| `refusal_quality` | 57 | 45 | 1.27 | **63** | **0.90** | ✓ |
| `calibration` | 71 | 45 | 1.58 | **72** | **0.99** | ✓ |

**★ 四道门的读数**：

| 门 | dpo_m3_final | **dpo_m4_final** |
|---|---|---|
| `AUDIT-DPO-LENGTH`（规则 37） | **FAIL** 5 类 / 6,540 对 ✗ | **PASS 0 对** ✓ |
| 非长度信号（推论 37.3） | 信号齐全 ✓ | **逐项完全相同** ✓ |

**★★ 但我先犯了一个错并自我抓到**：第一版长度匹配把目标写成单边
（"加到 ≥ 目标就停"）⇒ 整句粒度**系统性冲过头** ✗ ⇒ 比值落到 **0.84**
（rejected **比 chosen 更长**）⇒ **会把长度偏置反向成"越短越好"** ✗✗，
而**我当时的单边判据却报了 PASS** ✗✗。

**⇒ 两处修正**：
1. `pad_to` 改为在"加第 k 句"的各候选中取**与目标 token 长度最接近者** ✓
2. **规则 37 的判据改为双边** ✓：正向 `比>1.2 且 chosen更长>80%` ✗、
   反向 `比<0.82 且 chosen更长<20%` ✗ —— 两个方向**都是偏置** ✓

**⇒ 修完：最差比 1.02** ✓，`m4` 全类干净 ✓。
（并记录一处**边界**：`bt330_refusal` 比 0.71、chosen 更长 21.5%，
仅以 1.5pp 之差未触发反向判据 ⇒ 属**临界**，下次发射前应一并复核 ✓。）

### 6.3 ★ m4 的落位：**不放进活目录 `data/lf/`**（校验器替我抓到了）

我最初把 `dpo_m4_final.jsonl` 写在 `data/lf/` ✓ —— 结果
**`CARRIER-ONTOLOGY-CHECK` 立刻从 `errors=0` 变成 `errors=7`** ✓：

```
train_rows_mismatch:text:lf_total        ontology=27076  computed=28624  (+1548)
train_rows_mismatch:email:lf_total       ontology=10484  computed=12122  (+1638)
train_rows_mismatch:log:lf_total          ontology=4713   computed=5713   (+1000)
train_rows_mismatch:webpage:lf_total      ontology=5607   computed=6607   (+1000)
train_rows_mismatch:code:lf_total         ontology=4718   computed=5718   (+1000)
train_rows_mismatch:document:lf_total     ontology=5200   computed=6200   (+1000)
train_rows_mismatch:tool_output:lf_total  ontology=5624   computed=6724   (+1100)
```

**★ 诊断**：`lf_total` 定义为 `data/lf/*.jsonl`（通配）✓ ⇒ 新增一份就抬高它 ✓。
而 **m4 是 m3 的"版本替代"**（同一份数据、同样 28,842 行 ✓）⇒ **两者并列会把"总数"变成版本累加** ✗。

**★★ 但真正的错在更前面：`data/lf/` 是**活训练文件**目录** ✓
（`sft_m25` / `sec_sft_needlefix` / `dpo_m3_final`），
把**尚未发射的候选数据**放进去会**污染活目录** ✗ —— 而本项目对这种情况**早有既定模式**
（`data/sft/m2.5-staging/` ✓）。

**⇒ 改为落位 `data/dpo-remediation-staging/dpo_m4_final.jsonl`** ✓
（暂存区在**三个扫描范围之外** ✓ ⇒ 不抬高 `lf_total` ✓、不动 `live_lineage` ✓、
不需改 ontology ✓）。

**★★ 并且说明了为什么这不是"规避审计"** ✓：
**m4 尚未被任何训练消费** ✓ ⇒ 它**本就不属于训练语料** ✓ ⇒ 不入账是**正确的记账** ✓，
而不是把问题藏起来 ✓。

**★ 复验**：`CARRIER-ONTOLOGY-CHECK=PASS errors=0` ✓（且**未改一个字**的 ontology ✓ ——
反证"移出活目录"才是正解 ✓）；暂存区未被任何范围纳入 ✓；
长度门对暂存路径复验 `AUDIT-DPO-LENGTH=PASS` ✓。

**★★★ 一个待决策的问题（关系泛化声明，我不擅自改 ✗）**

`live_lineage`（"**被活产物消费的训练文件并集**"，覆盖矩阵 train 列的依据 ✓）现含
`dpo_m3_final.jsonl` ✓。严格说：**M3 已判定 FAIL、不进交付谱系** ⇒ `dpo_m3_final`
已**不再**属于活谱系 ✗。但**现在就把它移出** ⇒ 会在**替代版本尚未训练**前先改变
**载体暴露基准** ✗ ⇒ **提前动摇留出集泛化声明** ✗。

**⇒ 我的建议（纪律性做法）**：**现在不动** ✓，待**重开 M3 发射的那一刻**用
`dpo_m4_final` **替换**（而非并列 ✗）`dpo_m3_final` ✓。

### 6.4 ★★★ 512 预算的决定性读数（soup-a050 三集全完成）

| 集（heldout 仪器） | 行数 | `finish_reason` | **截断率 @512** | 历史 @96 |
|---|---|---|---|---|
| v0.3-gen（`chat-gen-`） | 258 | stop 255 / **length 3** | **1.2%** | ~68% ✗ |
| v0.2.1（`chat-`） | 161 | stop 158 / **length 3** | **1.9%** | ~68% ✗ |
| v0.4-toolout（`chat-to-`） | 70 | stop 70 / length 0 | **0.0%** | ~68% ✗ |
| **合计** | **489** | stop 483 / **length 6** | **1.2%** | **~68%** ✗ |

**⇒ 预算诊断被实测完全证实** ✓✓：把部署生成预算从 96 提到 **512**，
截断率从约 **68%** 降到 **1.2%** ✓。

**★ 这是"M3 失败机制 = 部署预算装不下响应 ⇒ 尾部契约行被截断 ⇒ MUST-B 崩塌"
的最强证据** ✓ —— 而不是"契约设计错了" ✗，也不是"数据不可用" ✗。

**★ 并且 `token_ids=OK` 在 489 条上全部成立** ✓ ⇒
`derive_budget_curve.py` 可由这一批 512 数据**离线导出** 96/128/192/256/384/512
整条预算曲线（贪心前缀确定性 ✓），**与实跑逐 token 等价** ✓。

## 七、状态与下一步

**跑批**：512 口径 18:57:41 起 ✓ 健康单链 ✓；v0.3-gen 已完成（258 条 ✓），
正在跑 v0.2.1 → toolout → 再 m3-dpo ⇒ 预计约 20:50 结束 ✓。

**M3 重开的前置条件**：
1. ✅ 数据侧唯一阻塞项（长度混杂）**已修并通过复验**
2. ⏳ 512 完整曲线（`derive_budget_curve.py`）→ 定正式部署预算
3. ⏳ `dpo_m4_final.jsonl` 需**登记**（ontology / manifest / 训练配置）
4. ⏳ 四道门对新配置全 PASS 后再发射

**★ 目标保持 active**（objective ④ 未完成）。

```
CARRIER-ONTOLOGY-CHECK=PASS   SYSPATH-HYGIENE=PASS     RUNBOOK-GATES=PASS
STAGING-MANIFEST=PASS         DOCUMENT-GATE-CHECK=PASS  ESCAPE-DAMAGE-CHECK=PASS
FIX-PS1-BOM=PASS              VERDICT-96-REGRESSION=PASS（第 16 轮）
```

**四道门**（2.0 规则 33 / 2.0c 规则 37 + 37.3 / 2.0b 规则 36）：
- `AUDIT-DPO-AXES` = **PASS** ✓
- `AUDIT-DPO-LENGTH` = **FAIL**（5 类 / 6,540 对）✗ ← **唯一的数据侧阻塞项**
- `AUDIT-DPO-NONLENGTH-SIGNAL` = **信号齐全** ✓（数据可用 ✓）
- `AUDIT-S1-TRAINING` = FAIL（长度；预算对齐到 512 即解 ✓）

**512 跑批**：18:57:41 起 ✓ 健康单链 ✓ 无并发 ✓；预计 ~110 分钟（约 20:50）⇒ 本轮不结束 ✓。

**★ 目标保持 active**：objective ④ 仍待——512 曲线 → 定正式预算 →
**外科式长度匹配** → 四道门全 PASS → 发射 M3。
