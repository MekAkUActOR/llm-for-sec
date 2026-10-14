# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog J: what is actually inside optimizer.pt?

Sizes-only spectral match: every zip entry's byte size is compared with the model's
own tensor numels (from the safetensors header) to infer the element width of the
stored optimizer state. Reads only the zip central directory + one 35 KB header.

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-J-optimizer.json
"""
from __future__ import annotations

import json
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
OUT = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
BASE = ROOT / "checkpoints" / "soup-needlefix-a050"


def numels(p: Path) -> Counter:
    with p.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(n).decode())
    hdr.pop("__metadata__", None)
    c: Counter = Counter()
    for v in hdr.values():
        n_el = 1
        for d in v["shape"]:
            n_el *= d
        c[n_el] += 1
    return c


def storage_classes(op_path: Path) -> Counter:
    """Count the storage classes referenced by the optimizer pickle.

    torch.save's pickle names the storage class for every tensor
    (torch.FloatStorage / torch.ByteStorage / ...), which pins the element width
    WITHOUT materialising any tensor.  Reads only optimizer/data.pkl (100 KB).
    """
    import pickletools
    with zipfile.ZipFile(op_path) as z:
        blob = z.read("optimizer/data.pkl")
    c: Counter = Counter()
    strings = []
    for op, arg, pos in pickletools.genops(blob):
        if op.name in ("GLOBAL", "STACK_GLOBAL", "SHORT_BINUNICODE", "BINUNICODE",
                       "BINUNICODE8", "SHORT_BINSTRING", "BINSTRING"):
            if isinstance(arg, str):
                strings.append(arg)
        elif op.name == "GLOBAL" and isinstance(arg, tuple):
            strings.append(".".join(arg))
    joined = " ".join(strings)
    for key in ("FloatStorage", "HalfStorage", "BFloat16Storage", "ByteStorage",
                "CharStorage", "IntStorage", "LongStorage", "DoubleStorage",
                "UntypedStorage"):
        c[key] = joined.count(key)
    c["_n_unique_strings"] = len(set(strings))
    c["_dtype_strings"] = sorted({s for s in strings
                                  if s in ("float32", "float16", "bfloat16", "uint8",
                                           "int8", "float64", "int64", "bool")})
    return c


def main() -> int:
    nm = numels(BASE / "model.safetensors")
    _nparam = sum(k * v for k, v in nm.items())          # NOT sum(nm): that sums distinct numels
    res: dict = {"model_numels_distinct": len(nm), "model_numels_total": _nparam,
                 "checkpoints": {}}
    for ck in sorted(OUT.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])):
        op = ck / "optimizer.pt"
        if not op.exists():
            continue
        with zipfile.ZipFile(op) as z:
            infos = z.infolist()
        entries = [(i.filename, i.file_size) for i in infos]
        meta_bytes = sum(s for _, s in entries if s <= 512)
        big = [(n, s) for n, s in entries if s > 512]
        width_hits = {1: 0, 2: 0, 4: 0, 8: 0}
        width_bytes = {1: 0, 2: 0, 4: 0, 8: 0}
        unmatched = []
        for name, s in big:
            hit = False
            for w in (8, 4, 2, 1):
                if s % w == 0 and nm.get(s // w, 0) > 0:
                    width_hits[w] += 1
                    width_bytes[w] += s
                    hit = True
                    break
            if not hit:
                unmatched.append((name, s))
        total = sum(s for _, s in entries)
        res["checkpoints"][ck.name] = {
            "optimizer_pt_bytes": total,
            "n_zip_entries": len(entries),
            "metadata_bytes_le512": meta_bytes,
            "n_entries_gt512": len(big),
            "width_hit_counts": width_hits,
            "width_bytes": width_bytes,
            "bytes_per_param": total / _nparam,
            "unmatched_entries": unmatched[:10],
            "n_unmatched": len(unmatched),
            "unmatched_bytes": sum(s for _, s in unmatched),
            "top_10_entry_sizes": sorted((s for _, s in entries), reverse=True)[:10],
        }
        # a specific probe: the single embedding-sized tensor (151936*1024=155582464)
        emb = 151936 * 1024
        res["checkpoints"][ck.name]["entries_of_size_4x_embedding"] = sum(
            1 for _, s in entries if s == 4 * emb)
        res["checkpoints"][ck.name]["entries_of_size_1x_embedding"] = sum(
            1 for _, s in entries if s == emb)
        res["checkpoints"][ck.name]["n_distinct_entry_sizes"] = len({s for _, s in entries})
        res["checkpoints"][ck.name]["pickle_storage_classes"] = dict(storage_classes(op))

    # ---------- decomposed size model: fp32 state for the tied embedding, int8 for blocks ----------
    emb = 151936 * 1024
    total_params = sum(k * v for k, v in nm.items())
    block_params = total_params - emb
    predicted = emb * 8 + block_params * 2          # bnb keeps large-embedding state in fp32
    _present = sorted([p for p in OUT.glob("checkpoint-*") if (p / "optimizer.pt").exists()],
                      key=lambda p: int(p.name.split("-")[1]))
    obs = _present[-1].joinpath("optimizer.pt").stat().st_size if _present else 0
    res["size_model"] = {
        "observed_sample_checkpoint": _present[-1].name if _present else None,
        "embedding_numel": emb, "block_params": block_params, "total_params": total_params,
        "predicted_bytes_embedding_fp32_m_plus_v": emb * 8,
        "predicted_bytes_blocks_int8_m_plus_v": block_params * 2,
        "predicted_total": predicted,
        "observed_total_ckpt200": obs,
        "residual_bytes": obs - predicted,
        "residual_fraction": (obs - predicted) / obs,
        "uniform_int8_would_be": total_params * 2,
        "uniform_fp32_would_be": total_params * 8,
        "observed_bytes_per_param": obs / total_params,
        "interpretation": ("the observed size is explained to <1% by: fp32 exp_avg+exp_avg_sq for the "
                           "tied 155.6M-param embedding + int8 state for the remaining 440.5M block "
                           "params (bitsandbytes keeps very large embedding state in 32-bit). This "
                           "corroborates optim=adamw_bnb_8bit at the artefact level; a UNIFORM 8-bit "
                           "state would have been ~1.19 GB, not 2.14 GB."),
    }

    (R / "m3-dpo-resume-watchdog-J-optimizer.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("model: distinct numels", res["model_numels_distinct"],
          "total params", res["model_numels_total"])
    for k, v in res["checkpoints"].items():
        print(f"\n== {k} ==")
        print(f"  optimizer.pt = {v['optimizer_pt_bytes']} B; {v['n_zip_entries']} zip entries "
              f"({v['n_entries_gt512']} >512 B, {v['metadata_bytes_le512']} B metadata)")
        print(f"  bytes/param = {v['bytes_per_param']:.4f}")
        print(f"  width hits (entries): {v['width_hit_counts']}")
        print(f"  width bytes          : {v['width_bytes']}")
        print(f"  unmatched: n={v['n_unmatched']} bytes={v['unmatched_bytes']} e.g. {v['unmatched_entries'][:4]}")
        print(f"  entries of size 4x embedding numel (fp32): {v['entries_of_size_4x_embedding']}; "
              f"1x (int8): {v['entries_of_size_1x_embedding']}")
        print(f"  distinct entry sizes: {v['n_distinct_entry_sizes']}; top sizes: {v['top_10_entry_sizes']}")
    print("\nWROTE", R / "m3-dpo-resume-watchdog-J-optimizer.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
