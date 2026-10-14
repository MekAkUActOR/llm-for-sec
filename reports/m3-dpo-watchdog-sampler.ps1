# M3 DPO watchdog sampler (read-only). Appends one CSV row per interval.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File reports\m3-dpo-watchdog-sampler.ps1 -IntervalSec 60 -MaxMinutes 300
[CmdletBinding()]
param(
  [int]$IntervalSec = 60,
  [int]$MaxMinutes = 300
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$csv  = "$root\reports\m3-dpo-watchdog-telemetry.csv"
$raw  = "$root\reports\m3-dpo-watchdog-sampler.log"
$flag = "$root\reports\m3-dpo-watchdog-ALERT.txt"
$tj   = "$root\checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl"
$run  = "$root\reports\logs\m3-dpo-run.log"

function Write-Line([string]$s) {
  $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  Add-Content -Path $raw -Value ("[$stamp] " + $s) -Encoding UTF8
}

function Read-Shared([string]$p) {
  try {
    $fs = [System.IO.File]::Open($p, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    $sr = New-Object System.IO.StreamReader($fs, $true)
    $t = $sr.ReadToEnd(); $sr.Close(); $fs.Close()
    return $t
  } catch { return $null }
}

if (-not (Test-Path $csv)) {
  $hdr = 'ts,jsonl_lines,steps,total,loss,acc,lr,epoch,elapsed,remaining,prog_step,prog_eta,gpu_mem_MiB,power_W,util_pct,free_phys_MB,commit_used_MB,proc_ws_MB,proc_priv_MB,jsonl_age_s,pid,alive'
  Set-Content -Path $csv -Value $hdr -Encoding UTF8
}
Write-Line "sampler start interval=${IntervalSec}s max=${MaxMinutes}min"

$t0 = Get-Date
$iter = 0
while ($true) {
  $iter++
  $now = Get-Date
  if (($now - $t0).TotalMinutes -ge $MaxMinutes) { Write-Line 'sampler reached MaxMinutes, exiting'; break }

  # --- training process (match by command line, NOT by exe name) ---
  $procs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -and $_.CommandLine -match 'm3-dpo-final\.yaml' })
  $alive = 0; $pid_ = ''; $ws = ''; $priv = ''
  if ($procs.Count -gt 0) {
    $alive = 1
    $main = $procs | Sort-Object WorkingSetSize -Descending | Select-Object -First 1
    $pid_ = $main.ProcessId
    $ws = [math]::Round($main.WorkingSetSize / 1MB, 0)
    $priv = [math]::Round(($main.PrivatePageCount * 4KB) / 1MB, 0)
    $pr = Get-Process -Id $main.ProcessId -ErrorAction SilentlyContinue
    if ($pr) { $priv = [math]::Round($pr.PrivateMemorySize64 / 1MB, 0) }
  }

  # --- trainer_log.jsonl (reliable realtime channel) ---
  $jlines = 0; $steps = ''; $total = ''; $loss = ''; $acc = ''; $lr = ''; $epoch = ''; $elapsed = ''; $remaining = ''; $jage = ''
  if (Test-Path $tj) {
    $jt = Read-Shared $tj
    if ($jt) {
      $arr = @($jt -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
      $jlines = $arr.Count
      if ($jlines -gt 0) {
        try {
          $o = $arr[-1] | ConvertFrom-Json
          $steps = $o.current_steps; $total = $o.total_steps; $loss = $o.loss; $acc = $o.accuracy
          $lr = $o.lr; $epoch = $o.epoch; $elapsed = $o.elapsed_time; $remaining = $o.remaining_time
        } catch { Write-Line "jsonl parse fail: $($_.Exception.Message)" }
      }
    }
    $jage = [math]::Round(((Get-Date) - (Get-Item $tj).LastWriteTime).TotalSeconds, 0)
  }

  # --- progress line from run.log ---
  $prog = ''; $eta = ''
  $rt = Read-Shared $run
  if ($rt) {
    $pl = @($rt -split "`r?`n" | Where-Object { $_ -match '\d+/(\d+)\s*\[' })
    if ($pl.Count -gt 0) {
      $last = $pl[-1]
      if ($last -match '(\d+)/(\d+)\s*\[([0-9:]+)<([0-9:]+),\s*([0-9.]+)s/it\]') {
        $prog = $Matches[1]; $eta = $Matches[4]
      }
    }
    if ($rt -match '(?i)\b(traceback|CUDA out of memory|RuntimeError|Killed|nan|inf)\b') {
      Add-Content -Path $flag -Value ("[" + (Get-Date).ToString('s') + "] pattern hit in run.log: " + $Matches[0]) -Encoding UTF8
    }
  }

  # --- GPU ---
  $gm = ''; $pw = ''; $ut = ''
  try {
    $g = (nvidia-smi --query-gpu=memory.used,power.draw,utilization.gpu --format=csv,noheader) -join ' '
    if ($g -match '([0-9]+)\s*MiB,\s*([0-9.]+)\s*W,\s*([0-9]+)\s*%') { $gm = $Matches[1]; $pw = $Matches[2]; $ut = $Matches[3] }
  } catch { Write-Line "nvidia-smi failed: $($_.Exception.Message)" }

  # --- host memory / commit ---
  $fp = ''; $cu = ''
  $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
  if ($os) {
    $fp = [math]::Round($os.FreePhysicalMemory / 1024, 0)
    $cu = [math]::Round(($os.TotalVirtualMemorySize - $os.FreeVirtualMemory) / 1024, 0)
  }

  $row = @(
    $now.ToString('yyyy-MM-dd HH:mm:ss'), $jlines, $steps, $total, $loss, $acc, $lr, $epoch,
    $elapsed, $remaining, $prog, $eta, $gm, $pw, $ut, $fp, $cu, $ws, $priv, $jage, $pid_, $alive
  ) -join ','
  Add-Content -Path $csv -Value $row -Encoding UTF8

  if (($iter % 15) -eq 0) { Write-Line "iter=$iter steps=$steps loss=$loss acc=$acc gpu=$gm MiB ${pw}W util=$ut% freePhys=${fp}MB commit=${cu}MB alive=$alive" }

  if ($alive -eq 0) {
    Write-Line 'training process no longer present (matched m3-dpo-final.yaml); sampler exiting'
    break
  }
  Start-Sleep -Seconds $IntervalSec
}
Write-Line 'sampler end'
