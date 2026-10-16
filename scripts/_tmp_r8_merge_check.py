# -*- coding: utf-8 -*-
"""_tmp_r8_merge_check.py — r8 合并模型完整性验证（门禁链发射前机械关卡）。

镜像 r7 的验证口径（reports/m5a-dpo-r7-download-trace.md §六）：
  1. export_dir 存在且含 config.json / generation_config.json / tokenizer 件
  2. index weight_map 全部键指向**存在的**分片文件
  3. 各分片 safetensors 头的 tensor 名集合 = index 键集合按分片分组（无缺失/无悬多）
  4. 权重总数与底座结构一致（Qwen3-8B：399）
fail-closed：任一不过 rc=1。
"""
import json
import struct
import sys
from pathlib import Path

MERGED = Path(r"J:\Projects\llm_for_sec\checkpoints\qwen3-8b-sec-m5a-dpo-r8-merged")
EXPECT_WEIGHTS = 399  # Qwen3-8B 状态键数（r7 合并实测同值）


def shard_tensors(p: Path) -> set:
    with p.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n))
    return {k for k in hdr if k != "__metadata__"}


def main() -> int:
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(("[OK] " if cond else "[BAD] ") + msg)
        if not cond:
            ok = False

    check(MERGED.is_dir(), f"export_dir 存在: {MERGED}")
    for f in ("config.json", "generation_config.json", "tokenizer_config.json", "tokenizer.json"):
        check((MERGED / f).is_file(), f"{f} 在位")

    idx_p = MERGED / "model.safetensors.index.json"
    check(idx_p.is_file(), "index 在位")
    if not idx_p.is_file():
        return 1
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    wmap = idx["weight_map"]
    shards = sorted(set(wmap.values()))
    check(len(wmap) == EXPECT_WEIGHTS, f"weight_map 键数 = {len(wmap)}（期望 {EXPECT_WEIGHTS}）")
    for s in shards:
        check((MERGED / s).is_file(), f"{s} 在位")

    for s in shards:
        p = MERGED / s
        expect = {k for k, v in wmap.items() if v == s}
        got = shard_tensors(p)
        check(expect == got, f"{s}: tensor 集一致（分片 {len(got)}，缺失 {len(expect - got)}，悬多 {len(got - expect)}）")

    print("MERGE-CHECK=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
