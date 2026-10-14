r"""SFT v0 → LLaMA-Factory 转换 + dataset_info 注册（M2 校准跑启动件）。

格式依据（LLaMA-Factory 0.9.6 源码，非猜测）：
- src/llamafactory/data/parser.py DatasetAttr：sharegpt 格式经 columns.messages
  映射消息列表、tags.* 映射角色标签；
- src/llamafactory/data/converter.py SharegptDatasetConverter：messages[0] 若为
  system_tag 则提取为 _system（进 template 的 system 槽位），其余按奇偶轮次
  校验 user/assistant 交替，末条 assistant 为 _response（训练目标）；
- 本转换保持生成侧中性格式 {"messages":[system,user,assistant]}，注册条目用
  tags 重映射 role/content/user/assistant/system —— 样例文件即直接可训练格式；
- template 用 qwen3_nothink（template.py：chatml 槽位、无 ReasoningTemplate 的
  think 机制——base 起步 + VERDICT 目标不引入思考块）。

转换时逐行硬校验（转换器即质检器）：
1. 三消息且角色为 system/user/assistant；
2. system 含政策引用（pack:<name>@0.1）；
3. assistant 末行 VERDICT 可被判分器 v2 严格模板层解析。

用法：python scripts/convert_sft_v0.py
    [--sft-dir data/sft/v0] [--out data/lf/sft_v0.jsonl]
    [--dataset-info data/lf/dataset_info.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from score_heldout_v2 import _extract_structured  # noqa: E402

SFT_DIR = ROOT / "data" / "sft" / "v0"
OUT = ROOT / "data" / "lf" / "sft_v0.jsonl"
DATASET_INFO = ROOT / "data" / "lf" / "dataset_info.json"
DATASET_NAME = "sec_sft_v0"

SOURCES = ("policy_pairs.jsonl", "injection_pairs.jsonl",
           "pii_synthetic.jsonl", "calibration.jsonl")

# 注册条目（sharegpt + tags 重映射；与 SharegptDatasetConverter 语义一一对应）
REGISTRATION = {
    "file_name": "sft_v0.jsonl",
    "formatting": "sharegpt",
    "columns": {"messages": "messages"},
    "tags": {"role_tag": "role", "content_tag": "content",
             "user_tag": "user", "assistant_tag": "assistant",
             "system_tag": "system"},
}


def validate_row(row: dict, src: str) -> dict:
    """行级硬校验：结构、政策引用、VERDICT 闭环。"""
    msgs = row.get("messages")
    assert isinstance(msgs, list) and len(msgs) == 3, f"{src}: 消息数≠3"
    roles = [m.get("role") for m in msgs]
    assert roles == ["system", "user", "assistant"], f"{src}: 角色 {roles}"
    assert "pack:" in msgs[0]["content"] and "@0.1" in msgs[0]["content"], (
        f"{src}: system 区缺政策引用")
    v = _extract_structured(msgs[2]["content"])
    assert v is not None, f"{src}: assistant VERDICT 不可解析"
    assert v["policy"] == row["pack"], f"{src}: policy 字段与 pack 不符"
    return {"id": row["id"], "task": row["task"], "pack": row["pack"],
            "lang": row["lang"], "messages": msgs}


def convert(sft_dir: Path = SFT_DIR, out: Path = OUT,
            dataset_info: Path = DATASET_INFO) -> dict:
    stats = {}
    total = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for name in SOURCES:
            n = 0
            with open(sft_dir / name, encoding="utf-8") as g:
                for i, line in enumerate(g):
                    if not line.strip():
                        continue
                    row = validate_row(json.loads(line), f"{name}:{i}")
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
            stats[name] = n
            total += n

    # dataset_info 注册（其余条目原样保留；红线：不动既有条目）
    info = json.loads(dataset_info.read_text(encoding="utf-8"))
    info[DATASET_NAME] = dict(REGISTRATION)
    dataset_info.write_text(json.dumps(info, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
    return {"sources": stats, "total": total, "out": str(out),
            "dataset_info": str(dataset_info), "name": DATASET_NAME}


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT v0 → LLaMA-Factory 转换")
    ap.add_argument("--sft-dir", default=str(SFT_DIR))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--dataset-info", default=str(DATASET_INFO))
    args = ap.parse_args(argv)
    res = convert(Path(args.sft_dir), Path(args.out), Path(args.dataset_info))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
