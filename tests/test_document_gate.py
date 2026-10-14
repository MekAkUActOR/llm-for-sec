# -*- coding: utf-8 -*-
"""v0.6-document 门禁的轻量回归测试（不扫全语料，秒级）。

覆盖：
  1. 条目结构 / 计数 / id 唯一 / 键序（schema 与 v0.4-toolout 一致）
  2. 定种子逐字节可复现（内存重装配 == 盘上字节，sha256 自证）
  3. manifest.claims 的**按模型**强制规则（不可对已训模型声明未见载体）
  4. 「未见机理 = 未见结构位点」机器可判：门禁位点集 ∩ 活谱系位点集 = ∅
  5. 每个门禁机理都有干净负例（本轮补的 split_site_directive 亦在内）
  6. 可判性冒烟：两条假答复 × 两个 action_rule 口径
  7. 失败闭合：篡改输入（换键序 / 重复 id / 越界计数）必须被判错

用法：`python tests/test_document_gate.py`（无第三方依赖；退出码 0 = 全通过）
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_document_gate as B                                    # noqa: E402
import check_document_gate as C                                    # noqa: E402

GATE = ROOT / "data" / "heldout" / "v0.6-document"
FAILS = []


def ok(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("  [FAIL] %s" % msg)
    else:
        print("  [ok]   %s" % msg)


def main():
    rows = B.assemble_rows()
    text = B.dumps_rows(rows)
    disk = (GATE / B.FAMILY).read_text(encoding="utf-8")
    man = json.loads((GATE / B.MANIFEST).read_text(encoding="utf-8"))

    print("== 1. 结构 / 计数 / 键序 ==")
    ok(len(rows) == 80, "条目数 = 80（实际 %d）" % len(rows))
    ok(len({r["id"] for r in rows}) == len(rows), "id 唯一")
    ok(all(tuple(list(r.keys())[:9]) == tuple(B.KEY_ORDER) for r in rows),
       "每行前 9 键序 == %s（第 10 键 _spec 为构建器内部字段）"
       % (list(B.KEY_ORDER),))
    kinds = [r["kind"] for r in rows]
    ok(kinds.count("robustness") == 52 and kinds.count("alignment") == 28,
       "robustness=52 / alignment=28")
    langs = [r["language"] for r in rows]
    ok(langs.count("zh") == 40 and langs.count("en") == 40, "zh=40 / en=40")
    ok(all(r["policy_pack"] for r in rows), "policy_pack 非空")

    print("== 2. 定种子逐字节可复现 / sha256 自证 ==")
    ok(text == disk, "内存重装配与盘上 document.jsonl 逐字节一致")
    sha = B.sha256_text(text)
    ok(sha == man["sha256"], "manifest.sha256 == 重算 %s" % sha[:16])
    ok(B.sha256_text(B.dumps_rows(B.assemble_rows())) == sha,
       "两次装配 sha256 相同（定种子 SEED=%d）" % B.SEED)

    print("== 3. claims 按模型强制 ==")
    pm = man["claims"]["per_model"]
    ok(pm["soup-a050"]["carrier_seen"] is False
       and pm["soup-a050"]["document_rows_in_training"] == 0
       and "unseen_carrier" in pm["soup-a050"]["supports"],
       "soup-a050：训练 document 行=0 ⇒ 可声明未见载体")
    ok(pm["m3-dpo"]["carrier_seen"] is True
       and pm["m3-dpo"]["document_rows_in_training"] == 1000
       and "unseen_carrier" not in pm["m3-dpo"]["supports"]
       and pm["m3-dpo"]["supports"] == ["unseen_mechanism_only"],
       "m3-dpo：训练 document 行=1000 ⇒ 只声明未见机理，不得声明未见载体")
    ok(man["claims"]["unseen_carrier"] is False,
       "顶层 claims.unseen_carrier=false（主登记产物 m3-dpo 已见）")
    ok(len(man["claims"]["unseen_mechanism"]) == 8
       and man["claims"]["unseen_mechanism_scope"] == "structure_site_only",
       "声明 8 类未见机理且作用域=structure_site_only")

    print("== 4. 未见机理（未见结构位点）机器可判 ==")
    census = json.loads((GATE / "_work" / ("census-%s.json"
                                           % man["overlap"]["scope"]))
                        .read_text(encoding="utf-8"))
    gate_keys = set()
    for m in man["claims"]["unseen_mechanism"]:
        gate_keys |= set(B.GATE_MECHS[m]["site_keys"])
    live_keys = {k for k, v in census["train_structure_sites_live"].items()
                 if v}
    ok(not (gate_keys & live_keys),
       "门禁位点集 ∩ 活谱系位点集 = ∅（%d 个位点 vs %d 个）"
       % (len(gate_keys), len(live_keys)))
    ok(gate_keys - live_keys == gate_keys, "门禁位点集 ⊄ 活谱系位点集")

    print("== 5. 每个门禁机理都有干净负例 ==")
    clean_mechs = {re.search(r"mech=([A-Za-z0-9_]+)",
                             r["intent"]).group(1)
                   for r in rows if r["kind"] == "alignment"}
    for m in B.GATE_MECHS:
        ok(m in clean_mechs, "机理 %s 有干净负例" % m)
    ok("body_contract_clause" in clean_mechs
       and "body_report_outline" in clean_mechs,
       "在训位点对照机理的干净对照存在于正文层（body_contract_clause / "
       "body_report_outline）")

    print("== 6. 可判性冒烟（双口径）==")
    from score_heldout_v2 import score_items
    rob = [r for r in rows if r["kind"] == "robustness"]
    for rule in ("selfreport", "strict"):
        good, bad = {}, {}
        for r in rob:
            good[r["id"]] = re.search(r"正确行为=(.*?)；注入要求=",
                                      r["intent"], re.S).group(1).strip()
            bad[r["id"]] = re.search(r"注入要求=(.*)$",
                                     r["intent"], re.S).group(1).strip()
        rg = score_items(rob, good, action_rule=rule)
        rb = score_items(rob, bad, action_rule=rule)
        ng = [x for x in rg["items"]
              if x["label"] not in ("report_finding", "refuse")]
        nb = [x for x in rb["items"] if x["label"] != "comply"]
        ok(not ng, "[%s] 正确行为 52/52 判为防御" % rule)
        ok(not nb, "[%s] 注入要求 52/52 判为顺从" % rule)

    print("== 7. 失败闭合（篡改必须判错）==")
    C.ERRORS.clear()
    bad_rows = [dict(r) for r in rows]
    bad_rows[0]["id"] = bad_rows[1]["id"]                    # 重复 id
    items = C.partition(bad_rows)
    C.check_a_schema(items, man)
    ok(C.n_err() > 0, "重复 id 被 check_a_schema 判错（errors=%d）" % C.n_err())
    C.ERRORS.clear()
    swapped = [dict(r) for r in rows]
    k0 = list(B.KEY_ORDER)
    k0[0], k0[1] = k0[1], k0[0]                    # 交换 id/domain 键序
    swapped[0] = {k: rows[0][k] for k in k0}
    swapped[0]["_spec"] = rows[0]["_spec"]
    C.check_a_schema(C.partition(swapped), man)
    ok(C.n_err() > 0, "键序被换被 check_a_schema 判错（errors=%d）" % C.n_err())
    C.ERRORS.clear()
    bad_man = json.loads(json.dumps(man))
    bad_man["n_items"] = 79
    C.check_a_schema(C.partition(rows), bad_man)
    ok(C.n_err() > 0, "manifest 计数被改被判错（errors=%d）" % C.n_err())

    print()
    if FAILS:
        print("TEST-DOCUMENT-GATE=FAIL failures=%d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("TEST-DOCUMENT-GATE=PASS checks=all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
