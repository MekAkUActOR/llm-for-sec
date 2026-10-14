# -*- coding: utf-8 -*-
"""P1.6 三轮（备选案 M2b）数据施工：D 良单旋钮（纯 CPU，确定性，fail-closed）。

权威规格：reports/p1.6-round2-design.md **§七（M2b 预注册，配方与预测已冻结）**
+ §五（施工规格，二轮已验证流程照抄）；上游链 = data/dpo/p16-calibration/ 一轮冻结件
（manifest.json sha256 登记链）+ data/dpo/p16-calibration-r2/ 二轮冻结件（只读）。

配方（M2b，单一机制变量 = D 良最小对强度下调，只删不改 ✗✓ 零新生成；与一轮唯一差异 = D 良子选）：
  - A 普通良性×放行：1,500 **原样**（全量逐字节复制，不子选）
  - D 诚实性·放行向（src_task=p16:D:release）：240 → **96**（确定性子选 seed=20261014m2b）
  - D 拒绝向（conversational 120 + carrier 120）：240 原样
  - B 多轮良性 480 / C 判断教学 360 / E 稀释判断层 300 / F 恶意诚实对照 2,640：逐字节复制
  - 合计 5,616 = 良 2,736 : 恶 2,880 = 48.7 : 51.3（一轮 5,760 = 50:50、二轮 5,216 = 44.8:55.2）

子选算法（与二轮 build_p16_r2.py 逐字同款，仅轮次标签/seed 按设计 §七 更新，manifest 全登记可独立复算）：
  key = sha256(b'p16-r3:20261014m2b:' + 一轮 release 原行字节) 十六进制**升序**
  （并列以 id 升序决断），取前 N，产物按 id 升序。二轮先例前缀 = b'p16-r2:20261014:'。

数据源纪律（§五.1/§五.2 照抄）：
  - 一轮三个 sha 登记件全量对账后才动工（两 release + 两 parts + 三 manifest）；
    二轮冻结件只读复核（4 jsonl + dataset_info sha 对 r2 manifest 登记值）；
  - 子选与复制一律取**一轮合并件（release 文件）的原始行字节**——不重生、不再序列化
    （原 sha 链保持可验）；
  - 行级断言（恒等式 + 子集完整性）：
      ① D 良 96 全部来自原 240（字节级 ∈，id 级双向）
      ② D 恶 240 原样（120+120 逐字节）
      ③ A/B/C/E/F/D恶 与一轮逐字节一致（F+D恶 = 整恶意文件 sha = 一轮登记值；
         六族按族抽取行串 sha 双侧对拍全等——A 为全量复制，指纹必须相等）
      ④ 行数恒等式 5,616 = 1500+480+360+240+96+300+2640 = 良 2,736 + 恶 2,880
      ⑤ 全局 id 唯一 5,616 且 ⊆ 一轮 id 集（零新生成）

门禁时序处置（本脚本不做、但登记；二轮 RESOLVED_BY_SEQUENCING 先例 + 任务书钉死）：
  check_p16_calibration.py 的 G1 字节级扫描范围 = data/dpo/**/*.jsonl（仅豁免一轮
  data/dpo/p16-calibration/）。**r2（p16-calibration-r2/，5,216 个合法下游 id）已在
  扫描范围内 ⇒ 任何时点全量重跑 checker 都会 G1 误触 r2+r3 的 id**（合法下游消费件
  非污染，同 data/m5a-run/manifest.json g1_scan_interaction 裁决镜像）。故三轮快检
  **不跑全 checker**，替代 = ①一轮 release 冻结件 sha 复验未动（本脚本 assert_frozen
  施工前后双跑）+ ②r3 行级子集断言（本脚本 assert_subset_integrity + 独立核验
  scripts/_tmp_p16_r3_verify.py）；checker 零改动 ✗。

产出（PREFLIGHT 防覆写：目标路径已存在即拒，零落盘 ✗）：
  data/dpo/p16-calibration-r3/
    parts-d-sub.jsonl            336 行（D 重组 = 良 96 子选 + 恶 240 原样，按 id 升序）
    p16_benign_release.jsonl   2,736 行（A1,500+B480+C360+E300+D放行96，按 id 升序）
    p16_malicious_honest.jsonl 2,880 行（= 一轮恶意件逐字节副本，sha 恒等）
    manifest.json / README.md
  data/m5a-r3-run/dataset_info.json（三注册，多数据集装载——一轮 m5a CastError/GBK 两教训
    闭环 ✗✓；LF parser.py 以 locale 默认编码（本机 GBK）open 本件 ⇒ 强制纯 ASCII，落盘前断言）

用法：.venv\\Scripts\\python.exe scripts\\build_p16_r3.py
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
P16_R3 = os.path.join(ROOT, "data", "dpo", "p16-calibration-r3")
M5A_R3_RUN = os.path.join(ROOT, "data", "m5a-r3-run")
M4_BASE = os.path.join(ROOT, "data", "m4-run", "dpo_m4_capfix.jsonl")
GATE_REPORT = os.path.join(ROOT, "reports", "p1.6-gate-report.md")
CKPT_R3 = os.path.join(ROOT, "checkpoints", "qwen3-06b-sec-m5a-dpo-r3")
CFG_R3 = os.path.join(ROOT, "configs", "m5a-dpo-r3.yaml")
REPORT_R3 = os.path.join(ROOT, "reports", "p1.6-round3-build.md")

SEED = "20261014m2b"           # 设计 §七 钉死（字符串 seed；二轮先例 = 整数 20261014）
SUB_PREFIX = f"p16-r3:{SEED}:"  # 子选哈希前缀（二轮先例 = "p16-r2:20261014:"）
BUILT = "2026-10-14"
SPEC = ("reports/p1.6-round2-design.md §七（M2b 预注册，配方与预测已冻结）"
        "+ §五（施工规格，二轮已验证流程照抄）")

# ---- 一轮冻结 sha 常量（= data/dpo/p16-calibration/manifest.json 及两 parts manifest 登记值，
#      与二轮 build_p16_r2.py 常量表逐字一致；对账不符即 fail-closed） ----
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

# ---- 二轮冻结 sha 常量（= data/dpo/p16-calibration-r2/manifest.json 登记值 + r2 注册件；
#      二轮冻结件只读纪律的机器证据，对账不符即 fail-closed） ----
FROZEN_R2 = {
    "parts-a-sub.jsonl": "230fa5cb47e008bfbd08207c9b5a632bed417790a43a15713ad39b3b039c3507",
    "parts-d-sub.jsonl": "b804dd4d5a7cc44e07b79355c1fa088462f5602824bac503b22edfbe355cf398",
    "p16_benign_release.jsonl": "c55da1e8d05dcaf648ee0bbc690fae066913960bf787e6e41761641c5bc5e183",
    "p16_malicious_honest.jsonl": "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d",
}
R2_DSINFO_SHA = "1c0788e4cce250cf2254f4eafd4b243a2de075c341324da6449af38dbae66539"

# ---- M2b 组成契约（设计 §七；任一不符 ⇒ fail-closed，零落盘） ----
EXPECT = {
    "a": 1500, "b": 480, "c": 360, "e": 300, "f": 2640,
    "d_good_orig": 240, "d_good_sub": 96,
    "d_evil_conv": 120, "d_evil_carrier": 120, "d_evil": 240,
    "benign_r3": 2736, "malicious_r3": 2880, "total_r3": 5616,
}
KEYS = {"dpo_class", "id", "pack", "lang", "polarity", "rejected_form", "archetype_id",
        "conversations", "chosen", "rejected", "src_task"}
D_GOOD_TASK = "p16:D:release"
D_EVIL_TASKS = ("p16:D:refuse_conversational", "p16:D:refuse_carrier")


def die(msg: str) -> None:
    print(f"[FATAL] {msg}")
    print("BUILD-P16-R3=FAIL（fail-closed，未落盘）")
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
    """确定性子选（二轮 build_p16_r2.py 同算法，前缀/seed 按 §七）：
    key = sha256(b'p16-r3:20261014m2b:' + 原行字节) 十六进制**升序**（并列以 id 升序决断），
    取前 n 行；返回（按 id 升序的选中行, 选中阈值摘要 = 第 n 名 key, 首id, 末id）。"""
    keyed = sorted(
        (sha256_bytes(SUB_PREFIX.encode() + ln), json.loads(ln)["id"], ln)
        for ln in lines
    )
    if n > len(keyed):
        die(f"子选 n={n} > 候选 {len(keyed)}")
    sel = [t[2] for t in keyed[:n]]
    sel.sort(key=lambda ln: json.loads(ln)["id"])
    threshold = keyed[n - 1][0]
    return sel, threshold, json.loads(sel[0])["id"], json.loads(sel[-1])["id"]


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
    targets = [("数据目录", P16_R3), ("注册目录", M5A_R3_RUN), ("训练 output_dir", CKPT_R3),
               ("训练配置", CFG_R3), ("施工报告", REPORT_R3)]
    for tag, d in targets:
        if os.path.exists(d):
            die(f"目标路径已存在（防覆写/防部分态）：{tag} {os.path.relpath(d, ROOT)}——"
                f"如确需重建请先人工移除（版本目录纪律 ✗）")
    # 门禁前置：一轮 G1–G12 判定必须为 PASS 在案（含二轮 09:08 快检重跑链）
    if not os.path.exists(GATE_REPORT):
        die(f"缺一轮门禁报告 {os.path.relpath(GATE_REPORT, ROOT)}")
    gate = open(GATE_REPORT, encoding="utf-8").read()
    if "P16-GATE=PASS" not in gate:
        die("一轮门禁报告不含 P16-GATE=PASS（发射链前置断裂）")
    print(f"[OK] output/目标路径 NOT-EXIST ×{len(targets)} ✓ · 一轮门禁 P16-GATE=PASS 在案 ✓")


# ================================================================ 1. 冻结对账 ==
def assert_frozen() -> None:
    print("== 1. 一轮 + 二轮冻结件全量对账（快检替代 ①：release 冻结件 sha 复验未动） ==")
    for fn, want in FROZEN_R1.items():
        p = os.path.join(P16_R1, fn)
        if not os.path.exists(p):
            die(f"一轮冻结件缺失：{fn}")
        got = sha256_file(p)
        if got != want:
            die(f"一轮冻结件 sha 漂移：{fn} {got[:16]}… != 登记 {want[:16]}…")
        print(f"[OK] 一轮 {fn}: sha256 …{got[:12]} 与登记一致 ✓")
    # manifest.json 登记与常量双源一致（belt）
    m = json.loads(open(os.path.join(P16_R1, "manifest.json"), encoding="utf-8").read())
    for fn in ("p16_benign_release.jsonl", "p16_malicious_honest.jsonl"):
        if m["files"][fn]["sha256"] != FROZEN_R1[fn]:
            die(f"一轮 manifest.json 登记 sha 与常量表不符：{fn}")
    # 二轮冻结件只读复核（r2 manifest 登记 = 常量表双源 + 4 jsonl + dataset_info）
    m2 = json.loads(open(os.path.join(P16_R2, "manifest.json"), encoding="utf-8").read())
    for fn, want in FROZEN_R2.items():
        p = os.path.join(P16_R2, fn)
        if not os.path.exists(p):
            die(f"二轮冻结件缺失：{fn}")
        got = sha256_file(p)
        if got != want:
            die(f"二轮冻结件 sha 漂移：{fn} {got[:16]}… != 登记 {want[:16]}…")
        if m2["files"][fn]["sha256"] != want:
            die(f"二轮 manifest.json 登记 sha 与常量表不符：{fn}")
        print(f"[OK] 二轮 {fn}: sha256 …{got[:12]} 与登记一致 ✓")
    if sha256_file(os.path.join(ROOT, "data", "m5a-r2-run", "dataset_info.json")) != R2_DSINFO_SHA:
        die("二轮注册件 data/m5a-r2-run/dataset_info.json sha 漂移（≠ r2 manifest 登记）")
    print("[OK] 二轮注册件 dataset_info.json sha256 与 r2 manifest 登记一致 ✓")
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
    # 组成契约（一轮登记值）
    b, m = out["benign_by_fam"], out["malicious_by_fam"]
    for fam, want in (("A", EXPECT["a"]), ("B", EXPECT["b"]), ("C", EXPECT["c"]), ("E", EXPECT["e"]),
                      ("D", EXPECT["d_good_orig"])):
        if len(b.get(fam, [])) != want:
            die(f"良性件族 {fam} 行数 {len(b.get(fam, []))} != 一轮登记 {want}")
    if len(m.get("D_evil", [])) != EXPECT["d_evil"]:
        die("D 恶族行数与一轮登记不符")
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
    print(f"== 3. 确定性子选（前缀 b'{SUB_PREFIX}'，与二轮同算法）与字节级组装 ==")
    # M2b 单旋钮：仅 D 良子选；A 原样 1,500 全量复制（不子选 ✗✓）
    d_sub, d_thr, d_first, d_last = subsample(r1["benign_by_fam"]["D"], EXPECT["d_good_sub"])
    print(f"[OK] D 良子选 {EXPECT['d_good_sub']}/{EXPECT['d_good_orig']}（阈值摘要 …{d_thr[:12]}，"
          f"id {d_first}…{d_last}）✓")
    print(f"[OK] A 原样 {EXPECT['a']:,} 全量逐字节复制（不子选，M2b 与一轮唯一差异 = D 良子选）✓")

    def idsorted(lines: list[bytes]) -> list[bytes]:
        return sorted(lines, key=lambda ln: json.loads(ln)["id"])

    parts_d = idsorted(d_sub + r1["malicious_by_fam"]["D_evil"])
    benign_r3 = idsorted(r1["benign_by_fam"]["A"] + r1["benign_by_fam"]["B"] + r1["benign_by_fam"]["C"]
                         + r1["benign_by_fam"]["E"] + d_sub)
    malicious_r3 = r1["malicious_raw"]  # 整文件逐字节副本（F 2,640 + D 恶 240 原样）

    return {
        "d_sub": d_sub, "parts_d": parts_d,
        "benign_r3": benign_r3, "malicious_r3": malicious_r3,
        "d_thr": d_thr, "d_first": d_first, "d_last": d_last,
    }


# ================================================================ 4. 行级断言 ==
def assert_subset_integrity(r1: dict, r3: dict) -> dict:
    print("== 4. 子集完整性断言（恒等式 + ①–⑤；快检替代 ② = r3 行级子集断言） ==")
    rep = {}

    # ① D 良子选行全部 ∈ 原件（字节级 + id 级，双向无重复）
    d_orig_set = set(r1["benign_by_fam"]["D"])
    sel = r3["d_sub"]
    if len(sel) != EXPECT["d_good_sub"]:
        die(f"D 良子选行数 {len(sel)} != {EXPECT['d_good_sub']}")
    outside = [json.loads(ln)["id"] for ln in sel if ln not in d_orig_set]
    if outside:
        die(f"D 良子选 {len(outside)} 行不在原件字节集内：{outside[:5]}")
    ids = [json.loads(ln)["id"] for ln in sel]
    if len(set(ids)) != len(ids):
        die("D 良子选 id 重复")
    if not set(ids) <= {json.loads(ln)["id"] for ln in d_orig_set}:
        die("D 良子选 id 集溢出原件")
    rep["D良_sub_in_original"] = (f"{EXPECT['d_good_sub']}/{EXPECT['d_good_sub']} 行逐字节 ∈ 原 "
                                  f"{EXPECT['d_good_orig']} 行 ✓")
    print(f"[OK] 断言① D 良子选 {EXPECT['d_good_sub']}/{EXPECT['d_good_sub']} 行逐字节 ∈ "
          f"原 {EXPECT['d_good_orig']} ✓")

    # ② D 恶 240 原样（120 对话 + 120 载体，逐字节全量在场）
    evil = r1["malicious_by_fam"]["D_evil"]
    missing = [json.loads(ln)["id"] for ln in evil if ln not in set(r3["parts_d"])]
    if missing:
        die(f"D 恶 {len(missing)} 行未原样进 parts-d-sub：{missing[:5]}")
    conv = sum(1 for ln in evil if json.loads(ln)["src_task"].endswith("conversational"))
    rep["d_evil_unchanged"] = (f"240/240 行逐字节原样（对话式 {conv} + 载体 {EXPECT['d_evil'] - conv}）✓")
    print(f"[OK] 断言② D 恶 240/240 原样（对话 {conv} + 载体 {EXPECT['d_evil'] - conv}）✓")

    # ③ 六族与一轮逐字节一致：F+D恶 = 整恶意文件 sha 恒等（= 一轮 manifest 登记值）；
    #    A/B/C/E/F/D恶 = 按族抽取行串 sha 双侧对拍（A 为全量复制，指纹必须相等）
    if sha256_bytes(r3["malicious_r3"]) != FROZEN_R1["p16_malicious_honest.jsonl"]:
        die("r3 恶意件 sha != 一轮登记值（F/D恶 逐字节复制破坏）")
    rep["f_whole_file_sha_round1_registered"] = FROZEN_R1["p16_malicious_honest.jsonl"]
    print(f"[OK] 断言③ F+D恶：r3 恶意件整文件 sha256 = 一轮登记 "
          f"…{FROZEN_R1['p16_malicious_honest.jsonl'][:12]} ✓")

    r3_benign_by_fam: dict[str, list[bytes]] = {}
    for ln in r3["benign_r3"]:
        r3_benign_by_fam.setdefault(meta(ln)["fam"], []).append(ln)
    fam_sha_reg = {}
    for fam, r1_lines, r2_lines in (
            ("A(全量复制)", r1["benign_by_fam"]["A"], r3_benign_by_fam.get("A", [])),
            ("B", r1["benign_by_fam"]["B"], r3_benign_by_fam.get("B", [])),
            ("C", r1["benign_by_fam"]["C"], r3_benign_by_fam.get("C", [])),
            ("E", r1["benign_by_fam"]["E"], r3_benign_by_fam.get("E", [])),
            ("F", r1["malicious_by_fam"]["F"], [ln for ln in r3["malicious_r3"].split(b"\n")[:-1]
                                                if json.loads(ln)["id"][4] == "F"]),
            ("D拒绝", r1["malicious_by_fam"]["D_evil"], [ln for ln in r3["malicious_r3"].split(b"\n")[:-1]
                                                         if json.loads(ln)["id"][4] == "D"]),
    ):
        if len(r1_lines) != len(r2_lines):
            die(f"族 {fam} 行数不一致：一轮 {len(r1_lines)} / r3 {len(r2_lines)}")
        s1, s2 = family_sha(r1_lines), family_sha(r2_lines)
        if s1 != s2:
            die(f"族 {fam} 按族抽取行串 sha 不一致：一轮 {s1[:16]}… / r3 {s2[:16]}…（逐字节复制破坏）")
        fam_sha_reg[fam] = {"rows": len(r1_lines), "round1_sha256": s1, "r3_sha256": s2, "equal": True}
        print(f"[OK] 断言③ 族 {fam} {len(r1_lines)} 行按族行串 sha 对拍一致 …{s1[:12]} ✓")
    # D 良子选族指纹登记（子集 ⇒ 不相等是预期；子集性由断言①保证）
    fam_sha_reg["D放行(96子选)"] = {
        "round1_rows": EXPECT["d_good_orig"], "r3_rows": EXPECT["d_good_sub"],
        "note": "子选族（指纹不相等是预期；子集性由断言①保证）",
        "round1_sha256": family_sha(r1["benign_by_fam"]["D"]),
        "r3_sha256": family_sha(r3["d_sub"]),
    }
    rep["family_sha256_vs_round1"] = fam_sha_reg

    # ④ 行数恒等式：5,616 = 1500+480+360+240+96+300+2640 = 良 2,736 + 恶 2,880
    s = (EXPECT["a"] + EXPECT["b"] + EXPECT["c"] + EXPECT["d_evil"] + EXPECT["d_good_sub"]
         + EXPECT["e"] + EXPECT["f"])
    if s != EXPECT["total_r3"]:
        die(f"配方行数恒等式失效：{s} != {EXPECT['total_r3']}")
    nb, nm = len(r3["benign_r3"]), r3["malicious_r3"].count(b"\n")
    if nb != EXPECT["benign_r3"] or nm != EXPECT["malicious_r3"] or nb + nm != EXPECT["total_r3"]:
        die(f"产物行数 {nb}+{nm} != 良 {EXPECT['benign_r3']} + 恶 {EXPECT['malicious_r3']}")
    if len(r3["parts_d"]) != EXPECT["d_good_sub"] + EXPECT["d_evil"]:
        die("parts 件行数不符")
    rep["row_invariant"] = (f"5,616 = {EXPECT['a']}+{EXPECT['b']}+{EXPECT['c']}+{EXPECT['d_evil']}"
                            f"+{EXPECT['d_good_sub']}+{EXPECT['e']}+{EXPECT['f']}"
                            f" = 良 {nb} + 恶 {nm} ✓")
    print(f"[OK] 断言④ 行数恒等式：5,616 = 1500+480+360+240+96+300+2640 = 良 {nb:,} + 恶 {nm:,} ✓")

    # ⑤ 全局 id 唯一 + id ⊆ 一轮 id 集 + 极性比
    all_ids = [json.loads(ln)["id"] for ln in r3["benign_r3"]] + \
              [json.loads(ln)["id"] for ln in r3["malicious_r3"].split(b"\n")[:-1]]
    if len(set(all_ids)) != len(all_ids):
        die("r3 全局 id 重复")
    r1_ids = {json.loads(ln)["id"] for ln in r1["benign_lines"]} | \
             {json.loads(ln)["id"] for ln in r1["malicious_lines"]}
    if not set(all_ids) <= r1_ids:
        die("r3 id 集溢出一轮（零新生成被破坏）")
    if any(json.loads(ln)["polarity"] != "benign_release" for ln in r3["benign_r3"]):
        die("r3 良件极性非全 benign_release")
    pct = 100.0 * nb / (nb + nm)
    rep["polarity_balance"] = {"benign_release": nb, "malicious_refuse": nm,
                               "benign_pct": round(pct, 2), "malicious_pct": round(100.0 - pct, 2)}
    print(f"[OK] 断言⑤ 全局 id 唯一 {len(all_ids):,} 且 ⊆ 一轮 id 集 ✓ · 良:恶 = {nb}:{nm} "
          f"= {pct:.1f}:{100.0 - pct:.1f}（设计 §七 48.7:51.3 ✓）")
    return rep


# ================================================================ 5. 分布统计 ==
def distributions(r3: dict) -> dict:
    def dist(rows: list) -> dict:
        out = {}
        for k in ("lang", "pack", "polarity", "dpo_class", "src_task"):
            out[k] = dict(sorted(Counter(r[k] for r in rows).items()))
        return out

    benign_rows = [json.loads(ln) for ln in r3["benign_r3"]]
    malicious_rows = [json.loads(ln) for ln in r3["malicious_r3"].split(b"\n")[:-1]]
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
def emit(r3: dict, integ: dict, dists: dict) -> dict:
    print("== 5. 落盘（先建 r3 目录，三 jsonl + manifest + README + 三注册 dataset_info） ==")
    os.makedirs(P16_R3, exist_ok=False)
    os.makedirs(M5A_R3_RUN, exist_ok=False)

    def join_lines(lines: list[bytes]) -> bytes:
        return b"".join(ln + b"\n" for ln in lines)

    files = {}
    for tag, data in (("parts-d-sub.jsonl", join_lines(r3["parts_d"])),
                      ("p16_benign_release.jsonl", join_lines(r3["benign_r3"])),
                      ("p16_malicious_honest.jsonl", r3["malicious_r3"])):
        p = os.path.join(P16_R3, tag)
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
        "sec_dpo_m5a_r3_base_m4capfix": entry(
            "../m4-run/dpo_m4_capfix.jsonl",
            "M5A-R3 multi-dataset loading (round-3 M2b; see reports/p1.6-round3-build.md and "
            "reports/p1.6-round2-design.md section 7): base dpo_m4_capfix 28842 rows, sha256 "
            + M4_BASE_SHA + " = frozen constant of build_p16_r3.py (verified at build time, "
            "2026-10-14); byte-identical to the base segment of the round-1 m5a mix "
            "(erratum precedent: reports/m5a-preregistration.md section 7). ASCII-only note: "
            "LF parser.py opens this file with locale default encoding (GBK on this host), "
            "non-ASCII bytes break parsing."),
        "sec_dpo_m5a_r3_p16_benign": entry(
            "../dpo/p16-calibration-r3/p16_benign_release.jsonl",
            "M5A-R3 multi-dataset loading: p16-r3 benign_release 2736 rows = A 1500 (unchanged, "
            "full byte-identical copy of round-1 family) + B 480 + C 360 + E 300 + D-release 96 "
            "(deterministic subsample from round-1 240, seed 20261014m2b, algorithm = "
            "sha256(b'p16-r3:20261014m2b:'+row) hex ascending); sha256 "
            + files["p16_benign_release.jsonl"]["sha256"] + " = frozen constant of "
            "build_p16_r3.py; single 11-key homogeneous schema (round-1 SMOKE-M5A-MULTIDS "
            "precedent). ASCII-only note (GBK lesson, m5a erratum section 7)."),
        "sec_dpo_m5a_r3_p16_malicious": entry(
            "../dpo/p16-calibration-r3/p16_malicious_honest.jsonl",
            "M5A-R3 multi-dataset loading: p16-r3 malicious_honest 2880 rows = F 2640 + "
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
    dump_bytes(os.path.join(M5A_R3_RUN, "dataset_info.json"), ds_bytes, "dataset_info.json (3 registrations)")

    # ---- manifest ----
    manifest = {
        "name": "p16-calibration-r3-release",
        "built": BUILT,
        "seed": SEED,
        "spec": SPEC,
        "recipe": "M2b D 良单旋钮（p1.6-round2-design §七 预注册）：A 1,500 原样（全量复制，不子选）· "
                  "D放行 240→96 · B480/C360/E300/F2640/D恶240 逐字节不动 · "
                  "良 2,736:恶 2,880 = 48.7:51.3；与一轮唯一差异 = D 良子选",
        "builder": "scripts/build_p16_r3.py",
        "checker": "scripts/check_p16_calibration.py —— 三轮不跑全 checker（G1 扫描交互，见 "
                   "g1_scan_interaction：r2+r3 均在 data/dpo 扫描范围、5,216+5,616 个合法下游 id "
                   "必误触）；快检替代 = ①一轮 release 冻结件 sha 复验未动（builder assert_frozen "
                   "六登记件 + m4 基座 + 二轮冻结件只读复核）+ ②r3 行级子集断言（builder "
                   "assert_subset_integrity + scripts/_tmp_p16_r3_verify.py 独立核验）",
        "files": {
            "parts-d-sub.jsonl": {**files["parts-d-sub.jsonl"],
                                  "composition": "D 重组 336 = 放行向子选 96/240 + 拒绝向 240 原样（按 id 升序）"},
            "p16_benign_release.jsonl": {**files["p16_benign_release.jsonl"],
                                         "composition": "A 1,500（原样全量）+ B 480 + C 360 + E 300 + D放行 96（按 id 升序）"},
            "p16_malicious_honest.jsonl": {**files["p16_malicious_honest.jsonl"],
                                           "composition": "F 2,640 + D拒绝 240（= 一轮恶意件逐字节副本）"},
        },
        "subsample": {
            "algorithm": "key = sha256(b'p16-r3:20261014m2b:' + 一轮 release 原行字节) 十六进制升序"
                         "（并列以 id 升序决断），取前 N；产物按 id 升序。输入 = 一轮合并件原行字节"
                         "（不重生、不再序列化 ✗）。同算法 = 二轮 build_p16_r2.py 逐字同款"
                         "（r2 先例前缀 = b'p16-r2:20261014:'）",
            "seed": SEED,
            "prefix_bytes": "p16-r3:20261014m2b:",
            "D_good": {"n": EXPECT["d_good_sub"], "from": EXPECT["d_good_orig"],
                       "threshold_digest": r3["d_thr"],
                       "first_id": r3["d_first"], "last_id": r3["d_last"]},
            "A": {"n": EXPECT["a"], "from": EXPECT["a"],
                  "note": "M2b：A 原样全量复制，不子选（与二轮 M2a 的差异点）"},
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
            "round2_release": {
                "dir": "data/dpo/p16-calibration-r2/",
                "note": "二轮冻结件只读复核（4 jsonl + dataset_info sha 对 r2 manifest 登记值一致，"
                        "见 builder 输出）；r3 数据源 = 一轮 release（非 r2），r2 仅作只读对照",
                "manifest": "data/dpo/p16-calibration-r2/manifest.json（P16-R2-RELEASE=FROZEN）",
            },
            "round1_gate": "reports/p1.6-gate-report.md（P16-GATE=PASS；G1–G12 原跑 + 二轮 09:08 快检重跑"
                           "双重在案）；三轮快检处置见 g1_scan_interaction（不跑全 checker）",
            "m4_base": {"file": "data/m4-run/dpo_m4_capfix.jsonl", "rows": M4_BASE_ROWS,
                        "sha256": M4_BASE_SHA, "role": "多数据集装载 base 注册源（冻结常量）"},
            "registration": {
                "dataset_info": "data/m5a-r3-run/dataset_info.json",
                "sha256": sha256_bytes(ds_bytes),
                "entries": ["sec_dpo_m5a_r3_base_m4capfix", "sec_dpo_m5a_r3_p16_benign",
                            "sec_dpo_m5a_r3_p16_malicious"],
                "ascii_only": True,
                "note": "多数据集装载（一轮 m5a CastError/GBK 两教训闭环 ✗✓）；"
                        "训练配置 configs/m5a-dpo-r3.yaml（= m5a-dpo-r2 复制，仅 dataset 三注册 + "
                        "dataset_dir + output_dir 三行差异，HP 零改动）",
            },
            "training_totals": {
                "rows": M4_BASE_ROWS + EXPECT["total_r3"],
                "formula": f"m4 base {M4_BASE_ROWS} + p16-r3 {EXPECT['total_r3']} = {M4_BASE_ROWS + EXPECT['total_r3']}",
                "p16r3_share_pct": round(100.0 * EXPECT["total_r3"] / (M4_BASE_ROWS + EXPECT["total_r3"]), 3),
                "full_epoch_steps": (M4_BASE_ROWS + EXPECT["total_r3"] + 15) // 16,
                "probe_visibility_300steps": "4,800 × 16.3% ≈ 782 行（σ≈26）",
            },
        },
        "g1_scan_interaction": {
            "status": "RESOLVED_BY_SEQUENCING",
            "decision": "r3 落点 data/dpo/p16-calibration-r3/ 在 check_p16_calibration.py G1 字节级扫描范围"
                        "（data/dpo/**/*.jsonl，仅豁免一轮 data/dpo/p16-calibration/，checker L314–L324）之内；"
                        "且二轮 data/dpo/p16-calibration-r2/（5,216 个合法下游 id）已在扫描范围内 ⇒ "
                        "任何时点（r3 落盘前后皆然）全量重跑 checker 都会 G1 误触 r2+r3 的 id",
            "consequence": "三轮门禁处置（二轮 RESOLVED_BY_SEQUENCING 先例 + 任务书钉死）：**不跑全 checker**；"
                           "快检替代 = ①一轮 release 冻结件 sha 复验未动（六登记件 + m4 基座，builder "
                           "assert_frozen）+ ②r3 行级子集断言（builder assert_subset_integrity + 独立核验）。"
                           "证明力：r3 每行输入内容 = 一轮 G1–G12 PASS 内容（一轮门禁 + 二轮快检重跑双重在案）"
                           "的纯子集/复制 ⇒ 行级门性质（G2/G3/G4/G5/G8 行断言、G9/G10 内容隔离）逐行继承；"
                           "唯集合级配额（G6 的 50:50）为 M2b 设计有意变更（48.7:51.3，§七）；"
                           "checker 零改动 ✗（同 data/m5a-run/manifest.json g1_scan_interaction "
                           "RESOLVED_BY_PLACEMENT 裁决镜像：G1 职责 = 防 p16 泄漏到不该含它的文件，"
                           "下游消费件合法内容非污染 ✗✓）",
        },
        "version_discipline": "冻结 = 本 manifest sha256；任何修改 ⇒ 新开版本目录（p16-calibration-r4/…），"
                              "不得原地改 ✗（一轮/二轮 README 同款纪律）；重建 = 移除本目录后重跑 builder（确定性）",
    }
    mtxt = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    dump_bytes(os.path.join(P16_R3, "manifest.json"), mtxt.encode("utf-8"), "manifest.json")

    readme = f"""# P1.6 三轮拒绝校准对 · r3 release（M2b D 良单旋钮，冻结件）

