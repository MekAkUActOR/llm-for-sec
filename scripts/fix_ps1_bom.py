# -*- coding: utf-8 -*-
"""给 .ps1 补 UTF-8 BOM（PowerShell 5.1 读非 ASCII 脚本的硬前提）。

为什么需要：本项目的 `.ps1` 全含中文注释/输出，而 PS 5.1 **无 BOM 时按 ANSI 解码**，
于是中文变乱码并连带破坏语法（实测报 "Array index expression is missing"、
"Unexpected token '}'" 之类**看似语法错、实为编码错**的 6 条错误）。
`edit`/`write` 工具会剥掉 BOM，所以每次改完 `.ps1` 都要跑一次本脚本。

用法：
    python scripts/fix_ps1_bom.py scripts/a.ps1 scripts/b.ps1     # 指定文件
    python scripts/fix_ps1_bom.py --scan                            # 扫 scripts/*.ps1
    python scripts/fix_ps1_bom.py --scan --check                    # 只报告不改
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"


def fix(path: Path, check_only: bool = False) -> str:
    raw = path.read_bytes()
    if raw.startswith(BOM):
        return "ok"
    if check_only:
        return "缺少 BOM"
    path.write_bytes(BOM + raw)
    return "已补 BOM"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scan = "--scan" in sys.argv
    check = "--check" in sys.argv
    # ★2026-10-06 修：原先**无参数时**打印 docstring 并 return 2，
    #   但使用者（我）会以为"跑一下修复器就修好了"，实际什么都没做——
    #   当天我正因此误判"fix_ps1_bom.py 没修我的文件"（其实是我没给参数）。
    #   现改为：**无参数即等价 --scan**（最常用的意图），要只报告就加 --check。
    if not args and not scan:
        scan = True
    files = ([p for p in sorted((ROOT / "scripts").glob("*.ps1"))]
             if scan else [Path(a) for a in args])
    if not files:
        print(__doc__)
        return 2
    bad = 0
    for p in files:
        if not p.exists():
            print(f"  [跳过] 不存在：{p}")
            continue
        r = fix(p, check_only=check)
        flag = "" if r == "ok" else "  <-- 需处理"
        if r != "ok":
            bad += 1
        print(f"  {p.name:42} {r}{flag}")
    print(f"\nFIX-PS1-BOM={'PASS' if bad == 0 else f'{bad} 个需要处理'}"
          f"{'（--check 只报告）' if check else ''}")
    # ★2026-10-06 修：原式 `0 if (bad == 0 or check or not check) and not check ...`
    #   里 `check or not check` **恒为真** ⇒ 不加 --check 时**永远返回 0**，
    #   即使修复没生效也报成功（退出码说谎）。现按真实状态返回：
    #     --check 模式下"有缺 BOM"= 1（让 CI/编排能发现，与语义一致）
    #     实修模式后仍缺 BOM = 1（说明修复失败，必须暴露，不能静默）
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
