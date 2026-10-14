# -*- coding: utf-8 -*-
"""P1.6 四轮施工后独立核验（_tmp 先例，可退役）：对已落盘 r4 release 全量复检。

与 build_p16_r4.py 的区别：不含 PREFLIGHT/组装（产物已在位），纯只读复检——
冻结输入 8 项 sha / r4 五件 sha 对 manifest / 行级断言复跑 / 恒等式 / config diff /
dataset_info 与装载合计。rc=0 ⇔ 全过。
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "_p16_parts_cef"))
import p16cef_common as K  # noqa: E402

R1 = ROOT / "data" / "dpo" / "p16-calibration"
R3 = ROOT / "data" / "dpo" / "p16-calibration-r3"
R4 = ROOT / "data" / "dpo" / "p16-calibration-r4"
PARTS = ROOT / "scripts" / "_p16_r4_dialog" / "parts"
M4 = ROOT / "data" / "dpo-remediation-staging" / "dpo_m4_capfix.jsonl"
CFG_R3 = ROOT / "configs" / "m5a-dpo-r3.yaml"
CFG_R4 = ROOT / "configs" / "m5a-dpo-r4.yaml"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jsonl(p: Path) -> list:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ok = 0
    # A. 冻结输入 8 项（一轮两 release + 两 parts + r3 三件 + m4）
    m1 = json.loads((R1 / "manifest.json").read_text(encoding="utf-8"))
    for f, meta in m1["files"].items():
        assert sha(R1 / f) == meta["sha256"], f"r1/{f} drift"
        ok += 1
    abd = json.loads((R1 / "parts-abd.manifest.json").read_text(encoding="utf-8"))
    cef = json.loads((R1 / "manifest-cef.json").read_text(encoding="utf-8"))
    assert sha(R1 / "parts-abd.jsonl") == abd["sha256"]
    assert sha(R1 / "parts-cef.jsonl") == cef["assembled"]["sha256"]
    ok += 2
    m3 = json.loads((R3 / "manifest.json").read_text(encoding="utf-8"))
    for f, meta in m3["files"].items():
        assert sha(R3 / f) == meta["sha256"], f"r3/{f} drift"
        ok += 1
    assert sha(M4) == "d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414" and len(jsonl(M4)) == 28842
    ok += 1
    print(f"[A] frozen inputs: {ok}/8 sha-verified")

    # B. r4 五件对 manifest
    m4r = json.loads((R4 / "manifest.json").read_text(encoding="utf-8"))
    for f, meta in m4r["files"].items():
        assert sha(R4 / f) == meta["sha256"], f"r4/{f} drift"
    assert m4r["files"]["p16_benign_release.jsonl"]["sha256"] == m3["files"]["p16_benign_release.jsonl"]["sha256"]
    assert m4r["files"]["p16_malicious_honest.jsonl"]["sha256"] == m1["files"]["p16_malicious_honest.jsonl"]["sha256"]
    # parts 账本一致
    g01 = json.loads((PARTS / "part-g01.check.json").read_text(encoding="utf-8"))
    g02 = json.loads((PARTS / "part-g02.check.json").read_text(encoding="utf-8"))
    assert sha(PARTS / "part-g01.jsonl") == g01["sha256"] and sha(PARTS / "part-g02.jsonl") == g02["sha256"]
    g9 = json.loads((PARTS / "part-f4-g9.check.json").read_text(encoding="utf-8"))
    assert g9["ok"] is True
    assert "postmortem_20261014_2313" in m4r and m4r["schema_normalization"]["rewrites"] == 1616
    print(f"[B] r4 five files sha == manifest; benign == r3 value; malicious == r1 value; parts ledger "
          f"consistent; G9 ok=true; schema_normalization registered ✓")

    # C. 行级断言复跑 + 角色标签词表（release 口径）+ G9 终判
    rows = jsonl(R4 / "p16_f4_dialog.jsonl")
    assert len(rows) == 792
    # parts 层口径机检（p16cef_common 约定前缀轮 from ∈ {human, assistant}）
    parts_rows = jsonl(PARTS / "part-g01.jsonl") + jsonl(PARTS / "part-g02.jsonl")
    assert len(parts_rows) == 792
    summ = K.batch_check(parts_rows, "F")
    assert not summ["fails"], summ["fails"][:5]
    # release 层：组装归一化后词表/计数（训练发射事故的机器防线）
    ALLOWED = {"system", "human", "gpt"}
    for r in rows:
        assert all(c["from"] in ALLOWED for c in r["conversations"]), r["id"]
        assert r["chosen"]["from"] == "gpt" and r["rejected"]["from"] == "gpt", r["id"]
        assert r["conversations"][0]["from"] == "system" and r["conversations"][-1]["from"] == "human", r["id"]
    tag_c = Counter(c["from"] for r in rows for c in r["conversations"])
    assert tag_c == Counter({"system": 792, "human": 2408, "gpt": 1616}), tag_c
    # 归一化改写数登记与谱系一致（parts 保留 assistant；release 为 gpt）
    n_asst = sum(1 for r in parts_rows for c in r["conversations"][1:] if c["from"] == "assistant")
    assert n_asst == 1616 == m4r["schema_normalization"]["rewrites"], (n_asst, m4r["schema_normalization"])
    # 三件词表巡检（副本 = 已训件口径）
    for f, exp in ((R4 / "p16_benign_release.jsonl", 2736), (R4 / "p16_malicious_honest.jsonl", 2880)):
        for r in jsonl(f):
            assert all(c["from"] in ALLOWED for c in r["conversations"]), (f.name, r["id"])
    g9r = json.loads((PARTS / "part-f4-g9-release.check.json").read_text(encoding="utf-8"))
    assert g9r["ok"] is True and g9r["rows"] == 792
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids) and len(set(ids)) == 792
    assert ids[0] == "p16-F-002641" and ids[-1] == "p16-F-003432"
    r1_ids = {r["id"] for r in jsonl(R1 / "p16_benign_release.jsonl")} | {r["id"] for r in jsonl(R1 / "p16_malicious_honest.jsonl")}
    assert not (set(ids) & r1_ids)
    # parts-f4-dialog 谱系副本恒等
    assert sha(R4 / "parts-f4-dialog.jsonl") == sha(R4 / "p16_f4_dialog.jsonl")
    # 官方建造日志的拼接口径冒烟标记（SMOKE v2 = 训练真实路径；pwsh *> 重定向为 UTF-16LE，按 BOM 嗅探）
    raw_blog = (ROOT / "reports" / "logs" / "p16-r4-build-v2.log").read_bytes()
    blog = raw_blog.decode("utf-16") if raw_blog[:2] == b"\xff\xfe" else raw_blog.decode("utf-8", errors="replace")
    assert "SMOKE-M5A-R4-MULTIDS=OK (concat caliber)" in blog and "BUILD-P16-R4=OK" in blog
    print(f"[C] parts-layer batch_check fails=0 (H4 median {summ['ratio_median']}, token max {summ['token_max']}); "
          f"release role-tags system 792 / human 2408 / gpt 1616 (normalized 1616 = manifest); "
          f"3-file vocabulary sweep OK; G9-release ok=true; concat-caliber smoke marker in build log ✓")

    # D. 恒等式与配比
    nb, nm = len(jsonl(R4 / "p16_benign_release.jsonl")), len(jsonl(R4 / "p16_malicious_honest.jsonl"))
    assert (nb, nm, len(rows)) == (2736, 2880, 792) and nb + nm + len(rows) == 6408
    assert Counter(r["polarity"] for r in rows) == Counter({"malicious_refuse": 792})
    assert Counter(r["src_task"].rsplit(":", 1)[-1] for r in rows) == Counter(
        {"escalation": 198, "roleplay": 198, "fictional": 198, "puzzle": 198})
    assert Counter(r["lang"] for r in rows) == Counter({"en": 476, "zh": 316})
    assert Counter(r["pack"] for r in rows) == Counter({"default": 356, "professional": 316, "conservative": 120})
    assert Counter(r["rejected_form"] for r in rows) == Counter({"cd_conditional_transition": 396, "lip_refuse_deliver": 396})
    turns = Counter(sum(1 for c in r["conversations"] if c["from"] == "human") for r in rows)
    assert turns == Counter({2: 240, 3: 280, 4: 272})
    print(f"[D] identities: 6,408 = 2,736+2,880+792 = 良 2,736 + 恶 3,672; quota closure exact; turns {dict(sorted(turns.items()))} ✓")

    # E. config diff 恰 3 行（非注释功能行）
    def functional(p: Path):
        return [s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines()) if s and not s.startswith("#")]
    f3, f4 = functional(CFG_R3), functional(CFG_R4)
    diffs = [(a, b) for a, b in zip(f3, f4) if a != b]
    assert len(f3) == len(f4) == 29 and len(diffs) == 3
    for a, b in diffs:
        assert a.split(":")[0] in ("dataset_dir", "dataset", "output_dir")
    print(f"[E] config non-comment diff = exactly 3 lines (dataset_dir/dataset/output_dir); 29 functional lines ✓")

    # F. dataset_info + 合计
    info = json.loads((ROOT / "data" / "m5a-r4-run" / "dataset_info.json").read_text(encoding="ascii"))
    assert len(info) == 4
    raw = (ROOT / "data" / "m5a-r4-run" / "dataset_info.json").read_bytes()
    raw.decode("ascii")
    ds_line = next(l for l in CFG_R4.read_text(encoding="utf-8").splitlines() if l.startswith("dataset:"))
    names = [n.strip() for n in ds_line.split(":", 1)[1].split(",")]
    assert len(names) == 4 and all(n in info for n in names)
    total = 28842 + 2736 + 2880 + 792
    assert total == 35250
    print(f"[F] dataset_info 4 regs pure-ASCII; config names resolvable; total {total:,} ✓")

    print("VERIFY-R4-POST=PASS (A–F 6 sections, 20+ assertions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
