# _tmp_r9_notmpl_chain_detached.ps1 -- M5A-R9-TMPL gates chain, DETACHED launch (r8/r9 proven pattern)
# Launches: scripts\run_m5a_r9_notmpl_gates.ps1 (3 steps: jb -> toolout -> gen; tag m5a-dpo-r9-notmpl)
# Stdout/stderr -> m5a-dpo-r9-notmpl-gates-stdout.log / .err
# Heartbeat every 300s with notmpl artifact count + GPU evidence; rc sentinel (Handle pinned).
$ErrorActionPreference = 'Continue'
$ROOT = 'J:\Projects\llm_for_sec'
$hb     = "$ROOT\reports\logs\m5a-dpo-r9-notmpl-gates-chain-heartbeat.log"
$rcFile = "$ROOT\reports\logs\m5a-dpo-r9-notmpl-gates-chain-rc.txt"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) { [System.IO.File]::AppendAllText($hb, "$msg`r`n", $U8); Write-Host $msg }
function GpuLine {
  $g = & nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>$null
  if (-not $g) { return 'gpu=NA' }
  return 'gpu=[' + ($g -join ' | ').Trim() + ']'
}
if (Test-Path $rcFile) { Remove-Item $rcFile -Force }
HB "HEARTBEAT-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') wrapper_pid=$PID attempt=1 mode=detached-wmi arm=r9-tmpl"
Set-Location $ROOT
$proc = Start-Process powershell.exe `
  -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\run_m5a_r9_notmpl_gates.ps1" `
  -RedirectStandardOutput "$ROOT\reports\logs\m5a-dpo-r9-notmpl-gates-stdout.log" `
  -RedirectStandardError "$ROOT\reports\logs\m5a-dpo-r9-notmpl-gates-stderr.log" `
  -PassThru -WindowStyle Hidden
$null = $proc.Handle  # PS5.1 PassThru Handle pin (r7/r8/r9 lesson)
HB "CHAIN-SPAWNED chain_pid=$($proc.Id) start=$(Get-Date -Format 'HH:mm:ss') $(GpuLine)"
while (-not $proc.HasExited) {
  Start-Sleep -Seconds 300
  $files = @(Get-ChildItem "$ROOT\reports" -Filter "*m5a-dpo-r9-notmpl*" -File -ErrorAction SilentlyContinue).Count
  HB "HEARTBEAT $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($proc.Id) alive=$(-not $proc.HasExited) notmpl_files=$files $(GpuLine)"
}
$rc = $proc.ExitCode
HB "HEARTBEAT-END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($proc.Id) exit=$rc"
[System.IO.File]::WriteAllText($rcFile, "GATES-CHAIN-RC=$rc`r`nfinished=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "CHAIN-RC-SENTINEL-WRITTEN $rcFile"
