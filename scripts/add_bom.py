# -*- coding: utf-8 -*-
"""给指定 .ps1 回填 UTF-8 BOM（幂等）。

★为什么必须单独有它：`write`/`edit` 工具写出的文件**不带 BOM**，
  而 PowerShell 5.1 读无 BOM 的 UTF-8 会按 ANSI 解码 ⇒ 中文被破坏 ⇒
  **解析直接失败**（本次 obj2_remeasure.ps1 报 5 个语法错，实际引号/括号全平衡）。
  `scripts/fix_ps1_bom.py` 是全仓扫描器，此处用于**定点**回填。
"""
import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"


def fix(path: Path) -> bool:
    raw = path.read_bytes()
    if raw.startswith(BOM):
        print(f"BOM-ALREADY  {path.name}")
        return True
    # 先确认原内容是合法 UTF-8（否则不该加 BOM，应先查来源）
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"★BOM-SKIP  {path.name}：内容不是合法 UTF-8（{e}）")
        return False
    path.write_bytes(BOM + raw)
    back = path.read_bytes()
    ok = back.startswith(BOM) and back[3:] == raw
    print(f"BOM-ADDED  {path.name}  ({len(raw)} → {len(back)} B, 校验={ok})")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：add_bom.py <file.ps1> [more.ps1 ...]")
        raise SystemExit(2)
    allok = all(fix(Path(a)) for a in sys.argv[1:])
    raise SystemExit(0 if allok else 1)
