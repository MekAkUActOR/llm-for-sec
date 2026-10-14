# M4 capfix FULL-RUN DPO watchdog (configs/m4-capfix-full.yaml)

Run: `checkpoints\soup-needlefix-a050` -> `checkpoints\qwen3-06b-sec-m4-capfix-full` | data `data/m4-run/dpo_m4_capfix.jsonl` (28,842 rows) | 1 epoch = 1,803 steps | logging_steps=5, save_steps=100, save_total_limit=5
Scientific question: does `rewards/chosen` stay > +1 (capfix held) or collapse toward ~0 while `rewards/rejected` alone dives (M3 pathology returned; M3 @1800: chosen +0.34 / rejected -12.46 = 1:43)?

## Timeline
- 2026-10-06 21:35:20 | tick 1 | python(m4-capfix-full)=2 [4112,5988] | ckpts=0 max=0 | logstep=n/a epoch=n/a | loss=n/a chosen=n/a rejected=n/a acc=n/a ratio=n/a | log=83584B oomLines=0
- 2026-10-06 21:41:20 | tick 2 | python(m4-capfix-full)=2 [4112,5988] | ckpts=1 max=100 | logstep=stdout epoch=0.0555 | loss=0.1252 chosen=4.508 rejected=-4.59 acc=0.925 ratio=1:1.02 | log=117714B oomLines=0
- 2026-10-06 21:47:20 | tick 3 | python(m4-capfix-full)=2 [4112,5988] | ckpts=2 max=200 | logstep=stdout epoch=0.1109 | loss=0.0612 chosen=2.26 rejected=-10.57 acc=0.9625 ratio=1:4.68 | log=152044B oomLines=0
- 2026-10-06 21:53:20 | tick 4 | python(m4-capfix-full)=2 [4112,5988] | ckpts=3 max=300 | logstep=stdout epoch=0.1664 | loss=0.0786 chosen=-0.451 rejected=-10.73 acc=0.95 ratio=1:23.79 | log=186356B oomLines=0
- ANALYSIS 22:00 | probe-vs-full step-by-step diff: steps 5-100 agree to <0.06 (same seed/order), then diverge progressively - step 300 dCh=-0.75, dRj=-1.29, max|d|=1.70 @ step225 (bf16 nondeterminism compounding). => probe tail values are NOT reproducible per-point; only the SHAPE transfers. Windowed (200-step bins): probe 0-199 +2.09/-6.59, 200-299 +1.07/-9.96; full 0-199 +1.93/-6.86, 200-399 +0.35/-10.84. Parent's "probe +1.3..+4.8" = noise near the early peak. M3 baseline bins for reference: 0-199 +2.27/-3.80, 200-399 +0.59/-9.24, 400-599 +0.05/-11.07 ... 1600-1799 +1.13/-12.22, final point +0.34/-12.46.
- 2026-10-06 21:59:21 | tick 5 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=500 | logstep=stdout epoch=0.2774 | loss=0.0487 chosen=-0.5774 rejected=-12.15 acc=0.975 ratio=1:21.04 | log=236488B oomLines=0
- 2026-10-06 22:05:21 | tick 6 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=600 | logstep=stdout epoch=0.3328 | loss=0.1391 chosen=0.5488 rejected=-10.52 acc=0.9375 ratio=1:19.17 | log=270200B oomLines=0
- 2026-10-06 22:11:21 | tick 7 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=700 | logstep=stdout epoch=0.3883 | loss=0.0974 chosen=2.009 rejected=-8.304 acc=0.95 ratio=1:4.13 | log=303830B oomLines=0
- 2026-10-06 22:17:21 | tick 8 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=800 | logstep=stdout epoch=0.4438 | loss=0.0809 chosen=-0.4231 rejected=-12.99 acc=0.95 ratio=1:30.7 | log=337696B oomLines=0
- 2026-10-06 22:23:21 | tick 9 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1000 | logstep=stdout epoch=0.5547 | loss=0.1151 chosen=-2.1 rejected=-14.69 acc=0.925 ratio=1:7 | log=386542B oomLines=0
- ANALYSIS 22:27 | *** REGRESSION SIGNAL *** bin 800-999 (n=40) chosen=-0.912 rejected=-13.857 ratio 1:15.2 minChosen=-2.818; last-20 mean chosen=-1.368 rejected=-14.240. FIRST bin in either run where chosen is NEGATIVE (M3 same bin: +0.264/-12.653). M4 is now WORSE than M3 on chosen and deeper on rejected. Bin trajectory chosen: +1.926, +0.351, +0.896, +1.367, -0.912 (abrupt break). rejected: -6.858, -10.836, -10.716, -10.413, -13.857. NOTE acc=0.959 while chosen<0 => accuracy high + margins +12.6 yet chosen reward below reference = suppression-dominated learning; win-rate metric masks the pathology.
- 2026-10-06 22:29:21 | tick 10 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1100 | logstep=stdout epoch=0.6102 | loss=0.201 chosen=-1.021 rejected=-14.08 acc=0.95 ratio=1:13.79 | log=420440B oomLines=0
- 2026-10-06 22:35:21 | tick 11 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1200 | logstep=stdout epoch=0.6657 | loss=0.0683 chosen=-4.49 rejected=-16.69 acc=0.9625 ratio=1:3.72 | log=455270B oomLines=0
- ANALYSIS 22:37 | *** ESCALATION *** bin 1000-1199 chosen=-1.987 rejected=-15.146 min=-3.839; bin 1200-1399 (n=21) chosen=-5.792 rejected=-18.409 min=-7.852; last-20 mean chosen=-5.857 rejected=-18.495. chosen bin trajectory: +1.93, +0.35, +0.90, +1.37, -0.91, -1.99, -5.79 => monotone collapse, NO recovery. M3 worst bin ever was 1200-1399 = +0.164/-12.691; M4 is now -5.79/-18.41 i.e. catastrophically worse than the run it was meant to fix. margins still ~+12, acc ~0.95 (acc=1.0 touched at step 1300), so win-rate stays high while chosen falls BELOW reference => pure rejected-suppression + chosen-side unlearning. ~500 steps left.
- 2026-10-06 22:41:21 | tick 12 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1300 | logstep=stdout epoch=0.7212 | loss=0.0094 chosen=-5.795 rejected=-19.48 acc=1 ratio=1:3.36 | log=490158B oomLines=0
- 2026-10-06 22:47:21 | tick 13 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1500 | logstep=stdout epoch=0.8321 | loss=0.1788 chosen=-4.418 rejected=-17.84 acc=0.9375 ratio=1:4.04 | log=540198B oomLines=0
- 2026-10-06 22:53:21 | tick 14 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1600 | logstep=stdout epoch=0.8876 | loss=0.0994 chosen=-4.185 rejected=-17.07 acc=0.95 ratio=1:4.08 | log=574898B oomLines=0
- 2026-10-06 22:59:21 | tick 15 | python(m4-capfix-full)=2 [4112,5988] | ckpts=5 max=1700 | logstep=stdout epoch=0.9431 | loss=0.1061 chosen=-2.734 rejected=-16.61 acc=0.9625 ratio=1:6.08 | log=609812B oomLines=0
- 2026-10-06 23:05:21 | tick 16 | python(m4-capfix-full)=2 [7140,19680] | ckpts=5 max=1803 | logstep=1800 epoch=0.9985 | loss=0.0977 chosen=-3.6262 rejected=-16.8674 acc=0.9375 ratio=1:4.65 | log=637342B oomLines=0
- 2026-10-06 23:05:21 | MONITOR STOP: final checkpoint 1800 present

