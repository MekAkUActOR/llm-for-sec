# M6 Remote Delivery Curation Note (Lead, 2026-10-22)

## Why
GitHub hard limits: single file >100MB rejected; push pack ~2GB max. The window closeout range contained **14.4GB of regeneratable feature caches** (5x feat_cache dirs: m6-v1-3 / m6-v2-3a / m6-v2-4 / m6-v2-4dt / _tmp_v2plane2) plus one training resume snapshot (checkpoints/m6-v2/_snapshot.pt, 177MB). These are compute artifacts, regenerable via `scripts/m6_feat_probe.py` (~35min per trunk state); they are not part of the delivery.

## What was done
- `main-delivery` = filter-branch of local `main` range (origin/main..main), stripping ONLY those paths. All 116 commits preserved: messages, authors, dates, and all delivery content (code / reports / schemas / data pools / probe-heads.pt [all <=90MB] / eval evidence).
- 7 early commits kept identical hashes; 109 rewritten (removed paths entered history mid-range). Full old-to-new mapping below.
- LOCAL `main` retains the complete unfiltered history (with caches). REMOTE `main` = curated chain.
- Final checkpoints mirrored on HuggingFace: `howwhenRaw/m6-security-detector-v2-4dt` (v2.4-dt @ 19eaaba, QA point) and `howwhenRaw/m6-detector-v1-2`.

