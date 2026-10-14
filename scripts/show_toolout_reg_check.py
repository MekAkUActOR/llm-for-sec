# -*- coding: utf-8 -*-
"""打印 v0.5-toolout-reg 校验器的关键字段（核查其断言是否实质）。"""
import json
from pathlib import Path

d = json.loads(Path("reports/_verify-toolout-reg.json").read_text(encoding="utf-8"))
print("=== errors ===", d.get("errors"))
print("\n=== counts ===")
print(json.dumps(d.get("counts"), ensure_ascii=False, indent=1)[:900])
print("\n=== mechanism_carrier ===")
print(json.dumps(d.get("mechanism_carrier"), ensure_ascii=False)[:600])
print("\n=== corpus_hits（训练语料泄漏扫描）===")
print(json.dumps(d.get("corpus_hits"), ensure_ascii=False)[:700])
print("\n=== rule_divergence（selfreport vs strict）===")
print(json.dumps(d.get("rule_divergence"), ensure_ascii=False)[:700])
print("\n=== selfreport_probe ===")
print(json.dumps(d.get("selfreport_probe"), ensure_ascii=False)[:600])
print("\n=== wordlist_gaps ===")
print(json.dumps(d.get("wordlist_gaps"), ensure_ascii=False)[:600])
print("\n=== rebuild_identical ===", d.get("rebuild_identical"))
print("=== scorer_sha256 ===", d.get("scorer_sha256"))
