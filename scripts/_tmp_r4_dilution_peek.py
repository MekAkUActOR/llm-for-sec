# -*- coding: utf-8 -*-
import json

d = json.load(open(r"reports\dilution-m5a-dpo-r4-v0.6.json", encoding="utf-8"))
print("detection_rate:", json.dumps(d.get("detection_rate"), ensure_ascii=False))
print("detection_counts:", json.dumps(d.get("detection_counts"), ensure_ascii=False))
print("benign_counts:", json.dumps(d.get("benign_counts"), ensure_ascii=False))
print("benign_pass_rate:", json.dumps(d.get("benign_pass_rate"), ensure_ascii=False))
print("grid:", json.dumps(d.get("grid"), ensure_ascii=False))
