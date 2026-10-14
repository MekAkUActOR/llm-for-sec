# -*- coding: utf-8 -*-
"""第 17 轮：记录进程取证事故，并新增 docs/01 §11.37 规则 38。

★事故（2026-10-06 第 17 轮）：
  我看到进程表里有 **2 个 `python.exe` 匹配 `baseline_eval.py`**，
  就断定"两个评测在抢同一块 GPU、读数互相污染" ✗，
  于是**杀掉了当时已跑 13 分钟的健康跑批**（产物写盘在末尾 ⇒ 未丢数据，只损失 GPU 时间）。

★真因：
  `venv\\Scripts\\python.exe` 在 Windows 上是 **uv 的 trampoline** ⇒
  **一次调用 = 2 个 python.exe 进程**（~4 MB 薄壳 + ~2 GB 真 worker）；
  外加 launcher 会**调用子脚本 powershell**（`eval_needlefix.ps1`）⇒
  **一条健康单链同时匹配 4–5 个进程** ✗。

★判据（规则 38）：**并发与否看"重 worker 数"与"GPU 占用"，不看匹配进程数。**
"""
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
DOC = ROOT / "docs" / "01-engineering-definition.md"

BLOCK = """
### §11.37 规则 38（进程取证：判"并发"必须看**重 worker 数**与 **GPU 占用**，不看匹配进程数）

**规则 38**：判定"是否有多个训练/评测在并发"时，**禁止**用"命令行匹配某脚本名的
进程个数"作为判据 ✗。**必须**使用下列**可分辨**的判据：

1. **重 worker 数**：工作集显著超过模型量级的解释器进程数
   （本项目 0.6B 模型 ⇒ 真 worker 约 **2 GB**；薄壳约 **4 MB**）。正常 = **1**；
   **≥2 才是真并发** ✗。
2. **GPU 占用**：`nvidia-smi` 的 used 是否与**一个**模型的量级一致
   （0.6B ⇒ 约 **3.2 GB**）；明显超出 ⇒ 可能多实例。
3. **父子关系**：真并发是**两条独立的祖先链**；同一条链上的进程是**协作**，不是竞争。

**推论 38.1（Windows venv 的 trampoline 会倍增进程数）**：
`venv\\Scripts\\python.exe` 在 Windows 上可能是 **uv 的 trampoline** ⇒
**一次调用产生 2 个 python.exe**（薄壳 + 真解释器）✗。
因此"看到 2 个 python"**完全不能**推断"跑了 2 份任务"。

**推论 38.2（包装 shell 与子脚本也会被计入）**：
launcher（`recaliber_mnt.ps1`）→ 子脚本（`eval_needlefix.ps1`）→
trampoline → worker，**一条健康链会有 4–5 个进程**同时命中同一模式串 ✗。
**用模式串计数判并发，必然误报。**

**来历（2026-10-06 第 17 轮）**：我据"2 个 python 匹配 baseline_eval"判定并发污染，
**杀掉了一次已运行 13 分钟的健康跑批** ✗。事后实测该链为
`launcher(94MB) → eval_needlefix.ps1(92MB) → trampoline(4MB) → worker(1962MB)`，
**重 worker = 1、GPU = 3.28 GB** ⇒ **从头到尾就没有并发** ✗。

**★并附一条操作纪律**：**"停止"是不可逆操作，执行前必须先取证**：
先行 `scripts\\stop_eval_procs.ps1 -Tree`（看树）与 `-Guard`（判定），
确认确为真并发后再停。**"我以为有异常"不是停止的理由** ✗。

**★工具已按本规则改造**：`scripts\\stop_eval_procs.ps1` 新增
`-Tree`（打印父子链与工作集，标注 ★重worker / (trampoline?)）
与 `-Guard`（重 worker ≥2 ⇒ rc=1），并把判据写在输出里，
使**误判无法悄悄发生** ✓。
"""


def main() -> int:
    src = DOC.read_text(encoding="utf-8")
    checks = {}
    if "### §11.37 规则 38" in src:
        checks["规则 38 已存在（幂等）"] = True
    else:
        src = src.rstrip("\n") + "\n" + BLOCK
        checks["规则 38 已落"] = True
    DOC.write_text(src, encoding="utf-8")
    back = DOC.read_text(encoding="utf-8")
    checks["无乱码"] = not any(t in back for t in ("\ufffd", "锟斤拷"))
    checks["含关键判据"] = ("重 worker" in back and "trampoline" in back)
    ok = all(checks.values())
    print(f"DOCS-RULE38={'PASS' if ok else 'FAIL'} 行数={len(back.splitlines())}")
    for k, v in checks.items():
        print(f"    {'OK ' if v else '★NG'} {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
