# _tmp_r7_chain_detached.ps1 -- M5A-R7 gates chain, DETACHED relaunch (attempt 2)
# Context: attempt 1 (harness background job pwsh-265, launched 02:07) was killed
# ~03:02-03:13 together with the whole r7-runner background-job family (including a
# pure sleep-only watcher) by an external process-tree reaping; no OS-level OOM/WER
# events, no python traceback -> hard external kill, not a model/instrument failure.
# Lead verdict pending -> launch only on explicit go (Plan R1).
# Design:
#   * launched via WMI Win32_Process.Create -> parent = WmiPrvSE, outside the
#     harness job tree -> survives harness-side job reaping
#   * heartbeat file every 300s (alive vs dead distinguishable without stdout)
#   * rc sentinel file at end (GATES-CHAIN-RC=n)
#   * all file appends explicit UTF-8 no-BOM per Lead encoding discipline 2026-10-16
#   * gates script itself unchanged (frozen flow: PREFLIGHT -> sha -> 8 steps,
#     WaitIdle+Guard before each GPU step)
$ErrorActionPreference = 'Continue'
$ROOT      = 'J:\Projects\llm_for_sec'
$hb        = "$ROOT\reports\logs\m5a-dpo-r7-gates-chain-heartbeat.log"
$rcFile    = "$ROOT\reports\logs\m5a-dpo-r7-gates-chain-rc.txt"
$stdoutLog = "$ROOT\reports\logs\m5a-dpo-r7-gates-stdout.log"
$stderrLog = "$ROOT\reports\logs\m5a-dpo-r7-gates-stderr.log"
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
HB "HEARTBEAT-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') wrapper_pid=$PID attempt=2 mode=detached-wmi"
$p = Start-Process powershell `
  -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',"$ROOT\scripts\run_m5a_r7_gates.ps1" `
  -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog `
  -PassThru -WindowStyle Hidden
HB "CHAIN-SPAWNED chain_pid=$($p.Id) start=$(Get-Date -Format 'HH:mm:ss') $(GpuLine)"
while (-not $p.HasExited) {
  Start-Sleep -Seconds 300
  $arts = @(Get-ChildItem "$ROOT\reports" -Filter '*m5a-dpo-r7*' -ErrorAction SilentlyContinue).Count
  HB "HEARTBEAT $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($p.Id) alive=$(-not $p.HasExited) r7_files=$arts $(GpuLine)"
}
$rc = $p.ExitCode
HB "HEARTBEAT-END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') chain_pid=$($p.Id) exit=$rc"
[System.IO.File]::WriteAllText($rcFile, "GATES-CHAIN-RC=$rc`r`nfinished=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "RC-SENTINEL-WRITTEN $rcFile"
