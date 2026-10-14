# -*- coding: utf-8 -*-
"""★量化截断偏倚：撞顶（≥96 token）与未撞顶条目的 ASR 差异。

逻辑：截断会**阻止模型产出防御** ⇒ 撞顶条目应显示**更高**的 ASR。
若确实如此，则本项目的门禁读数**系统性地偏向报告失败**，其含义是：
  **PASS 稳健**（截断不会让失败者通过），**FAIL 可疑**（可能是截断造成的）。

用法：join `reports/resp-*.jsonl`（取正文）与 `reports/scored-*.json`（取标签）。
只加载 tokenizer（CPU）。
"""
import glob
import json
import os
import re
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
ROOT = Path(__file__).resolve().parent.parent
TOK_DIR = (ROOT / ".cache" / "huggingface" / "hub" /
           "models--Qwen--Qwen3-0.6B-Base" / "snapshots" /
           "da87bfb608c14b7cf20ba1ce41287e8de496c0cd")
CAP = 96

from transformers import AutoTokenizer  # noqa: E402
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))
from secfm.eval.stats import fisher_p_greater  # noqa: E402

tok = AutoTokenizer.from_pretrained(str(TOK_DIR), trust_remote_code=True)
RESP_KEYS = ("response", "content", "text", "completion", "output", "answer")


def get_text(r):
    for k in RESP_KEYS:
        if isinstance(r.get(k), str):
            return r[k]
    if isinstance(r.get("messages"), list):
        for m in r["messages"]:
            if isinstance(m, dict) and m.get("role") == "assistant":
                return str(m.get("content") or "")
    return ""


# --- 建立 (tag, id) -> token 长度 ---
lenmap = {}
for f in sorted(glob.glob(str(ROOT / "reports" / "resp-*.jsonl"))):
    tag = Path(f).name.replace("resp-", "").replace(".jsonl", "")
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = get_text(r)
            if not t:
                continue
            lenmap[(tag, str(r.get("id")))] = len(tok.encode(t, add_special_tokens=False))

print(f"已计 token 的 (tag,id) 数 = {len(lenmap)}\n")

# --- 对每个 scored 文件做撞顶/未撞顶分层 ---
print(f"{'scored 文件':<44} {'撞顶 n/k':>12} {'未撞顶 n/k':>12} {'ASR撞顶':>8} "
      f"{'ASR未撞':>8} {'Δ':>8} {'Fisher p':>9}")
print("-" * 108)
rows = []
for sf in sorted(glob.glob(str(ROOT / "reports" / "scored-*.json"))):
    sname = Path(sf).name.replace("scored-", "").replace(".json", "")
    d = json.loads(Path(sf).read_text(encoding="utf-8"))
    items = [it for it in d.get("items", []) if it.get("responded")]
    if not items:
        continue
    # 找对应的 resp 文件：尝试若干命名
    cands = [sname, sname.replace("-v2", ""), sname.rstrip("-v2")]
    if sname.startswith("chat-gen-"):
        cands = ["chat-gen-" + sname[len("chat-gen-"):]]
    keymap = {}
    for c in cands:
        if any(k[0] == c for k in lenmap):
            keymap = {k[1]: v for k, v in lenmap.items() if k[0] == c}
            break
    if not keymap:
        # 宽松匹配：取最后一个 '-' 之后的 tag
        for k in lenmap:
            if k[0] in sname or sname.endswith(k[0]):
                keymap[k[1]] = lenmap[k]
    if not keymap:
        continue
    hi = [it for it in items if keymap.get(str(it.get("id")), 0) >= CAP]
    lo = [it for it in items if 0 < keymap.get(str(it.get("id")), 0) < CAP]
    if len(hi) < 5 or len(lo) < 5:
        continue
    khi = sum(1 for it in hi if it.get("derived", {}).get("attack_success"))
    klo = sum(1 for it in lo if it.get("derived", {}).get("attack_success"))
    rhi, rlo = khi / len(hi), klo / len(lo)
    p = fisher_p_greater(khi, len(hi) - khi, klo, len(lo) - klo)
    rows.append((sname, len(hi), khi, len(lo), klo, rhi, rlo, rhi - rlo, p))
    print(f"{sname:<44} {f'{khi}/{len(hi)}':>12} {f'{klo}/{len(lo)}':>12} "
          f"{rhi:>8.3f} {rlo:>8.3f} {rhi - rlo:>+8.3f} {p:>9.4f}")

if rows:
    deltas = [r[7] for r in rows]
    print("\n" + "=" * 108)
    print(f"共 {len(rows)} 个可比文件；Δ = ASR(撞顶) − ASR(未撞顶)")
    print(f"   Δ 的中位数 = {sorted(deltas)[len(deltas) // 2]:+.3f}")
    print(f"   Δ > 0 的文件数 = {sum(1 for x in deltas if x > 0)} / {len(deltas)}")
    sig = [r for r in rows if r[8] < 0.05]
    print(f"   Fisher p<0.05 的文件数 = {len(sig)}")
    print("\n⇒ 判读：Δ 系统性为正 = 截断把读数**推向失败**，则 PASS 稳健、FAIL 可疑。")
    print("   若 Δ≈0，则截断虽普遍但**不改变门禁结论**（仍需在裁定里登记）。")
