# -*- coding: utf-8 -*-
"""提取门禁脚本 argparse 接口（r4 命令重构用）。"""
import re
import io

for f in ("scripts/baseline_eval.py", "scripts/probe_longctx.py", "scripts/probe_dilution.py",
          "scripts/probe_jailbreak.py", "scripts/probe_ppl.py"):
    src = io.open(f, encoding="utf-8", errors="replace").read()
    args = re.findall(r"add_argument\(\s*[\"']([^\"']+)[\"']([^)]*)", src)
    print("===", f)
    for a, rest in args:
        d = "-"
        m = re.search(r"default=([^,\)]+)", rest)
        if m:
            d = m.group(1).strip()[:60]
        print("   ", a, "|", d)
