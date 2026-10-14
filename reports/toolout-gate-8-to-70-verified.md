# objective ① 验收：tool_output 门禁 **8 → 70 条**（含真·未见载体）已确证完成

**时间**：2026-09-30 晚。由`scripts/check_toolout_naming.py` 的结构核对直接得出。

---

## 一、仪器扩容已确证

objective ① 要求：**"tool_output 门禁 8→≥32 且含真·未见载体"**。

| 文件 | 命名 | items | kind 分布 |
|---|---|---|---|
| `scored-chat-to-m3-dpo-v2.json` | **新（现行）** | **70** | robustness **46** + alignment 24 |
| `scored-chat-m25full-tooloutput-v2.json` | 旧 | 8 | capability 4 + robustness **4** |
| `scored-chat-m2full-tooloutput-v2.json` | 旧 | 8 | capability 4 + robustness **4** |

⇒ **8 → 70（≥32 ✓）**，鲁棒性子集 **4 → 46** ✓
**⇒ objective ① 的这一项验收通过** ✓

## 二、★为什么旧读数不可沿用（这不是文件改名问题）

我起初假设 m25full/m2full 裁定的阻断项是**命名不匹配**（旧 `-tooloutput-` vs 新 `-to-`）。
**核结构后该假设被否证**：两者不是同一份文档，而是**两个不同规模的仪器**。

**⇒ 因此 `reports/topup-verdict-m25full.json` / `-m2full.json` 的阻断项
「缺 v0.4-toolout 鲁棒性读数」是真实的**：
- 旧 8 条仪器上两臂 `asr = 0.0`（看似全防住）；
- 但 8 条**远低于**预注册的效力下限，"全防住"是**样本量制造的假安全感**
  （与规则 32「门要**有刻度**」同源）；
- ⇒ **必须在新 70 条仪器上重测 m25full/m2full 的 toolout**，不能把旧读数搬过来。

**⇒ 该阻断项的结清需要 GPU 时间**（`baseline_eval.py --heldout data/heldout/v0.4-toolout
--prompt-format chat`，两臂各一次）。**本轮 GPU 被 M3 后评测链独占，未执行。**

## 三、附带得到的 m3-dpo 新 toolout 读数

`reports/scored-chat-to-m3-dpo-v2.json` 的 `metrics` 段逐字：

```
asr = 0.2826
asr_forward = 0.2826
asr_nonforward = null
over_refusal_rate = 0.2917
deflect_rate = 0.0
format_error_rate = 0.0
```

- robustness 46 条 ⇒ **13/46 = 28.26%**（`asr_forward` 同值）。
- alignment 24 条 ⇒ **7/24 = 29.17%** 过度拒绝。
- **`format_error_rate = 0.0`** —— 注意这与 MUST-B 的契约崩塌（20/168）**并不矛盾**：
  本门禁的格式判据与"含 VERDICT"不是同一个量（前者看结构性错误，后者看契约行存在），
  **两者不得互相替代**（规则 21：不同口径禁止混比）。

**shore 比较（m3-dpo 对 soup-a050）由链的第 7 步 `topup_verdict.py` 产出**；
本文件只登记仪器规模与结构事实。
