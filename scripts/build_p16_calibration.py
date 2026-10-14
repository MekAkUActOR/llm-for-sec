# -*- coding: utf-8 -*-
"""P1.6 最终合并器：parts-abd + parts-cef → 冻结 release 文件 + manifest（纯 CPU）。

职责（reports/p1.6-calibration-design.md §4.4 施工规格）：
  1. 启动断言（fail-closed ✗ 即退出、零落盘）：
     - 三包 × zh/en 共 6 个冻结 system 模板 sha256 与基座
       data/dpo-remediation-staging/dpo_m4_capfix.jsonl 逐字节一致（§4.2）；
     - parts-abd.jsonl / parts-cef.jsonl 的 sha256 与行数与两份 parts manifest 一致。
  2. 合并组装 + 良/恶 50:50 校验（任一不符即 fail-closed ✗）：
     - 良 2,880 = CEF 660（C 360 + E 300）+ ABD 2,220（A 1,500 + B 480 + D放行 240）
     - 恶 2,880 = F 2,640 + D拒绝 240（对话式 cd 120 + 载体指令顺从 120）
  3. schema 规范化（登记在 manifest）：CEF 多轮前缀轮 from='assistant' → 'gpt'
     （m4/house DPO 口径 = LLaMA-Factory dataset_info 的 user_tag=human/assistant_tag=gpt，
      不归一则在 ranking 转换器里被判 Invalid role tag 而整行丢弃 ✗）。
  4. 产出（§4.4 布局，PREFLIGHT 防覆写：已存在且字节不同 ⇒ 拒绝 ✗ 不得原地改）：
     data/dpo/p16-calibration/p16_benign_release.jsonl   （2,880 行，按 id 排序）
     data/dpo/p16-calibration/p16_malicious_honest.jsonl （2,880 行，按 id 排序）
     data/dpo/p16-calibration/manifest.json              （全量 sha256/分布/两 parts 谱系链）
     data/dpo/p16-calibration/README.md                  （结账记录）
  5. 门禁 G1–G12 不在本脚本（checker 职责 ✗）；本脚本零 heldout/probes 读取 ✓。

用法：.venv\\Scripts\\python.exe scripts\\build_p16_calibration.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P16_DIR = os.path.join(ROOT, "data", "dpo", "p16-calibration")
PARTS_ABD = os.path.join(P16_DIR, "parts-abd.jsonl")
PARTS_CEF = os.path.join(P16_DIR, "parts-cef.jsonl")
MANIFEST_ABD = os.path.join(P16_DIR, "parts-abd.manifest.json")
MANIFEST_CEF = os.path.join(P16_DIR, "manifest-cef.json")
M4_BASE = os.path.join(ROOT, "data", "dpo-remediation-staging", "dpo_m4_capfix.jsonl")
OUT_BENIGN = os.path.join(P16_DIR, "p16_benign_release.jsonl")
OUT_MALICIOUS = os.path.join(P16_DIR, "p16_malicious_honest.jsonl")
OUT_MANIFEST = os.path.join(P16_DIR, "manifest.json")
OUT_README = os.path.join(P16_DIR, "README.md")

SEED = 20261008
SPEC = "reports/p1.6-calibration-design.md（§4 施工规格 / §5.1 配比 / §6 门禁表）"

# ---- 冻结模板哈希（§4.2：m4 基座三包 × zh/en，启动断言；来源 2026-10-08 实测提取） ----
FROZEN_TEMPLATE_SHA256 = {
    ("professional", "zh"): "67d223f225115a417f0bd12f76100bc7aad6c6297d587db15a829b3ee2b6f45b",
    ("professional", "en"): "74a00b892596c82100621fda96ead06d6c4503e9c90bf92c0c8136c430ef5c0b",
    ("default", "zh"): "8adcb0e403ea4fd0f02cb4bf824b8c860f7c10adba3a289b47637415b8dc34c0",
    ("default", "en"): "c5140564c688ff86f472d6ee14c202732c6f3b9cff439ff49338b7bf889320bb",
    ("conservative", "zh"): "861286d215aef95f1aa4540fbfd97fbcc46a11e8065e8ac07410d9bf6062f3cc",
    ("conservative", "en"): "f4dc69fb50bb78a72a52a2fa0809718a8d271bfa8d20202737209ca86f252a36",
}

# ---- 50:50 组成契约（§5.1；任一不符 ⇒ fail-closed，零落盘） ----
EXPECT = {
    "abd_rows": 2460, "cef_rows": 3300,
    "family": {"A": 1500, "B": 480, "C": 360, "D": 480, "E": 300, "F": 2640},
    "benign": {"A": 1500, "B": 480, "C": 360, "E": 300, "D_release": 240},   # = 2,880
    "malicious": {"F": 2640, "D_conv": 120, "D_carrier": 120},               # = 2,880
}
ID_RE = re.compile(r"^p16-([A-F])-(\d{6})$")


def die(msg: str) -> None:
    print(f"[FATAL] {msg}")
    print("BUILD-P16=FAIL（fail-closed，未落盘）")
    sys.exit(1)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as e:
                    die(f"{os.path.basename(path)} 第 {ln + 1} 行 JSON 解析失败：{e}")
    return out


# ================================================================ 启动断言 ==
def assert_templates() -> dict:
    """从 m4 基座提取全部 system 模板，断言与冻结哈希集合逐项一致（§4.2）。"""
    seen = {}
    n = 0
    with open(M4_BASE, encoding="utf-8") as f:
        for line in f:
            n += 1
            r = json.loads(line)
            for t in r.get("conversations", []):
                if t.get("from") == "system":
                    v = t["value"]
                    h = hashlib.sha256(v.encode("utf-8")).hexdigest()
                    seen[h] = v
                    break
    got = set(seen)
    want = set(FROZEN_TEMPLATE_SHA256.values())
    if got != want:
        die(f"m4 基座模板集漂移：多出 {[h[:12] for h in got - want]} / 缺失 {[h[:12] for h in want - got]}")
    by_hash = {h: k for k, h in FROZEN_TEMPLATE_SHA256.items()}
    print(f"[OK] 冻结模板断言：m4 基座 {n} 行内 6 个 system 模板 sha256 与冻结表逐项一致 ✓")
    return {by_hash[h]: v for h, v in seen.items()}  # (pack, lang) -> 模板文本


def assert_parts() -> tuple[list, list, dict, dict]:
    """parts 完整性：sha256 / 行数 / manifest 一致；返回两批行与两份 manifest。"""
    m_abd = json.loads(open(MANIFEST_ABD, encoding="utf-8").read())
    m_cef = json.loads(open(MANIFEST_CEF, encoding="utf-8").read())
    checks = [
        (PARTS_ABD, m_abd.get("sha256"), m_abd.get("lines"), EXPECT["abd_rows"], "parts-abd"),
        (PARTS_CEF, m_cef.get("assembled", {}).get("sha256"), m_cef.get("assembled", {}).get("rows"),
         EXPECT["cef_rows"], "parts-cef"),
    ]
    for path, want_sha, want_rows, expect_rows, tag in checks:
        if not os.path.exists(path):
            die(f"{tag} 不存在：{path}")
        sha = sha256_file(path)
        if sha != want_sha:
            die(f"{tag} sha256 与 manifest 不符：{sha[:16]}… != {want_sha[:16] if want_sha else '∅'}…")
        rows = load_jsonl(path)
        if len(rows) != want_rows or len(rows) != expect_rows:
            die(f"{tag} 行数 {len(rows)} != manifest {want_rows} / 预期 {expect_rows}")
        print(f"[OK] {tag}: {len(rows)} 行，sha256 …{sha[:12]} 与 manifest 一致 ✓")
    return load_jsonl(PARTS_ABD), load_jsonl(PARTS_CEF), m_abd, m_cef


# ================================================================ 合并与校验 ==
KEYS = {"dpo_class", "id", "pack", "lang", "polarity", "rejected_form", "archetype_id",
        "conversations", "chosen", "rejected", "src_task"}
SRC_FAMILY = {"p16:A": "A", "p16:B": "B", "p16:C": "C", "p16:D": "D", "p16:E": "E", "p16:F": "F"}


def classify(r: dict) -> str:
    """行族别（id 与 src_task 双源一致才可信）。"""
    m = ID_RE.match(r.get("id", ""))
    if not m:
        die(f"id 不合命名空间：{r.get('id')!r}")
    fam_id = m.group(1)
    prefix = ":".join(r.get("src_task", "").split(":")[:2])   # p16:A / p16:F / …（F 载体三段式取前两段）
    if SRC_FAMILY.get(prefix) != fam_id:
        die(f"{r['id']}: id 族 {fam_id} 与 src_task 前缀 {prefix} 不一致")
    return fam_id


def normalize_roles(rows: list) -> int:
    """前缀轮 from='assistant' → 'gpt'（house DPO 口径）；返回改写轮数。"""
    n = 0
    for r in rows:
        for t in r["conversations"][1:]:
            if t["from"] == "assistant":
                t["from"] = "gpt"
                n += 1
    return n


def main() -> int:
    print("== P1.6 最终合并（build_p16_calibration） ==")
    templates = assert_templates()
    abd, cef, m_abd, m_cef = assert_parts()
    rows = abd + cef

    # ---- 行级结构快检（详细门禁属 checker；此处只挡合并级致命伤） ----
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        dup = [k for k, v in Counter(ids).items() if v > 1][:5]
        die(f"id 全局重复：{dup}")
    for r in rows:
        if set(r.keys()) != KEYS:
            die(f"{r['id']}: 键集不符：{sorted(set(r.keys()) ^ KEYS)}")
        if r["chosen"]["value"] == r["rejected"]["value"]:
            die(f"{r['id']}: chosen 与 rejected 逐字相同")
        if r["pack"] not in ("professional", "default", "conservative"):
            die(f"{r['id']}: pack 非法 {r['pack']}")
        sysv = r["conversations"][0]
        if sysv["from"] != "system" or sysv["value"] not in templates.values():
            die(f"{r['id']}: system 轮不是冻结模板")
        if f"pack:{r['pack']}@0.1" not in sysv["value"]:
            die(f"{r['id']}: system 模板 pack 标记与行 pack 不符")

    n_norm = normalize_roles(rows)
    print(f"[OK] schema 快检通过；前缀轮 assistant→gpt 归一 {n_norm} 轮（CEF 多轮行）")

    # ---- 良/恶 50:50 组成校验（fail-closed 核心 ✗） ----
    fam_cnt = Counter(classify(r) for r in rows)
    for f, want in EXPECT["family"].items():
        if fam_cnt.get(f) != want:
            die(f"族 {f} 总量 {fam_cnt.get(f)} != 预期 {want}")
    benign, malicious = [], []
    d_rel = d_conv = d_car = 0
    for r in rows:
        f = r["id"][4]
        if f in ("A", "B", "C", "E"):
            if r["polarity"] != "benign_release":
                die(f"{r['id']}: 族 {f} 极性应为 benign_release，实为 {r['polarity']}")
            benign.append(r)
        elif f == "F":
            if r["polarity"] != "malicious_refuse":
                die(f"{r['id']}: 族 F 极性应为 malicious_refuse，实为 {r['polarity']}")
            malicious.append(r)
        else:  # D 双向
            st = r["src_task"]
            if st == "p16:D:release":
                d_rel += 1
                if r["polarity"] != "benign_release":
                    die(f"{r['id']}: D 放行向极性应为 benign_release")
                benign.append(r)
            elif st in ("p16:D:refuse_conversational", "p16:D:refuse_carrier"):
                if st.endswith("conversational"):
                    d_conv += 1
                else:
                    d_car += 1
                if r["polarity"] != "malicious_refuse":
                    die(f"{r['id']}: D 拒绝向极性应为 malicious_refuse")
                malicious.append(r)
            else:
                die(f"{r['id']}: 未知 D src_task {st}")
    exp_b = EXPECT["benign"]
    exp_m = EXPECT["malicious"]
    got_b = {"A": fam_cnt["A"], "B": fam_cnt["B"], "C": fam_cnt["C"], "E": fam_cnt["E"], "D_release": d_rel}
    got_m = {"F": fam_cnt["F"], "D_conv": d_conv, "D_carrier": d_car}
    if got_b != exp_b:
        die(f"良性组成不符：{got_b} != {exp_b}（良 {len(benign)} ≠ 2,880）")
    if got_m != exp_m:
        die(f"恶意组成不符：{got_m} != {exp_m}（恶 {len(malicious)} ≠ 2,880）")
    if len(benign) != 2880 or len(malicious) != 2880:
        die(f"50:50 校验失败：良 {len(benign)} / 恶 {len(malicious)}")
    print(f"[OK] 良/恶 50:50 校验：良 2,880（CEF 660=C 360+E 300 · ABD 2,220=A 1,500+B 480+D放行 240）"
          f" / 恶 2,880（F 2,640 + D拒绝 240=对话 120+载体 120）✓")

    # ---- 产出（确定性：按 id 排序；PREFLIGHT 防覆写） ----
    benign.sort(key=lambda r: r["id"])
    malicious.sort(key=lambda r: r["id"])
    def dump(rows: list, path: str) -> bytes:
        data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
        if os.path.exists(path):
            old = open(path, "rb").read()
            if old != data:
                die(f"防覆写：{os.path.basename(path)} 已存在且内容不同（冻结纪律：修改 ⇒ 新开 p16b 版本目录，"
                    f"如需重建请先人工确认并移除旧文件）")
            print(f"[SKIP] {os.path.basename(path)} 已存在且字节一致（幂等）")
        else:
            with open(path, "wb") as f:
                f.write(data)
            print(f"[WRITE] {os.path.basename(path)}: {len(rows)} 行 {len(data):,} B")
        return data

    data_b = dump(benign, OUT_BENIGN)
    data_m = dump(malicious, OUT_MALICIOUS)

    # ---- 分布统计（manifest 全量登记） ----
    def dist(rows: list, keys) -> dict:
        out = {}
        for k in keys:
            d = Counter(r[k] for r in rows)
            out[k] = dict(sorted(d.items()))
        return out

    fam_of = {r["id"]: r["id"][4] for r in rows}
    by_family = {}
    for f in "ABCDEF":
        frows = [r for r in rows if r["id"][4] == f]
        by_family[f] = {"rows": len(frows), **dist(frows, ("lang", "pack", "polarity",
                                                          "rejected_form", "dpo_class", "src_task"))}
    verdict_pairs = Counter()
    for r in rows:
        for side in ("chosen", "rejected"):
            last = r[side]["value"].rstrip("\n").split("\n")[-1]
            o = json.loads(last[len("VERDICT: "):])
            verdict_pairs[f"{o['action']}/{o['verdict']}"] += 1

    manifest = {
        "name": "p16-calibration-release",
        "built": "2026-10-08",
        "seed": SEED,
        "spec": SPEC,
        "builder": "scripts/build_p16_calibration.py",
        "checker": "scripts/check_p16_calibration.py（G1–G12，fail-closed）",
        "files": {
            "p16_benign_release.jsonl": {"rows": len(benign), "bytes": len(data_b),
                                         "sha256": hashlib.sha256(data_b).hexdigest(),
                                         "composition": "A 1,500 + B 480 + C 360 + E 300 + D放行 240"},
            "p16_malicious_honest.jsonl": {"rows": len(malicious), "bytes": len(data_m),
                                           "sha256": hashlib.sha256(data_m).hexdigest(),
                                           "composition": "F 2,640 + D拒绝 240（对话式 120 + 载体 120）"},
        },
        "polarity_balance": {"benign_release": len(benign), "malicious_refuse": len(malicious)},
        "normalization": {
            "prefix_assistant_to_gpt": n_norm,
            "reason": "CEF 多轮前缀轮 from=assistant 归一为 house DPO 口径 gpt"
                      "（LLaMA-Factory dataset_info user_tag=human/assistant_tag=gpt；不归一则 ranking 转换器整行丢弃）",
        },
        "distributions": {
            "overall": dist(rows, ("lang", "pack", "polarity", "dpo_class")),
            "by_family": by_family,
            "verdict_pairs": dict(sorted(verdict_pairs.items())),
            "a_subdomain": dict(sorted(Counter(r["src_task"] for r in rows if r["id"][4] == "A").items())),
        },
        "pack_templates_sha256": {f"{p}/{l}": h for (p, l), h in sorted(FROZEN_TEMPLATE_SHA256.items())},
        "pack_template_usage": {
            "abd": "pack × lang 六模板全用（zh/en 各三）",
            "cef": "三包 zh 模板（en 行亦用 zh 模板，批次既定设计，见 manifest-cef.json）",
        },
        "lineage": {
            "parts_abd": {
                "file": "data/dpo/p16-calibration/parts-abd.jsonl",
                "rows": m_abd["lines"], "sha256": m_abd["sha256"],
                "manifest": "data/dpo/p16-calibration/parts-abd.manifest.json",
                "manifest_sha256": sha256_file(MANIFEST_ABD),
                "generated_by": m_abd.get("generated_by"),
                "ledger": m_abd.get("ledger"),
                "sub_parts": m_abd.get("parts", []),
            },
            "parts_cef": {
                "file": "data/dpo/p16-calibration/parts-cef.jsonl",
                "rows": m_cef["assembled"]["rows"], "sha256": m_cef["assembled"]["sha256"],
                "manifest": "data/dpo/p16-calibration/manifest-cef.json",
                "manifest_sha256": sha256_file(MANIFEST_CEF),
                "generated_by": "scripts/_p16_parts_cef/gen_c.py + gen_e.py + gen_f_carrier.py + gen_f_dialog.py + assemble_cef.py",
                "sub_parts": m_cef.get("parts", []),
            },
            "m4_base": {
                "file": "data/dpo-remediation-staging/dpo_m4_capfix.jsonl",
                "role": "冻结三包 system 模板来源（§4.2 逐字节复用）",
                "templates_sha256_asserted": True,
            },
        },
        "gate_registration": {
            "g9_whitelist": {
                "policy_pack_system_templates": "6 个冻结模板全文（上表 sha256）",
                "verdict_json_skeleton": "正则 VERDICT: \\{[^\\n]*\\}（双侧对称剥离：骨架+冻结词表值；"
                                          "findings 内容由 G4 槽位/形态断言另行把关）",
                "dsh_protocol_header_skeleton": ["<dsh-protocol v=\"0.1\">", "</dsh-protocol>", "<system>",
                                                 "</system>", "<operator>", "</operator>", "<user>", "</user>",
                                                 "<meta>", "</meta>", "<body>", "</body>", "<carrier",
                                                 "type=\"tool_output\"", "trust=\"untrusted\"", "id=\"c1\">",
                                                 "role: security_analyst", "role: 安全分析助手",
                                                 "authorization: read-only assessment", "authorization: 分析授权：只读评估",
                                                 "authorization: analyst", "output-mode: structured",
                                                 "policy: default", "policy: professional", "policy: conservative",
                                                 "policy: pack:default@0.1", "policy: pack:professional@0.1",
                                                 "policy: pack:conservative@0.1"],
            },
            "g10_official_signature_source": "scripts/check_jailbreak_suite.py F4_SIG/F6_SIG（B3 官方口径，"
                                             "checker 内嵌副本 + 对源文件 ast 机器校验一致）",
            "g7_interpretation": "响应级 chosen~rejected 偏好极性探针（长度/契约键格式特征，action/verdict "
                                 "值属语义载荷列入诊断不入门，详见门禁报告）",
            "g11_policy": "每原型条数上限（A–E 30 / F 48）+ 族内全行精确重复零容忍 + m3 口径相似度全景报告",
        },
        "launch_audit_wiring": {
            "status": "PENDING_REGISTRATION",
            "note": "scripts/launch_audit.py 尚不存在（P1.8 待建，2026-10-08 实查 ✓ 不猜）；建成后必须："
                    "①串接 scripts/check_p16_calibration.py 退出码，无 P16-GATE=PASS 输出即拒绝发射（fail-closed）；"
                    "②把本目录两 release 文件 sha256 纳入发射审计基座登记（§8.7 归因可溯）",
        },
        "spotcheck": {"status": "PENDING_HUMAN_GATE",
                      "note": "冻结前人工抽查 15 行/族 × 6 = 90 行 → reports/p16-spotcheck.md（§6 人工关口，"
                              "机检不可全代）；parts 批已出 reports/p1.6-spotcheck-abd.md + p1.6-spotcheck-cef.md"},
        "version_discipline": "冻结 = 本 manifest sha256；任何修改 ⇒ 新开 data/dpo/p16b-calibration/ 版本目录，"
                              "不得原地改 ✗（v0.6/v0.7 先例）",
        "tokenizer": "checkpoints/qwen3-06b-sec-m4-capfix-probe（G8 部署口径逐行实测 ≤1,000）",
    }
    mtxt = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    if os.path.exists(OUT_MANIFEST):
        old = open(OUT_MANIFEST, "rb").read()
        if old != mtxt.encode("utf-8"):
            die("防覆写：manifest.json 已存在且内容不同")
        print("[SKIP] manifest.json 已存在且字节一致（幂等）")
    else:
        with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
            f.write(mtxt)
        print("[WRITE] manifest.json")

    # ---- README（结账记录） ----
    readme = f"""# P1.6 拒绝校准对 · 最终 release（冻结件）

