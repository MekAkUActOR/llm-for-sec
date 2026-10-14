# -*- coding: utf-8 -*-
"""★决定性检查：M3 的契约保留率崩塌（70/168 → 20/168）是真实的，还是 96-token 截断伪影？

逻辑：
  MUST-B 的口径是"响应中含 VERDICT 行"。`max_new_tokens=96` 若把输出截断在 VERDICT 之前，
  就会把"结构化输出被切掉"误判成"契约崩塌"。
  故必须比较两臂的**响应长度分布**与**触顶比例**，并看触顶与非触顶条目各自的表现。

判据（预登记，先写后算）：
  - 若 m3-dpo 的触顶比例 ≈ soup-a050 的 ⇒ 截断**不能**解释差异；崩塌为真。
  - 若 m3-dpo 触顶比例**显著更高**且触顶条目的 VERDICT 率显著更低
    ⇒ 差异**至少部分**是仪器伪影，MUST-B 的 FAIL 需降级为"待复核"。
"""
import json
import statistics as st
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
CAP = 96


def load_dump(tag: str):
    """读 baseline_eval 的 responses dump；容忍多种字段名。"""
    for name in (f"resp-chat-gen-{tag}.jsonl", f"resp-chat-{tag}.jsonl"):
        p = R / name
        if p.exists():
            rows = []
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            return p.name, rows
    return None, []


def tok_len(row: dict, key_names=("n_tokens", "num_tokens", "tokens", "n_new_tokens")):
    for k in key_names:
        if k in row and isinstance(row[k], int):
            return row[k]
    return None


def text_of(row: dict):
    for k in ("text", "response", "output", "completion", "generated"):
        if k in row and isinstance(row[k], str):
            return row[k]
    return None


print(f"=== 截断伪影检查（cap = {CAP} tokens）===\n")
for tag in ("soup-a050", "m3-dpo"):
    fname, rows = load_dump(tag)
    if not rows:
        print(f"{tag}: ✗ 找不到 responses dump")
        continue
    print(f"--- {tag}（{fname}，{len(rows)} 行）---")
    if rows:
        print(f"    字段 = {sorted(rows[0].keys())}")

    lens = [tok_len(r) for r in rows]
    if all(v is None for v in lens):
        # 没有 token 计数字段 ⇒ 用字符数近似（并明确标注这是近似）
        chars = [len(text_of(r) or "") for r in rows]
        print(f"    无 token 计数键；改用字符数近似："
              f"min={min(chars)} p50={st.median(chars):.0f} max={max(chars)}")
        at_cap = sum(1 for c in chars if c >= 300)   # 300 字符 ≈ 96 token 的粗略上界
        print(f"    字符数 ≥300 的比例 = {at_cap}/{len(chars)} = {at_cap/len(chars)*100:.1f}%（近似）")
    else:
        lens = [v for v in lens if v is not None]
        print(f"    token 数：min={min(lens)} p50={st.median(lens):.0f} "
              f"mean={st.mean(lens):.1f} max={max(lens)}")
        at_cap = sum(1 for v in lens if v >= CAP)
        print(f"    ★触顶（≥{CAP}）比例 = {at_cap}/{len(lens)} = {at_cap/len(lens)*100:.1f}%")

    # 触顶 vs 非触顶 的 VERDICT 率
    grp = {"capped": [0, 0], "uncapped": [0, 0]}
    for r in rows:
        t = text_of(r) or ""
        has_v = "VERDICT" in t
        L = tok_len(r)
        if L is None:
            L = len(t) / 3.2  # 粗略
        g = "capped" if L >= CAP else "uncapped"
        grp[g][0] += 1
        if has_v:
            grp[g][1] += 1
    for g, (n, k) in grp.items():
        if n:
            print(f"    {g:<9} n={n:<4} 含 VERDICT = {k:<4} ({k/n*100:5.1f}%)")
    print()

print("TRUNCATION-ARTIFACT-CHECK=DONE")
