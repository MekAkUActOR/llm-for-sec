# _tmp_r9_train_detached.ps1 -- M5A-R9 LoRA-DPO training, DETACHED launch (r8 proven pattern)
# Prerequisites (GPU serial iron law): Guard PASS before launch (launcher's duty).
# r9 = three-lever round: rank64/alpha128, 1200 steps (47% consumption), r9 data mix.
# VRAM est ~24GB borderline (rank64, gradient checkpointing on); OOM -> report Lead
#   immediately (rank48 fallback requires Lead registration).
# Output: checkpoints\qwen3-8b-sec-m5a-dpo-r9 (+ checkpoint-50..1200)
# Log: reports\logs\m5a-dpo-r9-train.log ; rc sentinel: reports\logs\m5a-dpo-r9-train-rc.txt
# Heartbeat every 120s with nvidia-smi dual evidence; UTF-8 no-BOM appends; Handle pinned.
$ErrorActionPreference = 'Continue'
$ROOT   = 'J:\Projects\llm_for_sec'
$hb     = "$ROOT\reports\logs\m5a-dpo-r9-train-heartbeat.log"
$rcFile = "$ROOT\reports\logs\m5a-dpo-r9-train-rc.txt"
$log    = "$ROOT\reports\logs\m5a-dpo-r9-train.log"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) { [System.IO.File]::AppendAllText($hb, "$msg`r`n", $U8); Write-Host $msg }
function GpuLine {
  $g = & nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>$null
  if (-not $g) { return 'gpu=NA' }
  return 'gpu=[' + ($g -join ' | ').Trim() + ']'
}
if (Test-Path $rcFile) { Remove-Item $rcFile -Force }
HB "TRAIN-HEARTBEAT-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') wrapper_pid=$PID attempt=1"
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$proc = Start-Process "$ROOT\.venv\Scripts\llamafactory-cli.exe" `
  -ArgumentList 'train',"$ROOT\configs\m5a-dpo-r9.yaml" `
  -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
  -PassThru -WindowStyle Hidden
$null = $proc.Handle  # PS5.1 PassThru Handle pin (r7/r8 lesson: unpinned ExitCode reads empty)
HB "TRAIN-SPAWNED pid=$($proc.Id) start=$(Get-Date -Format 'HH:mm:ss') $(GpuLine)"
while (-not $proc.HasExited) {
  Start-Sleep -Seconds 120
  HB "TRAIN-HEARTBEAT $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') pid=$($proc.Id) alive=$(-not $proc.HasExited) $(GpuLine)"
}
$rc = $proc.ExitCode
HB "TRAIN-HEARTBEAT-END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') pid=$($proc.Id) exit=$rc"
[System.IO.File]::WriteAllText($rcFile, "TRAIN-RC=$rc`r`nfinished=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "TRAIN-RC-SENTINEL-WRITTEN $rcFile"
