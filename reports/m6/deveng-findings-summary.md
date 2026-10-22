# deveng-m6 Findings Summary (task-13/14 source material)

**Scope**: v2 iteration chain → delivery candidates. All commits `[deveng-m6]`-prefixed on main; only Lead pushes.
**DELIVERY CONFIRMED (arch 21:1x)**: **checkpoints/m6-v2-4dt @ 19eaaba = the delivery artifact** (QA point; full chain: assembly macro 0.935 + gate −51% FP + isolation perfect [red-team/T3/G1 zero perturbation]). v2 archived as lineage.
**Post-window engineering roadmap (arch-ordered, task-13 roadmap chapter)**: ① span context gate (doc-contextualized span validity — NOT subordination; 9% TP load-bearing proven; doc-quiet spans → "pending-context" intermediate state + context classifier) ② OOD head repair (learned discriminator w/ mirror supervision — principled first choice; or robust stats patch; gains computed on the 1.00x baseline) ③ span-only demotion re-eval AFTER OOD head repair ④ lawful-hard coverage deepening (T1-G3 3.3x calib path) ⑤ recipe stabilization (basin-lottery structural root: 17.7k T1-neg balance × head lr).
**Macro arc (all zero-FP)**: v1-2 0.681 → v1-3 0.818 → v2 0.866 → v2.4 0.910 → **v2.4-dt 0.935**.

## 1. Artifact menu (delivery judgment = arch's domain)

| artifact | readings (dev plane, zero-FP) | macro | state |
|---|---|---|---|
| m6-v2 (e2a758c) | T1 0.626/T2 0.900/T3 0.747/T4 0.792/T5 0.788/T6 0.948 (old plane) | 0.866 | committed; WARN+last lineage |
| m6-v2-4 (f7a580a) | T1 0.899/T2 0.948/T3 0.911/T4 0.797/T5 0.948/T6 0.956 | 0.910 | committed; single-trunk composite |
| **m6-v2-4dt (19eaaba)** | T1 0.899/T2 0.948/T3 0.911/**T4 0.949**/T5 0.948/T6 0.956 | **0.935** | committed; dual-trunk + span gate; **qa read object** |

All three verified: determinism (97f2860a for v2-4dt), contract 0 issues, 35-test suite green, adapter autoload.

## 2. Iteration chain (what happened and why)

1. **v2.1 (3 attempts)**: T1-fix robust 3/3, but T2 erosion (−11/−17/−26pp) and T6 death 3/3 at ep2 (all-high-risk saturation basin). Attempt-2 best artifact lost uncommitted → hard rule: commit at run end.
2. **v2.2 four-increment (arch 16:37)**: T1 0.747 ✓ + T4 0.949 ✓ delivered, but T2 0.453/T3 0.536/T5 0.776 casualties + T6 post-stage failed (my init choice: v2-init on drifted features = saturation trap; fresh inits are saturation-free by near-zero weights). **Joint path closed (arch 18:4x): 4/5 runs hit the ep2 all-benign basin.**
3. **Branch A (v2.2 trunk + fresh heads)**: NEGATIVE — T2 0.735/T3 0.683/T5 0.876/T6 0.0. **Representational damage confirmed**: the T1-neg flood reshaped the trunk; T1/T4 separability was bought with the others'.
4. **Branch B (v2 trunk + fresh heads + current data)**: T1 0.949/T3 0.901/T4 0.949 (with own trunk-MLP) but T2 0.868/T5 0.928 below v2's own heads; **T6 unfixable by fresh heads** (microscopic degenerate regime: benign lp ≈ −1e-7 at fp32 ceiling; only v2's exact trunk+head pair orders positives above the worst benign).
5. **v2.4 composite**: v2 full probe + fresh T1/T3 on the FROZEN v2 trunk-MLP. T4doc retrain on v2 trunk failed (0.45 — t4-lawful info not linearly present) → T4 kept v2's head.
6. **v2.4-dt (dual-trunk, arch 19:5x)**: routing {T4doc→trunkB}; trunkB = branch-B's trunk-MLP+T4doc pairing (same v2-adapter backbone, single forward preserved). T4 0.797→0.949.
7. **Span length gate (arch 20:0x)**: min_span_len=2 decode-side, config-exposed. Kills 161/1,166 dev span-FPs (13.8%); residual = real spans on lawfully-benign rows (context-blind extraction).
8. **Subordination NO-GO (arch 20:2x, data-decided)**: heldout gold join → 27/300 T4-pos TPs (9.0%) ride span-only flags (G1 would break the 95 floor) AND heldout G2 span-share only 2.3% (no G2 win either). **Span channel is load-bearing.**

