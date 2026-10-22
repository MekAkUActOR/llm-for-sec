# -*- coding: utf-8 -*-
"""v2.4-dt assembly (arch 19:5x order, design sketch 1b886bf).

Dual-trunk composite: trunkA (v2) serves T1/T2/T3/T5/T6 (T6 pair
untouched); trunkB (branch-B) serves T4doc (0.949 pairing). OOD stays on
trunkA. Sources (all committed):
  - checkpoints/m6-v2-4  : trunkA + T1/T3 fresh + T2/T5/T6 v2 heads + bio
  - checkpoints/m6-v2-3b : trunkB + branch-B's T4doc head
Assembly-only: no training. Writes checkpoints/m6-v2-4dt/probe-heads.pt +
head_structure.json (routing) + build manifest, then --recalibrate
computes thresholds (T4 on trunkB doc logits; OOD on trunkA).
"""
import json
import sys
from pathlib import Path

import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from m6_train import M6Probe  # noqa: E402

SRC_A = REPO / "checkpoints/m6-v2-4"
SRC_B = REPO / "checkpoints/m6-v2-3b"
OUT = REPO / "checkpoints/m6-v2-4dt"
OUT.mkdir(parents=True, exist_ok=True)
ROUTING = {"T4doc": "B"}

sdA = torch.load(SRC_A / "probe-heads.pt", map_location="cpu",
                 weights_only=False)["state"]
sdB = torch.load(SRC_B / "probe-heads.pt", map_location="cpu",
                 weights_only=False)["state"]

# build the dual model from A's structure + routing
structA = json.loads((SRC_A / "head_structure.json").read_text(encoding="utf-8"))
model = M6Probe(**{k: structA[k] for k in
                   ("in_dim", "trunk_hidden", "head_hidden", "dropout",
                    "n_bio", "tok_feat_dim", "bio_hidden")},
                routing=ROUTING)
model.load_state_dict(sdA, strict=False)  # trunk_b fresh-initialized here

# graft trunkB + branch-B's T4doc head
model.trunk_b.load_state_dict(
    {k[len("trunk."):]: v for k, v in sdB.items()
     if k.startswith("trunk.")})
model.heads["T4doc"].load_state_dict(
    {k[len("heads.T4doc."):]: v for k, v in sdB.items()
     if k.startswith("heads.T4doc.")})

# sanity: trunkA/T6 pair identical to v2.4 (must be untouched)
for k in ("trunk.", "heads.T1.", "heads.T2.", "heads.T3.", "heads.T5.",
          "heads.T6.", "bio."):
    for kk, v in sdA.items():
        if kk.startswith(k):
            assert torch.equal(model.state_dict()[kk], v), f"drift: {kk}"
print("graft OK: trunkB + T4doc(B) | trunkA/T1/T2/T3/T5/T6/bio unchanged")

torch.save({"state": model.state_dict()}, OUT / "probe-heads.pt")
(OUT / "head_structure.json").write_text(
    json.dumps(model.structure_json(), ensure_ascii=False, indent=1),
    encoding="utf-8")
manifest = {
    "artifact": "m6-v2-4dt",
    "pattern": "dual-trunk assembly (design sketch 1b886bf, arch 19:5x)",
    "routing": ROUTING,
    "sources": {
        "trunkA + T1/T2/T3/T5/T6 + bio": {
            "runpoint": "checkpoints/m6-v2-4",
            "commits": ["f7a580a"],
            "note": "v2 trunk-MLP (e2a758c lineage) + fresh T1/T3 + v2 "
                    "T2/T5/T6 heads; T6 microscopic-regime pair intact"},
        "trunkB + T4doc": {
            "runpoint": "checkpoints/m6-v2-3b",
            "commits": ["89cd266"],
            "note": "branch-B trunk-MLP + its fresh T4doc head (0.949 "
                    "pairing; trained on v2-adapter features 64,070)"},
    },
    "ood": "trunkA (G4 dissociation: OOD geometry rides the unchanged "
           "v2 trunk; head-independent, verified 474168c)",
    "training": "none (assembly-only)",
}
(OUT / "build_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"assembled -> {OUT/'probe-heads.pt'} + head_structure(routing) "
      f"+ build_manifest.json")
