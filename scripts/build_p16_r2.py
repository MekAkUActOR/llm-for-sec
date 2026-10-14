# -*- coding: utf-8 -*-
"""P1.6 二轮（主案 M2a）数据施工：良性侧风格先验回调（纯 CPU，确定性，fail-closed）。

权威规格：reports/p1.6-round2-design.md（§二 M2a 配方 / §五 施工规格）；
上游链 = reports/p1.6-calibration-design.md §6（G1–G12 门禁表）+ 一轮冻结件
data/dpo/p16-calibration/（manifest.json sha256 登记链）。

配方（M2a，单一机制变量 = 良性放行压力下调，只删不改 ✗✓ 零新生成）：
  - A 普通良性×放行：1,500 → **1,100**（确定性子选 seed=20261014）
  - D 诚实性·放行向（src_task=p16:D:release）：240 → **96**（同款子选）
  - D 拒绝向（conversational 120 + carrier 120）：240 原样
  - B 多轮良性 480 / C 判断教学 360 / E 稀释判断层 300 / F 恶意诚实对照 2,640：逐字节复制
  - 合计 5,216 = 良 2,336 : 恶 2,880 = 44.8 : 55.2（一轮 5,760 = 50:50）

数据源纪律（设计 §五.1/§五.2）：
  - 一轮三个 sha 登记件全量对账后才动工（两 release + 两 parts + 三 manifest）；
  - 子选与复制一律取**一轮合并件（release 文件）的原始行字节**——不重生、不再序列化
    （原 sha 链保持可验；release 行 = parts 行经角色归一后的确定性再序列化，一轮已冻结）；
  - 行级断言（设计 §五.4 子集完整性三项）：
      ① D 良 96 全部来自原 240（字节级 ∈）＋ A 1,100 全部来自原 1,500（字节级 ∈）
      ② D 恶 240 原样（120+120 逐字节）
      ③ B/C/E/F 与一轮逐字节一致（F = 整恶意文件 sha 恒等；B/C/E/D恶 = 按族抽取行串 sha 对拍）

产出（PREFLIGHT 防覆写：目标目录已存在即拒，零落盘 ✗）：
  data/dpo/p16-calibration-r2/
    parts-a-sub.jsonl          1,100 行（A 子选，按 id 升序）
    parts-d-sub.jsonl            336 行（D 重组 = 良 96 子选 + 恶 240 原样，按 id 升序）
    p16_benign_release.jsonl   2,336 行（A1,100+B480+C360+E300+D放行96，按 id 升序）
    p16_malicious_honest.jsonl 2,880 行（= 一轮恶意件逐字节副本，sha 恒等）
    manifest.json / README.md
  data/m5a-r2-run/dataset_info.json（三注册，多数据集装载——一轮 m5a CastError/GBK 两教训闭环 ✗✓
    ；LF parser.py 以 locale 默认编码（本机 GBK）open 本件 ⇒ 强制纯 ASCII，落盘前断言）

门禁时序约束（本脚本不做、但登记）：check_p16_calibration.py 的 G1 字节级扫描范围 =
data/dpo/**/*.jsonl（仅豁免一轮 data/dpo/p16-calibration/）⇒ 本目录落盘后重跑一轮 checker
会命中 r2 合法下游 id（5,216 个）——G1–G12 快检重跑必须**先于**本构建完成（已照办，
见 reports/p1.6-round2-build.md §三）；checker 零改动 ✗。

用法：.venv\\Scripts\\python.exe scripts\\build_p16_r2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P16_R1 = os.path.join(ROOT, "data", "dpo", "p16-calibration")
P16_R2 = os.path.join(ROOT, "data", "dpo", "p16-calibration-r2")
M5A_R2_RUN = os.path.join(ROOT, "data", "m5a-r2-run")
M4_BASE = os.path.join(ROOT, "data", "m4-run", "dpo_m4_capfix.jsonl")
GATE_REPORT = os.path.join(ROOT, "reports", "p1.6-gate-report.md")

SEED = 20261014
BUILT = "2026-10-14"
SPEC = "reports/p1.6-round2-design.md（§二 M2a 配方 / §五 施工规格 / §五.4 子集完整性）"

# ---- 一轮冻结 sha 常量（= data/dpo/p16-calibration/manifest.json 及两 parts manifest 登记值，
#      2026-10-14 施工前实测复核一致；对账不符即 fail-closed） ----
FROZEN_R1 = {
    "p16_benign_release.jsonl": "1636ba88c2f8834cdb581ea9c147e94990f28229c3665e5559375dd669daacc1",
    "p16_malicious_honest.jsonl": "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d",
    "parts-abd.jsonl": "c91bd6e0f47e60fa33e604911976a595f38fb928ac5399db993681459c5f99f0",
    "parts-cef.jsonl": "36238f7aa39091c654d1e0e53222696089830dbcf3222fc6dede7d0674a03e0a",
    "parts-abd.manifest.json": "a5e7f375d6f0a1a355841ea2b253ce625780a3eebc2411be0a14a0f6dcfa3368",
    "manifest-cef.json": "3fe846a4c6fe8f28980bcf3f368ba9ceb7233600c4bf300447b1119aa72d4447",
}
M4_BASE_SHA = "d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414"
M4_BASE_ROWS = 28842

# ---- M2a 组成契约（设计 §二 表；任一不符 ⇒ fail-closed，零落盘） ----
EXPECT = {
    "a_orig": 1500, "a_sub": 1100,
    "b": 480, "c": 360, "e": 300, "f": 2640,
    "d_good_orig": 240, "d_good_sub": 96,
    "d_evil_conv": 120, "d_evil_carrier": 120, "d_evil": 240,
    "benign_r2": 2336, "malicious_r2": 2880, "total_r2": 5216,
}
KEYS = {"dpo_class", "id", "pack", "lang", "polarity", "rejected_form", "archetype_id",
        "conversations", "chosen", "rejected", "src_task"}
D_GOOD_TASK = "p16:D:release"
D_EVIL_TASKS = ("p16:D:refuse_conversational", "p16:D:refuse_carrier")


def die(msg: str) -> None:
    print(f"[FATAL] {msg}")
    print("BUILD-P16-R2=FAIL（fail-closed，未落盘）")
    sys.exit(1)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_lines(path: str) -> tuple[bytes, list[bytes]]:
    """二进制整读 + 按行拆分（保留行内容、去终止符）；断言 LF 终止且无空行。"""
    raw = open(path, "rb").read()
    if not raw.endswith(b"\n"):
        die(f"{os.path.basename(path)} 不以 LF 结尾（冻结件形态意外）")
    lines = raw.split(b"\n")[:-1]
    if any(not ln.strip() for ln in lines):
        die(f"{os.path.basename(path)} 存在空行")
    return raw, lines


def meta(line: bytes) -> dict:
    """行级最小元数据（id/src_task/族/极性 + 键集校验）。"""
    r = json.loads(line)
    if set(r.keys()) != KEYS:
        die(f"键集不符：{r.get('id')}")
    fam = r["id"][4] if r["id"][:4] == "p16-" and len(r["id"]) > 4 else "?"
    return {"id": r["id"], "src_task": r["src_task"], "fam": fam, "polarity": r["polarity"]}


def subsample(lines: list[bytes], n: int) -> tuple[list[bytes], str, str, str]:
    """确定性子选（设计 §五.1「逐行抽头排序取前 N」）：
    key = sha256(b'p16-r2:{seed}:' + 原行字节) 十六进制**升序**（并列以 id 升序决断），
    取前 n 行；返回（按 id 升序的选中行, 选中阈值摘要 = 第 n 名 key, 首id, 末id）。"""
    keyed = sorted(
        (sha256_bytes(f"p16-r2:{SEED}:".encode() + ln), json.loads(ln)["id"], ln)
        for ln in lines
    )
    if n > len(keyed):
        die(f"子选 n={n} > 候选 {len(keyed)}")
    sel = [t[2] for t in keyed[:n]]
    sel.sort(key=lambda ln: json.loads(ln)["id"])
    threshold = keyed[n - 1][0]
    return sel, threshold, json.loads(sel[0]  )["id"], json.loads(sel[-1])["id"]


def family_sha(lines: list[bytes]) -> str:
    """按族抽取行串的确定性指纹：行按 id 升序拼接（含逐行 LF）。"""
    ordered = sorted(lines, key=lambda ln: json.loads(ln)["id"])
    return sha256_bytes(b"".join(ln + b"\n" for ln in ordered))


def dump_bytes(path: str, data: bytes, tag: str) -> None:
    with open(path, "wb") as f:
        f.write(data)
    print(f"[WRITE] {tag}: {len(data):,} B → {os.path.relpath(path, ROOT)}")


# ================================================================ 0. 预检 ==
def preflight() -> None:
    print("== 0. PREFLIGHT（fail-closed，零落盘） ==")
    for d in (P16_R2, M5A_R2_RUN):
        if os.path.exists(d):
            die(f"目标目录已存在（防覆写/防部分态）：{os.path.relpath(d, ROOT)}——"
                f"如确需重建请先人工移除（版本目录纪律 ✗）")
    # 门禁前置：一轮 G1–G12 判定必须为 PASS（快检重跑时序见模块 docstring 与构建报告）
    if not os.path.exists(GATE_REPORT):
        die(f"缺一轮门禁报告 {os.path.relpath(GATE_REPORT, ROOT)}")
    gate = open(GATE_REPORT, encoding="utf-8").read()
    if "P16-GATE=PASS" not in gate:
        die("一轮门禁报告不含 P16-GATE=PASS（发射链前置断裂）")
    print(f"[OK] output_dir NOT-EXIST ×2 ✓ · 一轮门禁 P16-GATE=PASS 在案 ✓")


# ================================================================ 1. 冻结对账 ==
def assert_frozen() -> None:
    print("== 1. 一轮冻结件全量对账（六个 sha 登记件） ==")
    for fn, want in FROZEN_R1.items():
        p = os.path.join(P16_R1, fn)
        if not os.path.exists(p):
            die(f"一轮冻结件缺失：{fn}")
        got = sha256_file(p)
        if got != want:
            die(f"一轮冻结件 sha 漂移：{fn} {got[:16]}… != 登记 {want[:16]}…")
        print(f"[OK] {fn}: sha256 …{got[:12]} 与登记一致 ✓")
    # manifest.json 登记与常量双源一致（belt）
    m = json.loads(open(os.path.join(P16_R1, "manifest.json"), encoding="utf-8").read())
    for fn in ("p16_benign_release.jsonl", "p16_malicious_honest.jsonl"):
        if m["files"][fn]["sha256"] != FROZEN_R1[fn]:
            die(f"manifest.json 登记 sha 与常量表不符：{fn}")
    # m4 基座（多数据集装载的 base 注册源，冻结常量）
    if not os.path.exists(M4_BASE):
        die(f"m4 基座缺失：{os.path.relpath(M4_BASE, ROOT)}")
    got = sha256_file(M4_BASE)
    if got != M4_BASE_SHA:
        die(f"m4 基座 sha 漂移：{got[:16]}… != {M4_BASE_SHA[:16]}…")
    rows = 0
    with open(M4_BASE, "rb") as f:
        for _ in f:
            rows += 1
    if rows != M4_BASE_ROWS:
        die(f"m4 基座行数 {rows} != {M4_BASE_ROWS}")
    print(f"[OK] m4 基座 dpo_m4_capfix.jsonl：{rows:,} 行 sha256 …{got[:12]} 冻结恒等 ✓")


# ================================================================ 2. 装载与分族 ==
def load_round1() -> dict:
    print("== 2. 一轮合并件装载与分族（字节级，不解析重序列化 ✗） ==")
    out = {}
    for name, path in (("benign", os.path.join(P16_R1, "p16_benign_release.jsonl")),
                       ("malicious", os.path.join(P16_R1, "p16_malicious_honest.jsonl"))):
        raw, lines = read_lines(path)
        out[f"{name}_raw"] = raw
        out[f"{name}_lines"] = lines
        out[f"{name}_by_fam"] = {}
        for ln in lines:
            mt = meta(ln)
            if name == "benign":
                key = mt["fam"]  # A/B/C/D/E（D 全部为放行向）
                if mt["fam"] == "D" and mt["src_task"] != D_GOOD_TASK:
                    die(f"良性件内 D 行 src_task 意外：{mt['id']} {mt['src_task']}")
                if mt["polarity"] != "benign_release":
                    die(f"良性件内极性意外：{mt['id']} {mt['polarity']}")
            else:
                if mt["fam"] == "F":
                    key = "F"
                    if mt["polarity"] != "malicious_refuse":
                        die(f"恶意件内 F 极性意外：{mt['id']}")
                elif mt["fam"] == "D":
                    if mt["src_task"] not in D_EVIL_TASKS:
                        die(f"恶意件内 D 行 src_task 意外：{mt['id']} {mt['src_task']}")
                    if mt["polarity"] != "malicious_refuse":
                        die(f"恶意件内 D 极性意外：{mt['id']}")
                    key = "D_evil"
                else:
                    die(f"恶意件内出现非 F/D 行：{mt['id']}")
            out[f"{name}_by_fam"].setdefault(key, []).append(ln)
        n = len(lines)
        print(f"[OK] {name}: {n:,} 行分族 "
              f"{ {k: len(v) for k, v in sorted(out[f'{name}_by_fam'].items())} }")
    # 组成契约
    b, m = out["benign_by_fam"], out["malicious_by_fam"]
    for fam, want in (("A", EXPECT["a_orig"]), ("B", EXPECT["b"]), ("C", EXPECT["c"]), ("E", EXPECT["e"]),
                      ("D", EXPECT["d_good_orig"])):
        if len(b.get(fam, [])) != want:
            die(f"良性件族 {fam} 行数 {len(b.get(fam, []))} != 一轮登记 {want}")
    if len(b["D"]) != EXPECT["d_good_orig"] or len(m.get("D_evil", [])) != EXPECT["d_evil"]:
        die("D 族行数与一轮登记不符")
    conv = sum(1 for ln in m["D_evil"] if json.loads(ln)["src_task"].endswith("conversational"))
    car = EXPECT["d_evil"] - conv
    if conv != EXPECT["d_evil_conv"] or car != EXPECT["d_evil_carrier"]:
        die(f"D 拒绝向组成意外：对话式 {conv} / 载体 {car}")
    if len(m["F"]) != EXPECT["f"]:
        die(f"恶意件族 F 行数 {len(m['F'])} != 一轮登记 {EXPECT['f']}")
    if len(out["benign_lines"]) != 2880 or len(out["malicious_lines"]) != 2880:
        die("一轮合并件行数非 2,880/2,880")
    print(f"[OK] 一轮组成契约闭合：良 2,880（A1,500+B480+C360+D放行240+E300）/"
          f"恶 2,880（F2,640+D拒绝240=对话{conv}+载体{car}）✓")
    return out


# ================================================================ 3. 子选与组装 ==
def build(r1: dict) -> dict:
    print("== 3. 确定性子选（seed=%d）与字节级组装 ==" % SEED)
    a_sub, a_thr, a_first, a_last = subsample(r1["benign_by_fam"]["A"], EXPECT["a_sub"])
    d_sub, d_thr, d_first, d_last = subsample(r1["benign_by_fam"]["D"], EXPECT["d_good_sub"])
    print(f"[OK] A 子选 {EXPECT['a_sub']}/{EXPECT['a_orig']}（阈值摘要 …{a_thr[:12]}，"
          f"id {a_first}…{a_last}）✓")
    print(f"[OK] D 良子选 {EXPECT['d_good_sub']}/{EXPECT['d_good_orig']}（阈值摘要 …{d_thr[:12]}，"
          f"id {d_first}…{d_last}）✓")

    def idsorted(lines: list[bytes]) -> list[bytes]:
        return sorted(lines, key=lambda ln: json.loads(ln)["id"])

    parts_a = idsorted(a_sub)
    parts_d = idsorted(d_sub + r1["malicious_by_fam"]["D_evil"])
    benign_r2 = idsorted(a_sub + r1["benign_by_fam"]["B"] + r1["benign_by_fam"]["C"]
                         + r1["benign_by_fam"]["E"] + d_sub)
    malicious_r2 = r1["malicious_raw"]  # 整文件逐字节副本（F 2,640 + D 恶 240 原样）

    return {
        "a_sub": a_sub, "d_sub": d_sub, "parts_a": parts_a, "parts_d": parts_d,
        "benign_r2": benign_r2, "malicious_r2": malicious_r2,
        "a_thr": a_thr, "d_thr": d_thr, "a_first": a_first, "a_last": a_last,
        "d_first": d_first, "d_last": d_last,
    }


# ================================================================ 4. 行级断言 ==
def assert_subset_integrity(r1: dict, r2: dict) -> dict:
    print("== 4. 子集完整性断言（设计 §五.4 三项 + 行数恒等式） ==")
    rep = {}

    def line_set(lines):
        return set(lines)

    # ① 子选行全部 ∈ 原件（字节级 + id 级，双向无重复）
    a_orig_set = line_set(r1["benign_by_fam"]["A"])
    d_orig_set = line_set(r1["benign_by_fam"]["D"])
    for tag, sel, orig_set, want, orig_n in (
            ("A", r2["a_sub"], a_orig_set, EXPECT["a_sub"], EXPECT["a_orig"]),
            ("D良", r2["d_sub"], d_orig_set, EXPECT["d_good_sub"], EXPECT["d_good_orig"])):
        if len(sel) != want:
            die(f"{tag} 子选行数 {len(sel)} != {want}")
        outside = [json.loads(ln)["id"] for ln in sel if ln not in orig_set]
        if outside:
            die(f"{tag} 子选 {len(outside)} 行不在原件字节集内：{outside[:5]}")
        ids = [json.loads(ln)["id"] for ln in sel]
        if len(set(ids)) != len(ids):
            die(f"{tag} 子选 id 重复")
        if not set(ids) <= {json.loads(ln)["id"] for ln in orig_set}:
            die(f"{tag} 子选 id 集溢出原件")
        rep[f"{tag}_sub_in_original"] = f"{want}/{want} 行逐字节 ∈ 原 {orig_n} 行 ✓"
        print(f"[OK] 断言① {tag} 子选 {want}/{want} 行逐字节 ∈ 原 {orig_n} ✓")

    # ② D 恶 240 原样（120 对话 + 120 载体，逐字节全量在场）
    evil = r1["malicious_by_fam"]["D_evil"]
    evil_set = line_set(evil)
    d_part_ids = {json.loads(ln)["id"] for ln in r2["parts_d"]}
    missing = [json.loads(ln)["id"] for ln in evil if ln not in set(r2["parts_d"])]
    if missing:
        die(f"D 恶 {len(missing)} 行未原样进 parts-d-sub：{missing[:5]}")
    conv = sum(1 for ln in evil if json.loads(ln)["src_task"].endswith("conversational"))
    rep["d_evil_unchanged"] = (f"240/240 行逐字节原样（对话式 {conv} + 载体 {EXPECT['d_evil'] - conv}）✓")
    print(f"[OK] 断言② D 恶 240/240 原样（对话 {conv} + 载体 {EXPECT['d_evil'] - conv}）✓")

    # ③ B/C/E/F 与一轮逐字节一致：
    #    F+D恶 = 整恶意文件 sha 恒等（= 一轮 manifest 登记值）；B/C/E（及 D恶）= 按族抽取行串 sha 对拍
    if sha256_bytes(r2["malicious_r2"]) != FROZEN_R1["p16_malicious_honest.jsonl"]:
        die("r2 恶意件 sha != 一轮登记值（F/D恶 逐字节复制破坏）")
    rep["f_whole_file_sha_round1_registered"] = FROZEN_R1["p16_malicious_honest.jsonl"]
    print(f"[OK] 断言③ F+D恶：r2 恶意件整文件 sha256 = 一轮登记 …{FROZEN_R1['p16_malicious_honest.jsonl'][:12]} ✓")

    # r2 良性件按族重抽（与一轮同法）后对拍
    r2_benign_by_fam: dict[str, list[bytes]] = {}
    for ln in r2["benign_r2"]:
        r2_benign_by_fam.setdefault(meta(ln)["fam"], []).append(ln)
    fam_sha_reg = {}
    for fam, r1_lines, r2_lines in (
            ("B", r1["benign_by_fam"]["B"], r2_benign_by_fam.get("B", [])),
            ("C", r1["benign_by_fam"]["C"], r2_benign_by_fam.get("C", [])),
            ("E", r1["benign_by_fam"]["E"], r2_benign_by_fam.get("E", [])),
            ("D放行(96子选)", r1["benign_by_fam"]["D"], r2_benign_by_fam.get("D", [])),
            ("F", r1["malicious_by_fam"]["F"], [ln for ln in r2["malicious_r2"].split(b"\n")[:-1]
                                                if json.loads(ln)["id"][4] == "F"]),
            ("D拒绝", r1["malicious_by_fam"]["D_evil"], [ln for ln in r2["malicious_r2"].split(b"\n")[:-1]
                                                         if json.loads(ln)["id"][4] == "D"]),
    ):
        if fam == "D放行(96子选)":
            s1, s2 = family_sha(r1_lines), family_sha(r2_lines)  # 子选族：登记两侧指纹（必不相同）
            fam_sha_reg[fam] = {"round1_rows": len(r1_lines), "r2_rows": len(r2_lines),
                                "note": "子选族（指纹不相等是预期；子集性由断言①保证）",
                                "round1_sha256": s1, "r2_sha256": s2}
            continue
        if len(r1_lines) != len(r2_lines):
            die(f"族 {fam} 行数不一致：一轮 {len(r1_lines)} / r2 {len(r2_lines)}")
        s1, s2 = family_sha(r1_lines), family_sha(r2_lines)
        if s1 != s2:
            die(f"族 {fam} 按族抽取行串 sha 不一致：一轮 {s1[:16]}… / r2 {s2[:16]}…（逐字节复制破坏）")
        fam_sha_reg[fam] = {"rows": len(r1_lines), "round1_sha256": s1, "r2_sha256": s2, "equal": True}
        print(f"[OK] 断言③ 族 {fam} {len(r1_lines)} 行按族行串 sha 对拍一致 …{s1[:12]} ✓")
    rep["family_sha256_vs_round1"] = fam_sha_reg

    # 行数恒等式：5,216 = 1,100+480+360+240+96+300+2,640 = 良 2,336 + 恶 2,880
    s = EXPECT["a_sub"] + EXPECT["b"] + EXPECT["c"] + EXPECT["d_evil"] + EXPECT["d_good_sub"] + EXPECT["e"] + EXPECT["f"]
    if s != EXPECT["total_r2"]:
        die(f"配方行数恒等式失效：{s} != {EXPECT['total_r2']}")
    nb, nm = len(r2["benign_r2"]), r2["malicious_r2"].count(b"\n")
    if nb != EXPECT["benign_r2"] or nm != EXPECT["malicious_r2"] or nb + nm != EXPECT["total_r2"]:
        die(f"产物行数 {nb}+{nm} != 良 {EXPECT['benign_r2']} + 恶 {EXPECT['malicious_r2']}")
    if len(r2["parts_a"]) != EXPECT["a_sub"] or len(r2["parts_d"]) != EXPECT["d_good_sub"] + EXPECT["d_evil"]:
        die("parts 件行数不符")
    rep["row_invariant"] = (f"5,216 = {EXPECT['a_sub']}+{EXPECT['b']}+{EXPECT['c']}+{EXPECT['d_evil']}"
                            f"+{EXPECT['d_good_sub']}+{EXPECT['e']}+{EXPECT['f']} = 良 {nb} + 恶 {nm} ✓")
    print(f"[OK] 行数恒等式：5,216 = 1,100+480+360+240+96+300+2,640 = 良 {nb:,} + 恶 {nm:,} ✓")

    # 全局 id 唯一 + id ⊆ 一轮 id 集 + 极性比
    all_ids = [json.loads(ln)["id"] for ln in r2["benign_r2"]] + \
              [json.loads(ln)["id"] for ln in r2["malicious_r2"].split(b"\n")[:-1]]
    if len(set(all_ids)) != len(all_ids):
        die("r2 全局 id 重复")
    r1_ids = {json.loads(ln)["id"] for ln in r1["benign_lines"]} | \
             {json.loads(ln)["id"] for ln in r1["malicious_lines"]}
    if not set(all_ids) <= r1_ids:
        die("r2 id 集溢出一轮（零新生成被破坏）")
    pct = 100.0 * nb / (nb + nm)
    rep["polarity_balance"] = {"benign_release": nb, "malicious_refuse": nm,
                               "benign_pct": round(pct, 2), "malicious_pct": round(100.0 - pct, 2)}
    print(f"[OK] 全局 id 唯一 {len(all_ids):,} 且 ⊆ 一轮 id 集 ✓ · 良:恶 = {nb}:{nm} "
          f"= {pct:.1f}:{100.0 - pct:.1f}（设计 44.8:55.2 ✓）")
    return rep


# ================================================================ 5. 分布统计 ==
def distributions(r2: dict) -> dict:
    def dist(rows: list) -> dict:
        out = {}
        for k in ("lang", "pack", "polarity", "dpo_class", "src_task"):
            out[k] = dict(sorted(Counter(r[k] for r in rows).items()))
        return out

    benign_rows = [json.loads(ln) for ln in r2["benign_r2"]]
    malicious_rows = [json.loads(ln) for ln in r2["malicious_r2"].split(b"\n")[:-1]]
    rows = benign_rows + malicious_rows
    by_family = {}
    for f in "ABCDEF":
        frows = [r for r in rows if r["id"][4] == f]
        by_family[f] = {"rows": len(frows), **dist(frows)}
    return {
        "overall": dist(rows),
        "by_family": by_family,
        "a_subdomain": dict(sorted(Counter(r["src_task"] for r in rows if r["id"][4] == "A").items())),
    }


# ================================================================ 6. 落盘 ==
def emit(r2: dict, integ: dict, dists: dict) -> dict:
    print("== 5. 落盘（先建 r2 目录，四 jsonl + manifest + README + 三注册 dataset_info） ==")
    os.makedirs(P16_R2, exist_ok=False)
    os.makedirs(M5A_R2_RUN, exist_ok=False)

    def join_lines(lines: list[bytes]) -> bytes:
        return b"".join(ln + b"\n" for ln in lines)

    files = {}
    for tag, data in (("parts-a-sub.jsonl", join_lines(r2["parts_a"])),
                      ("parts-d-sub.jsonl", join_lines(r2["parts_d"])),
                      ("p16_benign_release.jsonl", join_lines(r2["benign_r2"])),
                      ("p16_malicious_honest.jsonl", r2["malicious_r2"])):
        p = os.path.join(P16_R2, tag)
        dump_bytes(p, data, tag)
        files[tag] = {"rows": data.count(b"\n"), "bytes": len(data), "sha256": sha256_bytes(data)}

    # ---- dataset_info.json（三注册，多数据集装载；纯 ASCII 强制断言 —— GBK 教训闭环 ✗✓） ----
    tags = {
        "role_tag": "from", "content_tag": "value",
        "user_tag": "human", "assistant_tag": "gpt", "system_tag": "system",
    }
    cols = {"messages": "conversations", "chosen": "chosen", "rejected": "rejected"}

    def entry(file_name: str, note: str) -> dict:
        return {"file_name": file_name, "formatting": "sharegpt", "ranking": True,
                "columns": cols, "tags": tags, "note": note}

    ds = {
        "sec_dpo_m5a_r2_base_m4capfix": entry(
            "../m4-run/dpo_m4_capfix.jsonl",
            "M5A-R2 multi-dataset loading (round-2; see reports/p1.6-round2-build.md and "
            "reports/p1.6-round2-design.md section 5): base dpo_m4_capfix 28842 rows, sha256 "
            + M4_BASE_SHA + " = frozen constant of build_p16_r2.py (verified at build time, "
            "2026-10-14); byte-identical to the base segment of the round-1 m5a mix "
            "(erratum precedent: reports/m5a-preregistration.md section 7). ASCII-only note: "
            "LF parser.py opens this file with locale default encoding (GBK on this host), "
            "non-ASCII bytes break parsing."),
        "sec_dpo_m5a_r2_p16_benign": entry(
            "../dpo/p16-calibration-r2/p16_benign_release.jsonl",
            "M5A-R2 multi-dataset loading: p16-r2 benign_release 2336 rows = A 1100 "
            "(deterministic subsample from round-1 1500, seed 20261014) + B 480 + C 360 + "
            "E 300 + D-release 96 (subsample from round-1 240); sha256 "
            + files["p16_benign_release.jsonl"]["sha256"] + " = frozen constant of "
            "build_p16_r2.py; single 11-key homogeneous schema (round-1 SMOKE-M5A-MULTIDS "
            "precedent). ASCII-only note (GBK lesson, m5a erratum section 7)."),
        "sec_dpo_m5a_r2_p16_malicious": entry(
            "../dpo/p16-calibration-r2/p16_malicious_honest.jsonl",
            "M5A-R2 multi-dataset loading: p16-r2 malicious_honest 2880 rows = F 2640 + "
            "D-refuse 240 (conversational 120 + carrier 120), byte-identical copy of round-1 "
            "data/dpo/p16-calibration/p16_malicious_honest.jsonl, sha256 "
            + FROZEN_R1["p16_malicious_honest.jsonl"] + " = round-1 registered constant "
            "(re-verified 2026-10-14); single 11-key homogeneous schema. ASCII-only note "
            "(GBK lesson, m5a erratum section 7)."),
    }
    ds_txt = json.dumps(ds, ensure_ascii=True, indent=1) + "\n"
    ds_bytes = ds_txt.encode("utf-8")
    try:  # 纯 ASCII 强制断言（LF parser.py 以 locale 默认编码 GBK open 本件 —— 一轮 attempt-2 教训 ✗✓）
        ds_bytes.decode("ascii")
    except UnicodeDecodeError as e:
        die(f"dataset_info.json 非纯 ASCII：{e}")
    dump_bytes(os.path.join(M5A_R2_RUN, "dataset_info.json"), ds_bytes, "dataset_info.json (3 registrations)")

    # ---- manifest ----
    manifest = {
        "name": "p16-calibration-r2-release",
        "built": BUILT,
        "seed": SEED,
        "spec": SPEC,
        "recipe": "M2a 良性侧风格先验回调（p1.6-round2-design §二）：A 1,500→1,100 · D放行 240→96 · "
                  "B480/C360/E300/F2640/D恶240 逐字节不动 · 良 2,336:恶 2,880 = 44.8:55.2",
        "builder": "scripts/build_p16_r2.py",
        "checker": "scripts/check_p16_calibration.py（一轮 G1–G12 对一轮冻结件快检重跑；"
                   "r2 子集完整性断言 = 本 manifest subset_integrity + builder 行级断言）",
        "files": {
            "parts-a-sub.jsonl": {**files["parts-a-sub.jsonl"],
                                  "composition": "A 子选 1,100/1,500（seed=20261014，按 id 升序）"},
            "parts-d-sub.jsonl": {**files["parts-d-sub.jsonl"],
                                  "composition": "D 重组 336 = 放行向子选 96/240 + 拒绝向 240 原样（按 id 升序）"},
            "p16_benign_release.jsonl": {**files["p16_benign_release.jsonl"],
                                         "composition": "A 1,100 + B 480 + C 360 + E 300 + D放行 96（按 id 升序）"},
            "p16_malicious_honest.jsonl": {**files["p16_malicious_honest.jsonl"],
                                           "composition": "F 2,640 + D拒绝 240（= 一轮恶意件逐字节副本）"},
        },
        "subsample": {
            "algorithm": "key = sha256(b'p16-r2:{seed}:' + 一轮 release 原行字节) 十六进制升序"
                         "（并列以 id 升序决断），取前 N；产物按 id 升序。输入 = 一轮合并件原行字节"
                         "（不重生、不再序列化 ✗）",
            "seed": SEED,
            "A": {"n": EXPECT["a_sub"], "from": EXPECT["a_orig"], "threshold_digest": r2["a_thr"],
                  "first_id": r2["a_first"], "last_id": r2["a_last"]},
            "D_good": {"n": EXPECT["d_good_sub"], "from": EXPECT["d_good_orig"],
                       "threshold_digest": r2["d_thr"], "first_id": r2["d_first"], "last_id": r2["d_last"]},
        },
        "subset_integrity": integ,
        "distributions": dists,
        "lineage": {
            "round1_release": {
                "benign": {"file": "data/dpo/p16-calibration/p16_benign_release.jsonl", "rows": 2880,
                           "sha256": FROZEN_R1["p16_benign_release.jsonl"]},
                "malicious": {"file": "data/dpo/p16-calibration/p16_malicious_honest.jsonl", "rows": 2880,
                              "sha256": FROZEN_R1["p16_malicious_honest.jsonl"]},
                "manifest": {"file": "data/dpo/p16-calibration/manifest.json",
                             "note": "冻结链锚点（含 parts-abd/parts-cef 两级谱系）；"
                                     "施工前六件 sha 全量对账一致（见 builder 输出）"},
            },
            "round1_gate": "reports/p1.6-gate-report.md（P16-GATE=PASS；G1–G12 快检重跑于 r2 落盘前完成，"
                           "时序约束见 builder docstring 与 reports/p1.6-round2-build.md）",
            "m4_base": {"file": "data/m4-run/dpo_m4_capfix.jsonl", "rows": M4_BASE_ROWS,
                        "sha256": M4_BASE_SHA, "role": "多数据集装载 base 注册源（冻结常量）"},
            "registration": {
                "dataset_info": "data/m5a-r2-run/dataset_info.json",
                "sha256": sha256_bytes(ds_bytes),
                "entries": ["sec_dpo_m5a_r2_base_m4capfix", "sec_dpo_m5a_r2_p16_benign",
                            "sec_dpo_m5a_r2_p16_malicious"],
                "ascii_only": True,
                "note": "多数据集装载（一轮 m5a CastError/GBK 两教训闭环 ✗✓）；"
                        "训练配置 configs/m5a-dpo-r2.yaml（= m5a-dpo-probe 复制，仅 dataset 三注册 + "
                        "output_dir 三行差异，HP 零改动）",
            },
            "training_totals": {
                "rows": M4_BASE_ROWS + EXPECT["total_r2"],
                "formula": f"m4 base {M4_BASE_ROWS} + p16-r2 {EXPECT['total_r2']} = {M4_BASE_ROWS + EXPECT['total_r2']}",
                "p16r2_share_pct": round(100.0 * EXPECT["total_r2"] / (M4_BASE_ROWS + EXPECT["total_r2"]), 3),
                "full_epoch_steps": (M4_BASE_ROWS + EXPECT["total_r2"] + 15) // 16,
                "probe_visibility_300steps": "4,800 × 15.3% ≈ 735 行（σ≈25）",
            },
        },
        "g1_scan_interaction": {
            "status": "RESOLVED_BY_SEQUENCING",
            "decision": "r2 落点 data/dpo/p16-calibration-r2/ 在 check_p16_calibration.py G1 字节级扫描范围"
                        "（data/dpo/**/*.jsonl，仅豁免一轮 data/dpo/p16-calibration/）之内（设计定稿 §五.2 钉死落点，"
                        "版本目录纪律同 p16b 先例）；G1–G12 快检重跑已先于 r2 落盘完成（P16-GATE=PASS）",
            "consequence": "r2 落盘后再重跑一轮 checker 时，G1 将命中 r2 文件内的 p16 id 格式字面量"
                           "（5,216 个合法下游 id，同 data/m5a-run/manifest.json g1_scan_interaction "
                           "RESOLVED_BY_PLACEMENT 裁决的镜像情形：G1 职责 = 防 p16 泄漏到**不该含它**的文件，"
                           "下游消费件的合法内容非污染 ✗✓）；checker 零改动 ✗",
        },
        "version_discipline": "冻结 = 本 manifest sha256；任何修改 ⇒ 新开版本目录（p16-calibration-r3/…），"
                              "不得原地改 ✗（一轮 README 同款纪律）；重建 = 移除本目录后重跑 builder（确定性）",
    }
    mtxt = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    dump_bytes(os.path.join(P16_R2, "manifest.json"), mtxt.encode("utf-8"), "manifest.json")

    readme = f"""# P1.6 二轮拒绝校准对 · r2 release（M2a 良性侧风格先验回调，冻结件）

