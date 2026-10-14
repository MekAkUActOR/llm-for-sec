"""解析 LLaMA-Factory/HF Trainer 输出目录中的训练日志，输出冒烟门禁摘要。

用法：
    python scripts/parse_train_log.py checkpoints/qwen3-06b-sec-c0-smoke

读取 trainer_state.json（优先）或 trainer_log.jsonl，输出：
- loss 曲线（每个 logging step）
- 门禁判定：无 NaN、loss 下降幅度、吞吐（若日志含 tokens_per_second）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_records(out_dir: Path) -> list[dict]:
    st = out_dir / "trainer_state.json"
    if st.exists():
        state = json.loads(st.read_text(encoding="utf-8"))
        return state.get("log_history", [])
    tj = out_dir / "trainer_log.jsonl"
    if tj.exists():
        return [json.loads(l) for l in tj.read_text(encoding="utf-8").splitlines() if l.strip()]
    raise SystemExit(f"no trainer_state.json / trainer_log.jsonl under {out_dir}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    d = Path(sys.argv[1])
    recs = load_records(d)
    # 兼容两种格式：HF trainer_state.json（step/learning_rate）
    # 与 LLaMA-Factory trainer_log.jsonl（current_steps/lr）
    norm = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        norm.append({
            "step": r.get("step", r.get("current_steps")),
            "loss": r.get("loss"),
            "grad_norm": r.get("grad_norm"),
            "learning_rate": r.get("learning_rate", r.get("lr")),
            "tokens_per_second": r.get("tokens_per_second"),
        })
    losses = [(r["step"], r["loss"], r["grad_norm"])
              for r in norm if r.get("loss") is not None and r.get("step") is not None]
    if not losses:
        raise SystemExit("no loss records found")

    print(f"{'step':>6} {'loss':>10} {'grad_norm':>10}")
    for step, loss, gn in losses:
        gn_s = f"{gn:.4f}" if gn is not None else "-"
        print(f"{step:>6} {loss:>10.4f} {gn_s:>10}")

    first_step, first_loss = losses[0][0], losses[0][1]
    last_step, last_loss = losses[-1][0], losses[-1][1]
    nan = any(l != l for _, l, _ in losses)  # NaN != NaN
    exp = first_loss > 0 and last_loss > 0
    drop = (first_loss - last_loss) / first_loss if first_loss else 0.0

    print("\n--- 门禁摘要 ---")
    print(f"loss: {first_loss:.4f} (step {first_step}) -> {last_loss:.4f} (step {last_step})"
          f"  相对下降 {drop * 100:.1f}%")
    print(f"NaN: {'有 ✗' if nan else '无 ✓'}")
    print(f"loss 下降: {'✓' if last_loss < first_loss else '✗'}")

    tps = [r["tokens_per_second"] for r in norm if r.get("tokens_per_second")]
    if tps:
        print(f"吞吐: 均值 {sum(tps) / len(tps):,.0f} tok/s（{len(tps)} 个记录）")

    # 学习率轨迹末值（确认 cosine 衰减生效）
    lrs = [(r["step"], r["learning_rate"]) for r in norm
           if r.get("learning_rate") is not None and r.get("step") is not None]
    if lrs:
        print(f"lr: 起始 {lrs[0][1]:.2e} -> 末值 {lrs[-1][1]:.2e}")

    # checkpoint 文件清单
    ckpts = sorted(p.name for p in d.iterdir() if p.is_dir() and p.name.startswith("checkpoint"))
    if ckpts:
        print(f"checkpoints: {', '.join(ckpts)}")


if __name__ == "__main__":
    main()
