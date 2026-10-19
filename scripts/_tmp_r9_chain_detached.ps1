# _tmp_r9_chain_detached.ps1 -- M5A-R9 gates chain, DETACHED launch (r8 proven pattern)
# Launches: scripts\run_m5a_r9_gates.ps1 (8 steps, X-front order: v023->gen->jb->ppl->toolout->longctx->verdict->dilution)
# Stdout/stderr -> m5a-dpo-r9-gates-stdout.log / .err
# Heartbeat every 300s with r9 artifact count + GPU evidence; rc sentinel (Handle pinned).
# Chain log (with merge sha header) is written separately by the orchestrator:
#   reports\logs\m5a-dpo-r9-gates-chain.log
$ErrorActionPreference = 'Continue'
$ROOT = 'J:\Projects\llm_for_sec'
$hb     = "$ROOT\reports\logs\m5a-dpo-r9-gates-chain-heartbeat.log"
$rcFile = "$ROOT\reports\logs\m5a-dpo-r9-gates-chain-rc.txt"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) { [System.IO.File]::AppendAllText($hb, "$msg`r`n", $U8); Write-Host $msg }
function GpuLine {
  $g = & nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>$null
  if (-not $g) { return 'gpu=NA' }
  return 'gpu=[' + ($g -join ' | ').Trim() + ']'
}
if (Test-Path $rcFile) { Remove-Item $rcFile -Force }
HB "HEARTBEAT-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') wrapper_pid=$PID attempt=1 mode=detached-wmi"
Set-Location $ROOT
$proc = Start-Process powershell.exe `
  -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\run_m5a_r9_gates.ps1" `
  -RedirectStandardOutput "$ROOT\reports\logs\m5a-dpo-r9-gates-stdout.log" `
  -RedirectStandardError "$ROOT\reports\logs\m5a-dpo-r9-gates-stderr.log" `
  -PassThru -WindowStyle Hidden
$null = $proc.Handle  # PS5.1 PassThru Handle pin (r7/r8 lesson)
HB "CHAIN-SPAWNED chain_pid=$($proc.Id) start=$(Get-Date -Format 'HH:mm:ss') $(GpuLine)"
while (-not $proc.HasExited) {
  Start-Sleep -Seconds 300
  $files = @(Get-ChildItem "$ROOT\reports" -Filter "*m5a-dpo-r9*" -File -ErrorAction SilentlyContinue).Count
  HB "HEARTBEAT $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($proc.Id) alive=$(-not $proc.HasExited) r8->r9_files=$files $(GpuLine)"
}
$rc = $proc.ExitCode
HB "HEARTBEAT-END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($proc.Id) exit=$rc"
[System.IO.File]::WriteAllText($rcFile, "GATES-CHAIN-RC=$rc`r`nfinished=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "CHAIN-RC-SENTINEL-WRITTEN $rcFile"
