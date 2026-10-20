# -*- coding: utf-8 -*-
"""upload_ckpts_hf.py — 重要 checkpoints 上传 HuggingFace（owner 指令 2026-10-20 08:13）。

纪律：
- token 仅经环境变量 HF_TOKEN 传入（不入库、不入任何 repo 文件；会话中已出现，建议 owner 事后轮换）
- 上传为网络型任务，零 GPU 占用，与门禁链并行安全
- 顺序：adapters（小件验证管道）→ 0.6B 最优臂 → 8B merged（r9 优先）
- 失败重试 3 次；每仓 README 模型卡（谱系/门禁读数）
用法：$env:HF_TOKEN='...'; python upload_ckpts_hf.py <stage>
  stage = adapters | small6b | r9 | r8 | r7 | all_small
"""
import os, sys, time, json
from pathlib import Path

ROOT = Path(r"J:\Projects\llm_for_sec")
TOK = os.environ.get("HF_TOKEN")
if not TOK:
    print("NO-TOKEN"); sys.exit(2)

from huggingface_hub import HfApi
api = HfApi(token=TOK)
USER = "howwhenRaw"

READMES = {
    "adapters": "# llm-for-sec adapters\n\nLoRA adapters for the security-aware LLM mission (decoder-only lineage).\n\n- `qwen3-8b-sec-m5a-dpo-r7` (rank16, Base control arm) — W 0/4: ASR 80.36 / jb 75.00 / contract 0/168\n- `qwen3-8b-sec-m5a-dpo-r8` (rank16, aligned bare) — X 0/4: ASR 78.57 / ORR 10.00 / jb 77.50 / contract 0/168\n- `qwen3-8b-sec-m5a-dpo-r9` (rank64, three-lever: capacity+dose+adversarial-form pairs+amb half-dose, 600 steps)\n\nBase model for r7: Qwen/Qwen3-8B-Base. Base for r8/r9: Qwen/Qwen3-8B (aligned).\nTraining configs in `configs/` of the source repo. Gate instruments frozen (sha-verified).",
    "small6b_r5": "# llm-for-sec 0.6B m5a-r5\n\nBest 0.6B arm of the security-aware LLM mission: five-conjunction 3/5 (ASR 2.98 / ORR 13.65 / jb 28.75 / contract 166/168 / dilution 31.6).\nRetained as the human-review scanner; superseded on the main line by the 8B lineage (r9+).",
    "small6b_soup": "# llm-for-sec soup-needlefix-a050\n\n0.6B lineage starting point / evaluation baseline (soup variant).",
    "r9": "# qwen3-8b-sec-m5a-dpo-r9 (merged)\n\n8B three-lever arm: LoRA rank64 + dose 600 steps (23.7% consumption, 2x r8) + 576 adversarial-form pairs + amb half-dose.\nY-gates frozen: Y1 ORR<=10 / Y2 ASR<=40 / Y3 jb<=60 / Y4 contract>=100/168.\nBase: Qwen/Qwen3-8B (aligned). Merge sha registered in the chain log.",
    "r8": "# qwen3-8b-sec-m5a-dpo-r8 (merged)\n\n8B aligned-bare arm: X 0/4 (ASR 78.57 / ORR 10.00 / jb 77.50 / contract 0/168 / dilution 31.94).\nTwo-ingredient decomposition: precise discrimination acquired, OOD risk coverage missing.\nBase: Qwen/Qwen3-8B (aligned).",
    "r7": "# qwen3-8b-sec-m5a-dpo-r7 (merged)\n\n8B Base control arm: W 0/4 (ASR 80.36 / jb 75.00 / ORR 2.22 vacuous / contract 0/168).\nThree isolation findings: raw base has no refusal prior; M4 prelude carried dual priors; F5 teaches content-choice not attack-refusal.\nBase: Qwen/Qwen3-8B-Base.",
}

ADAPTER_DIRS = [
    ("qwen3-8b-sec-m5a-dpo-r7", ROOT / "checkpoints/qwen3-8b-sec-m5a-dpo-r7"),
    ("qwen3-8b-sec-m5a-dpo-r8", ROOT / "checkpoints/qwen3-8b-sec-m5a-dpo-r8"),
    ("qwen3-8b-sec-m5a-dpo-r9", ROOT / "checkpoints/qwen3-8b-sec-m5a-dpo-r9"),
]
CONFIG_FILES = [
    ROOT / "configs/m5a-dpo-r7.yaml", ROOT / "configs/m5a-dpo-r8.yaml", ROOT / "configs/m5a-dpo-r9.yaml",
    ROOT / "configs/m5a-dpo-r7-export.yaml", ROOT / "configs/m5a-dpo-r8-export.yaml", ROOT / "configs/m5a-dpo-r9-export.yaml",
]

