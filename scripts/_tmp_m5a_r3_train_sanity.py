# -*- coding: utf-8 -*-
"""M5A-R3 训练后曲线 sanity + 子档数核对（纯 CPU 读档）。"""
import json
import math
import os

CK = r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m5a-dpo-r3"
CK2 = r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m5a-dpo-r2"

st = json.load(open(os.path.join(CK, "trainer_state.json"), encoding="utf-8"))
print("global_step:", st["global_step"], "/ max_steps:", st["max_steps"])
hist = st["log_history"]
losses = [h["loss"] for h in hist if "loss" in h]
rews = [h for h in hist if "rewards/chosen" in h]
nan = [x for x in losses if math.isnan(x) or math.isinf(x)]
print(f"log entries: {len(hist)} (loss points: {len(losses)}, reward points: {len(rews)})")
print(f"loss: first {losses[0]:.4f} -> last {losses[-1]:.4f} | min {min(losses):.4f} | max {max(losses):.4f} | NaN/Inf: {len(nan)}")
acc = [h["rewards/accuracies"] for h in rews]
mar = [h["rewards/margins"] for h in rews]
ch = [h["rewards/chosen"] for h in rews]
rj = [h["rewards/rejected"] for h in rews]
print(f"rewards/chosen:   first {ch[0]:+.4f} -> last {ch[-1]:+.4f} | mean(last10) {sum(ch[-10:])/10:+.3f}")
print(f"rewards/rejected: first {rj[0]:+.4f} -> last {rj[-1]:+.4f} | mean(last10) {sum(rj[-10:])/10:+.3f}")
print(f"accuracies:       first {acc[0]:.4f} -> last {acc[-1]:.4f} | min {min(acc):.4f} | max {max(acc):.4f} | mean(last10) {sum(acc[-10:])/10:.4f}")
print(f"margins:          first {mar[0]:.4f} -> last {mar[-1]:.4f} | min {min(mar):.4f} | max {max(mar):.4f} | all>0: {all(m > 0 for m in mar)}")
gn = [h["grad_norm"] for h in rews]
print(f"grad_norm: min {min(gn):.3f} | max {max(gn):.3f}")
print("epoch_final:", hist[-1].get("epoch"), "| train_loss(final agg):", hist[-1].get("train_loss"))
tr = json.load(open(os.path.join(CK, "train_results.json"), encoding="utf-8"))
print("train_results.json:", json.dumps(tr, ensure_ascii=False))
sub = sorted(d for d in os.listdir(CK) if d.startswith("checkpoint-"))
print("checkpoint subdirs:", len(sub), sub)
final_files = ["model.safetensors", "trainer_state.json", "train_results.json", "all_results.json",
               "training_loss.png", "training_rewards_accuracies.png", "config.json", "tokenizer.json"]
missing = [f for f in final_files if not os.path.exists(os.path.join(CK, f))]
print("终档关键件齐:", not missing, ("缺 " + str(missing)) if missing else "")

print()
print("=== 对照 r2（qwen3-06b-sec-m5a-dpo-r2）===")
st2 = json.load(open(os.path.join(CK2, "trainer_state.json"), encoding="utf-8"))
l2 = [h["loss"] for h in st2["log_history"] if "loss" in h]
r2r = [h for h in st2["log_history"] if "rewards/chosen" in h]
t2 = st2["log_history"][-1]["train_loss"]
print(f"r2: train_loss {t2:.4f} | loss min/max {min(l2):.4f}/{max(l2):.4f} | acc last {r2r[-1]['rewards/accuracies']:.4f} | margin last {r2r[-1]['rewards/margins']:.2f} | runtime {st2['log_history'][-1]['train_runtime']:.0f}s")
print(f"r3: train_loss {hist[-1]['train_loss']:.4f} | loss min/max {min(losses):.4f}/{max(losses):.4f} | acc last {acc[-1]:.4f} | margin last {mar[-1]:.2f} | runtime {hist[-1]['train_runtime']:.0f}s")
