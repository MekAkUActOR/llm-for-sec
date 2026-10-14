# -*- coding: utf-8 -*-
"""m5b-r2 门禁：jb-scored 汇总提取（一次性辅助）。"""
import json

d = json.load(open(r"J:\Projects\llm_for_sec\reports\jb-scored-m5b-p2rl-grpo-v2-v0.7-full-v2.json", encoding="utf-8"))
t = d["tiered"]
s = d["selfreport"]
print("tiered asr.final:", t["asr"]["final"])
print("tiered asr.any_turn:", t["asr"]["any_turn"])
print("tier_distribution_final:", t["tier_distribution_final"])
print("tiered by_language:", json.dumps(t["by_language"]))
print("tiered by_family:", json.dumps({k: (v["k"], v["n"]) for k, v in t["by_family"].items()}))
print("selfreport asr.final:", s["asr"]["final"])
print("benign orr_final:", s["benign"]["orr_final"])
print("benign orr_any:", s["benign"]["orr_any"])
print("contract final:", t["contract"]["final_rate"])
print("elapsed_s:", t.get("elapsed_s"))
