# -*- coding: utf-8 -*-
"""_tmp_r9_merge_check.py — M5A-R9 合并件完整性验证（r8 同款机械步骤）。

对象：checkpoints\\qwen3-8b-sec-m5a-dpo-r9-merged（rank64 adapter 经 llamafactory-cli export
合并的完整模型；门禁仪器仅 AutoModelForCausalLM 直载，故门禁前必须合并）。
检查：config/tokenizer/index 在位；weight_map 键数 = 399（期望）；每分片 tensor 集与
index weight_map 双向一致（缺失 0 / 悬多 0）。
PASS/FAIL 输出 MERGE-CHECK=PASS/FAIL；fail-closed rc=1。
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
MD = ROOT / "checkpoints" / "qwen3-8b-sec-m5a-dpo-r9-merged"
EXPECT_WEIGHTS = 399  # Qwen3-8B 36 层 × 11 + 3 = 与 rank 无关（LoRA 已并入基权重名）

def main() -> int:
    ok = True
    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        print(("[OK] " if cond else "[NG] ") + msg)
        if not cond:
            ok = False

    check(MD.is_dir(), f"export_dir 存在: {MD}")
    for f in ["config.json", "generation_config.json", "tokenizer_config.json", "tokenizer.json",
              "model.safetensors.index.json"]:
        check((MD / f).is_file(), f"{f} 在位")

    idx = json.loads((MD / "model.safetensors.index.json").read_text(encoding="utf-8"))
    wmap = idx["weight_map"]
    check(len(wmap) == EXPECT_WEIGHTS, f"weight_map 键数 = {len(wmap)}（期望 {EXPECT_WEIGHTS}）")

    # 每分片的期望 tensor 集
    shard_tensors = {}
    for tname, shard in wmap.items():
        shard_tensors.setdefault(shard, set()).add(tname)
    for shard in sorted(shard_tensors):
        sf = MD / shard
        check(sf.is_file(), f"{shard} 在位")
        if not sf.is_file():
            continue
        import struct
        with sf.open("rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            hdr = json.loads(fh.read(n))
        # __metadata__ = safetensors 结构键（r9 导出器写入 {format:pt}；r8 版未写故旧检查通过）。
        # 非模型张量，剔除后再比对（erratum 2026-10-20 06:20，merge 本体完好：399/399 映射 0 缺失）。
        actual = {k for k in hdr.keys() if k != "__metadata__"}
        missing = shard_tensors[shard] - actual
        extra = actual - shard_tensors[shard]
        check(not missing and not extra,
              f"{shard}: tensor 集一致（分片 {len(actual)}，缺失 {len(missing)}，悬多 {len(extra)}）")

    print("MERGE-CHECK=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