## Old-to-new hash mapping (109 changed; identical 7 omitted)
d4a3a59 -> 915ca74 | lead-m6: closeout evidence capture - qa v2.4/v2.4-dt dual-op
0610a69 -> 4c202df | qa-m6: closing housekeeping - stage rename deletion of super
0ea5f69 -> 020493a | pm-m6: Lead closure broadcast logged (39th anchor 21:34:22):
4315dbe -> 6b5f569 | pm-m6: FULL TEAM CLOSURE + BOARD 15/15 COMPLETE: deveng form
1f34a59 -> a1be092 | pm-m6: task-14 FINAL REPORT (Lead terminal ruling Option A e
5d2f7fc -> 038a3e9 | deveng-m6: closure housekeeping - (1) checkpoints/m6-v2-4dt/
f30adfe -> 633de1b | pm-m6: closure-chain board flow: arch integration confirmed 
db0a34e -> 793476a | arch-m6: 更正交付物 hash 笔误 19eaba→19eaaba（与 pm 汇编一致）
5685fa4 -> eecd6f7 | pm-m6: task-13 FINAL-ADJUDICATION COMPILATION (pm lead autho
000fdf3 -> 1dcbffa | pm-m6: final-adjudication material set COMPLETE + board flow
5dd16bc -> c4d66d9 | qa-m6: task-15 ethanol statement FINAL (no-violation across 
6098276 -> 2ecbcd1 | arch-m6: task-13 arch sections（判定声明+归因链+备案+⑬论证+工艺教训+post-win
8511b29 -> 4aec4cf | deveng-m6: findings summary FINAL - delivery confirmed (arch
32b10b4 -> e0dfe6d | qa-m6: task-13 directed materials - gap table (v2.4-dt six-g
560758e -> ec27116 | arch-m6: ADR-2b §2d 终局周期+交付判定（v2.4-dt @ 19eaba，QA 点，门卡定版）
94867e6 -> ac3d47e | pm-m6: qa v2.4-dt readings segment COMPLETE (21:01, section-
2ac6c06 -> 17751a5 | qa-m6: v2.4-dt gate-only final readings - T4 G2 4.78->2.33pc
72b8f14 -> 78c7b62 | pm-m6: arch NO-GO finalized + readings RUNNING: final count 
6c26f16 -> 215fd4f | deveng-m6: findings summary (task-13/14 source material) - a
77cc864 -> ac8559d | deveng-m6: FINAL subordination count (labels-heldout gold jo
56cc3d4 -> 9b5e080 | pm-m6: arch adjudication-flow update (final count in progres
433c565 -> 7213e5b | deveng-m6: span-subordination counts (arch 20:0x order, data
19eaaba -> 4d77f60 | deveng-m6: span length gate ON v2.4-dt (arch 20:0x order - l
3d3a56a -> 0151335 | pm-m6: arch scheduling update (+30min gate implementation, r
b17d5d5 -> 13f8d8e | deveng-m6: v2.4-dt dual-trunk assembly (arch 19:5x order, sk
3c2d723 -> 089b0bd | pm-m6: arch v2.4 confirmation + final-step scheduling: v2.4 
3e0de29 -> 77888d0 | qa-m6: task-15 v2.4-wave leak recheck PASS (train 16,144 vs 
c56ec34 -> 8f44238 | qa-m6: final acceptance report refreshed to v2.4 (G1 six-hea
46d901f -> 1fe520f | pm-m6: qa v2.4 readings segment COMPLETE (19:40, section-9 1
e46d027 -> f47e55e | qa-m6: v2.4 full readings - G1 SIX heads pass (QA point), re
e3a34f6 -> 898ceaa | arch-m6: ADR-2b §2c OOD 对照实验定版（三层依赖框架实证+G4 归因表）
474168c -> bdd2a01 | deveng-m6: arch prediction-1 control runpoint VERIFIED - v2 
d4de8a5 -> 05363a4 | deveng-m6: v2.4 OOD telemetry (3-item, dissociation test res
92a46d4 -> e7de1e6 | pm-m6: qa chase CROSSED with approval (pm notification gap):
48fa3d6 -> 0db5b40 | pm-m6: qa slot APPROVED - v2.4 acceptance readings chain (~5
1b886bf -> da8dd5f | deveng-m6: dual-trunk design sketch (T4 residual lever, arch
a196050 -> a314191 | arch-m6: ADR-2b §2c v2.2/v2.4 周期（联合关闭+后处理复合+头级投递保基质）
f7a580a -> a8035ee | deveng-m6: v2.4 COMPOSITE - delivery candidate. Assembly: v2
89cd266 -> cb644a8 | deveng-m6: Branch A artifact + verdict + Branch B launch - A
e7df00e -> b169494 | pm-m6: deveng GPU registration - Branch A composite chain ST
7bcdfc3 -> 44ead3c | deveng-m6: Branch A implementation (arch 18:4x ruling - join
38051a3 -> 7a0fa96 | pm-m6: arch v2.2 readings + path adjudication: JOINT TRAININ
5aa75a9 -> 165c819 | pm-m6: v2.2 LAUNCH (16:5x, job bf70eef5, commit 3748b43, joi
3748b43 -> 33b1140 | deveng-m6: v2.2 GO - four-increment integration (arch 16:37)
be519a1 -> a3459e5 | [sysdesign] D-16 registered: v2.2 third increment audited (d
0d46b42 -> 4aed5c1 | [dataeng] inventory v5: v2.2 increment-3 deployment trail
df6df6a -> de911a8 | [dataeng] v2.2 increment-3 (arch execution order): deploy t4
9d99a69 -> 2b9e751 | pm-m6: qa diagnostic slot CLOSED (abandoned - lossless): mid
71b4113 -> 7e26f2b | pm-m6: qa diagnostic slot APPROVED (~13min, run-and-return):
bd6f271 -> a11df5f | arch-m6: ADR-2b §2b v2.1 周期记录（三跑模式+T2/T6 机制读+裁定链）
e296277 -> 4958bf7 | pm-m6: arch v2.2 INTEGRATION RUN adjudication: three-run evi
4debd8c -> 186ae1f | arch-m6: ADR-2b §2 v2 LoRA 效应段（四案例验证+三靶面+G4 机制链+同源假说）
f66630b -> 98eecea | pm-m6: arch second-run adjudication + deveng third-run regis
3e6805b -> 1f0027e | deveng-m6: T6 per-epoch guard (structural blind spot closed)
f5714ae -> 0b811ab | pm-m6: v2.1 first run completed but product UNUSABLE - guard
24b759b -> 4ac0378 | deveng-m6: WARN fallback = least-bad epoch, not last (v2.1 l
632c6f5 -> 4419863 | [sysdesign] schemas v0.3.24: t1_projection fix-wave dual key
1302549 -> c90f5fc | pm-m6: deveng GPU registration - v2.1 LoRA STARTED (job da19
7356d1f -> c1be5a6 | [dataeng] inventory v4: v2.1 wave audit trail (D-f/D-g, gate
06a4a34 -> 6a03bb0 | deveng-m6: v2.1 GO - plane-consistent guard baseline injecte
16dc228 -> 7cb8661 | [dataeng] T4 contingency staging (arch pre-order, NOT in cur
8612eec -> aeff09c | qa-m6: G4 joint-condition data (2/314 = 0.6% is_ood on flagg
ac70120 -> 8644592 | [dataeng] v2.1 fix wave (arch rulings): release 159 PII/inje
e21498a -> c0ea9da | pm-m6: qa acceptance round (task-12) v2 SEGMENT complete: qa
7c51a90 -> a5814cb | qa-m6: G4 discriminant tree data - three-generation is_ood t
8d25800 -> ccd4e06 | qa-m6: v2 acceptance final report (verdict FAIL -> v2.1 conf
29c5902 -> ab804cf | pm-m6: qa v2 readings segment COMPLETE (11:33, within slot, 
9e8379c -> c25dd80 | qa-m6: four-line comparison updated with v2 LoRA segment (fo
b1db4fb -> e1389c8 | qa-m6: v2 ep2-best full readings - FIVE heads pass G1 (T3 lo
22d2980 -> 6cdc3fa | [sysdesign] schemas v0.3.23: t1_projection absorbed (v2.1 wa
ef0570d -> c51b0e7 | [dataeng] v2.1 wave (arch D-f/D-g): t1-lawful 700 (4-family 
3280463 -> ee715c2 | deveng-m6: v2.1 config pre-staged - T1 data-effect iteration
1701b44 -> fc384a6 | pm-m6: arch timing correction - v2.1 LoRA full run APPROX 4H
96fd746 -> 4456430 | arch-m6: ADR-2b s1c - D-16 fifth case: guard per-epoch fp32 
c437ea7 -> 5f58551 | pm-m6: deveng three-question answers + MAJOR new finding: (1
18e02a4 -> e325618 | deveng-m6: per-epoch guard eval migrated to logit space (D-1
1fa7bb2 -> f917995 | pm-m6: arch T1 diagnosis closed + v2.1 path ruling: deveng d
e03817f -> 0050c41 | pm-m6: qa readings slot APPROVED with conflict DISSOLVED by 
ed2457d -> 9f18c41 | deveng-m6: T1 saturation family decomposition artifacts (arc
e2a758c -> 5e1f695 | deveng-m6: v2 LoRA artifacts - ep2/WARN+last (guard caught T
105e7f1 -> bb11fdd | deveng-m6: ROOT CAUSE of v2 ep1 crashes - full-vocab lm_head
377bb00 -> e0a19e0 | pm-m6: section-9 verification - restart HEALTHY (process for
012bc57 -> 784c370 | deveng-m6: fix NameError in lora-resume scaffolding (args no
4f912c7 -> c6737b7 | pm-m6: v2 LoRA CRASH retrospective + restart (fb00cfe fixes)
fb00cfe -> ff98736 | deveng-m6: LoRA OOM resilience + crash recovery - v2 first a
9ac4f5f -> 94b2692 | pm-m6: Lead EPOCH RULING - no manual trim, run to completion
0bd5bdb -> 9181c8e | pm-m6: LoRA ETA revision TWO (measured 4.3s/step mean, doc-l
e01a9a7 -> 9c025d1 | qa-m6: acceptance template v2 sections (2a T3 family table, 
d234d4a -> 24f1c55 | deveng-m6: qa task-15 v2-review nit - notes tail line correc
9f49036 -> a1eb06f | pm-m6: deveng v2 LoRA progress + PROJECTION REVISION (double
8265f39 -> 958df6d | qa-m6: task-15 v2-segment config audit (m6-v2.yaml clean - n
f79f1fa -> 5d40255 | pm-m6: qa three-line comparison master table landed (qa-thre
a941f25 -> 4396115 | qa-m6: three-line comparison table (v0/v1-2/v1-3 effect deco
8222730 -> 0ededad | deveng-m6: per-task logit field in inference output (qa/arch
68aaa2f -> f3c7623 | [sysdesign] schemas v0.3.22: TaskResult + per-item logit key
b1a83e1 -> a46d6af | qa-m6: spec section 10 known-limits (K1 flag-only ruling D-1
ae050b2 -> 283d453 | arch-m6: ADR-2b s1b - D-16 fourth case: score round(6) consu
9c67da3 -> 313899a | qa-m6: T3 family breakdown tool (flag-only caliber aligned w
8989b72 -> 96eb760 | pm-m6: arch v1-3 readings adjudication complete (LoRA unbloc
c3459b3 -> ed83cc2 | qa-m6: v1-3 sensitivity (theta-0.05 releases recall: T1 98/T
8f195ad -> b3f54f8 | qa-m6: task-15 D-wave content-level leak re-verification PAS
2f32fb5 -> 240670f | pm-m6: v2 LoRA STARTED 03:30 (all gate conditions green): in
29fdf89 -> 9bbab49 | deveng-m6: ADR-2b s1 task_weights retune applied (T5 1.0->1.
2d7ea2a -> fc9d049 | pm-m6: qa v1-3 guard baseline FORMAL readings complete (03:2
7b1ad3f -> 539607d | qa-m6: v1-3 post-fix guard-baseline readings (dual runpoint:
d378def -> 7a28954 | [sysdesign] schemas v0.3.21: per-band threshold_space absorb
ad1e6a2 -> d558252 | arch-m6: ADR-2b created - s1 task_weights retune T5 1.0->1.3
b908974 -> 84317f4 | pm-m6: deveng v1-3 rerun READINGS + guard baseline injection
98a64c8 -> a892a42 | deveng-m6: v1-3 artifacts (checkpoints/m6-v1-3 + regression 