## 3. Mechanism findings (reusable engineering conclusions)

- **F-1 头级投递保基质 (head-of-cycle's top finding, arch §2c)**: T1's active ingredient was supervision data, not representational reshaping — the joint runs paid representational cost (T2/T3/T5/T6 separability) for what a head-level retrain on the frozen healthy trunk bought for free (T1 0.899, τ 8.5, zero saturation).
- **F-2 init healthiness is feature-relative**: a "healthy" head init saturates on a shifted feature distribution; fresh (near-zero) inits are saturation-free on any features. Head-only zero-death history explained.
- **F-3 T6 pairing is a functional unit**: the microscopic degenerate regime on the v2 trunk admits exactly one working (trunk-MLP + head) ordering; grafting/fresh-retraining breaks it. Keep T6 pairs intact.
- **F-4 OOD three-layer dependency (arch framework, empirically verified 474168c)**: trunk (geometry) / calibration plane (centers+tau placement) / eval plane (readings). tau_ood moved 4944→3369 purely by plane recalibration (trunk unchanged); OOD telemetry is fully head-independent (identical to the decimal across head swaps).
- **F-5 G4 dual-vector**: G4 failure = is_ood collapse (4.6% vs v1-3 9.2%) × span strong-band bypass (310/500 ≈ 98% of OOD-suite T4 flags). Post-window: OOD head (b/c) AND span contextualization, both.
- **F-6 span channel structural tension (three planes)**: dev TP:FP 1:30 / heldout 9% TP load-bearing + 2.3% benign FP share / OOD 62% default-pass violation vector. Context-blind token extraction carries real detections the doc head cannot see (defense-in-depth empirical) while producing lawful-context FPs it cannot avoid.
- **F-7 D-16 family (measurement-domain)**: all per-epoch guards + calibrates in LOGIT/log-P space (fp32 sigmoid ties at logit > ~16.6 are artifacts); least-bad fallback never ships a collapsed epoch; T6 guard in fp64 log-P.
- **F-8 training non-determinism**: bf16/cuDNN on RTX 5090 diverges mid-run under fixed seed — every retrain is a fresh draw over degenerate basins. Deterministic post-processing (assembly/head-retrain on frozen features) is the stable alternative.

## 4. Reproduction pointers

- Artifacts: `checkpoints/{m6-v2, m6-v2-4, m6-v2-4dt}` (v2-4dt build manifest in-artifact: sources f7a580a + 89cd266, routing, gate increment, ood=trunkA).
- Tools: `scripts/_tmp_v24.py` (composite), `_tmp_v24dt.py` (dual-trunk), `_tmp_t4decomp.py` (FP source), `_tmp_gaterisk.py` (gate recall check), `_tmp_subord_final.py` (gold join count), `_tmp_g4diag.py` (OOD 3-item), `_tmp_v21_pkg.py` (telemetry package).
- Reports: `reports/m6/{v24-telemetry.json, t4-fp-source-decomposition.json, span-subordination-counts.json, span-subord-final-count.json, dual-trunk-design-sketch.md}`.
- Configs: `configs/m6-v2-4.yaml`, `m6-v2-4dt.yaml` (span_gate.min_len: 2).
- Ethanol: thresholds calibrated ONLY on dev (current plane); heldout read-only (counting joins only, arch-ordered, no calibration use); data/heldout never in training.

## 5. Known limitations (delivery-relevant)

- T4 G2/G3: span-driven residual FPs (1,005 dev rows post-gate; heldout benign span-share 2.3%) — context gate is post-window.
- G4: 4.6% is_ood (vs v1-3 9.2%) + span bypass — dual-vector, post-window.
- T4 dev recall 0.949 rides trunkB (branch-B ep3-least-bad selection); its G1 acceptance-plane verification is in qa's current read.
- v2.4/v2.4-dt T1 0.899/T3 0.911 are dev-plane zero-FP readings; acceptance-plane numbers pending qa.
