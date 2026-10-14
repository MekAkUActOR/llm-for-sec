# -*- coding: utf-8 -*-
r"""★★★★★ 转向：查 **M3 DPO 这次 run 本身**（数据侧已排除殆尽 ✗）。

## 为什么转向

数据侧已被逐条排除 ✓：
| 假说 | 结论 |
|---|---|
| 框架漂移 / 长度显著性 / 动作偏好 / 词法化 / 模板多样性 | 全部出局 ✗ |
| 裁决伪造族缺口 | 训练里有 `verdict_suppress` 282 条 ✗ |
| 载体覆盖缺口 | 分布内 51.6% ≈ 分布外 54.8% ✗ |
| 稀释 | 有效信号 45.7%、真抵抗对 **32.6%** ✗ |
| 偏好环 | **环存在 ✓，但按违例代价数据仍应让模型偏好 `report`** ✗ |

**⇒ 数据侧无法解释"偏向了环里最便宜那一项的相反面"** ✗✓
**⇒ 必须查 run：超参、参考模型、训练曲线、checkpoint 选择** ✓。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")


def show(p: Path, n: int = 90) -> None:
    print(f"\n{'='*84}\n### {p.relative_to(ROOT)}\n{'='*84}")
    if not p.exists():
        print("  ★不存在")
        return
    t = p.read_text(encoding="utf-8", errors="replace")
    ls = t.splitlines()
    for l in ls[:n]:
        print(f"  {l}")
    if len(ls) > n:
        print(f"  …（共 {len(ls)} 行）")


def main() -> int:
    print("=== ① DPO 配置文件 ===")
    for pat in ("configs/*.yaml", "configs/*.yml", "configs/*.json"):
        for p in sorted(ROOT.glob(pat)):
            if "dpo" in p.name or "m3" in p.name:
                show(p, 70)

    print("\n\n=== ② 训练脚本里的 DPO 超参 ===")
    for p in sorted(ROOT.glob("scripts/*dpo*.py")) + sorted(ROOT.glob("secfm/**/*dpo*.py")):
        t = p.read_text(encoding="utf-8", errors="replace")
        hits = [l.strip() for l in t.splitlines()
                if re.search(r"\bbeta\b|num_train_epochs|learning_rate|lr\s*=|"
                             r"max_length|max_prompt|gradient_accum|"
                             r"warmup|loss_type|rpo_alpha|reference_free|"
                             r"save_steps|eval_steps|per_device_train", l)]
        if hits:
            print(f"\n  --- {p.relative_to(ROOT)} （{len(hits)} 处）---")
            for h in hits[:26]:
                print(f"    {h}")

    print("\n\n=== ③ 训练日志 / 指标 ===")
    logs = ROOT / "reports" / "logs"
    cands = []
    if logs.exists():
        for p in sorted(logs.glob("*")):
            if p.is_file() and re.search(r"dpo|m3|train", p.name, re.I):
                cands.append(p)
    for p in cands[:10]:
        print(f"  {p.relative_to(ROOT):<52} {p.stat().st_size:>10,} B")

    print("\n=== ④ checkpoint 目录（看有几个档、选了哪个）===")
    ck = ROOT / "checkpoints"
    if ck.exists():
        for d in sorted(ck.iterdir()):
            if d.is_dir():
                n = sum(1 for _ in d.rglob("*") if _.is_file())
                print(f"  {d.name:<46} {n:>6} 文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
