# post_m16_eval.ps1 — M1.6 长上下文恢复跑训后评估链
# [2026-09-28] 8k 段死于 WDDM 死亡螺旋（无 checkpoint）——方案合并为补丁版
# 单段 32k 直跑（qwen3-06b-sec-m16-32k），本链路径同步更新。
# 判据：train_results.json 出现（勿用 trainer_log 的 train_loss——历史教训）
# 评估：16k/32k PPL + needle 三方对照（base / c1-full / m16-32k）
# 门禁：32k PPL 相对 base 回升 <=10%（C1-full 是 +11.0%/+13.1%）+
#       needle 总数 >= 9/12（base 12/12，c1-full 7/12）

$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$ckpt = "$root\checkpoints\qwen3-06b-sec-m16-32k"
$done = Join-Path $ckpt 'train_results.json'
$base = "$root\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd"

Write-Host "[m16-eval] waiting for training to finish..."
while (-not (Test-Path $done)) {
    Start-Sleep -Seconds 300
}
Start-Sleep -Seconds 120  # wait for final file writes

Set-Location $root
if (-not (Test-Path 'reports\longctx-base.json')) {
    & $py scripts\probe_longctx.py --model $base --name base 2>&1
}
if (Test-Path 'reports\longctx-c1-full.json') {
    & $py scripts\probe_longctx.py --model $ckpt --name m16 2>&1
    & $py scripts\probe_longctx.py --compare reports\longctx-base.json reports\longctx-c1-full.json reports\longctx-m16.json 2>&1 |
        Tee-Object -FilePath reports\longctx-compare-m16.txt
} else {
    & $py scripts\probe_longctx.py --model $ckpt --name m16 2>&1
    & $py scripts\probe_longctx.py --compare reports\longctx-base.json reports\longctx-m16.json 2>&1 |
        Tee-Object -FilePath reports\longctx-compare-m16.txt
}
Write-Host "[m16-eval] done. Gate: 32k PPL vs base <= +10%; needles >= 9/12."