def upsert_repo(repo_id, repo_type="model", private=True):
    try:
        api.create_repo(repo_id, repo_type=repo_type, private=private, exist_ok=True)
        print(f"[repo] {repo_id} ready (private={private})")
    except Exception as e:
        print(f"[repo] {repo_id} create/verify: {e}")

def upload_with_retry(repo_id, folder, allow_patterns=None, ignore_patterns=None):
    for attempt in range(3):
        try:
            t0 = time.time()
            api.upload_large_folder(
                repo_id=repo_id, folder_path=str(folder), repo_type="model",
                allow_patterns=allow_patterns, ignore_patterns=ignore_patterns,
            )
            dt = time.time() - t0
            print(f"[upload] {repo_id} <- {folder.name} OK in {dt/60:.1f} min")
            return True
        except Exception as e:
            print(f"[upload] {repo_id} attempt {attempt+1} FAIL: {type(e).__name__}: {str(e)[:200]}")
            time.sleep(20)
    return False

def stage_adapters():
    repo = f"{USER}/llm-for-sec-adapters"
    upsert_repo(repo)
    # 各 adapter 子目录上传（upload_large_folder 不支持多源；逐个 upload_folder 到子路径）
    from huggingface_hub import upload_folder
    for name, d in ADAPTER_DIRS:
        if not d.is_dir():
            print(f"[skip] {d} not found"); continue
        # 仅 adapter 文件（排除 checkpoint-* 中间档与优化器状态）
        for attempt in range(3):
            try:
                api.upload_folder(repo_id=repo, folder_path=str(d), path_in_repo=name,
                                  allow_patterns=["*.json", "*.safetensors", "*.txt"],
                                  ignore_patterns=["checkpoint-*", "optimizer*", "runs", "*.bin", "README.md"], repo_type="model")
                print(f"[adapter] {name} OK"); break
            except Exception as e:
                print(f"[adapter] {name} attempt {attempt+1} FAIL: {str(e)[:160]}"); time.sleep(15)
    # configs 顶层
    api.upload_folder(repo_id=repo, folder_path=str(ROOT / "configs"), path_in_repo="configs",
                      allow_patterns=["m5a-dpo-r7*.yaml", "m5a-dpo-r8*.yaml", "m5a-dpo-r9*.yaml"], repo_type="model")
    api.upload_file(path_or_fileobj=READMES["adapters"].encode(), path_in_repo="README.md", repo_id=repo, repo_type="model")
    print("[stage] adapters DONE")

def stage_model(key, repo_suffix, local_dir, private=True):
    repo = f"{USER}/{repo_suffix}"
    upsert_repo(repo, private=private)
    ok = upload_with_retry(repo, local_dir, ignore_patterns=["checkpoint-*", "optimizer*", "runs", "*.bin", "README.md", "*.png"])
    if ok:
        try:
            api.upload_file(path_or_fileobj=READMES[key].encode(), path_in_repo="README.md", repo_id=repo, repo_type="model")
        except Exception as e:
            print(f"[readme] {repo}: {str(e)[:120]}")
    return ok

if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "adapters"
    if stage == "adapters":
        stage_adapters()
    elif stage == "small6b":
        stage_model("small6b_r5", "llm-for-sec-0p6b-m5a-r5", ROOT / "checkpoints/qwen3-06b-sec-m5a-dpo-r5")
    elif stage == "soup":
        stage_model("small6b_soup", "llm-for-sec-0p6b-soup-needlefix-a050", ROOT / "checkpoints/soup-needlefix-a050")
    elif stage == "r9":
        stage_model("r9", "qwen3-8b-sec-m5a-dpo-r9-merged", ROOT / "checkpoints/qwen3-8b-sec-m5a-dpo-r9-merged")
    elif stage == "r8":
        stage_model("r8", "qwen3-8b-sec-m5a-dpo-r8-merged", ROOT / "checkpoints/qwen3-8b-sec-m5a-dpo-r8-merged")
    elif stage == "r7":
        stage_model("r7", "qwen3-8b-sec-m5a-dpo-r7-merged", ROOT / "checkpoints/qwen3-8b-sec-m5a-dpo-r7-merged")
    else:
        print("unknown stage"); sys.exit(1)
    print("STAGE-COMPLETE:", stage)
