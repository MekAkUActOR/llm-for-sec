# Stage 1 (202M) 训练完成后自动评估链：
#   1. 等待训练结束（trainer_log.jsonl 出现 train_loss 汇总行）
#   2. base 全探针 PPL -> reports/ppl-base.json
#   3. stage1 checkpoint 全探针 PPL -> reports/ppl-stage1-202m.json
#   4. 门禁对比（sec 降>=25%, 通用回升<=10%）-> reports/ppl-compare-stage1-202m.txt
#   5. heldout 复评 -> reports/heldout-stage1-202m.json
$ErrorActionPreference = 'Continue'
$py = 'J:\Projects\llm_for_sec\.venv\Scripts\python.exe'
$ckpt = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-stage1-202m'
$base = 'J:\Projects\llm_for_sec\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd'
$env:HF_HOME = 'J:\Projects\llm_for_sec\.cache\huggingface'
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location 'J:\Projects\llm_for_sec'

# --- 1. 等待训练完成 ---
# 完成标志 = train_results.json 落盘（trainer_log.jsonl 不含 train_loss 行——勿用错误判据）
$done = Join-Path $ckpt 'train_results.json'
Write-Host "[post-eval] waiting for training to finish..."
while (-not (Test-Path $done)) {
    Start-Sleep -Seconds 300
}
Start-Sleep -Seconds 120  # 等最终文件落盘
Write-Host "[post-eval] training done, starting evals"

# --- 2. base PPL ---
& $py scripts\probe_ppl.py --model $base --name base --out reports\ppl-base.json 2>&1
# --- 3. stage1 PPL ---
& $py scripts\probe_ppl.py --model $ckpt --name stage1-202m --out reports\ppl-stage1-202m.json 2>&1
# --- 4. 门禁对比 ---
& $py scripts\compare_ppl.py reports\ppl-base.json reports\ppl-stage1-202m.json 2>&1 | Tee-Object -FilePath reports\ppl-compare-stage1-202m.txt
# --- 5. heldout 复评 ---
& $py scripts\baseline_eval.py --model $ckpt --heldout data\heldout\v0.1 --out reports\heldout-stage1-202m.json 2>&1
# --- 6. 长上下文探针（16k/32k 整段 PPL + needle，docs/05 §7 第三项） ---
& $py scripts\probe_longctx.py --model $base --name base 2>&1
& $py scripts\probe_longctx.py --model $ckpt --name stage1-202m 2>&1
& $py scripts\probe_longctx.py --compare reports\longctx-base.json reports\longctx-stage1-202m.json 2>&1 | Tee-Object -FilePath reports\longctx-compare-stage1-202m.txt
Write-Host "[post-eval] ALL DONE"