- 规格：`reports/p1.6-calibration-design.md`（§4 施工规格为唯一权威）· seed={SEED}
- 构建：`scripts/build_p16_calibration.py`（合并器，PREFLIGHT 防覆写）·
  门禁：`scripts/check_p16_calibration.py`（G1–G12 fail-closed，报告 `reports/p1.6-gate-report.md`）

## 内容

| 文件 | 行数 | 组成 | sha256 |
|---|---|---|---|
| `p16_benign_release.jsonl` | 2,880 | A 1,500 + B 480 + C 360 + E 300 + D放行 240 | `{manifest['files']['p16_benign_release.jsonl']['sha256']}` |
| `p16_malicious_honest.jsonl` | 2,880 | F 2,640 + D拒绝 240（对话式 120 + 载体 120） | `{manifest['files']['p16_malicious_honest.jsonl']['sha256']}` |

极性 50:50（良 2,880 / 恶 2,880）；en:zh ≈ 60:40；全量分布与两 parts 谱系链见 `manifest.json`。

## 纪律

- 冻结 = `manifest.json` sha256；任何修改 ⇒ 新开 `data/dpo/p16b-calibration/`，**不得原地改** ✗。
- parts 中间件（`parts-abd.jsonl` / `parts-cef.jsonl`）保持原样，本目录只增不改 ✗。
- 门禁 G9 样板豁免白名单（政策包模板/VERDICT 骨架/dsh-protocol 头骨架）逐条登记于 `manifest.json`
  `gate_registration.g9_whitelist`，逐条可审计。
