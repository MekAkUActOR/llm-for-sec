# -*- coding: utf-8 -*-
"""M5A-R4 训练 sanity 核验（TRAIN-SANITY）：结构 + trainer_state + 曲线（loss/margins/acc）。"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "checkpoints" / "qwen3-06b-sec-m5a-dpo-r4"

fails = []


def chk(name, ok, detail=""):
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        fails.append(name)


print(f"== M5A-R4 训练 sanity（{CKPT.name}）==")
sub = sorted(p.name for p in CKPT.glob("checkpoint-*"))
chk("6 sub-checkpoints", sub == [f"checkpoint-{i}" for i in (50, 100, 150, 200, 250, 300)], str(sub))
chk("root model.safetensors", (CKPT / "model.safetensors").exists() and (CKPT / "model.safetensors").stat().st_size > 2e9)
chk("tokenizer/config", (CKPT / "tokenizer.json").exists() and (CKPT / "config.json").exists())

st = json.loads((CKPT / "trainer_state.json").read_text(encoding="utf-8"))
chk("global_step == 300", st["global_step"] == 300, f"step={st['global_step']} epoch={st.get('epoch')}")
tr = json.loads((CKPT / "train_results.json").read_text(encoding="utf-8"))
rt, tl = tr.get("train_runtime"), tr.get("train_loss")
chk("train_runtime recorded", isinstance(rt, (int, float)), f"{rt}s")
chk("train_loss finite & sane", isinstance(tl, (int, float)) and 0 < tl < 2 and math.isfinite(tl), f"loss={tl}")

hist = st["log_history"]
losses = [h["loss"] for h in hist if "loss" in h]
margins = [h["rewards/margins"] for h in hist if "rewards/margins" in h]
accs = [h["rewards/accuracies"] for h in hist if "rewards/accuracies" in h]
chk("log_history rich (>=30 entries)", len(hist) >= 30, f"{len(hist)} entries")
chk("loss no NaN/Inf", all(math.isfinite(l) for l in losses), f"first={losses[0]:.4f} last={losses[-1]:.4f}")
chk("margins all positive", all(m > 0 for m in margins), f"min={min(margins):.4f} max={max(margins):.4f}")
chk("acc converges >=0.9 tail", max(accs) >= 0.9, f"first={accs[0]:.3f} last={accs[-1]:.3f} max={max(accs):.3f}")

if fails:
    print(f"TRAIN-SANITY=FAIL ({fails})")
    sys.exit(1)
print(f"TRAIN-SANITY=PASS (runtime {rt:.1f}s, loss {tl:.4f}, margins>0, acc max {max(accs):.3f})")
