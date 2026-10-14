# -*- coding: utf-8 -*-
"""把"needle 每格 ≥16"的证据等级从「源码声称」升级为「报告实测」，追加到 S0 状态报告。"""
from pathlib import Path

p = Path("reports/s0-measurement-layer-status.md")
t = p.read_text(encoding="utf-8")
assert "needle 每格 ≥16 —— 证据升级" not in t, "已追加过"

BLOCK = """
---

## 附：objective①‑6「needle 每格 ≥16」—— 证据升级（2026-09-30 晚，父代理实测）

**升级原因**：本表第 6 行原先的依据是**源码注释**（`probe_longctx.py:46` 声称"8 深度 × 2 变体 = 16/格"），
**不是实测**。这是本项目今晚反复吃亏的同一类问题（把"代码声称"当成"事实"）。
现用 `scripts/check_needle_cell_counts.py` **从报告明细现算每一格**（不读注释）：

口径（实测所得）：`needle[length][lang][f"{depth}#{variant}"] = {code, success, insert_pos, …}`
⇒ **格 = (length × lang)**，每格试次数 = 深度数 × 变体数。

| 报告 | 格数 | 最小格 | 总试次 | needle | 每格≥16 |
|---|---|---|---|---|---|
| `longctx-base` / `c1-full` / `m16` / `stage1-202m`（**扩容前**） | 4 | **3** | 12 | — | ✗ |
| `longctx-m15` | 4 | **16** | 64 | 0.672 | ✓ |
| `longctx-m25full` | 4 | **16** | 64 | 0.875 | ✓ |
| `longctx-m2calib` | 4 | **16** | 64 | 0.609 | ✓ |
| `longctx-m2calib-needlefix-e1` | 4 | **16** | 64 | 0.938 | ✓ |
| `longctx-soup-a020 / a035 / a050 / a065 / a080` | 4 | **16** | 64 | .703/.734/**.812**/.891/.938 | ✓ |

**结论**：①‑6 **达成** ✓，且现在是**实测**证据：
- 扩容后 **10 份报告全部 16/格 × 4 格 = 64**；逐格明细如 `16384/en=16 16384/zh=16 32768/en=16 32768/zh=16`；
- 扩容前的 4 份仍是 **3/格 = 12** ⇒ 证明**历史未被静默覆盖**（旧 12 试次报告按
  `scripts/remeasure_needle64.ps1` 的设计归档于 `reports/legacy-needle12/`，且原文件仍在）；
- 顺带复核：`soup-a050` 的 `needle_success = 52/64 = 0.812` 与本项目其它处记录**逐位一致** ✓。

> **仍待办的同类项**：该仪器的**部署格式口径**（raw → chat）尚未重测（本文 §三，GPU 受阻）。
> 即：本附验证的是**格数与试次数**，**不是**口径合规性。§三 §四 的缺口仍然存在。
"""
p.write_text(t.rstrip() + "\n" + BLOCK, encoding="utf-8")
print(f"✅ 已追加；报告行数 = {len(p.read_text(encoding='utf-8').splitlines())}")
