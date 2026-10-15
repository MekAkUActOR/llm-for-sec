# -*- coding: utf-8 -*-
"""M5B-R5 one-off: dump readings logs + verdict JSON for report writing (read-only)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-16"))


full = load(ROOT / "reports/logs/m5g-readings-m5b-r5-full.log")
v = full["v023"]
print("=== v023 ===")
for k in ("orr_total", "orr_ordinary_benign497", "orr_hardbenign120",
          "conservative13_refuse_compliant", "asr_intraining_rob64",
          "contract_robustness_verdict", "truncation_rate"):
    print(f"{k}: {v[k]}")
print("labels:", json.dumps(v["label_distribution"], ensure_ascii=False))

n = full["needle"]
print("=== needle ===")
print("k/n:", n["needle_k"], "/", n["needle_n"], "rate:", n["needle_rate"])
print("cells:", json.dumps(n["cells"]))
print("ppl32768:", n["ppl_32768"])

di = full["dilution"]
print("=== dilution ===")
print("det:", json.dumps(di["detection_rate"]), json.dumps(di["detection_counts"]))
print("bfp:", json.dumps(di["benign_false_positive"]))
print("by_lang:", json.dumps(di["detection_by_language"]))
print("verdict_dist:", json.dumps(di.get("verdict_distribution")))
tr = di.get("trials") or {}
depth = {}
for L, langs in tr.items():
    for lang, frags in langs.items():
        for frag, trials in frags.items():
            for key, t in trials.items():
                dep = str(key).split("#")[0]
                c = depth.setdefault(dep, {"k": 0, "n": 0})
                c["n"] += 1
                c["k"] += int(t.get("attack_success") == 0.0)
print("by_depth:", json.dumps(depth))

j = full["jb"]
print("=== jb ===")
for rule in ("selfreport", "strict_mirror", "tiered"):
    b = j[rule]
    print(f"{rule}: final={b['asr_final']} any={b['asr_any']}")
print("tiered tiers:", json.dumps(j["tiered"]["tier_distribution_final"]))
print("tiered by_lang:", json.dumps(j["tiered"]["by_language"]))
print("tiered by_family:", json.dumps(j["tiered"]["by_family"]))
print("selfreport by_family:", json.dumps(j["selfreport"]["by_family"]))
sr = j["tiered"].get("benign")
print("tiered benign:", json.dumps(sr)[:300])
print("contract_final:", j["tiered"]["contract_final"])
f = j["form_selfrefuse_bodydeliver"]
print("FORM decoupling:", f["k"], "/", f["n"])
print("form ids:", " ".join(f["ids"]))

print("=== toolout log ===")
print((ROOT / "reports/logs/m5g-readings-m5b-r5-toolout.log").read_text(encoding="utf-16").strip())
print("=== reploop log ===")
print((ROOT / "reports/logs/m5g-readings-m5b-r5-reploop.log").read_text(encoding="utf-16").strip())

print("=== verdict ===")
vd = json.loads((ROOT / "reports/topup-verdict-m5b-p2rl-grpo-v5-v023-mnt512.json").read_text(encoding="utf-8"))
print("decision:", vd["decision"])
print("must_gate_fail:", vd["must_gate_fail"], "blockers:", vd["must_blockers"], "should_unmeasured:", vd["should_unmeasured"])
for g2 in vd["must_gates"]:
    print(f"[{g2['gate']}]", json.dumps({k: g2.get(k) for k in ("baseline_counts", "variant_counts", "baseline", "variant", "diff", "verdict", "fisher_p", "diff_ci95_paired", "discordant", "threshold", "variant_ORR", "variant_ORR_ci95")}, ensure_ascii=False))
cv = vd["confusion"]["variant"]
print("confusion.variant:", json.dumps(cv, ensure_ascii=False))
cb = vd["confusion"]["baseline"]
print("confusion.baseline:", json.dumps(cb, ensure_ascii=False))
for s in vd["should"]:
    print("[SHOULD]", json.dumps(s, ensure_ascii=False))
for o in vd.get("observations", []):
    print("[OBS]", json.dumps(o, ensure_ascii=False))
pd_ = vd.get("per_dimension") or {}
if pd_.get("available"):
    print("ORR by domain (baseline->variant):")
    for dom, x in pd_["risk_absent_ORR"]["domains"].items():
        print(f"  {dom}: {x['baseline']['k']}/{x['baseline']['n']} -> {x['variant']['k']}/{x['variant']['n']} (diff {x['diff']:+.4f})")
    print("ASR gen by domain (baseline->variant):")
    for dom, x in pd_["risk_present_ASR"]["domains"].items():
        print(f"  {dom}: {x['baseline']['k']}/{x['baseline']['n']} -> {x['variant']['k']}/{x['variant']['n']}")
