# M5A-R4 训练发射器：等 RL v4 门禁链结束 → Guard + 空闲确认 → NOT-EXIST → llamafactory 训练
# 纪律（✗✓ GPU 严格串行）：等待条件 = RL 链 verdict 产物落地，或（重 worker=0 且 v4 日志静默>15min
# 连续两次确认）防呆；发射前 Guard（判并发）+ 重 worker=0（判空闲）双确认。
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$t0 = Get-Date
$deadline = $t0.AddHours(4)
$exitReason = ''
while ($true) {
  if ((Get-Date) -gt $deadline) { $exitReason = 'WAIT-TIMEOUT-4H'; break }
  $v = Get-ChildItem "$ROOT\reports" -Filter 'topup-verdict-m5b-p2rl-grpo-v4-*.json' -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($v) { $exitReason = "RL-CHAIN-DONE $($v.Name)"; break }
  $heavy = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
  $v4recent = @(Get-ChildItem "$ROOT\reports\logs" -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'v4' -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-15) })
  if ($heavy.Count -eq 0 -and $v4recent.Count -eq 0) {
    Start-Sleep -Seconds 45
    $heavy2 = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
    $v4recent2 = @(Get-ChildItem "$ROOT\reports\logs" -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'v4' -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-15) })
    if ($heavy2.Count -eq 0 -and $v4recent2.Count -eq 0) { $exitReason = 'RL-CHAIN-QUIET (no heavy worker, v4 logs silent >15min, double-confirmed)'; break }
    continue
  }
  Start-Sleep -Seconds 30
}
$waitSec = [int]((Get-Date) - $t0).TotalSeconds
Write-Host "WAIT-DONE reason=$exitReason waited_s=$waitSec"
# ---- Guard（判并发）----
& "$ROOT\scripts\stop_eval_procs.ps1" -Guard
if ($LASTEXITCODE -ne 0) { Write-Host 'GUARD=FAIL'; exit 1 }
# ---- 空闲确认（重 worker = 0，严于 Guard）----
$heavy3 = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
if ($heavy3.Count -ne 0) { Write-Host "GPU-NOT-FREE heavy=$($heavy3.Count)"; exit 1 }
Write-Host 'GUARD=PASS heavy=0 GPU-free'
# ---- NOT-EXIST 预检 ----
if (Test-Path "$ROOT\checkpoints\qwen3-06b-sec-m5a-dpo-r4") { Write-Host 'OUTPUT-DIR-EXISTS'; exit 2 }
Write-Host 'PREFLIGHT-NOT-EXIST=OK'
# ---- 发射（env 四变量显式，照抄 r3 §五）----
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
& "$ROOT\.venv\Scripts\llamafactory-cli.exe" train "$ROOT\configs\m5a-dpo-r4.yaml" 2>&1 | Tee-Object -FilePath "$ROOT\reports\logs\m5a-dpo-r4-train.log"
$rc = $LASTEXITCODE
Write-Host "TRAIN-RC=$rc waited_s=$waitSec"
exit $rc
