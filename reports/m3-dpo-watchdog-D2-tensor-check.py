# -*- coding: utf-8 -*-
"""M3 DPO watchdog: verify soup-needlefix-a050 == 0.5*m2-calib + 0.5*m2calib-needlefix-e1
at the tensor level, lazily (safetensors.safe_open, CPU only, small tensors only).
Read-only. NOTE: the soup builder's convention is alpha=0 -> m2-calib, alpha=1 -> needlefix-e1
(records/m2calib-needlefix-e1.json says: alpha=1.0 -> "采用 needlefix-e1")."""
import json
import os

import torch

ROOT = r"J:\Projects\llm_for_sec"
CK = os.path.join(ROOT, "checkpoints")
SOUP = os.path.join(CK, "soup-needlefix-a050")
NEEDLEFIX = os.path.join(CK, "qwen3-06b-sec-m2calib-needlefix-e1")
M2CALIB = os.path.join(CK, "qwen3-06b-sec-m2-calib")
ALPHA = 0.5
OUT = os.path.join(ROOT, "reports", "m3-dpo-watchdog-tensor-check.json")


def st_path(d):
    for fn in os.listdir(d):
        if fn.endswith(".safetensors"):
            return os.path.join(d, fn)
    return None


def main():
    from safetensors import safe_open

    res = {
        "alpha": ALPHA,
        "convention": "alpha=0 -> m2-calib ; alpha=1 -> m2calib-needlefix-e1",
        "paths": {
            "soup_a050": st_path(SOUP),
            "m2_calib": st_path(M2CALIB),
            "needlefix_e1": st_path(NEEDLEFIX),
        },
        "dirs": {"soup": SOUP, "m2_calib": M2CALIB, "needlefix_e1": NEEDLEFIX},
        "checks": [],
    }

    def keys_of(p):
        with safe_open(p, framework="pt", device="cpu") as f:
            return list(f.keys())

    ks, kb, kt = keys_of(res["paths"]["soup_a050"]), keys_of(res["paths"]["m2_calib"]), keys_of(res["paths"]["needlefix_e1"])
    res["key_counts"] = {"soup": len(ks), "m2_calib": len(kb), "needlefix_e1": len(kt)}
    res["keys_soup_not_in_parents"] = sorted(set(ks) - set(kb) - set(kt))[:20]
    res["keys_parent_not_in_soup"] = sorted((set(kb) | set(kt)) - set(ks))[:20]
    common = [k for k in ks if k in set(kb) and k in set(kt)]
    res["common_keys"] = len(common)

    def getdtype(p, k):
        with safe_open(p, framework="pt", device="cpu") as f:
            return str(f.get_slice(k).get_dtype())

    res["dtypes"] = {
        "soup": getdtype(res["paths"]["soup_a050"], common[0]) if common else None,
        "m2_calib": getdtype(res["paths"]["m2_calib"], common[0]) if common else None,
        "needlefix_e1": getdtype(res["paths"]["needlefix_e1"], common[0]) if common else None,
    }

    def load(p, k):
        with safe_open(p, framework="pt", device="cpu") as f:
            return f.get_tensor(k)

    pick = []
    for want in ("model.norm.weight", "model.layers.0.self_attn.q_proj.weight",
                 "model.layers.13.mlp.gate_proj.weight", "model.layers.27.mlp.down_proj.weight",
                 "model.layers.27.self_attn.o_proj.weight"):
        if want in common:
            pick.append(want)

    for k in pick:
        t_soup = load(res["paths"]["soup_a050"], k)
        soup_dtype = str(t_soup.dtype)
        t_b = load(res["paths"]["m2_calib"], k).to(torch.float32)
        t_t = load(res["paths"]["needlefix_e1"], k).to(torch.float32)
        interp = (1.0 - ALPHA) * t_b + ALPHA * t_t
        diff = (t_soup.to(torch.float32) - interp).abs()
        absmax = float(interp.abs().max().item())
        rec = {
            "tensor": k,
            "shape": list(t_soup.shape),
            "soup_dtype_in_file": soup_dtype,
            "numel": int(t_soup.numel()),
            "max_abs_diff_soup_vs_interp": float(diff.max().item()),
            "mean_abs_diff": float(diff.mean().item()),
            "interp_absmax": absmax,
            "rel_max_vs_interp_absmax": (float(diff.max().item() / absmax) if absmax else None),
            "base_vs_tuned_absmax_delta": float((t_b - t_t).abs().max().item()),
            "control_copy_m2calib_absmax": float((t_soup.to(torch.float32) - t_b).abs().max().item()),
            "control_copy_needlefix_absmax": float((t_soup.to(torch.float32) - t_t).abs().max().item()),
        }
        res["checks"].append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        del t_soup, t_b, t_t, interp, diff

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
