[CmdletBinding()] param(
    [int]$IntervalSec = 20,
    [int]$MaxMinutes = 150,
    [string]$OutCsv = 'J:\Projects\llm_for_sec\reports\m3-dpo-resume-watchdog-telemetry.csv'
)

$ErrorActionPreference = 'Continue'
$tl  = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo\trainer_log.jsonl'
$ckd = 'J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo'
$header = 'ts,step,loss,acc,lr,epoch,elapsed,tl_mtime_ticks,tl_len,mem_used_mib,power_w,util_pct,temp_c,commit_used_mib,free_phys_mib,n_train_procs,ckpt_dirs'
Set-Content -LiteralPath $OutCsv -Value $header -Encoding UTF8

$deadline = (Get-Date).AddMinutes($MaxMinutes)
while ((Get-Date) -lt $deadline) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    # --- trainer_log.jsonl (trusted realtime channel) ---
    $step = ''; $loss = ''; $acc = ''; $lr = ''; $epoch = ''; $elapsed = ''
    $mt = ''; $len = ''
    try {
        $fi = Get-Item -LiteralPath $tl -ErrorAction Stop
        $mt = $fi.LastWriteTimeUtc.Ticks
        $len = $fi.Length
        $line = Get-Content -LiteralPath $tl -Tail 1 -ErrorAction Stop
        if ($line) {
            $o = $line | ConvertFrom-Json
            $step = $o.current_steps; $loss = $o.loss; $acc = $o.accuracy
            $lr = $o.lr; $epoch = $o.epoch; $elapsed = $o.elapsed_time
        }
    } catch { }

    # --- GPU ---
    $mem = ''; $pw = ''; $ut = ''; $tc = ''
    try {
        $q = (& nvidia-smi --query-gpu=memory.used,power.draw,utilization.gpu,temperature.gpu --format=csv,noheader,nounits) -join ' '
        $parts = ($q -replace '\s', '') -split ','
        if ($parts.Count -ge 4) { $mem = $parts[0]; $pw = $parts[1]; $ut = $parts[2]; $tc = $parts[3] }
    } catch { }

    # --- host memory ---
    $cu = ''; $fp = ''
    try {
        $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        $cu = [int](([int64]$os.TotalVirtualMemorySize - [int64]$os.FreeVirtualMemory) / 1024)
        $fp = [int]([int64]$os.FreePhysicalMemory / 1024)
    } catch { }

    # --- training procs identified BY COMMAND LINE ---
    $np = 0
    try {
        $np = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
                Where-Object { $_.CommandLine -and ($_.CommandLine -match 'm3-dpo-final\.yaml') }).Count
    } catch { }

    # --- checkpoint dirs present ---
    $ck = ''
    try {
        $ck = (@(Get-ChildItem -LiteralPath $ckd -Directory -Filter 'checkpoint-*' -ErrorAction Stop |
                 Sort-Object Name | ForEach-Object { $_.Name }) -join '|')
    } catch { }

    $row = @($ts, $step, $loss, $acc, $lr, $epoch, $elapsed, $mt, $len, $mem, $pw, $ut, $tc, $cu, $fp, $np, $ck) -join ','
    Add-Content -LiteralPath $OutCsv -Value $row -Encoding UTF8
    Start-Sleep -Seconds $IntervalSec
}
