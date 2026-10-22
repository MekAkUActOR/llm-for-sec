# Dual-Trunk Design Sketch (T4 residual lever)

**Status**: design only — NOT implemented (arch 19:1x ruling: sketch in
parallel with qa's G2/G3 readings; decision on readings).
**Author**: deveng-m6 · 2026-10-22 19:1x
**Trigger**: v2.4's T4 = 0.797 (v2 head, hardened plane) vs branch-B's
T4doc = 0.949 — the t4-lawful information is not linearly present in v2's
1024-d trunk-MLP projection but IS in branch-B's retrained one.

## 1. Core idea

One backbone forward (v2 adapter, mission requirement intact) → pooled
10240-d features → **two trunk-MLPs**, each serving its head-set:

| path | trunk | heads | source of weights |
|---|---|---|---|
| A | v2 trunk-MLP | T1 (v2.4 fresh) / T2 (v2) / T3 (v2.4 fresh) / T5 (v2) / T6 (v2 pair, untouched) | checkpoints/m6-v2-4 |
| B | branch-B trunk-MLP | T4doc (branch-B fresh) | checkpoints/m6-v2-3b |

BIO head: **unchanged** — it consumes per-token features (L12+L28, 2048-d)
directly (`forward_bio`, trunk-independent), keeps v2.4's current BIO head.

**Critical feasibility fact** (verified in code, m6_train.py L353-362):
both trunks consume the SAME pooled features from the SAME v2-adapter
backbone. Branch-B's trunk-MLP was trained on v2-adapter features (not
v2.2's) — so no second backbone forward is needed. A hypothetical trunk
trained on the v2.2 adapter would NOT be loadable under single-forward
(mission violation) — out of scope by construction.

## 2. Modification surface

**M6Probe class** (scripts/m6_train.py):
- optional `trunk_b` (same arch as trunk) + `routing: {head: "A"|"B"}`
  (default all-A → single-trunk artifacts load unchanged, backward compat)
- `forward(x)`: `hA = trunk(x); hB = trunk_b(x) if present`; route each
  head to its trunk output
- OOD/Mahalanobis: **stays on trunk-A** (v2.4's centers are v2-trunk
  geometry; G4 dissociation finding — OOD rides the unchanged trunk)

**Checkpoint layout**:
- Option 1 (preferred): keep ONE probe-heads.pt with the dual state_dict
  (trunk + trunk_b + heads + bio) + `head_structure.json` gains a
  `head_trunk_routing` field. Loader: if routing absent → single-trunk.
- Option 2: two probe files + manifest — rejected (more moving parts,
  atomicity worse).

**m6_infer** (scripts/m6_infer.py):
- model construction: `M6Probe(in_dim, routing=...)` from
  head_structure.json (auto-detected) — ~10 lines
- forward path: zero changes (routing internal to forward())
- SCHEMA_VERSION: bump 0.3.3 → 0.3.4 ONLY if we expose per-task trunk id
  in the response (NOT needed for the contract — scores/logits unchanged);
  recommend NO bump: wire format unchanged.

**Calibration**: per-task on routed logits — calibrate() already iterates
tasks on model outputs; zero changes. The T4 thresholds calibrate on
trunk-B's T4doc logits over the same dev pool.

**Training/assembly**: the v2.4 surgical script pattern (freeze trunks,
retrain routed heads) generalizes: `_tmp_v24.py` with per-head trunk
selection. The dual artifact assembles from existing committed
checkpoints (v2-4 + v2-3b) — no new training required for T4=0.949.

**sysdesign**: head_structure.json schema absorbs `head_trunk_routing`
(schema v0.3.25-scale minor).

**qa harness**: zero changes (wire format unchanged).

## 3. Latency & memory cost

- trunk-MLP = Linear(10240→1024) + LN + GELU + Linear(1024→1024) ≈ 11.6M
  params ≈ 23 MFLOPs per row
- added per-row: **+23 MFLOPs ≈ 0.3-1 ms on RTX 5090** — vs current
  ~35-108 ms/row (backbone-forward dominated) = **<1-3% latency**
- memory: +44 MB fp32 weights — negligible vs 24 GB budget
- feat_cache: **unchanged** (backbone-level, trunk-agnostic)

## 4. Expected readings (if assembled)

T1 0.899 / T2 0.948 / T3 0.911 / **T4 0.949** / T5 0.948 / T6 0.956
→ macro ≈ **0.935** (vs v2.4's 0.910). T4's G2/G3 gates ride the doc-head
0.949 + the hardened-pool calibration; BIO span gates unchanged from
v2.4 (span thresholds already calibrated on the lawful-pii mirror pool).

## 5. Risks

- R1: branch-B's trunk-MLP was selected as ep3-least-bad for ALL its
  heads — its T4doc (0.949 at guard-boundary; 0.949 at final calibrate)
  is proven, but its interaction with v2.4's T2/T5/T6 heads is nil (they
  stay on trunk-A) → **no cross-talk risk by construction** (routed).
- R2: two trunks = two calibration planes for the guard — the per-epoch
  guard semantics for a dual model need a routing-aware pass if we ever
  RE-TRAIN it jointly (not needed for assembly-only).
- R3: artifact provenance complexity — two source checkpoints; mitigate
  with a build manifest inside the artifact (assembly log listing source
  runpoints per head/trunk; the v2.4 commit message pattern suffices).

## 6. Decision rule (arch's, restated)

qa's G2/G3 on v2.4: hardened-pool calibration pulls T4 FPR inside the
gates → **no action** (single-trunk ships). Still far → dual-trunk enters
design review with this sketch as the base; assembly ≈ 1h including
verification (no training).
