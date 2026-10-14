# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog H: artifact-level verification of (1) that the resumed
run really updates the weights (base vs ckpt-200 vs ckpt-300 tensor drift) and
(2) the optimizer-state element width, read out of the torch.save zip central
directory WITHOUT materialising 2 GB.

CPU only, read-only. Writes reports/m3-dpo-resume-watchdog-H-artifacts.json
"""
from __future__ import annotations

import json
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
OUT = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
BASE = ROOT / "checkpoints" / "soup-needlefix-a050"

WATCH = [
    "model.layers.0.self_attn.q_proj.weight",
    "model.layers.13.mlp.down_proj.weight",
    "model.norm.weight",
    "model.layers.27.self_attn.o_proj.weight",
]


def header(path: Path):
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        raw = f.read(n)
    return json.loads(raw.decode()), n


def read_tensor(path: Path, name: str) -> np.ndarray:
    hdr, n = header(path)
    meta = hdr[name]
    s, e = meta["data_offsets"]
    npd = {"F32": np.float32, "F16": np.float16, "BF16": None}[meta["dtype"]]
    with path.open("rb") as f:
        f.seek(8 + n + s)
        buf = f.read(e - s)
    if meta["dtype"] == "BF16":
        u16 = np.frombuffer(buf, dtype=np.uint16).astype(np.uint32)
        arr = (u16 << 16).view(np.float32)
    else:
        arr = np.frombuffer(buf, dtype=npd)
    return arr.reshape(meta["shape"])


def main() -> int:
    res: dict = {}

    # ---------- param count / dtype from the base header ----------
    hdr, hn = header(BASE / "model.safetensors")
    hdr = {k: v for k, v in hdr.items() if k != "__metadata__"}
    nparam = sum(int(np.prod(v["shape"])) for v in hdr.values())
    res["model"] = {
        "n_tensors": len(hdr),
        "n_params": nparam,
        "safetensors_bytes": (BASE / "model.safetensors").stat().st_size,
        "bytes_per_param": (BASE / "model.safetensors").stat().st_size / nparam,
        "dtype_counter": {d: sum(1 for v in hdr.values() if v["dtype"] == d)
                          for d in {v["dtype"] for v in hdr.values()}},
    }

    # ---------- tensor drift ----------
    # The compared checkpoints MUST be discovered dynamically: save_total_limit=5 keeps
    # deleting the oldest ones (ckpt-100..500 are already gone). We therefore always
    # compare base -> oldest present, then every adjacent present pair.
    files = {"base_a050": BASE / "model.safetensors"}
    present = sorted([p for p in OUT.glob("checkpoint-*") if (p / "model.safetensors").exists()],
                     key=lambda p: int(p.name.split("-")[1]))
    for ck in present:
        files[ck.name] = ck / "model.safetensors"
    res["compared_checkpoints"] = list(files.keys())
    drift: dict = {}
    cache = {tag: {nm: read_tensor(p, nm) for nm in WATCH} for tag, p in files.items()}
    for nm in WATCH:
        d = {}
        tags = list(files)
        for i in range(len(tags) - 1):
            a, b = tags[i], tags[i + 1]
            if nm in cache[a] and nm in cache[b]:
                diff = np.abs(cache[b][nm] - cache[a][nm])
                d[f"{a}->{b}"] = {"max_abs": float(diff.max()),
                                  "mean_abs": float(diff.mean()),
                                  "rel_rms": float(np.sqrt((diff ** 2).mean())
                                                   / (np.sqrt((cache[a][nm] ** 2).mean()) + 1e-30))}
        d["_shape"] = list(cache[tags[0]][nm].shape)
        d["_base_rms"] = float(np.sqrt((cache[tags[0]][nm] ** 2).mean()))
        drift[nm] = d
    res["tensor_drift"] = drift

    # ---------- optimizer state element width (zip central directory only) ----------
    optinfo: dict = {}
    for ck in ("checkpoint-200", "checkpoint-300"):
        p = OUT / ck / "optimizer.pt"
        if not p.exists():
            continue
        z = zipfile.ZipFile(p)
        infos = z.infolist()
        by_suffix: dict[str, list[int]] = {}
        for i in infos:
            nm = i.filename
            key = nm.rsplit("/", 1)[-1]
            by_suffix.setdefault(key, []).append(i.file_size)
        sizes = sorted({i.file_size for i in infos if i.file_size > 1_000_000})
        optinfo[ck] = {
            "optimizer_pt_bytes": p.stat().st_size,
            "n_zip_entries": len(infos),
            "bytes_per_param_total": p.stat().st_size / nparam,
            "entry_suffixes_top": sorted(by_suffix, key=lambda k: -len(by_suffix[k]))[:14],
            "sample_entry_names": [i.filename for i in infos[:12]],
            "distinct_entry_sizes_gt1MB_count": len(sizes),
            "largest_entry_sizes": sizes[-8:],
        }
        # infer width: entries per state key with a known numel
        pairs = []
        for i in infos:
            nm = i.filename
            if nm.endswith(("exp_avg", "exp_avg_sq")) or "exp_avg" in nm or "exp_avg_sq" in nm:
                pairs.append((nm, i.file_size))
        optinfo[ck]["state_entries_first10"] = pairs[:10]
        z.close()
    res["optimizer_artifact"] = optinfo
    res["optimizer_interpretation"] = {
        "pure_int8_state_bytes_per_param": 2.0,
        "pure_fp32_state_bytes_per_param": 8.0,
        "pure_bf16_state_bytes_per_param": 4.0,
        "observed_total_bytes_per_param": {k: v["bytes_per_param_total"] for k, v in optinfo.items()},
    }

    (R / "m3-dpo-resume-watchdog-H-artifacts.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("== model ==")
    print(json.dumps(res["model"], indent=1))
    print("\n== tensor drift (max|dW| per interval) ==")
    for nm, d in drift.items():
        print(f"  {nm}  shape={d['_shape']} base_rms={d['_base_rms']:.4g}")
        for k, v in d.items():
            if k.startswith("_"):
                continue
            print(f"     {k:34} max_abs={v['max_abs']:.3e} mean_abs={v['mean_abs']:.3e} rel_rms={v['rel_rms']:.3e}")
    print("\n== optimizer artifact ==")
    print(json.dumps(optinfo, indent=1))
    print("\nWROTE", R / "m3-dpo-resume-watchdog-H-artifacts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