- 规格：`reports/p1.6-round2-design.md` **§七（M2b 预注册，配方与预测已冻结）** · seed={SEED}
- 构建：`scripts/build_p16_r3.py`（纯 CPU，确定性子选 + 逐字节复制，PREFLIGHT 防覆写；
  = 二轮 `build_p16_r2.py` 同算法最小复制版，仅 D 良子选、A 原样全量）

## 内容

| 文件 | 行数 | 组成 | sha256 |
|---|---|---|---|
| `parts-d-sub.jsonl` | 336 | D 重组 = 良 96/240 子选 + 恶 240 原样 | `{files['parts-d-sub.jsonl']['sha256']}` |
| `p16_benign_release.jsonl` | 2,736 | A 1,500（原样全量）+ B 480 + C 360 + E 300 + D放行 96 | `{files['p16_benign_release.jsonl']['sha256']}` |
| `p16_malicious_honest.jsonl` | 2,880 | F 2,640 + D拒绝 240（一轮件逐字节副本） | `{files['p16_malicious_honest.jsonl']['sha256']}` |

极性 良 2,736 : 恶 2,880 = 48.7 : 51.3；总量 5,616（一轮 5,760、二轮 5,216）；
与一轮唯一差异 = D 良 240→96（seed={SEED}，B/C/E/F/D恶/A 逐字节不动）。
子选算法/阈值摘要/按族 sha 对拍/全量分布见 `manifest.json`。

