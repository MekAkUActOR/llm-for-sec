# -*- coding: utf-8 -*-
"""P1.6 三轮（M2b）独立核验（纯 CPU；不信 builder 内存态，重读落盘件重导）。

复刻二轮 p16-r2-verify 先例（reports/p1.6-round2-build.md §二「独立核验」），针对 r3：
  A. 行数与 sha（独立重读三 jsonl + 注册件；恶意件 sha = 一轮登记值）
  B. 族组成与极性（良 A1500/B480/C360/D96/E300 · 恶 F2640/D240=对话120+载体120；
     单文件 11 键同构 schema —— CastError 教训）
  C. 逐字节子集性（r3 每行 ∈ 一轮字节集；恶意件整文件字节恒等；六族多重集恒等）
  D. 子选算法独立复算（前缀 b'p16-r3:20261014m2b:'）逐字节复现 + id ⊆ 一轮
  E. dataset_info 注册件（纯 ASCII / 三条目 / file_name/行数/sha / sharegpt ranking 口径）
  F. r3 manifest 自洽（files rows/bytes/sha、极性 2736:2880=48.7:51.3、训练总量 34,458）
  G. 一轮 + 二轮冻结件 sha 复验未动（快检替代 ① 的独立复核）
  H. 行数恒等式（从落盘件实际族计数出发，规避二轮 verify 首跑的 parts 双计自误）
  附: r3 D良96 与 r2 D良96 的重叠数（描述性统计，非断言）
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P16_R1 = os.path.join(ROOT, "data", "dpo", "p16-calibration")
P16_R2 = os.path.join(ROOT, "data", "dpo", "p16-calibration-r2")
P16_R3 = os.path.join(ROOT, "data", "dpo", "p16-calibration-r3")
DS_INFO = os.path.join(ROOT, "data", "m5a-r3-run", "dataset_info.json")

FROZEN_R1 = {
    "p16_benign_release.jsonl": "1636ba88c2f8834cdb581ea9c147e94990f28229c3665e5559375dd669daacc1",
    "p16_malicious_honest.jsonl": "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d",
    "parts-abd.jsonl": "c91bd6e0f47e60fa33e604911976a595f38fb928ac5399db993681459c5f99f0",
    "parts-cef.jsonl": "36238f7aa39091c654d1e0e53222696089830dbcf3222fc6dede7d0674a03e0a",
    "parts-abd.manifest.json": "a5e7f375d6f0a1a355841ea2b253ce625780a3eebc2411be0a14a0f6dcfa3368",
    "manifest-cef.json": "3fe846a4c6fe8f28980bcf3f368ba9ceb7233600c4bf300447b1119aa72d4447",
}
FROZEN_R2 = {
    "parts-a-sub.jsonl": "230fa5cb47e008bfbd08207c9b5a632bed417790a43a15713ad39b3b039c3507",
    "parts-d-sub.jsonl": "b804dd4d5a7cc44e07b79355c1fa088462f5602824bac503b22edfbe355cf398",
    "p16_benign_release.jsonl": "c55da1e8d05dcaf648ee0bbc690fae066913960bf787e6e41761641c5bc5e183",
    "p16_malicious_honest.jsonl": "f9dac93030d94e2dab9735eacae5bbd5a3f4b44ed298908b27fca08a928c6b8d",
}
M4_SHA = "d4061d47df903d9156b7dfb38f74b588bd186435103ba3f8f7bb885b3f85a414"
PREFIX = b"p16-r3:20261014m2b:"

fails = []


def check(name, cond, detail=""):
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        fails.append(name)


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def lines_of(p):
    raw = open(p, "rb").read()
    assert raw.endswith(b"\n")
    return raw, raw.split(b"\n")[:-1]


print("== A. 行数与 sha（独立重读） ==")
raw_b, ben = lines_of(os.path.join(P16_R3, "p16_benign_release.jsonl"))
raw_m, mal = lines_of(os.path.join(P16_R3, "p16_malicious_honest.jsonl"))
raw_p, parts_d = lines_of(os.path.join(P16_R3, "parts-d-sub.jsonl"))
check("parts-d-sub.jsonl 行数=336", len(parts_d) == 336, f"实际 {len(parts_d)}")
check("p16_benign_release.jsonl 行数=2736", len(ben) == 2736, f"实际 {len(ben)}")
check("p16_malicious_honest.jsonl 行数=2880", len(mal) == 2880, f"实际 {len(mal)}")
check("恶意件 sha = 一轮登记 f9dac930…",
      sha_file(os.path.join(P16_R3, "p16_malicious_honest.jsonl")) == FROZEN_R1["p16_malicious_honest.jsonl"])

print("== B. 族组成与极性 ==")
J = lambda ln: json.loads(ln)  # noqa: E731
ben_fam, mal_fam = {}, {}
for ln in ben:
    r = J(ln)
    ben_fam.setdefault(r["id"][4], []).append(ln)
    assert r["polarity"] == "benign_release", r["id"]
for ln in mal:
    r = J(ln)
    mal_fam.setdefault(r["id"][4], []).append(ln)
    assert r["polarity"] == "malicious_refuse", r["id"]
check("良件族 A1500 B480 C360 D96 E300", {k: len(v) for k, v in ben_fam.items()} == {"A": 1500, "B": 480, "C": 360, "D": 96, "E": 300}, str({k: len(v) for k, v in sorted(ben_fam.items())}))
check("良件极性全 benign_release", True)
check("恶件族 F2640 D240", {k: len(v) for k, v in mal_fam.items()} == {"F": 2640, "D": 240}, str({k: len(v) for k, v in sorted(mal_fam.items())}))
check("恶件极性全 malicious_refuse", True)
conv = sum(1 for ln in mal_fam["D"] if J(ln)["src_task"].endswith("conversational"))
check("恶件 D 组成 对话120+载体120", conv == 120 and len(mal_fam["D"]) - conv == 120, f"对话{conv}+载体{len(mal_fam['D'])-conv}")
check("良件 D 全为放行向 p16:D:release", all(J(ln)["src_task"] == "p16:D:release" for ln in ben_fam["D"]))
pd_tasks = {}
for ln in parts_d:
    pd_tasks[J(ln)["src_task"]] = pd_tasks.get(J(ln)["src_task"], 0) + 1
check("parts-d-sub = D良96+D恶240（对话120+载体120）",
      pd_tasks == {"p16:D:release": 96, "p16:D:refuse_conversational": 120, "p16:D:refuse_carrier": 120}, str(pd_tasks))
KEYS = {"dpo_class", "id", "pack", "lang", "polarity", "rejected_form", "archetype_id",
        "conversations", "chosen", "rejected", "src_task"}
schemas = {frozenset(J(ln).keys()) for ln in ben} | {frozenset(J(ln).keys()) for ln in mal}
check("单文件 schema 同构（11 键 × 2 文件，CastError 教训）", schemas == {frozenset(KEYS)}, str([sorted(s) for s in schemas]))

print("== C. 逐字节子集性（独立重导） ==")
_, r1_ben = lines_of(os.path.join(P16_R1, "p16_benign_release.jsonl"))
_, r1_mal = lines_of(os.path.join(P16_R1, "p16_malicious_honest.jsonl"))
r1_ben_set, r1_mal_set = set(r1_ben), set(r1_mal)
check("r3 良件每行 ∈ 一轮良件字节集", all(ln in r1_ben_set for ln in ben))
check("r3 恶件每行 ∈ 一轮恶件字节集", all(ln in r1_mal_set for ln in mal))
check("r3 恶件 = 一轮恶件整文件字节恒等", raw_m == open(os.path.join(P16_R1, "p16_malicious_honest.jsonl"), "rb").read())
r1_ben_fam = {}
for ln in r1_ben:
    r1_ben_fam.setdefault(J(ln)["id"][4], []).append(ln)
r1_mal_fam = {}
for ln in r1_mal:
    r1_mal_fam.setdefault(J(ln)["id"][4], []).append(ln)
from collections import Counter  # noqa: E402
for fam, r1l, r3l in (("A", r1_ben_fam["A"], ben_fam["A"]), ("B", r1_ben_fam["B"], ben_fam["B"]),
                      ("C", r1_ben_fam["C"], ben_fam["C"]), ("E", r1_ben_fam["E"], ben_fam["E"]),
                      ("F", r1_mal_fam["F"], mal_fam["F"]), ("D恶", r1_mal_fam["D"], mal_fam["D"])):
    check(f"族 {fam} {len(r1l)} 行与一轮多重集逐字节恒等", Counter(r1l) == Counter(r3l))

print("== D. 子选算法独立复算（前缀 b'p16-r3:20261014m2b:'） ==")
keyed = sorted((hashlib.sha256(PREFIX + ln).hexdigest(), J(ln)["id"], ln) for ln in r1_ben_fam["D"])
sel = [t[2] for t in keyed[:96]]
sel.sort(key=lambda ln: J(ln)["id"])
check("D良 子选 96 复算逐字节恒等", sel == ben_fam["D"])
all_ids = [J(ln)["id"] for ln in ben] + [J(ln)["id"] for ln in mal]
r1_ids = {J(ln)["id"] for ln in r1_ben} | {J(ln)["id"] for ln in r1_mal}
check("全局 id 唯一且 ⊆ 一轮 id 集", len(set(all_ids)) == len(all_ids) == 5616 and set(all_ids) <= r1_ids)

print("== E. dataset_info 注册件 ==")
raw_ds = open(DS_INFO, "rb").read()
try:
    raw_ds.decode("ascii")
    ascii_ok = True
except UnicodeDecodeError:
    ascii_ok = False
check("dataset_info.json 纯 ASCII（GBK 教训）", ascii_ok)
info = json.loads(raw_ds.decode("ascii"))
names = ["sec_dpo_m5a_r3_base_m4capfix", "sec_dpo_m5a_r3_p16_benign", "sec_dpo_m5a_r3_p16_malicious"]
check("三注册条目齐", sorted(info.keys()) == sorted(names), str(sorted(info.keys())))
expect_rows = {"sec_dpo_m5a_r3_base_m4capfix": (28842, os.path.join(ROOT, "data", "m4-run", "dpo_m4_capfix.jsonl"), M4_SHA),
               "sec_dpo_m5a_r3_p16_benign": (2736, os.path.join(P16_R3, "p16_benign_release.jsonl"), None),
               "sec_dpo_m5a_r3_p16_malicious": (2880, os.path.join(P16_R3, "p16_malicious_honest.jsonl"), FROZEN_R1["p16_malicious_honest.jsonl"])}
total = 0
for n in names:
    e = info[n]
    want_rows, want_path, want_sha = expect_rows[n]
    path = os.path.normpath(os.path.join(os.path.dirname(DS_INFO), e["file_name"]))
    ok = (path == want_path and sum(1 for _ in open(path, "rb")) == want_rows
          and (want_sha is None or sha_file(path) == want_sha)
          and e["formatting"] == "sharegpt" and e["ranking"] is True
          and e["columns"] == {"messages": "conversations", "chosen": "chosen", "rejected": "rejected"}
          and e["tags"] == {"role_tag": "from", "content_tag": "value", "user_tag": "human",
                            "assistant_tag": "gpt", "system_tag": "system"})
    total += want_rows
    check(f"{n} file_name/行数/sha/口径", ok, f"{want_rows} 行 …{sha_file(path)[:12]}")
check("注册行数合计 = 34,458", total == 34458, str(total))

print("== F. r3 manifest 自洽 ==")
man = json.loads(open(os.path.join(P16_R3, "manifest.json"), encoding="utf-8").read())
for fn in ("parts-d-sub.jsonl", "p16_benign_release.jsonl", "p16_malicious_honest.jsonl"):
    p = os.path.join(P16_R3, fn)
    e = man["files"][fn]
    check(f"manifest[{fn}] rows/bytes/sha",
          e["rows"] == sum(1 for _ in open(p, "rb")) and e["bytes"] == os.path.getsize(p) and e["sha256"] == sha_file(p))
pb = man["subset_integrity"]["polarity_balance"]
check("manifest 极性 2736:2880 = 48.7:51.3", pb == {"benign_release": 2736, "malicious_refuse": 2880, "benign_pct": 48.72, "malicious_pct": 51.28}, str(pb))
tt = man["lineage"]["training_totals"]
share = round(100.0 * 5616 / 34458, 3)  # = 16.298（首跑误写 16.302 = 脚本自误，见报告 §六）
check("manifest 训练总量 34,458 = 28,842+5,616", tt["rows"] == 34458 and tt["full_epoch_steps"] == 2154 and tt["p16r3_share_pct"] == share, str(tt))
check("manifest subsample 前缀登记 = p16-r3:20261014m2b:", man["subsample"]["prefix_bytes"] == "p16-r3:20261014m2b:")
check("manifest g1_scan_interaction = RESOLVED_BY_SEQUENCING（不跑全 checker）", man["g1_scan_interaction"]["status"] == "RESOLVED_BY_SEQUENCING" and "不跑全 checker" in man["g1_scan_interaction"]["consequence"])

print("== G. 一轮 + 二轮冻结件 sha 复验未动（快检替代 ① 独立复核） ==")
for fn, want in FROZEN_R1.items():
    check(f"一轮 {fn} 未动", sha_file(os.path.join(P16_R1, fn)) == want)
for fn, want in FROZEN_R2.items():
    check(f"二轮 {fn} 未动", sha_file(os.path.join(P16_R2, fn)) == want)
check("m4 基座未动", sha_file(os.path.join(ROOT, "data", "m4-run", "dpo_m4_capfix.jsonl")) == M4_SHA)

print("== H. 行数恒等式（落盘件实际族计数；parts 为重列不计） ==")
famA = len(ben_fam["A"]); famB = len(ben_fam["B"]); famC = len(ben_fam["C"])
famE = len(ben_fam["E"]); famDg = len(ben_fam["D"])
famDe = len(mal_fam["D"]); famF = len(mal_fam["F"])
s = famA + famB + famC + famDe + famDg + famE + famF
check("配方恒等式 1500+480+360+240+96+300+2640 = 5,616", s == 5616, f"{famA}+{famB}+{famC}+{famDe}+{famDg}+{famE}+{famF} = {s}")
check("产物恒等式 良2,736 + 恶2,880 = 5,616（parts-d-sub 为 D 族重列，非额外行）",
      len(ben) + len(mal) == 5616 and len(parts_d) == famDg + famDe)
check("parts-d-sub 336 行 ⊆ 良+恶 D 族重列", Counter(parts_d) == Counter(ben_fam["D"]) + Counter(mal_fam["D"]))

# 附：r3 D良96 与 r2 D良96 重叠（描述性）
_, r2_ben = lines_of(os.path.join(P16_R2, "p16_benign_release.jsonl"))
r2_d = {ln for ln in r2_ben if J(ln)["id"][4] == "D"}
overlap = sum(1 for ln in ben_fam["D"] if ln in r2_d)
print(f"\n附（描述性，非断言）：r3 D良96 ∩ r2 D良96 重叠 = {overlap}/96（不同 seed 的独立抽头，"
      f"重叠期望 ≈ 96×96/240 = 38.4）")
print(f"\nr3 D良 子选阈值摘要 = {man['subsample']['D_good']['threshold_digest'][:16]}…"
      f"（首 {man['subsample']['D_good']['first_id']} / 末 {man['subsample']['D_good']['last_id']}）")

if fails:
    print(f"\nVERIFY-R3=FAIL {fails}")
    sys.exit(1)
print("\nVERIFY-R3=PASS")
