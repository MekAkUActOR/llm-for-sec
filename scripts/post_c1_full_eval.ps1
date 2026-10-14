# C1-full 训练完成后自动评估链（探针 v0.1.1 净化版）：
#   1. 等待训练结束（train_results.json 落盘——勿用 trainer_log 的 train_loss 判据）
#   2. base 全探针 PPL（v0.1.1 已有 ppl-base-v0.1.1.json，若存在则跳过）
#   3. c1-full checkpoint 全探针 PPL
#   4. 域门禁对比（sec 降>=25%, 通用回升<=10%）
#   5. heldout 复评
#   6. 长上下文 16k/32k PPL + needle + 32k 门禁
$ErrorActionPreference = 'Continue'
$py = 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe'
$ckpt = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-c1-full'
$base = 'J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd'
$probes = 'data/probes/v0.1.1'
$env:HF_HOME = 'J:\Projects\llm_for_sec\.cache\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'J:\Projects\llm_for_sec'

# --- 1. 等待训练完成 ---
$done = Join-Path $ckpt 'train_results.json'
Write-Host "[post-eval] waiting for training to finish..."
while (-not (Test-Path $done)) {
    Start-Sleep -Seconds 300
}
Start-Sleep -Seconds 120  # 等最终文件落盘
Write-Host "[post-eval] training done, starting evals"

# --- 2. base PPL（v0.1.1 已有则复用）---
if (-not (Test-Path 'reports\ppl-base-v0.1.1.json')) {
    & $py scripts\probe_ppl.py --model $base --name base-v0.1.1 --probes $probes --out reports\ppl-base-v0.1.1.json 2>&1
}
# --- 3. c1-full PPL ---
& $py scripts\probe_ppl.py --model $ckpt --name c1-full-v0.1.1 --probes $probes --out reports\ppl-c1-full-v0.1.1.json 2>&1
# --- 4. 域门禁对比 ---
& $py scripts\compare_ppl.py reports\ppl-base-v0.1.1.json reports\ppl-c1-full-v0.1.1.json 2>&1 | Tee-Object -FilePath reports\ppl-compare-c1-full.txt
# --- 5. heldout 复评 ---
& $py scripts\baseline_eval.py --model $ckpt --heldout data\heldout\v0.1 --out reports\heldout-c1-full.json 2>&1
# --- 6. 长上下文 ---
& $py scripts\probe_longctx.py --model $base --name base 2>&1
& $py scripts\probe_longctx.py --model $ckpt --name c1-full 2>&1
& $py scripts\probe_longctx.py --compare reports\longctx-base.json reports\longctx-c1-full.json 2>&1 | Tee-Object -FilePath reports\longctx-compare-c1-full.txt
Write-Host "[post-eval] ALL DONE"
