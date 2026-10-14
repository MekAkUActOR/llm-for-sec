# -*- coding: utf-8 -*-
"""恢复 coverage_matrix.columns 里被我覆盖掉的原描述性标签（保留新增的 document_gate）。

★为什么必须恢复：checker **不**比对 columns ⇒ 不恢复也能 PASS。
  但那是"以检查器为准"而非"以事实为准"——原标签承载了真实的计数口径说明
  （例如 train 列注明 basis 是 lf_total、unseen_gate 注明括号内是 robustness 分母）。
  丢了它 = 静默退化（docs/01 规则 25）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
P = ROOT / "data" / "ontology" / "carriers.json"
BAK = P.with_suffix(".json.bak-before-v06-document")


def main() -> int:
    if not BAK.exists():
        print("★无备份，无法恢复")
        return 1
    old = json.loads(BAK.read_text(encoding="utf-8"))
    cur = json.loads(P.read_text(encoding="utf-8"))
    o_cols = (old.get("coverage_matrix") or {}).get("columns") or {}
    c_cols = (cur.setdefault("coverage_matrix", {})).setdefault("columns", {})

    restored = []
    for k, v in o_cols.items():
        if c_cols.get(k) != v:
            c_cols[k] = v
            restored.append(k)
    print(f"恢复原标签 {len(restored)} 个：{restored}")
    print(f"保留新列 document_gate = {c_cols.get('document_gate')!r}")
    P.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")

    back = json.loads(P.read_text(encoding="utf-8"))
    b_cols = (back.get("coverage_matrix") or {}).get("columns") or {}
    ok = all(b_cols.get(k) == v for k, v in o_cols.items()) and "document_gate" in b_cols
    print(f"COLUMNS-RESTORE={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