## 纪律

- 冻结 = `manifest.json` sha256；任何修改 ⇒ 新开版本目录，**不得原地改** ✗。
- 一轮 `data/dpo/p16-calibration/` 与二轮 `data/dpo/p16-calibration-r2/` 全链只读
  （施工前后 sha 对账一致）。
- G1 扫描交互：r2+r3 均在一轮 checker G1 字节扫描范围内 ⇒ **三轮不跑全 checker**，
  快检替代 = 一轮冻结件 sha 复验未动 + r3 行级子集断言（见 `manifest.json`
  `g1_scan_interaction`；checker 零改动 ✗）。
- 装载 = 多数据集三注册 `data/m5a-r3-run/dataset_info.json`（纯 ASCII ✗✓ GBK 教训）+
  `configs/m5a-dpo-r3.yaml`（HP 零改动）。

P16-R3-RELEASE=FROZEN
"""
    dump_bytes(os.path.join(P16_R3, "README.md"), readme.encode("utf-8"), "README.md")
    return {"files": files, "dataset_info_sha256": sha256_bytes(ds_bytes),
            "manifest_sha256": sha256_bytes(mtxt.encode("utf-8"))}


def main() -> int:
    print("== P1.6 三轮数据施工（build_p16_r3 · M2b） ==")
    preflight()
    assert_frozen()
    r1 = load_round1()
    r3 = build(r1)
    integ = assert_subset_integrity(r1, r3)
    dists = distributions(r3)
    out = emit(r3, integ, dists)

    print("\n== 施工完成 ==")
    for fn, info in out["files"].items():
        print(f"  {fn:<30} {info['rows']:>6,} 行  sha256 {info['sha256']}")
    print(f"  {'dataset_info.json':<30} {'3':>6} 注册  sha256 {out['dataset_info_sha256']}")
    print(f"  {'manifest.json':<30} {'':>6}       sha256 {out['manifest_sha256']}")
    print(f"  行数恒等式：5,616 = 1500+480+360+240+96+300+2640 ✓ · 良:恶 = 2,736:2,880 = 48.7:51.3 ✓")
    print("BUILD-P16-R3=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
