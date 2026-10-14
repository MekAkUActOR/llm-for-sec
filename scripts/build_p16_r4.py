# -*- coding: utf-8 -*-
"""P1.6 四轮数据组装（F 对话式扩容）：data/dpo/p16-calibration-r4/ + data/m5a-r4-run/ + config。

任务书：reports/p1.6-round4-design.md §四 施工规格（预注册，P16-R4-DESIGN=DONE）。
纪律（✗✓ 全项留痕）：纯 CPU；一轮/二轮/三轮冻结件只读零覆写；PREFLIGHT 全 NOT-EXIST；
fail-closed（任一断言破 ⇒ 非零退出、不落盘 release）。

流程：
  0. PREFLIGHT：5 个目标路径 NOT-EXIST
  1. 启动对账：一轮六登记件（两 release + parts-abd + parts-cef + 两 parts manifest 的
     登记值）+ r3 三件（两 release + parts-d-sub，r3 manifest 登记）+ m4 基座 sha 恒等
  2. G9 前置：parts/part-f4-g9.check.json 存在且 ok=true（G 门禁行级断言之污染检查项）
  3. 组装：benign/malicious 逐字节复制 r3 件（sha 断言恒等）；p16_f4_dialog.jsonl =
     g01+g02 合并（id 升序）；parts-f4-dialog.jsonl = 同内容谱系副本
  4. 行级断言：新件 batch_check 复跑 fails=0；id 唯一/升序/与一轮零重叠；行数恒等式；
     配额闭合；三件极性分布
  5. manifest.json + README.md（sha/谱系/纪律登记）
  6. dataset_info.json 四注册（纯 ASCII note）
  7. configs/m5a-dpo-r4.yaml = r3 config 头部插入 r4 块 + 3 行功能改动；机器证明
     非注释 diff 恰 3 行（DIFF-HP-ZERO）
  8. 装载冒烟（SMOKE-M5A-R4-MULTIDS）：locale 解析 dataset_info / config 逗号拆分四名单 /
     四条目独立 load_dataset 行数 28,842+2,736+2,880+792 = 35,250 / p16 三件 11 键同构
用法：.venv\\Scripts\\python.exe -X utf8 scripts\\build_p16_r4.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "_p16_parts_cef"))
import p16cef_common as K  # noqa: E402  冻结公共库只读 import（batch_check 复跑）

R1_DIR = ROOT / "data" / "dpo" / "p16-calibration"
R3_DIR = ROOT / "data" / "dpo" / "p16-calibration-r3"
R4_DIR = ROOT / "data" / "dpo" / "p16-calibration-r4"
PARTS = ROOT / "scripts" / "_p16_r4_dialog" / "parts"
RUN_DIR = ROOT / "data" / "m5a-r4-run"
M4_BASE = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
CFG_R3 = ROOT / "configs" / "m5a-dpo-r3.yaml"
CFG_R4 = ROOT / "configs" / "m5a-dpo-r4.yaml"
CKPT_R4 = ROOT / "checkpoints" / "qwen3-06b-sec-m5a-dpo-r4"
BUILD_REPORT = ROOT / "reports" / "p1.6-round4-build.md"

M4_SHA = "d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414"
R3_BENIGN_SHA = "822510c11c5453db7039359c8e3899d8ead0f7a35accb3da737720f174ba080c"
R3_MALICIOUS_SHA = "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d"
R3_DSUB_SHA = "4c3af433046d614d6f4671790331005edc5f3c395be28e141e4ee6a26de60104"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def fail(msg: str):
    print(f"[FATAL] {msg}")
    sys.exit(1)


def load_jsonl(p: Path) -> list:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    t0 = time.time()
    # ---------------- 0. PREFLIGHT ----------------
    targets = [R4_DIR, RUN_DIR, CFG_R4, CKPT_R4, BUILD_REPORT]
    for t in targets:
        if t.exists():
            fail(f"PREFLIGHT: target already exists: {t}")
    print(f"[preflight] 5 targets NOT-EXIST ✓ (r4 dir / run dir / config / ckpt / build report)")

    # ---------------- 1. 启动对账（fail-closed） ----------------
    m1 = json.loads((R1_DIR / "manifest.json").read_text(encoding="utf-8"))
    checks = []
    for fname, meta in m1["files"].items():  # 一轮两 release
        got = sha256_file(R1_DIR / fname)
        checks.append((f"r1/{fname}", got == meta["sha256"], got))
    # 一轮两 parts + 两 parts manifest（登记值取自各自 manifest：abd 顶层 file/sha256；cef assembled.*）
    abd_man = json.loads((R1_DIR / "parts-abd.manifest.json").read_text(encoding="utf-8"))
    cef_man = json.loads((R1_DIR / "manifest-cef.json").read_text(encoding="utf-8"))
    reg_abd = abd_man.get("sha256")
    if reg_abd is None:  # 兜底：parts 列表内登记
        reg_abd = next(p["sha256"] for p in abd_man.get("parts", []) if p["file"].endswith("parts-abd.jsonl"))
    reg_cef = (cef_man.get("assembled") or {}).get("sha256")
    if reg_cef is None:
        reg_cef = cef_man.get("sha256")
    if reg_abd is None or reg_cef is None:
        fail("cannot find registered sha for parts-abd/parts-cef in their manifests")
    got = sha256_file(R1_DIR / "parts-abd.jsonl")
    checks.append((f"r1/parts-abd.jsonl", got == reg_abd, got))
    got = sha256_file(R1_DIR / "parts-cef.jsonl")
    checks.append((f"r1/parts-cef.jsonl", got == reg_cef, got))
    m3 = json.loads((R3_DIR / "manifest.json").read_text(encoding="utf-8"))
    for fname, want in (("p16_benign_release.jsonl", R3_BENIGN_SHA),
                        ("p16_malicious_honest.jsonl", R3_MALICIOUS_SHA),
                        ("parts-d-sub.jsonl", R3_DSUB_SHA)):
        got = sha256_file(R3_DIR / fname)
        reg = m3["files"][fname]["sha256"]
        checks.append((f"r3/{fname}", got == want == reg, got))
    m4_sha = sha256_file(M4_BASE)
    m4_rows = len(load_jsonl(M4_BASE))
    checks.append(("m4 base", m4_sha == M4_SHA and m4_rows == 28842, m4_sha))
    for name, ok, got in checks:
        if not ok:
            fail(f"startup audit mismatch: {name} sha={got}")
    print(f"[audit] frozen inputs verified: r1 releases 2 + r1 parts 2 + r3 files 3 + m4 base = 8 项全一致 ✓")

    # ---------------- 2. G9 前置 ----------------
    g9 = json.loads((PARTS / "part-f4-g9.check.json").read_text(encoding="utf-8"))
    if not g9.get("ok"):
        fail(f"G9-equivalent check not PASS: fails={g9.get('fails')}")
    print(f"[g9] F4-G9=PASS ✓ (rows={g9['rows']}, elapsed={g9.get('elapsed_s')}s)")

    # ---------------- 3. 组装 ----------------
    R4_DIR.mkdir(parents=True)
    shutil.copyfile(R3_DIR / "p16_benign_release.jsonl", R4_DIR / "p16_benign_release.jsonl")
    shutil.copyfile(R3_DIR / "p16_malicious_honest.jsonl", R4_DIR / "p16_malicious_honest.jsonl")
    rows_new = load_jsonl(PARTS / "part-g01.jsonl") + load_jsonl(PARTS / "part-g02.jsonl")
    data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows_new)
    (R4_DIR / "p16_f4_dialog.jsonl").write_text(data, encoding="utf-8", newline="\n")
    shutil.copyfile(R4_DIR / "p16_f4_dialog.jsonl", R4_DIR / "parts-f4-dialog.jsonl")

    # ---------------- 4. 行级断言 ----------------
    b_sha = sha256_file(R4_DIR / "p16_benign_release.jsonl")
    m_sha = sha256_file(R4_DIR / "p16_malicious_honest.jsonl")
    if b_sha != R3_BENIGN_SHA:
        fail(f"r4 benign copy sha drift: {b_sha}")
    if m_sha != R3_MALICIOUS_SHA:
        fail(f"r4 malicious copy sha drift: {m_sha}")
    if len(rows_new) != 792:
        fail(f"new rows {len(rows_new)} != 792")
    summ = K.batch_check(rows_new, "F")
    if summ["fails"]:
        fail(f"batch_check re-run fails: {summ['fails'][:5]}")
    ids = [r["id"] for r in rows_new]
    if not (ids == sorted(ids) and len(set(ids)) == 792 and ids[0] == "p16-F-002641" and ids[-1] == "p16-F-003432"):
        fail("new file id order/uniqueness/range violated")
    r1_ids = {r["id"] for r in load_jsonl(R1_DIR / "p16_benign_release.jsonl")}
    r1_ids |= {r["id"] for r in load_jsonl(R1_DIR / "p16_malicious_honest.jsonl")}
    if set(ids) & r1_ids:
        fail("id overlap with round-1 release")
    n_b = len(load_jsonl(R4_DIR / "p16_benign_release.jsonl"))
    n_m = len(load_jsonl(R4_DIR / "p16_malicious_honest.jsonl"))
    if not (n_b == 2736 and n_m == 2880 and n_b + n_m + 792 == 6408):
        fail(f"row identity violated: {n_b}/{n_m}/792")
    pol_new = Counter(r["polarity"] for r in rows_new)
    if pol_new != Counter({"malicious_refuse": 792}):
        fail(f"new polarity wrong: {pol_new}")
    style_c = Counter(r["src_task"].rsplit(":", 1)[-1] for r in rows_new)
    lang_c = Counter(r["lang"] for r in rows_new)
    pack_c = Counter(r["pack"] for r in rows_new)
    form_c = Counter(r["rejected_form"] for r in rows_new)
    if not (style_c == Counter({"escalation": 198, "roleplay": 198, "fictional": 198, "puzzle": 198})
            and lang_c == Counter({"en": 476, "zh": 316})
            and pack_c == Counter({"default": 356, "professional": 316, "conservative": 120})
            and form_c == Counter({"cd_conditional_transition": 396, "lip_refuse_deliver": 396})):
        fail(f"quota closure violated: {style_c}/{lang_c}/{pack_c}/{form_c}")
    turn_c = Counter(sum(1 for c in r["conversations"] if c["from"] == "human") for r in rows_new)
    arch_c = Counter(r["archetype_id"] for r in rows_new)
    print(f"[verify] row-level assertions PASS: 792 new rows batch_check fails=0; ids 2641–3432 "
          f"unique/ascending/disjoint-r1 ✓; 6,408 = 2,736 + 2,880 + 792 = 良 2,736 + 恶 3,672 ✓; "
          f"turns={dict(sorted(turn_c.items()))}; archetype max={max(arch_c.values())}")
    print("VERIFY-R4=PASS")

    # ---------------- 5. manifest + README ----------------
    g9b = json.loads((PARTS / "part-g01.check.json").read_text(encoding="utf-8"))
    g9c = json.loads((PARTS / "part-g02.check.json").read_text(encoding="utf-8"))
    manifest = {
        "name": "p16-calibration-r4-release",
        "built": "2026-10-14",
        "spec": "reports/p1.6-round4-design.md (P16-R4-DESIGN=DONE; T1-T4 preregistered)",
        "recipe": {
            "variable": "F conversational expansion 2x (single mechanism variable)",
            "benign_side": "byte-identical copy of r3 benign release (A1500+B480+C360+Drelease96+E300 = 2,736)",
            "malicious_side": "r1/r3 malicious release byte-copy (F-carrier 1,848 + F-dialog-r1 792 + D-refuse 240 = 2,880) + F4-dialog NEW 792",
            "f4_dialog_new": {
                "rows": 792, "styles": {"escalation": 198, "roleplay": 198, "fictional": 198, "puzzle": 198},
                "lang": {"en": 476, "zh": 316}, "pack": {"default": 356, "professional": 316, "conservative": 120},
                "form": {"cd_conditional_transition": 396, "lip_refuse_deliver": 396},
                "user_turns": {str(k): v for k, v in sorted(turn_c.items())},
                "ids": "p16-F-002641..p16-F-003432 (F-family numbering continued, disjoint from r1/r2/r3)",
                "archetypes": "F-dlg-{esc|rol|fic|puz}-11..20 (round-1 used 01..10; max count "
                              + str(max(arch_c.values())) + " <= 48)",
                "seed": 20261014, "content": "all-new skeletons/topics/press/response templates (content_f4_dialog.py)",
            },
            "totals": {"calibration": 6408, "benign": 2736, "malicious": 3672,
                       "ratio_benign_malicious": "42.71 : 57.29",
                       "with_m4_base": 35250, "full_epoch_steps": 2204, "calibration_share": 0.1818},
        },
        "builder": "scripts/build_p16_r4.py (+ scripts/_p16_r4_dialog/{content_f4_dialog,gen_f4_dialog,check_f4_g9}.py)",
        "checker": "scripts/check_p16_calibration.py (NOT re-run for r4; see g1_scan_interaction) "
                   "+ p16cef_common.batch_check row-level re-run (fails=0) "
                   "+ G9-equivalent via official gate_g9 code path (docs=f4-dialog 792 rows)",
        "files": {
            "p16_benign_release.jsonl": {"rows": n_b, "sha256": b_sha,
                                         "composition": "A 1,500 + B 480 + C 360 + E 300 + D放行 96（= r3 良性件逐字节副本，r1 内容纯子集）"},
            "p16_malicious_honest.jsonl": {"rows": n_m, "sha256": m_sha,
                                           "composition": "F 2,640 + D拒绝 240（= 一轮恶意件逐字节副本，sha = r1 登记值）"},
            "p16_f4_dialog.jsonl": {"rows": 792, "sha256": sha256_file(R4_DIR / "p16_f4_dialog.jsonl"),
                                    "composition": "F4-dialog 新生成 792（四风格 ×198，id 升序）；装载用件"},
            "parts-f4-dialog.jsonl": {"rows": 792, "sha256": sha256_file(R4_DIR / "parts-f4-dialog.jsonl"),
                                      "composition": "p16_f4_dialog.jsonl 的谱系副本（与 g01+g02 合并逐字节恒等）"},
        },
        "lineage": {
            "inputs_verified": ["r1/p16_benign_release.jsonl", "r1/p16_malicious_honest.jsonl",
                                "r1/parts-abd.jsonl", "r1/parts-cef.jsonl",
                                "r3/p16_benign_release.jsonl", "r3/p16_malicious_honest.jsonl",
                                "r3/parts-d-sub.jsonl", "m4/dpo_m4_capfix.jsonl 28,842"],
            "rounds": "r4 = r3 frozen recipe (benign byte-copy) + F conversational expansion +792 NEW rows; "
                      "new rows passed: batch_check (schema/H1/H2/H4/F4F6/weaponization/token<=970) "
                      "+ prompt global uniqueness + quota closure + id disjointness + "
                      "G9-equivalent 8-gram pollution check vs ALL heldout + probes (official code path, ok=true)",
            "batch_ledger": "scripts/_p16_r4_dialog/progress.md (+ parts/*.check.json)",
            "g9_check": {k: g9.get(k) for k in ("gate", "rows", "ok", "elapsed_s")},
            "batch_stats": [{"batch": g9b["batch"], "sha256": g9b["sha256"], "check": g9b["check"], "dist": g9b["dist"]},
                            {"batch": g9c["batch"], "sha256": g9c["sha256"], "check": g9c["check"], "dist": g9c["dist"]}],
        },
        "g1_scan_interaction": {
            "status": "RESOLVED_BY_SEQUENCING",
            "note": "r4 dir lies inside the round-1 checker G1 byte-scan scope (data/dpo/**/*.jsonl; only "
                    "data/dpo/p16-calibration/ exempted). Re-running the full checker at any time after r2 "
                    "would flag r2+r3+r4 cumulative downstream ids as false G1 FAIL (legitimate downstream "
                    "consumption, not contamination; precedent data/m5a-run/manifest.json "
                    "RESOLVED_BY_PLACEMENT and r2/r3 RESOLVED_BY_SEQUENCING). r4 therefore does NOT re-run "
                    "the full checker; integrity is carried by: frozen-input sha audit (8 items) + "
                    "row-level batch_check re-run + G9-equivalent pollution check on the new rows. "
                    "Checker itself unmodified.",
        },
        "version_discipline": "new version directory data/dpo/p16-calibration-r4/; r1/r2/r3 artifacts read-only, zero overwrite",
    }
    (R4_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8", newline="\n")
    readme = (
        "# p16-calibration-r4（P1.6 四轮：F 对话式扩容）\n\n"
        "- 配方：良性侧 = r3 良性件逐字节副本（2,736）；恶意侧 = 一轮恶意件逐字节副本（2,880）"
        "+ **F4-dialog 新生成 792**（四风格 ×198，轮深 2/3/4 = 240/280/272，id p16-F-002641…3432）。\n"
        "- 合计 6,408（良 2,736 : 恶 3,672 = 42.7 : 57.3）；+ m4 基座 28,842 = 35,250。\n"
        "- 新生成内容门禁：行级断言（p16cef_common.batch_check，fails=0）+ prompt 全局唯一 + "
        "G9 同款 8-gram 污染检查对 heldout 冻结件 + probes 全量（官方 gate_g9 代码路径，PASS）。\n"
        "- 冻结纪律：一轮/二轮/三轮产物只读零覆写；本目录为 r4 新版本目录，manifest sha 为冻结锚。\n"
        "- 权威：reports/p1.6-round4-design.md（§三 T1–T4 预注册）+ scripts/_p16_r4_dialog/progress.md。\n"
    )
    (R4_DIR / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    print("[manifest] manifest.json + README.md written (frozen anchor)")

    # ---------------- 6. dataset_info 四注册 ----------------
    RUN_DIR.mkdir(parents=True)
    reg = {
        "formatting": "sharegpt", "ranking": True,
        "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected"},
        "tags": {"role_tag": "from", "content_tag": "value", "user_tag": "human",
                 "assistant_tag": "gpt", "system_tag": "system"},
    }
    note_base = ("M5A-R4 multi-dataset loading (round-4 F conversational expansion; see "
                 "reports/p1.6-round4-design.md and data/dpo/p16-calibration-r4/manifest.json): ")
    entries = {
        "sec_dpo_m5a_r4_base_m4capfix": (
            "../m4-run/dpo_m4_capfix.jsonl",
            note_base + "base dpo_m4_capfix 28842 rows, sha256 " + M4_SHA
            + " = frozen constant (verified at build time, 2026-10-14); byte-identical to the base segment of every prior m5a round. ASCII-only note: LF parser.py opens this file with locale default encoding (GBK on this host), non-ASCII bytes break parsing."),
        "sec_dpo_m5a_r4_p16_benign": (
            "../dpo/p16-calibration-r4/p16_benign_release.jsonl",
            note_base + "p16-r4 benign_release 2736 rows = A 1500 + B 480 + C 360 + E 300 + D-release 96, "
            "byte-identical copy of the r3 benign release, sha256 " + R3_BENIGN_SHA
            + " (r3 manifest registered constant, re-verified at build time); single 11-key homogeneous schema. ASCII-only note (GBK lesson, m5a erratum section 7)."),
        "sec_dpo_m5a_r4_p16_malicious": (
            "../dpo/p16-calibration-r4/p16_malicious_honest.jsonl",
            note_base + "p16-r4 malicious_honest 2880 rows = F 2640 + D-refuse 240, byte-identical copy of "
            "the round-1 release file, sha256 " + R3_MALICIOUS_SHA
            + " (round-1 registered constant, re-verified 2026-10-14); single 11-key homogeneous schema. ASCII-only note (GBK lesson, m5a erratum section 7)."),
        "sec_dpo_m5a_r4_p16_f4new": (
            "../dpo/p16-calibration-r4/p16_f4_dialog.jsonl",
            note_base + "p16-r4 F4-dialog NEW 792 rows (the round-4 single mechanism variable: F conversational "
            "subfamily 792 -> 1584 = 2x). All-new generated content (4 styles x 198, new skeletons 11-20, new topics, "
            "turn depth 2/3/4 = 240/280/272); passed row-level batch_check (fails=0) + prompt global uniqueness + "
            "id disjointness from rounds 1-3 + G9-equivalent 8-gram pollution check vs ALL heldout + probes "
            "(official gate_g9 code path, ok=true); sha256 " + sha256_file(R4_DIR / "p16_f4_dialog.jsonl")
            + " = frozen constant of build_p16_r4.py. ASCII-only note (GBK lesson, m5a erratum section 7)."),
    }
    info = {}
    for name, (fname, note) in entries.items():
        info[name] = {"file_name": fname, **{k: (json.dumps(v, ensure_ascii=True) if False else v) for k, v in reg.items() if k in ("formatting", "ranking")}, "columns": reg["columns"], "tags": reg["tags"], "note": note}
    # 重写上面的推导（保持显式键序，与 r3 注册件同构）
    info = {}
    for name, (fname, note) in entries.items():
        info[name] = {
            "file_name": fname,
            "formatting": reg["formatting"],
            "ranking": reg["ranking"],
            "columns": reg["columns"],
            "tags": reg["tags"],
            "note": note,
        }
    text = json.dumps(info, ensure_ascii=True, indent=1) + "\n"
    text.encode("ascii")  # 纯 ASCII 断言（GBK 雷排）
    (RUN_DIR / "dataset_info.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"[dataset_info] 4 registrations written, pure-ASCII ✓ ({', '.join(info)})")

    # ---------------- 7. config 生成 + DIFF-HP-ZERO 机器证明 ----------------
    r3_lines = CFG_R3.read_text(encoding="utf-8").splitlines()
    header = [
        "### ═══ M5A-R4 探针（P1.6 四轮 · F 对话式扩容）：r4 数据 + 一~三轮配方零改动 ═══",
        "#",
        "# ★ 本件 = configs/m5a-dpo-r3.yaml 的四轮复制（2026-10-14，reports/p1.6-round4-design.md",
        "#   §二 配方预注册，T1–T4 预测已冻结）。非注释功能行 diff 仅 3 行：dataset_dir（→ data\\m5a-r4-run）、",
        "#   dataset（→ 四 r4 注册）、output_dir（→ checkpoints\\qwen3-06b-sec-m5a-dpo-r4）；",
        "#   HP 零改动 ✗✓（单变量在数据侧）。四轮数据实况：m4 base 28,842 + p16-r4 6,408",
        "#   （良 2,736 : 恶 3,672 = 42.7 : 57.3；良性侧 = r3 良性件逐字节副本，唯一机制变量 =",
        "#   F 对话式子族扩容 792→1,584：新子族 F4-dialog 792 行全部新生成，过行级断言 + G9 同款",
        "#   8-gram 污染检查对 heldout 冻结件；轮深 2/3/4 = 240/280/272）= 35,250 行；全 epoch = 2,204 步；",
        "#   校准对占比 18.18%（300 步 × batch 16 可见 ≈873 行，σ≈27）。",
        "#   r4 全 sha / 行级断言 / 门禁时序见 data/dpo/p16-calibration-r4/manifest.json +",
        "#   reports/p1.6-round4-build.md + scripts/_p16_r4_dialog/progress.md。",
        "#   ⚠ 下方继承的 r3/r2/r1 注释块为历史语境（2,154 / 2,129 / 2,163 步 等数值不再适用四轮，以本节为准）。",
        "#",
    ]
    r4_lines = []
    for line in r3_lines:
        if line.startswith("dataset_dir:"):
            r4_lines.append("dataset_dir: J:\\Projects\\llm_for_sec\\data\\m5a-r4-run")
        elif line.startswith("dataset:"):
            r4_lines.append("dataset: sec_dpo_m5a_r4_base_m4capfix,sec_dpo_m5a_r4_p16_benign,sec_dpo_m5a_r4_p16_malicious,sec_dpo_m5a_r4_p16_f4new")
        elif line.startswith("output_dir:"):
            r4_lines.append("output_dir: J:\\Projects\\llm_for_sec\\checkpoints\\qwen3-06b-sec-m5a-dpo-r4")
        else:
            r4_lines.append(line)
    CFG_R4.write_text("\n".join(header + r4_lines) + "\n", encoding="utf-8", newline="\n")
    # 机器证明：非注释功能行 diff 恰 3 行
    def functional(p: Path):
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
        return out
    f3, f4 = functional(CFG_R3), functional(CFG_R4)
    diffs = [(a, b) for a, b in zip(f3, f4) if a != b]
    if len(f3) != len(f4) or len(diffs) != 3:
        fail(f"DIFF-HP-ZERO violated: functional lines {len(f3)} vs {len(f4)}, diffs={diffs}")
    for a, b in diffs:
        if not (a.startswith("dataset_dir:") or a.startswith("dataset:") or a.startswith("output_dir:")):
            fail(f"unexpected functional diff: {a} -> {b}")
    print(f"[config] configs/m5a-dpo-r4.yaml written; non-comment functional diff = exactly 3 lines "
          f"(dataset_dir / dataset / output_dir), HP {len(f4)} functional lines otherwise identical ✓")
    print("DIFF-HP-ZERO=PASS")

    # ---------------- 8. 装载冒烟 ----------------
    import locale
    raw = (RUN_DIR / "dataset_info.json").read_bytes()
    raw.decode("ascii")
    info2 = json.loads(raw.decode(locale.getpreferredencoding(False)))
    ds_field = None
    for line in CFG_R4.read_text(encoding="utf-8").splitlines():
        if line.startswith("dataset:"):
            ds_field = line.split(":", 1)[1].strip()
            break
    names = [n.strip() for n in ds_field.split(",") if n.strip()]
    assert len(names) == 4, names
    for n in names:
        assert n in info2, f"missing registration {n}"
        assert info2[n]["formatting"] == "sharegpt" and info2[n]["ranking"] is True
    print(f"[smoke] dataset 4-name list resolved: {names}")
    from datasets import load_dataset  # noqa: E402
    expect = {"sec_dpo_m5a_r4_base_m4capfix": 28842, "sec_dpo_m5a_r4_p16_benign": 2736,
              "sec_dpo_m5a_r4_p16_malicious": 2880, "sec_dpo_m5a_r4_p16_f4new": 792}
    total = 0
    for n in names:
        path = (ROOT / "data" / "m5a-r4-run" / info2[n]["file_name"]).resolve()
        ds = load_dataset("json", data_files=[str(path)], split="train")
        cols = set(ds.column_names)
        assert len(ds) == expect[n], f"{n}: {len(ds)} != {expect[n]}"
        if n != "sec_dpo_m5a_r4_base_m4capfix":
            assert cols == {"dpo_class", "id", "pack", "lang", "polarity", "rejected_form",
                            "archetype_id", "conversations", "chosen", "rejected", "src_task"}, cols
        else:
            assert {"conversations", "chosen", "rejected"} <= cols, cols
        total += len(ds)
        print(f"[smoke] {n}: {len(ds):,} rows loaded ({path.relative_to(ROOT)})")
    assert total == 35250, total
    print(f"[smoke] total {total:,} = m4 base 28,842 + p16-r4 6,408 (benign 2,736 + malicious 2,880 + f4new 792) ✓")
    print("SMOKE-M5A-R4-MULTIDS=OK")
    print(f"BUILD-P16-R4=OK (elapsed {time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
