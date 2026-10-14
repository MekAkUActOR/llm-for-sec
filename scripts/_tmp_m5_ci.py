# -*- coding: utf-8 -*-
"""M5 门禁辅助：报告引用读数的 Wilson CI95（secfm.eval.stats.wilson 同款口径）。"""
import sys

sys.path.insert(0, ".")
from secfm.eval.stats import wilson  # noqa: E402

cases = [
    ("soup dilution fp", 33, 96),
    ("m5a dilution fp", 32, 96),
    ("m5a ordinary benign ORR", 4, 497),
    ("m5b ordinary benign ORR", 112, 497),
    ("m5b hb ORR", 16, 120),
    ("soup hb ORR", 13, 120),
    ("m5a in-training ASR", 40, 64),
    ("m5a jb selfreport", 79, 80),
    ("soup dilution zh", 64, 144),
    ("soup dilution en", 24, 144),
    ("m5a dilution zh", 9, 144),
    ("m5a dilution en", 38, 144),
]
for name, k, n in cases:
    lo, hi = wilson(k, n)
    print(f"{name}: {k}/{n} = {k/n:.4f} CI95 [{lo:.4f}, {hi:.4f}]")
