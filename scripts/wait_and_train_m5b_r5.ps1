# M5B-R5 训练发射器：等 GPU 空闲（m5a-r4 门禁链让出 / 数据轴 r5 若先占则等其让出并登记排队时长）
# → Guard + 重 worker=0 双确认 → 仪器/池 sha 复验 → PREFLIGHT NOT-EXIST → GRPO v5 训练
# 纪律（✗✓ GPU 严格串行，沿 wait_and_train_m5a_r4.ps1 同构）：
#   等待条件 = m5a-r4 链 verdict 产物落地，或（重 worker=0 且 m5a-dpo-r4 日志静默>15min 连续两次确认）防呆；
#   空闲后 45s 宽限再确认（防与数据轴 r5 发射竞态、防 m5a 链步间 CPU 间歇误判）；
#   发射前 Guard（判并发）+ 重 worker=0（判空闲）双确认。
$ROOT = 'J:\Projects\llm_for_sec'
Set-Location $ROOT
$t0 = Get-Date
$deadline = $t0.AddHours(4)
$exitReason = ''
while ($true) {
  if ((Get-Date) -gt $deadline) { $exitReason = 'WAIT-TIMEOUT-4H'; break }
  $v = Get-ChildItem "$ROOT\reports" -Filter 'topup-verdict-m5a-dpo-r4-*.json' -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($v) { $exitReason = "M5A-R4-CHAIN-DONE $($v.Name)"; break }
  $heavy = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
  $marecent = @(Get-ChildItem "$ROOT\reports\logs" -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'm5a-dpo-r4' -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-15) })
  if ($heavy.Count -eq 0 -and $marecent.Count -eq 0) {
    Start-Sleep -Seconds 45
    $heavy2 = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
    $marecent2 = @(Get-ChildItem "$ROOT\reports\logs" -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'm5a-dpo-r4' -and $_.LastWriteTime -gt (Get-Date).AddMinutes(-15) })
    if ($heavy2.Count -eq 0 -and $marecent2.Count -eq 0) { $exitReason = 'M5A-R4-CHAIN-QUIET (no heavy worker, m5a-r4 logs silent >15min, double-confirmed)'; break }
    continue
  }
  Start-Sleep -Seconds 30
}
$waitSec = [int]((Get-Date) - $t0).TotalSeconds
Write-Host "WAIT-DONE reason=$exitReason waited_s=$waitSec"
# ---- 45s 竞态宽限：让可能排队的数据轴 r5 先占；其若发射则本轮继续等 ----
$heavyG = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
if ($heavyG.Count -eq 0) {
  Start-Sleep -Seconds 45
  $heavyG2 = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
  if ($heavyG2.Count -gt 0) {
    Write-Host "RACE-GRACE: sibling grabbed GPU during 45s grace (heavy=$($heavyG2.Count)); yielding and re-waiting"
    while ($true) {
      if ((Get-Date) -gt $deadline) { Write-Host 'WAIT-TIMEOUT-4H after grace'; exit 3 }
      $h = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
      if ($h.Count -eq 0) { Start-Sleep -Seconds 30; $h2 = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB }); if ($h2.Count -eq 0) { break } } else { Start-Sleep -Seconds 30 }
    }
  }
}
$waitSec = [int]((Get-Date) - $t0).TotalSeconds
Write-Host "QUEUE-TOTAL waited_s=$waitSec"
# ---- Guard（判并发）----
& "$ROOT\scripts\stop_eval_procs.ps1" -Guard
if ($LASTEXITCODE -ne 0) { Write-Host 'GUARD=FAIL'; exit 1 }
# ---- 空闲确认（重 worker = 0，严于 Guard）----
$heavy3 = @(Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB })
if ($heavy3.Count -ne 0) { Write-Host "GPU-NOT-FREE heavy=$($heavy3.Count)"; exit 1 }
Write-Host 'GUARD=PASS heavy=0 GPU-free'
# ---- 仪器/池 sha 复验（fail-closed）----
& "$ROOT\.venv\Scripts\python.exe" -X utf8 "$ROOT\scripts\_tmp_m5b_r5_sha_check.py"
if ($LASTEXITCODE -ne 0) { Write-Host 'INSTRUMENT-SHA=FAIL'; exit 4 }
# ---- NOT-EXIST 预检（★必须显式 --output-dir：裸 --run 会自动续进 v1）----
if (Test-Path "$ROOT\checkpoints\qwen3-06b-sec-p2rl-grpo-v5") { Write-Host 'OUTPUT-DIR-EXISTS'; exit 2 }
Write-Host 'PREFLIGHT-NOT-EXIST=OK (checkpoints\qwen3-06b-sec-p2rl-grpo-v5)'
# ---- 发射（env 四变量显式，沿 r4 §五口径）----
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
& "$ROOT\.venv\Scripts\python.exe" -X utf8 "$ROOT\scripts\run_p2rl_grpo.py" --run --output-dir "J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-p2rl-grpo-v5" 2>&1 | Tee-Object -FilePath "$ROOT\reports\logs\m5b-grpo-train-r5.log"
$rc = $LASTEXITCODE
Write-Host "TRAIN-RC=$rc queue_waited_s=$waitSec"
exit $rc
