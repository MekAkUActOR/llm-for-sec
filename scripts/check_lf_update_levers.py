# -*- coding: utf-8 -*-
"""查 LLaMA-Factory 可用的"受限更新"开关（层冻结 / LoRA），为配方②备料。"""
import inspect

from llamafactory.hparams import FinetuningArguments

params = inspect.signature(FinetuningArguments.__init__).parameters
print("FinetuningArguments 字段（按字母）:")
for k in sorted(params):
    if k in ("self", "args"):
        continue
    ann = params[k].annotation
    print(f"  {k:34} {getattr(ann, '__name__', ann)}")

print("\n与冻结/LoRA/层选择相关的候选:")
for k in sorted(params):
    if any(t in k.lower() for t in ("freeze", "lora", "layer", "module", "adapter",
                                    "target", "rank", "alpha", "dropout")):
        print(f"  {k}")