## FINAL RESULT — COMPLETED (step 1803/1803, epoch 1.0)
train_loss=0.11545  train_runtime=5158.3s (1:25:58)  5.591 samples/s  Traceback=0  CUDA-OOM=0  trainer_log.jsonl=361 lines
Artifacts at output root: model.safetensors 2.38GB, trainer_state.json (global_step=1803), train_results.json, all_results.json, training_loss.png, training_rewards_accuracies.png. Training PIDs 4112/5988 gone; log ends 'Training completed.' + figure saves. (Parent's pwsh-2257 exit code is not observable from a delegated session.)

| window | n | chosen | rejected | ratio | margin | acc | minCh | logpsCh | logpsRj |
|---|---|---|---|---|---|---|---|---|---|
| 0-199 | 39 | +1.926 | -6.858 | 1:3.56 | +8.784 | 0.916 | -0.348 | -314.6 | -427.1 |
| 200-399 | 40 | +0.351 | -10.836 | 1:30.89 | +11.187 | 0.949 | -0.906 | -335.8 | -474.7 |
| 400-599 | 40 | +0.896 | -10.716 | 1:11.96 | +11.612 | 0.951 | -0.758 | -323.6 | -467.0 |
| 600-799 | 40 | +1.367 | -10.413 | 1:7.62 | +11.779 | 0.955 | -0.192 | -325.6 | -468.2 |
| 800-999 | 40 | -0.912 | -13.857 | 1:15.20 | +12.945 | 0.959 | -2.818 | -350.4 | -503.2 |
| 1000-1199 | 40 | -1.987 | -15.146 | 1:7.62 | +13.159 | 0.953 | -3.838 | -365.0 | -516.8 |
| 1200-1399 | 40 | -5.086 | -17.876 | 1:3.51 | +12.790 | 0.956 | -7.852 | -386.2 | -543.1 |
| 1400-1599 | 40 | -3.733 | -16.903 | 1:4.53 | +13.169 | 0.953 | -5.359 | -369.6 | -527.3 |
| 1600-1799 | 40 | -3.147 | -16.627 | 1:5.28 | +13.480 | 0.957 | -4.523 | -374.3 | -529.4 |
| 1800 | 1 | -3.626 | -16.867 | 1:4.65 | +13.241 | 0.938 | -3.626 | -321.7 | -502.0 |

FINAL logged point (step 1800) chosen=-3.6262 rejected=-16.8674 | last-20-mean chosen=-3.1587 rejected=-16.6919 margins=+13.5332 acc=0.9594
VERDICT: *** PATHOLOGY RETURNED, WORSE THAN M3 ***. Pathologist criterion was chosen>+1 at the end: actual -3.63. M3 same final bin was +0.343/-12.463, so M4 is -3.97 lower on chosen and -4.40 lower on rejected. Reference-relative (rewards/beta, beta=0.1): M4 ends with chosen 36.3 nats BELOW the reference (M3: +3.4 nats ABOVE) and rejected 168.7 nats below (M3: -124.6). accuracies never saturate (bin means 0.916-0.959; only 9/360 points >=0.99) yet win-rate stays ~0.95 => the model separates pairs by driving the rejected side down while also unlearning the chosen side. No recovery after the step-800 break.
