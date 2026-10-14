# 第 29 轮报告：门禁集干跑（风险排除）+ 基线 chat needle 已存在

**日期**：2026-10-06 22:20。**全长跑**：`checkpoint-900` / 1,803 ✓（预计 23:15 完成 ✓）。

---

## 一、★★★★★ 干跑 `gate_m4_full.ps1` 的跳过逻辑（**降低 50 分钟后那次运行的风险 ✓**）

**★ 为什么本轮做这件事**：门禁集要跑 ~30 分钟 ✓，**若它的跳过判据有 bug** ✗，
**我会在长跑结束后才发现** ✗✓ ⇒ **先干跑一遍是最便宜的保险** ✓。

**★★ 结果：`m4-capfix-full` 的 6 个产物**全部不存在**** ✓ ⇒ **门禁集会完整跑一遍** ✓（**零覆盖风险 ✓**）

| 产物 | 存在 |
|---|---|
| `heldout-chat-gen-m4-capfix-full-mnt512.json` | False ✓ |
| `scored-chat-gen-m4-capfix-full-v2-mnt512.json` | False ✓ |
| `longctx-m4-capfix-full-chat.json` | False ✓ |
| `scored-chat-m4-capfix-full-v2-mnt512.json` | False ✓ |
| `scored-chat-to-m4-capfix-full-v2-mnt512.json` | False ✓ |
| `ppl-m4-capfix-full-v0.4.json` | False ✓ |

**★★★ 结果二（**省事**）**：`soup-a050` 的 6 个产物**全部已存在** ✓，
**包括 `longctx-soup-a050-chat.json`** ✓✓
⇒ **裁决的「缺 needle 报告（soup-a050，口径 chat）」这个阻断项**本就不是缺的**** ✓
**⇒ `-Tag soup-a050` 复跑会**全部跳过** ✓ ⇒ 等价于 `-SkipBaseline` ✓（两条路都对 ✓）。**

**★ 即：`gate_m4_full.ps1` 的跳过判据与既有产物**逐条吻合** ✓** ⇒ **执行风险已排除 ✓✓**。

**★★ 附核**：`$mnt = if ($MaxNewTokens -eq 96) { '' } else { "-mnt$MaxNewTokens" }` ✓
⇒ 512 时后缀为 `-mnt512` ✓ ⇒ **与 96 的历史读数**互不覆盖** ✓**。

## 二、★★★★ 当前状态（预注册已就位 ✓）

**★ 预注册**：`reports/m4-endpoint-preregistration.md` ✓（8 节 ✓）
- §二 **裁决表**（ASR <15% ⇒ H-A ✓；15~40% ⇒ 都否 ✗；>40% ⇒ H-B ✗）✓
- §三 病态起点实测（三运行同为 200~250 步 ✗）✓
- §四 权重漂移实测（探针 0.00035 ✓ / M3 0.00079 ✗ / 全长 @500 0.00064 ✗）✓
- §七 **漂移-步数曲线** + **漂移-ASR 定量关系** ⇒ **预算 ≈ epoch 0.1** ✓
- §七 **外推警告**（两点定不出曲线形状 ✗ ⇒ **step_scan 必需** ✓）✓

**★★ 工具**：`scripts/step_scan.py` ✓（dry-run 验证 ✓）、`scripts/weight_drift.py` ✓、
`scripts/full_run_curve.py` ✓、`scripts/pathology_onset.py` ✓、`scripts/lr_schedule_check.py` ✓

**★★★ 强预测（本轮结束时仍成立 ✓）**：
**M3 的漂移在 @1500 与 @1803 **相同**（0.00079 ✓，已饱和 ✓），
而全长跑 @700 已 0.00072（91% ✓）⇒ **终点将 ≈0.0008~0.0009** ✗
⇒ **预测 ASR ≈ M3 的 50.6%** ✗ ⇒ **H-B** ✓
**⇒ 若终点 ASR 真的 ≈50%，则 H-B 被**证实**** ✓✓，**预算轴即为唯一出路** ✓。

## 三、★ 下一步（30 轮）

1. **读全长跑终点**（漂移 + 曲线 ✓）
2. **跑 `gate_m4_full.ps1`** ✓ ⇒ 完整门禁集（needle@chat + v0.2.1 + toolout + PPL ✓）
3. **按预注册 §二 的裁决表判 H-A / H-B** ✓（**不得事后改阈值 ✓**）
4. **若 H-B** ⇒ `scripts/step_scan.py` 测 **ASR-步数曲线** ✓ ⇒ **按曲线定预算** ✓
   （**不得用 §七 的两点外推直接定** ✗ —— 它只是**候选** ✓）

## 四、★ 复核路径

```
scripts/gate_m4_full.ps1          ← 跑完一键补齐（干跑已核跳过逻辑 ✓）
reports/m4-endpoint-preregistration.md ← 预注册（判据钉死 ✓）
scripts/weight_drift.py           ← 漂移-步数曲线 ✓
scripts/step_scan.py              ← ASR-步数曲线（H-B 成立时用 ✓）
```
