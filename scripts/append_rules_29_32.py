# -*- coding: utf-8 -*-
"""把本轮实证得出的四条规则（29–32）追加到 docs/01-engineering-definition.md §11。

★为什么用 Python 而不是 PowerShell：本项目的 docs/*.md 是无 BOM 的 UTF-8，
  PS 5.1 的 Get-Content / Set-Content 会把它读/写成乱码（本会话已两次踩到）。
  本脚本显式 encoding='utf-8' 读写，并在写后回读校验。
"""
from pathlib import Path

P = Path(r"J:\Projects\llm_for_sec\docs\01-engineering-definition.md")

BLOCK = """
### 11.28 规则 29 — **全局纪律必须回溯适用于既存脚本**；写下规则时同时产出合规扫描（2026-09-30 晚实证，一次事故）

**实证**：2026-09-30 晚，M3 训练成功后，评测链在**第 1 步被自己的守卫误杀**。
根因：`scripts/eval_needlefix.ps1` 的并发守卫**按进程名**判定——
"只要有任何 `python.exe` 就中止（GPU 严格串行）"。
它逮到的 `pid=9232` 是 `scripts\\build_document_gate.py --overlap`，
**一个纯 CPU 作业**（CPU 193 s、显存 0）⇒ **CPU 作业被误判为 GPU 作业，杀掉整条 GPU 评测链**。

**关键之处不是"有人不知道规则"**：规则 19（docs/01 §11.18「作业识别必须按命令行」）
**早已存在**，且被 `wait_then_post_m3.ps1`、`post_m3_safety_net.ps1`、
`run_needlefix.ps1`、`eval_m3_post.ps1` **四个脚本正确实现**。
我逐处查了全部 8 处 `Name='python.exe'`：**`eval_needlefix.ps1` 是唯一违规者**——
它是链上最老、最关键的一环，而**规则只被回填到了新脚本**。

⇒ **"知道规则"与"遵守规则"之间存在一个无人负责的缺口。**

**要求**：
1. 任何"全局性纪律"（按命令行识别作业、BOM 要求、幂等要求、路径约定）写入 docs/01 时，
   **必须同时产出一份既存脚本的合规扫描**，逐处判定并列出违规者。
2. 违规者**当场回填**，不得以"以后注意"结案。
3. 扫描命令应可复跑（如本轮的 `Name='python.exe'` 逐处判定），作为 Part B 复算入口之一。

**同型第二例（同一晚，同一模式）**：`scripts/probe_longctx.py` 的 chat 口径
**从未成功运行过**——`ModuleNotFoundError: No module named 'secfm'`，
因为它定义 `ROOT` 却**从未** `sys.path.insert(0, str(ROOT))`，
而该写法在本仓库出现 **221 次**，**它是唯一漏掉的脚本**。
⇒ 规则 29 覆盖的**不止安全守卫，也包括导入/路径这类隐式约定**。

### 11.29 规则 30 — 编排脚本必须检查子进程退出码；**"某步被跳过"必须比"链失败"更响亮**（2026-09-30 晚实证）

**实证**：`scripts/eval_m3_post.ps1` 用 `$ErrorActionPreference='Continue'`
且**不检查子脚本 `$LASTEXITCODE`**。子脚本 `eval_needlefix.ps1` 在 step 1 `exit 2` 后，
外层**照常执行 step 6/7**，产出 `topup-verdict-m3-dpo.json`（PENDING）。

**后果不是"链没跑"**——那会立刻被发现——**而是"链跑完了、还出了裁定文件，
只是其中一半的输入从未被测量"**。这是最危险的失败形态：
**产物存在、格式合法、内容是 PENDING**，极易被当作"已测但未过"。

**双重缺陷**：`eval_needlefix.ps1` **无条件 `exit 0`**（`-DecisiveOnly` 分支与末行"ALL DONE"
均不检查失败）⇒ **即使 needle 因 `ModuleNotFoundError` 崩掉也报成功**
⇒ **只给编排层加退出码检查是不够的**，两层都要修。

**要求**：
1. 编排脚本每个 GPU/子进程步骤后必须检查退出码；失败**记录并继续跑完可幂等补齐的步骤**，
   但**收尾必须以非零码退出**并打印未成功步骤清单。
2. **产物的成败判据是"产物是否存在"，不是退出码**——退出码会说谎（本规则已实证）。
   实现见 `eval_needlefix.ps1` 的 `Note-Step <name> <artifact>`：给定产物路径时只看产物存在性，
   因此"跳过"分支（前提就是产物已在）天然正确，而真崩了必然产物缺失。
3. **禁止无条件宣告 "ALL DONE"**。

### 11.30 规则 31 — 日志中的阈值必须与代码中的阈值**同源**（2026-09-30 晚实证）

**实证**：`eval_needlefix.ps1` 原 L32 打印 `显存占用 = 1437 MiB（应 < 1024）`，
而 L33 实际判 `$used -gt 3072`。**我据此一度误判"显存是中止原因"**，
真因是紧随其后的 python 进程检查。

**要求**：阈值以变量形式**只定义一次**，判定与打印**同源**；
不得出现"提示写 1024、代码判 3072"这类不一致。
**理由**：日志文本是排查的第一手依据，写错会把排查引向**错误方向**——
而错误的排查方向比没有方向更贵。

### 11.31 规则 32 — 判据与绊线登记时必须附**可行域验算**；**"没触发"不是观测结果**（2026-09-30 晚，三例同型）

本晚独立发现**三条同型病**：判据/绊线登记时只写了阈值，**没人验算它在本仪器上能否分辨**。
（详见 `reports/criterion-no-resolution-three-cases.md`）

| 实例 | 被读成 | 实际含义 |
|---|---|---|
| MUST-C（误拒 ORR 上升 ≤0.05） | "PASS"（修复前） | 参照值 0.0 是 fail-open bug 的输出（真实 0.1667） |
| MUST-B（契约保留率 ≥63/168） | "PASS" | 下跌虽**统计显著**（配对 p=0.0407）但在绝对阈值内 ⇒ **门太钝** |
| M3 早停绊线（`acc≥0.97 连 5` 且 `margins×>2`） | "未触发 ⇒ 没病" | **可行域为空**：滑动 5 点窗同时满足两条 = **0/76** |

**MUST-C 的分辨率实测**：n=54、容差 0.05 ⇒ **仅 +3 条即翻转**；
配对 McNemar p=0.1445、配对 CI [−0.0267, +0.1748] 含 0、`resolution_ok=false`；
要分辨 0.05 每臂需 **n≳600**。

**要求**：
1. 任何写进冻结文件的阈值/规则，登记时必须给出：
   （a）在本仪器（n、分辨率、方向）下**能分辨的最小效应量**；
   （b）该判据在**起点数据**上是否已触发/是否可触发（"可行域非空"的证据）；
   （c）若不可分辨，**显式标注"该判据在本实验上无判别力，其通过不构成证据"**，
        并登记所需 n 或替代判据。
2. **推论**：报告"绊线未触发"时**必须同时报告它本可以触发的窗口数**；
   若为 0，该句应改写为"**该绊线在本 run 上不可操作**"，**不得**计入健康证据。

**与规则 26 的关系**：规则 26 要求"每个 MUST 门必须有会失败的证据"（门要**活着**）；
本规则要求"每条判据必须有**能分辨**的证据"（门要**有刻度**）。
**活着但无刻度的门，与死门在结论上等价——而它更危险，因为它看起来是活的。**
"""


def main() -> int:
    txt = P.read_text(encoding="utf-8")
    if "### 11.28 规则 29" in txt:
        print("已存在 §11.28，跳过（幂等）")
        return 0
    if not txt.endswith("\n"):
        txt += "\n"
    before = len(txt.splitlines())
    P.write_text(txt + BLOCK, encoding="utf-8")

    # 写后回读校验（防双重编码）
    back = P.read_text(encoding="utf-8")
    after = len(back.splitlines())
    marks = [m for m in ("浠讳綍", "缈昏浆", "鐨勭粺", "鈽") if m in back]
    print(f"✅ 已追加 §11.28–§11.31：{before} 行 → {after} 行（+{after-before}）")
    print(f"   双重编码特征串 = {marks if marks else '无'} ✓")
    for k in ("### 11.28 规则 29", "### 11.29 规则 30", "### 11.30 规则 31", "### 11.31 规则 32"):
        print(f"   {'✓' if k in back else '✗'} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