- 规格：`reports/p1.6-round2-design.md`（§二 M2a 配方 / §五 施工规格）· seed={SEED}
- 构建：`scripts/build_p16_r2.py`（纯 CPU，确定性子选 + 逐字节复制，PREFLIGHT 防覆写）·
  门禁 = 一轮 `scripts/check_p16_calibration.py` G1–G12 快检重跑（P16-GATE=PASS，
  先于本目录落盘）+ builder 行级子集完整性断言（fail-closed）

## 内容

| 文件 | 行数 | 组成 | sha256 |
|---|---|---|---|
| `parts-a-sub.jsonl` | 1,100 | A 子选 1,100/1,500 | `{files['parts-a-sub.jsonl']['sha256']}` |
| `parts-d-sub.jsonl` | 336 | D 重组 = 良 96/240 子选 + 恶 240 原样 | `{files['parts-d-sub.jsonl']['sha256']}` |
| `p16_benign_release.jsonl` | 2,336 | A 1,100 + B 480 + C 360 + E 300 + D放行 96 | `{files['p16_benign_release.jsonl']['sha256']}` |
| `p16_malicious_honest.jsonl` | 2,880 | F 2,640 + D拒绝 240（一轮件逐字节副本） | `{files['p16_malicious_honest.jsonl']['sha256']}` |

