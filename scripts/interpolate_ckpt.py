# -*- coding: utf-8 -*-
"""权重插值（model soup）：在 m2-calib（泛化最好）与 needlefix-e1（needle 最好）之间取样。

目的：判定"长上下文能力"与"跨载体鲁棒性"在权重空间里是否**可分离**。
  - 若存在 α 使 needle ≥0.75 且未见载体 ASR ≈ 起点水6/168 ⇒ 零训练解决。
  - 若两者沿直线严格此消彼长 ⇒ 能力纠缠，必须走**受限更新**配方（LoRA/部分层冻结/低剂量）。

用法：
  python scripts/interpolate_ckpt.py --alpha 0.25 --out checkpoints/soup-needlefix-a025
  python scripts/interpolate_ckpt.py --alpha 0.25,0.5 --out-dir checkpoints          # 批量
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "checkpoints" / "qwen3-06b-sec-m2-calib"          # α=0
B = ROOT / "checkpoints" / "qwen3-06b-sec-m2calib-needlefix-e1"  # α=1
COPY = ["config.json", "generation_config.json", "tokenizer.json",
        "tokenizer_config.json", "chat_template.jinja"]


def build(alpha: float, out: Path) -> dict:
    fa = safe_open(A / "model.safetensors", framework="pt", device="cpu")
    fb = safe_open(B / "model.safetensors", framework="pt", device="cpu")
    ka, kb = set(fa.keys()), set(fb.keys())
    if ka != kb:
        raise SystemExit(f"FAIL：键集合不同（A 独有 {len(ka-kb)}、B 独有 {len(kb-ka)}）")
    out_dtype = None
    merged = {}
    n_tensor = 0
    for k in sorted(ka):
        ta = fa.get_tensor(k)
        tb = fb.get_tensor(k)
        if ta.shape != tb.shape:
            raise SystemExit(f"FAIL：{k} 形状不同 {ta.shape} vs {tb.shape}")
        if ta.dtype != tb.dtype:
            raise SystemExit(f"FAIL：{k} dtype 不同 {ta.dtype} vs {tb.dtype}")
        out_dtype = ta.dtype
        if not ta.is_floating_point():
            merged[k] = ta.clone()          # 整型缓冲（如 rotary inv_freq）原样取 A
            n_tensor += 1
            continue
        merged[k] = ((1.0 - alpha) * ta.float() + alpha * tb.float()).to(ta.dtype)
        n_tensor += 1
    out.mkdir(parents=True, exist_ok=True)
    save_file(merged, str(out / "model.safetensors"),
              metadata={"format": "pt", "soup_alpha": str(alpha),
                        "A": A.name, "B": B.name})
    for f in COPY:
        if (A / f).exists():
            shutil.copy2(A / f, out / f)
    return {"alpha": alpha, "tensors": n_tensor, "dtype": str(out_dtype),
            "out": str(out.relative_to(ROOT))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", required=True, help="单个或逗号分隔（如 0.25,0.5）")
    ap.add_argument("--out", default=None, help="仅单个 alpha 时可用")
    ap.add_argument("--out-dir", default="checkpoints")
    args = ap.parse_args()
    alphas = [float(x) for x in args.alpha.split(",")]
    reps = []
    for a in alphas:
        if not 0.0 <= a <= 1.0:
            raise SystemExit(f"alpha 越界：{a}")
        if args.out and len(alphas) == 1:
            out = Path(args.out)
            if not out.is_absolute():
                out = ROOT / out
        else:
            out = ROOT / args.out_dir / f"soup-needlefix-a{int(round(a*100)):03d}"
        r = build(a, out)
        reps.append(r)
        print(f"  [soup] alpha={a:.2f} → {r['out']}（{r['tensors']} 张量，{r['dtype']}）")
    rep = ROOT / "reports" / "needlefix-soup-build.json"
    old = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else []
    rep.write_text(json.dumps(old + reps, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"SOUP-BUILD=DONE 共 {len(reps)} 个；报告 {rep.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
