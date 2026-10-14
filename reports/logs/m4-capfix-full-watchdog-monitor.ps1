param([int]$Minutes = 125, [int]$EverySec = 360)

$ErrorActionPreference = 'SilentlyContinue'
$root = 'J:\Projects\llm_for_sec'
$wd   = Join-Path $root 'reports\logs\m4-capfix-full-watchdog.md'
$log  = Join-Path $root 'reports\logs\m4-capfix-full.log'
$out  = Join-Path $root 'checkpoints\qwen3-06b-sec-m4-capfix-full'
$state= Join-Path $out 'trainer_state.json'

$deadline = (Get-Date).AddMinutes($Minutes)
$tick = 0
$misses = 0

while ((Get-Date) -lt $deadline) {
    $tick++
    $now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    $plist = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*m4-capfix-full*' })
    $pids  = ($plist | ForEach-Object { $_.ProcessId }) -join ','
    $alive = $plist.Count

    $cks = @(Get-ChildItem (Join-Path $out 'checkpoint-*') -Directory |
             ForEach-Object { [int]($_.Name -replace '^checkpoint-','') } | Sort-Object)
    $maxck = 0; if ($cks.Count -gt 0) { $maxck = $cks[-1] }

    $step = -1; $ch = $null; $rj = $null; $ac = $null; $ls = $null; $ep = $null
    if (Test-Path $state) {
        try {
            $j = Get-Content $state -Raw | ConvertFrom-Json
            $h = @($j.log_history | Where-Object { $_.PSObject.Properties.Name -contains 'rewards/chosen' })
            if ($h.Count -gt 0) {
                $e = $h[-1]
                $step = $e.step; $ch = $e.'rewards/chosen'; $rj = $e.'rewards/rejected'
                $ac = $e.'rewards/accuracies'; $ls = $e.loss; $ep = $e.epoch
            }
        } catch { }
    }
    if ($step -lt 0) {
        $m = Select-String -Path $log -Pattern "rewards/chosen" -Encoding utf8 | Select-Object -Last 1
        if ($m) {
            $L = $m.Line
            if ($L -match "'loss':\s*'?([-0-9.eE+]+)'?")            { $ls = $Matches[1] }
            if ($L -match "'rewards/chosen':\s*'?([-0-9.eE+]+)'?")   { $ch = $Matches[1] }
            if ($L -match "'rewards/rejected':\s*'?([-0-9.eE+]+)'?") { $rj = $Matches[1] }
            if ($L -match "'rewards/accuracies':\s*'?([-0-9.eE+]+)'?") { $ac = $Matches[1] }
            if ($L -match "'epoch':\s*'?([-0-9.eE+]+)'?")            { $ep = $Matches[1] }
            $step = -2
        }
    }

    $logsz = 0; if (Test-Path $log) { $logsz = (Get-Item $log).Length }
    $oom = @(Select-String -Path $log -Pattern 'OutOfMemoryError|torch.OutOfMemory|cuda error|CUDA error' -Encoding utf8).Count

    if ($alive -eq 0) { $misses++ } else { $misses = 0 }

    $stp = if ($step -eq -1) { 'n/a' } elseif ($step -eq -2) { 'stdout' } else { "$step" }
    $num = { param($v) if ($null -eq $v) { 'n/a' } else { [string]([math]::Round([double]$v, 4)) } }
    $ratio = 'n/a'
    if ($null -ne $ch -and $null -ne $rj -and [double]$rj -ne 0) {
        $ratio = ('1:{0}' -f [math]::Round([math]::Abs([double]$rj / [double]$ch), 2))
    }

    $line = "- $now | tick $tick | python(m4-capfix-full)=$alive [$pids] | ckpts=$($cks.Count) max=$maxck | logstep=$stp epoch=$(if($ep){[math]::Round([double]$ep,4)}else{'n/a'}) | loss=$(& $num $ls) chosen=$(& $num $ch) rejected=$(& $num $rj) acc=$(& $num $ac) ratio=$ratio | log=${logsz}B oomLines=$oom"
    Add-Content -Path $wd -Value $line -Encoding utf8
    Write-Output $line
    [Console]::Out.Flush()

    if ($alive -eq 0 -and $misses -ge 2) {
        $end = "- $now | MONITOR STOP: no python(m4-capfix-full) process for 2 consecutive ticks; last ckpt=$maxck, last logstep=$stp chosen=$(& $num $ch) rejected=$(& $num $rj)"
        Add-Content -Path $wd -Value $end -Encoding utf8
        Write-Output $end
        break
    }
    if ($maxck -ge 1800) {
        $end = "- $now | MONITOR STOP: final checkpoint 1800 present"
        Add-Content -Path $wd -Value $end -Encoding utf8
        Write-Output $end
        break
    }

    Start-Sleep -Seconds $EverySec
}

Write-Output "MONITOR-EXIT ticks=$tick at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
