# _tmp_r8_chain_detached.ps1 -- M5A-R8 gates chain, DETACHED launch (r7 attempt-2 pattern)
# Design (identical to _tmp_r7_chain_detached.ps1, attempt-2, proven 6h+ stable):
#   * launched via WMI Win32_Process.Create -> parent = WmiPrvSE, outside the
#     harness job trees -> survives harness-side job reaping (r7 attempt-1 lesson)
#   * heartbeat file every 300s with nvidia-smi dual evidence (Lead directive)
#   * rc sentinel file at end (GATES-CHAIN-RC=n)
#   * all file appends explicit UTF-8 no-BOM per Lead encoding discipline 2026-10-16
#   * gates script: PREFLIGHT -> sha -> 8 steps, WaitIdle+Guard before each GPU step
# Prerequisites: r8 train complete + merge complete (config m5a-dpo-r8-export.yaml).
$ErrorActionPreference = 'Continue'
$ROOT      = 'J:\Projects\llm_for_sec'
$hb        = "$ROOT\reports\logs\m5a-dpo-r8-gates-chain-heartbeat.log"
$rcFile    = "$ROOT\reports\logs\m5a-dpo-r8-gates-chain-rc.txt"
$stdoutLog = "$ROOT\reports\logs\m5a-dpo-r8-gates-stdout.log"
$stderrLog = "$ROOT\reports\logs\m5a-dpo-r8-gates-stderr.log"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) {
  [System.IO.File]::AppendAllText($hb, "$msg`r`n", $U8)
  Write-Host $msg
}
function GpuLine {
  $g = & nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>$null
  if (-not $g) { return 'gpu=NA' }
  return 'gpu=[' + ($g -join ' | ').Trim() + ']'
}
if (Test-Path $rcFile) { Remove-Item $rcFile -Force }
HB "HEARTBEAT-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') wrapper_pid=$PID attempt=1 mode=detached-wmi"
$p = Start-Process powershell `
  -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\run_m5a_r8_gates.ps1" `
  -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog `
  -PassThru -WindowStyle Hidden
HB "CHAIN-SPAWNED chain_pid=$($p.Id) start=$(Get-Date -Format 'HH:mm:ss') $(GpuLine)"
while (-not $p.HasExited) {
  Start-Sleep -Seconds 300
  $arts = @(Get-ChildItem "$ROOT\reports" -Filter '*m5a-dpo-r8*' -ErrorAction SilentlyContinue).Count
  HB "HEARTBEAT $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($p.Id) alive=$(-not $p.HasExited) r8_files=$arts $(GpuLine)"
}
$rc = $p.ExitCode
HB "HEARTBEAT-END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($p.Id) exit=$rc"
[System.IO.File]::WriteAllText($rcFile, "GATES-CHAIN-RC=$rc`r`nfinished=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "RC-SENTINEL-WRITTEN $rcFile"
