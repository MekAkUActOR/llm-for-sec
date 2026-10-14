# -*- coding: utf-8 -*-
"""从**一次 512 口径跑批**离线导出整条部署预算曲线（96/128/192/256/384/512）。

## 为什么等价（这是本工具成立的全部依据）

`baseline_eval.py` 用 `do_sample=False`（贪心）⇒ 解码是**前缀确定**的：
以 `max_new_tokens=512` 跑出的 token 序列，其**前 N 个 token 逐位等于**
直接以 `max_new_tokens=N` 跑出的结果。

⇒ 取 `new_token_ids[:N]` 解码后重打分，**与实跑 N 得到同一文本**，
  故各预算点的读数**互相可比**，也**可比**实跑（docs/01 规则 21 的"同口径"要求）。

## ★这不是"近似"，但仍是**派生**产物，必须留痕

产出名与实跑相同（`-mnt{N}`），以便 `topup_verdict.py --max-new-tokens N` 直接复用；
**同时**写一份 provenance（`reports/derived-caliber-provenance.json`）记录
"哪些文件名是派生的、派生自哪次实跑、依据是什么" ✓
（规则 2：口径变更必须标注、历史读数必须保留）。

## fail-closed（规则 32）

任何一步写出 0 条记录 / 找不到源产物 / token 数不足，一律**报错退出**，
不得静默产出空产物（本模块正是被"空洞通过"事故催生的）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
TOK = (ROOT / ".cache" / "huggingface" / "hub"
       / "models--Qwen--Qwen3-0.6B-Base" / "snapshots"
       / "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
SOURCE = 512
BUDGETS = (96, 128, 192, 256, 384, 512)
PROV = R / "derived-caliber-provenance.json"

#: (标签, heldout 目录, scored 前缀, resp 前缀模板)
JOBS = (
    ("gen", ROOT / "data" / "heldout" / "v0.3-gen", "chat-gen-",
     "resp-chat-gen-{tag}"),
    ("v021", ROOT / "data" / "heldout" / "v0.2.1", "chat-",
     "resp-chat-{tag}"),
    ("to", ROOT / "data" / "heldout" / "v0.4-toolout", "chat-to-",
     "resp-chat-to-{tag}"),
)


def main() -> int:
    tags = sys.argv[1:] or ["soup-a050", "m3-dpo"]
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(TOK))
    provenance = {}
    problems = []

    for tag in tags:
        for label, held, prefix, resp_tpl in JOBS:
            src = R / f"{resp_tpl.format(tag=tag)}-mnt{SOURCE}.jsonl"
            if not src.exists():
                problems.append(f"{tag}/{label}: 缺源产物 {src.name}")
                continue
            recs = []
            for ln in src.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    recs.append(json.loads(ln))
            if not recs:
                problems.append(f"{tag}/{label}: 源产物 0 条记录")
                continue
            if "new_token_ids" not in recs[0]:
                problems.append(f"{tag}/{label}: 源产物缺 new_token_ids（无法派生）")
                continue
            print(f"--- {tag}/{label}：源 {len(recs)} 条 "
                  f"（{src.name}）---")
            for n in BUDGETS:
                # 截断率 = 该预算下会被切掉的比例（★规则 34：必须报告可计算覆盖率）
                trunc = sum(1 for r in recs
                            if len(r.get("new_token_ids") or []) > n)
                tp = R / f"{resp_tpl.format(tag=tag)}-mnt{n}.jsonl"
                sp = R / f"scored-{prefix}{tag}-v2-mnt{n}.json"
                with tp.open("w", encoding="utf-8", newline="\n") as f:
                    for r in recs:
                        ids = (r.get("new_token_ids") or [])[:n]
                        txt = tok.decode(ids, skip_special_tokens=True).strip()
                        f.write(json.dumps({"id": r.get("id"), "text": txt},
                                           ensure_ascii=False) + "\n")
                cp = subprocess.run(
                    [str(PY), str(ROOT / "scripts" / "score_heldout_v2.py"),
                     "--heldout", str(held), "--responses", str(tp), "--out", str(sp)],
                    cwd=str(ROOT), capture_output=True, text=True,
                    encoding="utf-8", errors="replace")
                ok = sp.exists() and sp.stat().st_size > 0
                print(f"    N={n:<4} 截断率={trunc/len(recs):6.1%}  "
                      f"{'OK' if ok else '★失败 rc=%d' % cp.returncode}")
                if not ok:
                    problems.append(f"{tag}/{label}/N={n}: 打分失败")
                provenance.setdefault(f"scored-{prefix}{tag}-v2-mnt{n}.json", []).append(
                    {"derived_from": src.name, "prefix_tokens": n,
                     "n_items": len(recs), "truncation_rate": round(trunc / len(recs), 6),
                     "equivalence": "贪心解码前缀确定 ⇒ 与实跑 max_new_tokens=N 等价"})

    PROV.write_text(json.dumps({
        "note": ("以下产物是**派生**的（不是实跑）：由一次 max_new_tokens=512 的跑批，"
                 "按贪心解码的**前缀确定性**取 new_token_ids[:N] 解码后重打分得到。"
                 "因 do_sample=False，其结果与直接以 max_new_tokens=N 实跑**逐 token 等价**。"
                 "★使用这些读数时仍应说明其为派生口径。"),
        "source_max_new_tokens": SOURCE,
        "budgets": list(BUDGETS),
        "files": provenance,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nprovenance -> {PROV.name}")

    if problems:
        print(f"\n★问题 {len(problems)} 项：")
        for p in problems[:20]:
            print(f"    {p}")
        print("DERIVE-BUDGET-CURVE=FAIL")
        return 1
    print("DERIVE-BUDGET-CURVE=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
