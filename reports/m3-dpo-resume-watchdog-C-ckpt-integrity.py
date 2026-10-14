# -*- coding: utf-8 -*-
"""M3 DPO resume watchdog C: checkpoint integrity (safetensors offset closure,
tensor count/shape vs base, resume prerequisites, log_history presence).

CPU only, read-only w.r.t. checkpoints. Writes
reports/m3-dpo-resume-watchdog-C-ckpt-integrity.json and a sha256 cache
reports/m3-dpo-resume-watchdog-C-sha-cache.json
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import time
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
R = ROOT / "reports"
OUT = ROOT / "checkpoints" / "qwen3-06b-sec-m3-dpo"
BASE = ROOT / "checkpoints" / "soup-needlefix-a050"
CACHE = R / "m3-dpo-resume-watchdog-C-sha-cache.json"


def read_header(path: Path) -> dict:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        raw = f.read(n)
    return json.loads(raw.decode("utf-8")), n


def sha256_cached(path: Path, cache: dict) -> tuple[str, float, bool]:
    st = path.stat()
    key = str(path)
    hit = cache.get(key)
    if hit and hit["size"] == st.st_size and abs(hit["mtime"] - st.st_mtime) < 1e-6:
        return hit["sha256"], 0.0, True
    h = hashlib.sha256()
    t0 = time.time()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    dt = time.time() - t0
    cache[key] = {"sha256": h.hexdigest(), "size": st.st_size, "mtime": st.st_mtime}
    return h.hexdigest(), dt, False


def main() -> int:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    out: dict = {"output_dir": str(OUT), "checkpoints": {}}

    base_hdr, base_n = read_header(BASE / "model.safetensors")
    base_keys = {k for k in base_hdr if k != "__metadata__"}
    base_shapes = {k: tuple(v["shape"]) for k, v in base_hdr.items() if k != "__metadata__"}
    base_nbytes = (BASE / "model.safetensors").stat().st_size
    out["base"] = {"path": str(BASE), "n_tensors": len(base_keys),
                   "safetensors_bytes": base_nbytes, "header_bytes": base_n}

    cks = sorted(OUT.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
    for ck in cks:
        d: dict = {"files": {}, "step_from_name": int(ck.name.split("-")[1])}
        for f in sorted(ck.iterdir()):
            if f.is_file():
                stt = f.stat()
                d["files"][f.name] = {"size": stt.st_size, "mtime": stt.st_mtime}
        d["n_files"] = len(d["files"])
        req = ["model.safetensors", "optimizer.pt", "scheduler.pt", "trainer_state.json",
               "rng_state.pth", "config.json", "training_args.bin"]
        d["missing_required"] = [k for k in req if k not in d["files"]]
        d["resume_ready"] = not d["missing_required"]

        msp = ck / "model.safetensors"
        if msp.exists():
            hdr, n = read_header(msp)
            meta = hdr.pop("__metadata__", None)
            ends = [v["data_offsets"][1] for v in hdr.values() if v.get("__class__") != "metadata"]
            starts = [v["data_offsets"][0] for v in hdr.values()]
            filesize = msp.stat().st_size
            maxend = max(ends)
            expected = 8 + n + maxend
            keys = set(hdr.keys())
            d["safetensors"] = {
                "filesize": filesize, "header_bytes": n,
                "n_tensors": len(hdr), "max_data_end": maxend,
                "computed_end": expected, "margin_bytes": filesize - expected,
                "closed_exactly": filesize - expected == 0,
                "min_data_start": min(starts),
                "n_out_of_bounds": sum(1 for e in ends if 8 + n + e > filesize),
                "dtype_counter": {k: sum(1 for v in hdr.values() if v["dtype"] == k)
                                  for k in {v["dtype"] for v in hdr.values()}},
                "keys_equal_to_base": keys == base_keys,
                "shapes_equal_to_base": {k: tuple(v["shape"]) for k, v in hdr.items()} == base_shapes,
                "n_shape_mismatches": sum(
                    1 for k in keys & base_keys if tuple(hdr[k]["shape"]) != base_shapes[k]),
                "keys_missing_vs_base": sorted(base_keys - keys)[:10],
                "keys_extra_vs_base": sorted(keys - base_keys)[:10],
                "metadata_present": meta is not None,
            }
            sha, dt, cached = sha256_cached(msp, cache)
            d["safetensors"]["sha256"] = sha
            d["safetensors"]["sha256_cached"] = cached
            d["safetensors"]["sha256_seconds"] = round(dt, 2)
        tsp = ck / "trainer_state.json"
        if tsp.exists():
            st = json.loads(tsp.read_text(encoding="utf-8"))
            lh = st.get("log_history", [])
            steps = [e.get("step") for e in lh if "step" in e]
            d["trainer_state"] = {
                "global_step": st.get("global_step"),
                "epoch": st.get("epoch"),
                "max_steps": st.get("max_steps"),
                "n_log_history": len(lh),
                "log_history_steps": steps,
                "log_history_has_rewards": sum(1 for e in lh if "rewards/chosen" in e),
                "bytes": tsp.stat().st_size,
            }
        out["checkpoints"][ck.name] = d

    # ---------- final output root (written by trainer.save_model() at the very end) ----------
    root_ms = OUT / "model.safetensors"
    if root_ms.exists():
        files = {}
        for f in sorted(OUT.iterdir()):
            if f.is_file():
                stt = f.stat()
                files[f.name] = {"size": stt.st_size, "mtime": stt.st_mtime}
        hdr2, n2 = read_header(root_ms)
        meta2 = hdr2.pop("__metadata__", None)
        ends2 = [v["data_offsets"][1] for v in hdr2.values()]
        starts2 = [v["data_offsets"][0] for v in hdr2.values()]
        fs2 = root_ms.stat().st_size
        exp2 = 8 + n2 + max(ends2)
        keys2 = set(hdr2)
        sha2, dt2, cached2 = sha256_cached(root_ms, cache)
        out["final_output_root"] = {
            "path": str(OUT),
            "files": files,
            "n_files": len(files),
            "safetensors": {
                "filesize": fs2, "header_bytes": n2, "n_tensors": len(hdr2),
                "max_data_end": max(ends2), "computed_end": exp2,
                "margin_bytes": fs2 - exp2, "closed_exactly": fs2 - exp2 == 0,
                "min_data_start": min(starts2),
                "n_out_of_bounds": sum(1 for e in ends2 if 8 + n2 + e > fs2),
                "dtype_counter": {k: sum(1 for v in hdr2.values() if v["dtype"] == k)
                                  for k in {v["dtype"] for v in hdr2.values()}},
                "keys_equal_to_base": keys2 == base_keys,
                "shapes_equal_to_base": {k: tuple(v["shape"]) for k, v in hdr2.items()} == base_shapes,
                "n_shape_mismatches": sum(
                    1 for k in keys2 & base_keys if tuple(hdr2[k]["shape"]) != base_shapes[k]),
                "metadata_present": meta2 is not None,
                "sha256": sha2, "sha256_cached": cached2, "sha256_seconds": round(dt2, 2),
            },
            "has_config_json": "config.json" in files,
            "has_generation_config": "generation_config.json" in files,
            "tokenizer_files": sorted(k for k in files if "token" in k or "chat_template" in k),
            "has_trainer_state_json": "trainer_state.json" in files,
            "trainer_log_jsonl": "trainer_log.jsonl" in files,
        }

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    (R / "m3-dpo-resume-watchdog-C-ckpt-integrity.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("base:", json.dumps({k: v for k, v in out["base"].items() if k != "path"}))
    for name, d in out["checkpoints"].items():
        print(f"\n== {name} ==")
        print("  n_files", d["n_files"], "missing_required", d["missing_required"],
              "resume_ready", d["resume_ready"])
        s = d.get("safetensors")
        if s:
            print(f"  safetensors: filesize={s['filesize']} header={s['header_bytes']} "
                  f"tensors={s['n_tensors']} max_end={s['max_data_end']}")
            print(f"  closure: 8+header+max_end={s['computed_end']} margin={s['margin_bytes']} "
                  f"exact={s['closed_exactly']} oob={s['n_out_of_bounds']}")
            print(f"  keys_equal_to_base={s['keys_equal_to_base']} "
                  f"shapes_equal_to_base={s['shapes_equal_to_base']} "
                  f"shape_mismatches={s['n_shape_mismatches']} "
                  f"extra={s['keys_extra_vs_base']} missing={s['keys_missing_vs_base']}")
            print(f"  sha256={s['sha256']} (cached={s['sha256_cached']})")
        t = d.get("trainer_state")
        if t:
            print(f"  trainer_state: global_step={t['global_step']} n_log_history={t['n_log_history']} "
                  f"rewards_rows={t['log_history_has_rewards']} last_step={t['log_history_steps'][-1] if t['log_history_steps'] else None}")
        print("  file sizes:", {k: v["size"] for k, v in d["files"].items()})
    print("\nWROTE", R / "m3-dpo-resume-watchdog-C-ckpt-integrity.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