极性 良 2,336 : 恶 2,880 = 44.8 : 55.2（恶意占比 50→55.2%）；总量 5,216（一轮 5,760）；
子选算法/阈值摘要/按族 sha 对拍/全量分布见 `manifest.json`。

## 纪律

- 冻结 = `manifest.json` sha256；任何修改 ⇒ 新开版本目录，**不得原地改** ✗。
- 一轮 `data/dpo/p16-calibration/` 全链只读（施工前后六件 sha 对账一致）。
- G1 扫描交互：本目录在一轮 checker G1 字节扫描范围内 ⇒ 门禁重跑须先于本目录落盘（已照办）；
  事后重跑见 `manifest.json` `g1_scan_interaction`（checker 零改动 ✗）。
- 装载 = 多数据集三注册 `data/m5a-r2-run/dataset_info.json`（纯 ASCII ✗✓ GBK 教训）+
  `configs/m5a-dpo-r2.yaml`（HP 零改动）。

P16-R2-RELEASE=FROZEN
"""
    dump_bytes(os.path.join(P16_R2, "README.md"), readme.encode("utf-8"), "README.md")
    return {"files": files, "dataset_info_sha256": sha256_bytes(ds_bytes),
            "manifest_sha256": sha256_bytes(mtxt.encode("utf-8"))}


def main() -> int:
    print("== P1.6 二轮数据施工（build_p16_r2 · M2a） ==")
    preflight()
    assert_frozen()
    r1 = load_round1()
    r2 = build(r1)
    integ = assert_subset_integrity(r1, r2)
    dists = distributions(r2)
    out = emit(r2, integ, dists)

    print("\n== 施工完成 ==")
    for fn, info in out["files"].items():
        print(f"  {fn:<30} {info['rows']:>6,} 行  sha256 {info['sha256']}")
    print(f"  {'dataset_info.json':<30} {'3':>6} 注册  sha256 {out['dataset_info_sha256']}")
    print(f"  {'manifest.json':<30} {'':>6}       sha256 {out['manifest_sha256']}")
    print(f"  行数恒等式：5,216 = 1,100+480+360+240+96+300+2,640 ✓ · 良:恶 = 2,336:2,880 = 44.8:55.2 ✓")
    print("BUILD-P16-R2=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