- CEF 多轮前缀轮 `from: assistant` 已归一为 `gpt`（house DPO / LLaMA-Factory 口径，共 {n_norm} 轮，
  登记 `normalization`）。

## 待办（发射前置）

1. `scripts/launch_audit.py`（P1.8）建成后串接 checker 退出码：无 `P16-GATE=PASS` = 拒绝发射
   （已登记 `manifest.json` `launch_audit_wiring`）。
2. 人工抽查 90 行 → `reports/p16-spotcheck.md`（§6 人工关口，状态 PENDING_HUMAN_GATE）。
3. M5 合并件 `data/m5-run/dpo_m5_calib.jsonl`（基座 28,842 + 本包 5,760）与
   `dataset_info.json` 注册 `sec_dpo_m5_calib` 属 P2.9 发射集成，不在本件职责内。
"""
    if os.path.exists(OUT_README):
        old = open(OUT_README, "rb").read()
        if old != readme.encode("utf-8"):
            die("防覆写：README.md 已存在且内容不同")
        print("[SKIP] README.md 已存在且字节一致（幂等）")
    else:
        with open(OUT_README, "w", encoding="utf-8", newline="\n") as f:
            f.write(readme)
        print("[WRITE] README.md")

    print("\n== 合并完成 ==")
    print(f"  良 {len(benign)} / 恶 {len(malicious)} = 50:50 ✓ · 归一 {n_norm} 前缀轮")
    print(f"  {os.path.basename(OUT_BENIGN)}  sha256 …{manifest['files']['p16_benign_release.jsonl']['sha256'][:16]}")
    print(f"  {os.path.basename(OUT_MALICIOUS)} sha256 …{manifest['files']['p16_malicious_honest.jsonl']['sha256'][:16]}")
    print("BUILD-P16=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
