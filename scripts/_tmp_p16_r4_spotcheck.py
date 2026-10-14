# -*- coding: utf-8 -*-
"""生成 reports/p1.6-spotcheck-r4.md（分层抽查 16 行全文，PENDING_HUMAN_GATE 先例）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ids = json.loads((ROOT / "reports" / "p1.6-spotcheck-r4-ids.json").read_text(encoding="utf-8"))
rows = {}
for l in (ROOT / "data" / "dpo" / "p16-calibration-r4" / "p16_f4_dialog.jsonl").read_text(encoding="utf-8").splitlines():
    if l.strip():
        r = json.loads(l)
        rows[r["id"]] = r

lines = [
    "# P1.6 四轮 F4-dialog 抽查样本（spotcheck-16，seed=20261014+999，分层确定性随机）",
    "",
    "- 范围：4 风格 × 2 语言 ×（cd/lip 各 1）= 16 行；对象 = p16_f4_dialog.jsonl 全新生成 792 行",
    "- 机检结论（已过）：batch_check fails=0（schema/VERDICT/H1 标记词/H4 长度平价/F4F6 红线/",
    "  零武器化/token ≤970）+ G9 同款 8-gram 污染检查对 heldout 冻结件 + probes 全量 0 命中",
    "  + prompt 全局唯一 + 配额闭合；本件供**人工抽查**（语义自然度/措辞质量）",
    "- 状态：**PENDING_HUMAN_GATE**（沿一轮 p1.6-spotcheck-abd/cef 先例）",
    "",
]
for rid in ids:
    r = rows[rid]
    turns = sum(1 for c in r["conversations"] if c["from"] == "human")
    lines.append(f"## {rid} · {r['src_task']} · archetype {r['archetype_id']} · pack {r['pack']} · "
                 f"{r['lang']} · 形态 {r['rejected_form']} · user 轮数 {turns}")
    lines.append("")
    lines.append("**conversations**（system 模板省略——冻结模板，sha 见 manifest）：")
    lines.append("")
    for c in r["conversations"][1:]:
        tag = "USER" if c["from"] == "human" else "ASSISTANT"
        lines.append(f"- [{tag}] {c['value']}")
    lines.append("")
    lines.append("**chosen**：")
    lines.append("")
    lines.append("```")
    lines.append(r["chosen"]["value"])
    lines.append("```")
    lines.append("")
    lines.append("**rejected**：")
    lines.append("")
    lines.append("```")
    lines.append(r["rejected"]["value"])
    lines.append("```")
    lines.append("")

out = ROOT / "reports" / "p1.6-spotcheck-r4.md"
out.write_text("\n".join(lines) + "\nP16-R4-SPOTCHECK=DONE\n", encoding="utf-8", newline="\n")
print(f"wrote {out} ({len(ids)} rows)")
