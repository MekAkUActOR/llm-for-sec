# -*- coding: utf-8 -*-
"""硬校验 data/lf/dpo_m3_v2.jsonl（失败即非零退出）。

覆盖（每条失败都打印样例，最多 10 条）：
  1. 行数 = 期望（由源文件重算：协议类保留数 + reserve 定容数）
  2. VERDICT 覆盖率 = 100%（每行两侧）
  3. VERDICT 行可 json.loads 且为 dict
  4. 键序严格 = action, verdict, confidence, findings, policy
  5. policy == 行 pack（唯一例外：policy 类 rejected 侧 == 行内 rejected_pack，
     这是源数据"错误包对照"的设计意图，逐字保留，计数并报告）
  6. chosen 与 rejected 的 VERDICT 不同（序列化后不等）
  7. id 全局唯一，且 ⊆ 源文件 id
  8. reserve 占比 ≤ 0.25（按总行数）；丢弃率 ≤ 5%（reserve 池）
  9. 协议类文本与源文件逐字一致：
       policy / refusal_quality / calibration -> chosen+rejected 逐字相同
       bt330_refusal -> chosen 逐字相同；rejected = 源文本 + 追加的 VERDICT 行
       reserve       -> 两侧 = 源文本 + 追加的 VERDICT 行（原文本逐字保留）
 10. 报告 reports/dpo-m3-v2-report.json 与实际文件一致（防报告过期）
 11. 值域：action ∈ {answer,refuse,propose}；
     verdict ∈ {allow,conditional,refuse,insufficient-context} 或
     （class=calibration 且 verdict=null，原协议）；confidence ∈ [0,1]；
     findings 为 list；pack ∈ {default,conservative,professional}
 12. 源文件未被改动（行数、类计数与基线一致）
可选：--rerun 用同一构建器重跑一遍到临时文件，比对字节（幂等/可复现）。

用法：python scripts/check_dpo_m3_v2.py [--rerun]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "lf" / "dpo_m3.jsonl"
V2 = ROOT / "data" / "lf" / "dpo_m3_v2.jsonl"
REPORT = ROOT / "reports" / "dpo-m3-v2-report.json"
STRICT_V2 = ROOT / "data" / "lf" / "dpo_m3_v2_strict.jsonl"
STRICT_REPORT = ROOT / "reports" / "dpo-m3-v2-strict-report.json"
Q_V2 = ROOT / "data" / "lf" / "dpo_m3_v2_q.jsonl"
Q_REPORT = ROOT / "reports" / "dpo-m3-v2-q-report.json"

VERDICT_KEYS = ["action", "verdict", "confidence", "findings", "policy"]
ACTION_VOCAB = {"answer", "refuse", "propose"}
VERDICT_VOCAB = {"allow", "conditional", "refuse", "insufficient-context"}
PACK_VOCAB = {"default", "conservative", "professional"}
PROTOCOL_CLASSES = {"policy", "bt330_refusal", "refusal_quality", "calibration"}
NEEDS_RENDER = {"reserve": ("chosen", "rejected"),
                "bt330_refusal": ("rejected",)}
VERBATIM_BOTH = {"policy", "refusal_quality", "calibration"}
RESERVE_SHARE_MAX = 0.25
DROP_RATE_MAX = 0.05
# 严格版"立场"字段：必须与 build_dpo_m3_v2.STANCE_FIELDS 一致，并由
# 严格版报告里的 strict_fields 交叉钉住（见 check_strict）。
STANCE_FIELDS = ("action", "verdict", "policy", "findings")
SRC_BASELINE_TOTAL = 47948          # 源文件基线（防被改写）
SRC_BASELINE_CLASSES = {"policy": 14688, "bt330_refusal": 1913,
                        "refusal_quality": 300, "calibration": 240,
                        "reserve": 30807}
VERDICT_LINE_RE = re.compile(r"(?m)^VERDICT:\s*(\{.*\})\s*$")


class Check:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.stats: dict = {}

    def fail(self, msg: str):
        if len(self.errors) < 10:
            self.errors.append(msg)
        elif len(self.errors) == 10:
            self.errors.append("... (更多错误已省略)")

    def warn(self, msg: str):
        if len(self.warnings) < 10:
            self.warnings.append(msg)


def split_verdict(text: str):
    """-> (前缀, VERDICT JSON 字符串) 或 (text, None)。"""
    m = VERDICT_LINE_RE.search(text or "")
    if not m:
        return text, None
    return text[:m.start()], m.group(1)


def load_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if line:
                yield ln, json.loads(line)


def solve_reserve_cap(n_protocol: int, share_max: float = RESERVE_SHARE_MAX) -> int:
    """独立复算定容公式：max r s.t. r/(n_protocol+r) <= share_max。"""
    cap = int((share_max * n_protocol) // (1 - share_max))
    while cap > 0 and cap / (n_protocol + cap) > share_max:
        cap -= 1
    while (cap + 1) / (n_protocol + cap + 1) <= share_max:
        cap += 1
    return cap


def check_reserve_ratio(ck: Check, n_reserve: int, n_total: int,
                        share_max: float = RESERVE_SHARE_MAX) -> float:
    """reserve 占比硬断言（可单测）。返回实测占比。"""
    share = n_reserve / n_total if n_total else 0.0
    if share > share_max:
        ck.fail(f"reserve 占比 {share:.6f} > {share_max}")
    return share


def stance_of(v: dict, fields: tuple = STANCE_FIELDS) -> tuple:
    """VERDICT 的"立场"投影（去掉 confidence）。"""
    return tuple(json.dumps(v.get(f), ensure_ascii=False, sort_keys=True)
                 for f in fields)


def has_stance_signal(ch: dict, rj: dict, fields: tuple = STANCE_FIELDS) -> bool:
    return stance_of(ch, fields) != stance_of(rj, fields)


def verdict_lines(r: dict):
    """-> (chosen VERDICT 行, rejected VERDICT 行)；缺行返回 None。"""
    out = []
    for side in ("chosen", "rejected"):
        m = VERDICT_LINE_RE.search(r.get(side, {}).get("value") or "")
        out.append(m.group(0) if m else None)
    return tuple(out)


def q_row_errors(r: dict, fields: tuple = STANCE_FIELDS) -> list[str]:
    """q 版逐行硬断言（可单测）：
      立场不同的对 → 两侧 VERDICT 必须不同；
      同立场的对   → 两侧 VERDICT 必须逐字相同（不得留人造置信差）。"""
    errs = []
    rid = r.get("id")
    ch = rj = None
    for side in ("chosen", "rejected"):
        pre, js = split_verdict(r.get(side, {}).get("value") or "")
        if js is None:
            return [f"{rid}: {side} 缺 VERDICT 行"]
        try:
            obj = json.loads(js)
        except json.JSONDecodeError:
            return [f"{rid}: {side} VERDICT 非法 JSON"]
        if side == "chosen":
            ch = obj
        else:
            rj = obj
    cs, rs = json.dumps(ch, ensure_ascii=False), json.dumps(rj, ensure_ascii=False)
    if has_stance_signal(ch, rj, fields):
        if cs == rs:
            # 防御性分支：逐字相同 ⇒ 立场必相同，实际不可达
            errs.append(f"{rid}: 立场不同的对两侧 VERDICT 却逐字相同")
    elif cs != rs:
        diff = "+".join(k for k in VERDICT_KEYS if ch.get(k) != rj.get(k))
        errs.append(f"{rid}: q 版同立场对两侧 VERDICT 未逐字相同"
                    f"（差异字段 {diff or '?'}；不得留人造置信差）")
    return errs


def strict_row_errors(r: dict, fields: tuple = STANCE_FIELDS) -> list[str]:
    """严格版逐行硬断言（可单测）：两侧立场必须不同。"""
    errs = []
    ch, rj = None, None
    for side in ("chosen", "rejected"):
        pre, js = split_verdict(r.get(side, {}).get("value") or "")
        if js is None:
            errs.append(f"{r.get('id')}: {side} 缺 VERDICT 行")
            return errs
        try:
            obj = json.loads(js)
        except json.JSONDecodeError:
            errs.append(f"{r.get('id')}: {side} VERDICT 非法 JSON")
            return errs
        if side == "chosen":
            ch = obj
        else:
            rj = obj
    if not has_stance_signal(ch, rj, fields):
        errs.append(f"{r.get('id')}: 两侧立场相同（{'+'.join(fields)} 全同，"
                    f"仅 confidence 不同）")
    return errs


def check_structure(ck: Check, path: Path = V2, strict: bool = False,
                    fields: tuple = STANCE_FIELDS,
                    collect_stats: dict | None = None, q: bool = False):
    """结构硬断言。统计写入 collect_stats（默认 ck.stats），避免严格版
    运行覆盖 v2 的统计。返回 {id: row}。

    q=True：改为 q 版口径（同立场对两侧 VERDICT 必须逐字相同）。
    """
    dst = ck.stats if collect_stats is None else collect_stats
    v2_rows: dict[str, dict] = {}
    by_class = Counter()
    vcov = Counter()
    act_dist = defaultdict(Counter)
    vcov_err = Counter()
    needs_render_seen = set()
    conf_only = Counter()
    same_stance = Counter()
    no_signal = Counter()
    reject_pack_exc = Counter()
    for ln, r in load_jsonl(path):
        rid, cls = r.get("id"), r.get("dpo_class")
        if rid is None or cls is None:
            ck.fail(f"line {ln}: 缺 id/dpo_class")
            continue
        if rid in v2_rows:
            ck.fail(f"{rid}: 重复 id")
        v2_rows[rid] = r
        by_class[cls] += 1
        if cls in NEEDS_RENDER:
            needs_render_seen.add(cls)
        if r.get("pack") not in PACK_VOCAB:
            ck.fail(f"{rid}: pack 非法 {r.get('pack')!r}")
        if not r["conversations"] or r["conversations"][-1]["from"] != "human":
            ck.fail(f"{rid}: conversations 结构异常")
        vs = {}
        for side in ("chosen", "rejected"):
            v = r.get(side, {}).get("value")
            if not isinstance(v, str) or not v.strip():
                ck.fail(f"{rid}: {side} 文本为空")
                continue
            pre, js = split_verdict(v)
            if js is None:
                ck.fail(f"{rid}: {side} 缺 VERDICT 行")
                continue
            try:
                obj = json.loads(js)
            except json.JSONDecodeError as e:
                ck.fail(f"{rid}: {side} VERDICT 非法 JSON ({e})")
                continue
            if not isinstance(obj, dict):
                ck.fail(f"{rid}: {side} VERDICT 非 dict")
                continue
            vcov[cls] += 1
            vs[side] = obj
            if list(obj) != VERDICT_KEYS:
                ck.fail(f"{rid}: {side} 键序/键集错误 {list(obj)}")
            if obj.get("action") not in ACTION_VOCAB:
                ck.fail(f"{rid}: {side} action 越界 {obj.get('action')!r}")
            vd = obj.get("verdict")
            if vd not in VERDICT_VOCAB:
                if cls == "calibration" and vd is None:
                    pass                       # 原协议允许 null
                else:
                    ck.fail(f"{rid}: {side} verdict 越界 {vd!r}")
            if not isinstance(obj.get("findings"), list):
                ck.fail(f"{rid}: {side} findings 非 list")
            cf = obj.get("confidence")
            if not isinstance(cf, (int, float)) or isinstance(cf, bool) \
                    or not (0.0 <= cf <= 1.0):
                ck.fail(f"{rid}: {side} confidence 越界 {cf!r}")
            act_dist[cls][obj.get("action")] += 1
            # 政策断言口径（父代理 2026-10-06 裁定）：
            #   chosen.policy  == row.pack                       （严格）
            #   rejected.policy == row.rejected_pack             （有该字段时：
            #       被拒回复引用它当时激活的"错误包"，是 policy 类的对照设计，
            #       也是该类唯一的偏好信号，不是缺陷）
            #   rejected.policy == row.pack                      （其余类，严格）
            pol, pack = obj.get("policy"), r.get("pack")
            if side == "chosen":
                if pol != pack:
                    vcov_err[cls] += 1
                    ck.fail(f"{rid}: chosen policy != pack ({pol!r} vs {pack!r})")
            else:
                rp = r.get("rejected_pack")
                if rp is not None:
                    reject_pack_exc[cls] += 1        # 对照设计，计数备查
                    if pol != rp:
                        vcov_err[cls] += 1
                        ck.fail(f"{rid}: rejected policy != rejected_pack "
                                f"({pol!r} vs {rp!r})")
                elif pol != pack:
                    vcov_err[cls] += 1
                    ck.fail(f"{rid}: rejected policy != pack ({pol!r} vs {pack!r})")
        if len(vs) == 2:
            if json.dumps(vs["chosen"], ensure_ascii=False) == \
                    json.dumps(vs["rejected"], ensure_ascii=False) and not q:
                # v2/strict：两侧 VERDICT 必须不同；q 版反过来（同立场对必须相同）
                ck.fail(f"{rid}: chosen VERDICT == rejected VERDICT")
            if (vs["chosen"]["action"], vs["chosen"]["verdict"]) == \
                    (vs["rejected"]["action"], vs["rejected"]["verdict"]):
                same_stance[cls] += 1
            a = {k: v for k, v in vs["chosen"].items() if k != "confidence"}
            b = {k: v for k, v in vs["rejected"].items() if k != "confidence"}
            if a == b:
                conf_only[cls] += 1
            if q:
                for e in q_row_errors(r, fields):
                    ck.fail(e)
            if not has_stance_signal(vs["chosen"], vs["rejected"], fields):
                no_signal[cls] += 1
                if strict:
                    ck.fail(f"{rid}: 两侧立场相同（{'+'.join(fields)} 全同，"
                            f"仅 confidence 不同）")
    dst.update({
        "file": str(path),
        "v2_total": len(v2_rows), "by_class": dict(by_class),
        "coverage_parsed_sides": sum(vcov.values()),
        "coverage_expected_sides": 2 * len(v2_rows),
        "action_dist": {k: dict(v) for k, v in act_dist.items()},
        "needs_render_seen": sorted(needs_render_seen),
        "policy_mismatch": dict(vcov_err),
        "rejected_pack_exception": dict(reject_pack_exc),
        "same_stance": dict(same_stance), "conf_only": dict(conf_only),
        "no_stance_signal": dict(no_signal),
        "no_stance_signal_total": sum(no_signal.values()),
        "verdict_coverage": {
            c: {"parsed": vcov.get(c, 0), "sides": 2 * by_class.get(c, 0),
                "rate": (vcov.get(c, 0) / (2 * by_class.get(c, 0)))
                if by_class.get(c) else None}
            for c in sorted(by_class)},
        "stance_fields": list(fields),
    })
    return v2_rows


def check_source_verbatim(ck: Check, v2_rows: dict):
    src_total = 0
    src_classes = Counter()
    matched = set()
    for ln, s in load_jsonl(SRC):
        src_total += 1
        scls = s["dpo_class"]
        src_classes[scls] += 1
        for side in NEEDS_RENDER.get(scls, ()):
            if s[side]["value"] != s[side]["value"].rstrip():
                ck.fail(f"{s['id']}: {side} 源文本带尾空白 {s[side]['value'][-8:]!r}"
                        f"（追加渲染会归一化它）")
        o = v2_rows.get(s["id"])
        if o is None:
            continue                               # 被丢弃/未抽样：正确
        matched.add(s["id"])
        if o["dpo_class"] != scls:
            ck.fail(f"{s['id']}: dpo_class 被改动")
        if o["conversations"] != s["conversations"]:
            ck.fail(f"{s['id']}: conversations 被改动")
        sides = NEEDS_RENDER.get(scls, ())
        for side in ("chosen", "rejected"):
            sv, ov = s[side]["value"], o[side]["value"]
            if side not in sides:
                if ov != sv:
                    ck.fail(f"{s['id']}: {side} 非渲染侧但文本被改动"
                            f"（{scls} 必须逐字一致）")
                continue
            pre, js = split_verdict(ov)
            if js is None:
                ck.fail(f"{s['id']}: {side} 无 VERDICT 行")
                continue
            # 追加语义：ov == sv + "\\n" + VERDICT 行，即前缀必须逐字等于源文本+换行
            if pre == sv + "\n":
                continue
            if pre == sv.rstrip("\n") + "\n" and sv != sv.rstrip("\n"):
                ck.fail(f"{s['id']}: {side} 源文本尾换行被归一化")
            else:
                ck.fail(f"{s['id']}: {side} 原文被改动（非单纯追加 VERDICT 行）"
                        f" prefix_len={len(pre)} src_len={len(sv)}")
        # 未在 NEEDS_RENDER 中的侧必须逐字
    ck.stats["src_total"] = src_total
    ck.stats["src_by_class"] = dict(src_classes)
    ck.stats["v2_rows_matched_in_src"] = len(matched)
    if src_total != SRC_BASELINE_TOTAL:
        ck.fail(f"源文件行数 {src_total} != 基线 {SRC_BASELINE_TOTAL}"
                f"（源文件可能被改动）")
    for cls, n in SRC_BASELINE_CLASSES.items():
        if src_classes.get(cls, 0) != n:
            ck.fail(f"源文件 {cls} 计数 {src_classes.get(cls, 0)} != 基线 {n}")
    missing = set(v2_rows) - matched
    if missing:
        ck.fail(f"{len(missing)} 个 v2 id 不在源文件中，例如 "
                f"{sorted(missing)[:3]}")


def check_counts_and_report(ck: Check, v2_rows: dict):
    s = ck.stats
    protocol_kept = sum(1 for r in v2_rows.values()
                        if r["dpo_class"] in PROTOCOL_CLASSES)
    cap = solve_reserve_cap(protocol_kept)
    n_reserve = sum(1 for r in v2_rows.values() if r["dpo_class"] == "reserve")
    expected_total = protocol_kept + cap
    s["protocol_kept"] = protocol_kept
    s["reserve_cap_recomputed"] = cap
    s["reserve_rows"] = n_reserve
    s["expected_total"] = expected_total
    if s["v2_total"] != expected_total:
        ck.fail(f"行数 {s['v2_total']} != 期望 {expected_total}")
    if n_reserve > cap:
        ck.fail(f"reserve 行数 {n_reserve} > 定容 {cap}")
    share = check_reserve_ratio(ck, n_reserve, s["v2_total"])
    s["reserve_share"] = share
    if s["coverage_parsed_sides"] != s["coverage_expected_sides"]:
        ck.fail(f"VERDICT 覆盖 {s['coverage_parsed_sides']}/"
                f"{s['coverage_expected_sides']} != 100%")
    s["coverage_rate"] = (s["coverage_parsed_sides"] / s["coverage_expected_sides"]
                          if s["coverage_expected_sides"] else 0.0)
    if s["coverage_rate"] != 1.0:
        ck.fail(f"VERDICT 覆盖率 {s['coverage_rate']:.6f} != 1.0")
    for cls in PROTOCOL_CLASSES:
        want = SRC_BASELINE_CLASSES[cls]
        got = s["by_class"].get(cls, 0)
        if cls != "bt330_refusal" and got != want:
            ck.fail(f"{cls} 行数 {got} != 源 {want}（协议类不得丢失）")
    n_drop = 0
    if not REPORT.exists():
        ck.fail("缺报告 reports/dpo-m3-v2-report.json")
        return
    rep0 = json.loads(REPORT.read_text(encoding="utf-8"))
    n_drop = (rep0.get("dropped_by_class") or {}).get("reserve", 0)
    if s["by_class"].get("bt330_refusal", 0) != \
            SRC_BASELINE_CLASSES["bt330_refusal"] \
            - (rep0.get("dropped_by_class") or {}).get("bt330_refusal", 0):
        ck.fail("bt330_refusal 行数与源-丢弃数不一致")
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    s["report_total"] = rep.get("total")
    if rep.get("total") != s["v2_total"]:
        ck.fail(f"报告 total {rep.get('total')} != 文件行数 {s['v2_total']}"
                f"（报告过期？）")
    if rep.get("by_class") != {k: s["by_class"].get(k, 0)
                               for k in rep.get("by_class", {})}:
        ck.fail("报告 by_class 与文件不一致")
    if rep.get("verdict_coverage_overall") != 1.0:
        ck.fail("报告 verdict_coverage_overall != 1.0")
    if abs(rep.get("reserve_share", -1) - share) > 1e-9:
        ck.fail(f"报告 reserve_share {rep.get('reserve_share')} != 实测 {share}")
    if rep.get("reserve_cap") != cap:
        ck.fail(f"报告 reserve_cap {rep.get('reserve_cap')} != 复算 {cap}")
    dp = rep.get("reserve_drop_rate_of_pool", 1.0)
    if dp > DROP_RATE_MAX:
        ck.fail(f"reserve 丢弃率 {dp:.6f} > {DROP_RATE_MAX}")
    s["report_reserve_drop_rate_of_pool"] = dp
    s["report_seed"] = rep.get("seed")
    s["report_dropped_by_class"] = rep.get("dropped_by_class")
    if abs(dp - n_drop / SRC_BASELINE_CLASSES["reserve"]) > 1e-9:
        ck.fail(f"报告丢弃率 {dp:.6f} != 复算 "
                f"{n_drop / SRC_BASELINE_CLASSES['reserve']:.6f}")
    s["reserve_unsampled"] = (SRC_BASELINE_CLASSES["reserve"] - n_drop - n_reserve)
    for rid in (rep.get("dropped_ids", {}).get("reserve", [])
                + rep.get("dropped_ids", {}).get("bt330_refusal", [])):
        if rid in v2_rows:
            ck.fail(f"{rid}: 已丢弃行仍出现在 v2 中")
    # 报告的 action 分布必须与实测一致
    for cls, dist in (rep.get("action_dist_by_class") or {}).items():
        if dist != s["action_dist"].get(cls, {}):
            ck.fail(f"报告 {cls} action 分布与实测不一致")


def check_strict(ck: Check, v2_rows: dict, strict_path: Path = STRICT_V2,
                 report_path: Path = STRICT_REPORT):
    """严格版（data/lf/dpo_m3_v2_strict.jsonl）校验：

    同一套结构断言 + "100% 两侧立场不同" + 必须严格是 v2 的子集（逐字相同）
    + 与 v2 的差集计数与严格版报告一致。（strict_path/report_path 可注入，
    便于用临时文件做反例测试。）
    """
    if not strict_path.exists():
        ck.fail(f"缺严格版文件 {strict_path}")
        return
    if not report_path.exists():
        ck.fail(f"缺严格版报告 {report_path}")
        return
    srep = json.loads(report_path.read_text(encoding="utf-8"))
    fields = tuple(srep.get("strict_fields") or ())
    if fields != STANCE_FIELDS:
        ck.fail(f"严格版报告 strict_fields={list(fields)} 与校验器口径 "
                f"{list(STANCE_FIELDS)} 不一致")
    # 1) 结构断言（strict=True ⇒ 每行两侧立场必须不同）
    # 1) 结构断言（strict=True ⇒ 每行两侧立场必须不同）；统计写入独立命名空间
    st: dict = {}
    st_rows = check_structure(ck, strict_path, strict=True,
                              fields=STANCE_FIELDS, collect_stats=st)
    st_total = len(st_rows)
    s = ck.stats
    s["strict_total"] = st_total
    for k in ("by_class", "no_stance_signal_total", "action_dist",
              "rejected_pack_exception", "verdict_coverage"):
        s["strict_" + k] = st.get(k)
    st_cov = (st["coverage_parsed_sides"] / st["coverage_expected_sides"]
              if st["coverage_expected_sides"] else 0.0)
    s["strict_coverage_rate"] = st_cov
    if len(st_rows) != st_total:                       # 重复 id 已由上面报错
        ck.fail("严格版存在重复 id")
    # 2) 子集 + 逐字一致
    only_strict = sorted(set(st_rows) - set(v2_rows))
    if only_strict:
        ck.fail(f"严格版有 {len(only_strict)} 行不在 v2 中，例如 {only_strict[:3]}")
    diff_bytes = 0
    for rid, r in st_rows.items():
        b = v2_rows.get(rid)
        if b is None:
            continue
        if json.dumps(r, ensure_ascii=False, sort_keys=True) != \
                json.dumps(b, ensure_ascii=False, sort_keys=True):
            diff_bytes += 1
            if diff_bytes <= 3:
                ck.fail(f"{rid}: 严格版行内容与 v2 不一致（应逐字相同）")
    if diff_bytes > 3:
        ck.fail(f"共 {diff_bytes} 行与 v2 内容不一致")
    # 3) 差集计数：独立从两个文件复算，必须等于报告
    diff = {"v2": len(v2_rows), "strict": st_total,
            "removed": len(v2_rows) - st_total}
    s["strict_diff"] = diff
    rem_class = Counter(r["dpo_class"] for rid, r in v2_rows.items()
                        if rid not in st_rows)
    s["strict_removed_by_class"] = {k: rem_class.get(k, 0)
                                    for k in st.get("by_class", {})}
    rep_diff = srep.get("diff_vs_v2") or {}
    if rep_diff.get("v2_total") != diff["v2"]:
        ck.fail(f"严格版报告 v2_total {rep_diff.get('v2_total')} != {diff['v2']}")
    if rep_diff.get("strict_total") != diff["strict"]:
        ck.fail(f"严格版报告 strict_total {rep_diff.get('strict_total')} "
                f"!= {diff['strict']}")
    if rep_diff.get("v2_only_rows") != diff["removed"]:
        ck.fail(f"严格版报告 v2_only_rows {rep_diff.get('v2_only_rows')} "
                f"!= 复算 {diff['removed']}")
    if rep_diff.get("strict_only_rows") != 0:
        ck.fail("严格版报告 strict_only_rows != 0（严格版必须是 v2 子集）")
    rep_rem = rep_diff.get("removed_by_class") or {}
    keys = set(rep_rem) | set(rem_class)
    if {k: rep_rem.get(k, 0) for k in keys} != \
            {k: rem_class.get(k, 0) for k in keys}:
        ck.fail(f"严格版报告 removed_by_class {rep_rem} "
                f"!= 复算 {dict(rem_class)}")
    if (srep.get("by_class") or {}) != {k: st["by_class"].get(k, 0)
                                        for k in srep.get("by_class", {})}:
        ck.fail("严格版报告 by_class 与文件不一致")
    v2c = v2_rows_by_class(v2_rows)
    for cls in set(rem_class) | set(st["by_class"]):
        if st["by_class"].get(cls, 0) + rem_class.get(cls, 0) != v2c.get(cls, 0):
            ck.fail(f"{cls}: strict({st['by_class'].get(cls, 0)}) + "
                    f"removed({rem_class.get(cls, 0)}) != v2 行数 "
                    f"{v2c.get(cls, 0)}")
    # 4) 覆盖率 / 占比 / 丢弃率
    if st_cov != 1.0:
        ck.fail(f"严格版 VERDICT 覆盖率 {st_cov:.6f} != 1.0")
    rep_cov = srep.get("verdict_coverage") or {}
    for cls, d in rep_cov.items():
        got = (st["verdict_coverage"].get(cls) or {}).get("rate")
        if d.get("rate") != got or d.get("parsed") != \
                (st["verdict_coverage"].get(cls) or {}).get("parsed"):
            ck.fail(f"严格版报告 {cls} 覆盖率 {d} != 实测 "
                    f"{st['verdict_coverage'].get(cls)}")
    share = check_reserve_ratio(ck, st["by_class"].get("reserve", 0), st_total)
    s["strict_reserve_share"] = share
    if abs(srep.get("reserve_share", -1) - share) > 1e-9:
        ck.fail(f"严格版报告 reserve_share {srep.get('reserve_share')} "
                f"!= 实测 {share}")
    if srep.get("verdict_coverage_overall") != 1.0:
        ck.fail("严格版报告 verdict_coverage_overall != 1.0")
    if srep.get("seed") != 20261001:
        ck.fail(f"严格版报告 seed {srep.get('seed')} != 20261001")
    if srep.get("total") != st_total:
        ck.fail(f"严格版报告 total {srep.get('total')} != 文件行数 {st_total}")
    dp = srep.get("reserve_drop_rate_of_pool", 1.0)
    if dp > DROP_RATE_MAX:
        ck.fail(f"严格版 reserve 丢弃率 {dp:.6f} > {DROP_RATE_MAX}")
    if st["no_stance_signal_total"]:
        ck.fail(f"严格版仍有 {st['no_stance_signal_total']} 行两侧立场相同")
    s["strict_no_stance_signal"] = st["no_stance_signal_total"]
    s["strict_signal_rate"] = 1.0 if not st["no_stance_signal_total"] else 0.0
    # 5) 被剔除行必须真的"无立场信号"（反查，防止多删/误删）
    bad_removed = []
    for rid, r in v2_rows.items():
        if rid in st_rows:
            continue
        ch = json.loads(split_verdict(r["chosen"]["value"])[1])
        rj = json.loads(split_verdict(r["rejected"]["value"])[1])
        if has_stance_signal(ch, rj, STANCE_FIELDS):
            bad_removed.append(rid)
    if bad_removed:
        ck.fail(f"{len(bad_removed)} 行有立场信号却被剔除，例如 "
                f"{bad_removed[:3]}")


def v2_rows_by_class(rows: dict) -> Counter:
    c = Counter()
    for r in rows.values():
        c[r["dpo_class"]] += 1
    return c


def check_q(ck: Check, v2_rows: dict, q_path: Path = Q_V2,
            report_path: Path = Q_REPORT):
    """q 版（data/lf/dpo_m3_v2_q.jsonl）校验：

    同一套结构断言 + q 口径（同立场对两侧 VERDICT 必须逐字相同、立场不同的对
    必须不同）+ 与 v2 的差异必须**只**落在同立场对 rejected 侧的 confidence
    数字上（逐行 diff 复算），且必须是 v2 的完整行集（无增删）。
    """
    if not q_path.exists():
        ck.fail(f"缺 q 版文件 {q_path}")
        return
    if not report_path.exists():
        ck.fail(f"缺 q 版报告 {report_path}")
        return
    qrep = json.loads(report_path.read_text(encoding="utf-8"))
    if list(qrep.get("stance_fields") or []) != list(STANCE_FIELDS):
        ck.fail(f"q 版报告 stance_fields={qrep.get('stance_fields')} 与校验器"
                f"口径 {list(STANCE_FIELDS)} 不一致")
    qst: dict = {}
    q_rows = check_structure(ck, q_path, q=True, fields=STANCE_FIELDS,
                             collect_stats=qst)
    s = ck.stats
    s["q_total"] = len(q_rows)
    for k in ("by_class", "no_stance_signal_total", "action_dist",
              "verdict_coverage"):
        s["q_" + k] = qst.get(k)
    q_cov = (qst["coverage_parsed_sides"] / qst["coverage_expected_sides"]
             if qst["coverage_expected_sides"] else 0.0)
    s["q_coverage_rate"] = q_cov
    if q_cov != 1.0:
        ck.fail(f"q 版 VERDICT 覆盖率 {q_cov:.6f} != 1.0")
    # 1) 行集必须与 v2 完全一致（无增无删）
    if set(q_rows) != set(v2_rows):
        add = sorted(set(q_rows) - set(v2_rows))
        rm = sorted(set(v2_rows) - set(q_rows))
        ck.fail(f"q 版与 v2 行集不一致：多 {len(add)} 少 {len(rm)}"
                f"（例如 {add[:3]} / {rm[:3]}）")
    # 2) 逐行 diff：只允许同立场对 rejected 侧 VERDICT 行变化（chosen 不动、
    #    前缀逐字不动、差异字段只能是 confidence）
    changed, chosen_changed, prefix_changed, other_field_changed = [], 0, 0, []
    for rid, qr in q_rows.items():
        b = v2_rows.get(rid)
        if b is None:
            continue
        if qr["chosen"]["value"] != b["chosen"]["value"]:
            chosen_changed += 1
            ck.fail(f"{rid}: q 版 chosen 侧被改动（不得改动）")
        if qr["rejected"]["value"] == b["rejected"]["value"]:
            continue
        changed.append(rid)
        pre_o, _ = split_verdict(b["rejected"]["value"])
        pre_n, _ = split_verdict(qr["rejected"]["value"])
        if pre_o != pre_n:
            prefix_changed += 1
            ck.fail(f"{rid}: q 版 rejected 原文前缀被改动")
        a = json.loads(split_verdict(b["rejected"]["value"])[1])
        z = json.loads(split_verdict(qr["rejected"]["value"])[1])
        fld = [k for k in VERDICT_KEYS if a.get(k) != z.get(k)]
        if fld != ["confidence"]:
            other_field_changed.append((rid, fld))
            if len(other_field_changed) <= 3:
                ck.fail(f"{rid}: q 版与 v2 差异字段为 {fld}（应只有 confidence）")
    s["q_changed_rows"] = len(changed)
    s["q_chosen_changed"] = chosen_changed
    s["q_prefix_changed"] = prefix_changed
    if other_field_changed:
        ck.fail(f"共 {len(other_field_changed)} 行差异字段不止 confidence")
    # 3) 报告一致性
    dv = qrep.get("diff_vs_v2") or {}
    if qrep.get("total") != len(q_rows):
        ck.fail(f"q 版报告 total {qrep.get('total')} != 文件行数 {len(q_rows)}")
    if (qrep.get("by_class") or {}) != {k: qst["by_class"].get(k, 0)
                                        for k in qrep.get("by_class", {})}:
        ck.fail("q 版报告 by_class 与文件不一致")
    share = check_reserve_ratio(ck, qst["by_class"].get("reserve", 0),
                               len(q_rows))
    s["q_reserve_share"] = share
    if abs(qrep.get("reserve_share", -1) - share) > 1e-9:
        ck.fail(f"q 版报告 reserve_share {qrep.get('reserve_share')} "
                f"!= 实测 {share}")
    if qrep.get("verdict_coverage_overall") != 1.0:
        ck.fail("q 版报告 verdict_coverage_overall != 1.0")
    if qrep.get("seed") != 20261001:
        ck.fail(f"q 版报告 seed {qrep.get('seed')} != 20261001")
    if dv.get("rows_changed") != len(changed):
        ck.fail(f"q 版报告 rows_changed {dv.get('rows_changed')} "
                f"!= 复算 {len(changed)}")
    if sorted(dv.get("changed_ids") or []) != sorted(changed):
        ck.fail("q 版报告 changed_ids 与复算不一致")
    if dv.get("rows_identical") != len(q_rows) - len(changed):
        ck.fail("q 版报告 rows_identical 与复算不一致")
    for k, v in (dv.get("side_diff_counts") or {}).items():
        want = {"chosen_side_changed": chosen_changed,
                "rejected_side_changed": len(changed),
                "rejected_prefix_changed": prefix_changed,
                "row_added": len(set(q_rows) - set(v2_rows)),
                "row_removed": len(set(v2_rows) - set(q_rows))}.get(k)
        if want is not None and v != want:
            ck.fail(f"q 版报告 side_diff_counts[{k}]={v} != 复算 {want}")
    # 4) 同立场对 ↔ 逐字相同对：计数必须相等，且与 v2 报告的 tiebreak 数一致
    ss = (qrep.get("same_stance_pairs") or {}).get("total")
    idv = (qrep.get("identical_verdict_pairs") or {}).get("total")
    if ss != qst["no_stance_signal_total"]:
        ck.fail(f"q 版报告 same_stance_pairs {ss} != 实测 "
                f"{qst['no_stance_signal_total']}")
    if idv != len(changed):
        ck.fail(f"q 版报告 identical_verdict_pairs {idv} != 复算 "
                f"{len(changed)}（同立场对必须逐字相同）")
    rep0 = json.loads(REPORT.read_text(encoding="utf-8"))
    tb = sum((rep0.get("output_pairs_confidence_tiebreak_by_class")
              or {}).values())
    writer = dv.get("changed_writer_dist") or {}
    s["q_tiebreak_removed"] = writer.get("artificial_tiebreak_0.02")
    s["q_natural_conf_removed"] = writer.get("natural_confidence_diff")
    if writer.get("artificial_tiebreak_0.02") != tb:
        ck.fail(f"q 版报告 artificial_tiebreak {writer.get('artificial_tiebreak_0.02')}"
                f" != v2 报告的 tiebreak 总数 {tb}")
    if (writer.get("artificial_tiebreak_0.02", 0)
            + writer.get("natural_confidence_diff", 0)) != len(changed):
        ck.fail("q 版报告 changed_writer_dist 之和 != 复算改动行数")
    if len(changed) != qst["no_stance_signal_total"]:
        ck.fail(f"改动行数 {len(changed)} != 同立场对 "
                f"{qst['no_stance_signal_total']}（应一一对应）")
    # 5) 消融一致性：strict 只取立场不同的对 ⇒ 由 v2 或 q 生成的 strict 相同
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_dpo_m3_v2 as B                            # noqa: PLC0415
    st_v2, _ = B.strict_filter(list(v2_rows.values()), STANCE_FIELDS)
    st_q, _ = B.strict_filter(list(q_rows.values()), STANCE_FIELDS)
    ids_v2 = sorted(r["id"] for r in st_v2)
    ids_q = sorted(r["id"] for r in st_q)
    if ids_v2 != ids_q:
        ck.fail("strict 由 v2 与由 q 生成的行集不一致（应完全相同）")


def check_rerun(ck: Check):
    """用同一构建器重跑（输出到临时文件），比对字节 => 幂等/可复现。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_dpo_m3_v2 as B                            # noqa: PLC0415
    with tempfile.TemporaryDirectory() as td:
        tmp_out = Path(td) / "dpo_m3_v2.jsonl"
        tmp_rep = Path(td) / "report.json"
        res, _ = B.build(B.SRC)
        rep = B.summarize(res, B.SEED)
        B.write_outputs(res["out_rows"], rep, out=tmp_out, report_path=tmp_rep)
        h1 = hashlib.sha256(V2.read_bytes()).hexdigest()
        h2 = hashlib.sha256(tmp_out.read_bytes()).hexdigest()
        ck.stats["rerun_sha256"] = h2
        ck.stats["v2_sha256"] = h1
        if h1 != h2:
            ck.fail(f"重跑字节不一致: {h1[:16]} vs {h2[:16]}（非幂等）")
        r1 = json.loads(REPORT.read_text(encoding="utf-8"))
        r2 = json.loads(tmp_rep.read_text(encoding="utf-8"))
        if json.dumps(r1, sort_keys=True, ensure_ascii=False) != \
                json.dumps(r2, sort_keys=True, ensure_ascii=False):
            ck.fail("重跑报告与已提交报告不一致")
        # 严格版同样复算（子集筛选 + 报告），比对字节
        if STRICT_V2.exists():
            st_rows, removed = B.strict_filter(res["out_rows"],
                                               tuple(STANCE_FIELDS))
            srep = B.summarize_strict(st_rows, removed, res["out_rows"], rep,
                                      res, B.SEED, tuple(STANCE_FIELDS))
            tmp_s = Path(td) / "dpo_m3_v2_strict.jsonl"
            tmp_sr = Path(td) / "strict-report.json"
            B.write_outputs(st_rows, srep, out=tmp_s, report_path=tmp_sr)
            h3 = hashlib.sha256(STRICT_V2.read_bytes()).hexdigest()
            h4 = hashlib.sha256(tmp_s.read_bytes()).hexdigest()
            ck.stats["strict_sha256"] = h3
            ck.stats["strict_rerun_sha256"] = h4
            if h3 != h4:
                ck.fail(f"严格版重跑字节不一致: {h3[:16]} vs {h4[:16]}")
            s1 = json.loads(STRICT_REPORT.read_text(encoding="utf-8"))
            s2 = json.loads(tmp_sr.read_text(encoding="utf-8"))
            if json.dumps(s1, sort_keys=True, ensure_ascii=False) != \
                    json.dumps(s2, sort_keys=True, ensure_ascii=False):
                ck.fail("严格版重跑报告与已提交报告不一致")
        # q 版同样复算（同立场对共用 chosen VERDICT），比对字节
        if Q_V2.exists():
            q_rows, changes = B.q_apply(res["out_rows"],
                                        tie_ids=res.get("tie_ids"),
                                        fields=tuple(STANCE_FIELDS))
            qrep = B.summarize_q(q_rows, changes, res["out_rows"], rep, res,
                                 B.SEED, tuple(STANCE_FIELDS))
            tmp_q = Path(td) / "dpo_m3_v2_q.jsonl"
            tmp_qr = Path(td) / "q-report.json"
            B.write_outputs(q_rows, qrep, out=tmp_q, report_path=tmp_qr)
            h5 = hashlib.sha256(Q_V2.read_bytes()).hexdigest()
            h6 = hashlib.sha256(tmp_q.read_bytes()).hexdigest()
            ck.stats["q_sha256"] = h5
            ck.stats["q_rerun_sha256"] = h6
            if h5 != h6:
                ck.fail(f"q 版重跑字节不一致: {h5[:16]} vs {h6[:16]}")
            q1 = json.loads(Q_REPORT.read_text(encoding="utf-8"))
            q2 = json.loads(tmp_qr.read_text(encoding="utf-8"))
            if json.dumps(q1, sort_keys=True, ensure_ascii=False) != \
                    json.dumps(q2, sort_keys=True, ensure_ascii=False):
                ck.fail("q 版重跑报告与已提交报告不一致")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true",
                    help="用构建器重跑并比对字节（慢，约 25s）")
    ap.add_argument("--no-strict", action="store_true",
                    help="跳过严格版校验")
    ap.add_argument("--no-q", action="store_true",
                    help="跳过 q 版校验")
    args = ap.parse_args(argv)
    ck = Check()
    if not V2.exists():
        print(f"CHECK_FAIL: 缺文件 {V2}")
        return 2
    v2_rows = check_structure(ck)
    check_source_verbatim(ck, v2_rows)
    check_counts_and_report(ck, v2_rows)
    if not args.no_strict:
        check_strict(ck, v2_rows)
    if not args.no_q:
        check_q(ck, v2_rows)
    if args.rerun:
        check_rerun(ck)
    s = ck.stats
    print("== 摘要 ==")
    print(json.dumps({k: s[k] for k in (
        "src_total", "v2_total", "expected_total", "by_class",
        "protocol_kept", "reserve_cap_recomputed", "reserve_rows",
        "reserve_share", "reserve_unsampled", "coverage_rate",
        "rejected_pack_exception", "same_stance", "conf_only",
        "report_seed", "report_reserve_drop_rate_of_pool",
        "strict_total", "strict_diff", "strict_removed_by_class",
        "strict_reserve_share", "strict_no_stance_signal",
        "strict_coverage_rate", "strict_by_class",
        "no_stance_signal_total",
        "q_total", "q_reserve_share", "q_coverage_rate", "q_changed_rows",
        "q_tiebreak_removed", "q_natural_conf_removed", "q_chosen_changed",
        "q_prefix_changed", "q_by_class",
        "v2_sha256", "rerun_sha256",
        "strict_sha256", "strict_rerun_sha256",
        "q_sha256", "q_rerun_sha256") if k in s},
        ensure_ascii=False, indent=2))
    if ck.warnings:
        print("warnings:", ck.warnings)
    for e in ck.errors:
        print("ERROR:", e)
    print(f"CHECK_{'PASS' if not ck.errors else 'FAIL'} errors={len(ck.errors)}")
    return 0 if not ck.errors else 1


if __name__ == "__main__":
    sys.exit(main())
