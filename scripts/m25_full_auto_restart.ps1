# m25_full_auto_restart.ps1 — M2.5 全量跑崩溃保险（2026-09-29 深夜）
# 逻辑：m25-full 训练进程消失且未出 train_results.json → 自动重启
#       （LF auto-resume 无损续训，最多 3 次）。OOM/驱动硬崩半夜无人时兜底。
# 判定"进程消失"：无命令行含 m25-full.yaml 的 python 进程。
# 运行：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\m25_full_auto_restart.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$ckpt = "$root\checkpoints\qwen3-06b-sec-m25-full"
$done = "$ckpt\train_results.json"
$maxRestarts = 3
$restarts = 0
$log = "$root\reports\m25full-restart.log"

function Write-RestartLog($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Host $line
}

Write-RestartLog "auto-restart armed (max $maxRestarts)"

while ($true) {
    if (Test-Path $done) {
        Write-RestartLog "train_results.json present -- training complete, standing down"
        break
    }
    $proc = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -like '*m25-full.yaml*' }
    if (-not $proc) {
        # 进程消失：可能是起跑间隙——给一轮宽限再判
        Start-Sleep -Seconds 120
        $proc = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
            Where-Object { $_.CommandLine -like '*m25-full.yaml*' }
        if (-not $proc -and -not (Test-Path $done)) {
            if ($restarts -ge $maxRestarts) {
                Write-RestartLog "DEAD: process gone, restart budget exhausted ($restarts/$maxRestarts) -- needs human"
                break
            }
            $restarts++
            Write-RestartLog "process gone without train_results.json -- restart $restarts/$maxRestarts"
            $env:HF_HOME = "$root\.cache\huggingface"
            $env:TORCH_HOME = "$root\.cache\torch"
            $env:PYTHONIOENCODING = 'utf-8'
            $env:HF_HUB_OFFLINE = '1'
            $env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
            Start-Process -FilePath "$root\.venv\Scripts\llamafactory-cli.exe" `
                -ArgumentList 'train', "$root\configs\m25-full.yaml" `
                -RedirectStandardOutput "$root\reports\logs\m25-full-restart$restarts.log" `
                -RedirectStandardError "$root\reports\logs\m25-full-restart$restarts.err.log" `
                -WindowStyle Hidden
            Write-RestartLog "relaunched, waiting 300s for process to appear"
            Start-Sleep -Seconds 300
        }
    }
    Start-Sleep -Seconds 180
}
