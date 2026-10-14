# run_auto_restart.ps1 — 通用训练崩溃保险 + 发射前预检（2026-09-30）
#
# 由 m25_full_auto_restart.ps1 泛化：不再为每个 run 复制一份脚本，改为参数化。
# 逻辑：目标进程消失且未出 train_results.json → 自动重启（LF 自动续训，最多 N 次）。
#
# **续训前提（2026-09-30 实证，务必不可破坏）**：LLaMA-Factory 仅在
#   stage ∈ {pt,sft,dpo,kto} 且 output_dir 存在 且 `overwrite_output_dir` 未设/为假
#   且 `resume_from_checkpoint` 未显式指定
# 时自动从最新检查点续训（hparams/parser.py:612-627）。配置里若出现
# `overwrite_output_dir: true`，重启会**从 step 0 重跑并轮转覆盖检查点**。
# 本脚本的 -Check 模式即校验此前提。
#
# **运维盲点**：重启进程的输出写往 <LogPrefix>-restart<N>.log（不是主日志）——
# 真发生重启时主日志 mtime 会冻结，监控须看重启日志 + 检查点目录增长。
#
# 用法：
#   预检（发射前/巡检，单次执行后退出）：
#     pwsh -NoProfile -File scripts\run_auto_restart.ps1 -Check `
#          -Config configs\m3-dpo.yaml -OutDir checkpoints\qwen3-06b-sec-m3-dpo
#   武装（后台常驻）：
#     pwsh -NoProfile -File scripts\run_auto_restart.ps1 `
#          -Config configs\m25-full.yaml -OutDir checkpoints\qwen3-06b-sec-m25-full
param(
    [string]$Config = 'configs\m25-full.yaml',
    [string]$OutDir = 'checkpoints\qwen3-06b-sec-m25-full',
    [int]$MaxRestarts = 3,
    [int]$IntervalSec = 180,
    [int]$GraceSec = 120,
    [switch]$Check
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$cfgPath = Join-Path $root $Config
$outPath = Join-Path $root $OutDir
$done = Join-Path $outPath 'train_results.json'
$name = [IO.Path]::GetFileNameWithoutExtension($Config)
$restartLog = Join-Path $root "reports\$name-restart.log"
$logDir = Join-Path $root 'reports\logs'
$logPrefix = Join-Path $logDir "$name"

function Write-RestartLog($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
    Add-Content -Path $restartLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-TrainProc {
    # 用配置文件名定位（与发射命令一致：llamafactory-cli train <config>）
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$([IO.Path]::GetFileName($Config))*" }
}

function Test-ResumePreconditions {
    $res = [ordered]@{}
    if (-not (Test-Path $cfgPath)) { $res['config_exists'] = $false; return $res }
    $res['config_exists'] = $true
    $text = Get-Content $cfgPath -Raw -Encoding UTF8
    $bad1 = $text -match '(?m)^\s*overwrite_output_dir\s*:\s*true'
    $bad2 = $text -match '(?m)^\s*resume_from_checkpoint\s*:\s*\S+'
    $res['overwrite_output_dir_not_true'] = (-not $bad1)
    $res['resume_from_checkpoint_unset'] = (-not $bad2)
    $res['stage_ok'] = ($text -match '(?m)^\s*stage\s*:\s*(pt|sft|dpo|kto)\s*$')
    $res['outdir_exists'] = (Test-Path $outPath)
    $ck = @()
    if (Test-Path $outPath) {
        $ck = Get-ChildItem $outPath -Directory -Filter 'checkpoint-*' -ErrorAction SilentlyContinue |
            Sort-Object Name
    }
    $res['checkpoints'] = $ck.Count
    $res['latest_checkpoint'] = if ($ck.Count -gt 0) { $ck[-1].Name } else { $null }
    $res['train_results_present'] = (Test-Path $done)
    return $res
}

if ($Check) {
    Write-Host "=== 崩溃保险预检：$Config ==="
    $r = Test-ResumePreconditions
    $ok = $true
    foreach ($k in @('config_exists', 'overwrite_output_dir_not_true',
                     'resume_from_checkpoint_unset', 'stage_ok')) {
        $v = $r[$k]; if (-not $v) { $ok = $false }
        Write-Host ("  [{0}] {1}" -f $(if ($v) { 'PASS' } else { 'FAIL' }), $k)
    }
    Write-Host ("  outdir_exists={0}  checkpoints={1}  latest={2}  train_results={3}" -f `
        $r['outdir_exists'], $r['checkpoints'], $r['latest_checkpoint'],
        $r['train_results_present'])
    $p = Get-TrainProc
    Write-Host ("  训练进程：{0}" -f $(if ($p) { "存活 PID=" + ($p.ProcessId -join ',') } else { '未运行' }))
    # 边角判据（只报告、不自动动作）：进程链 = llamafactory-cli.exe → python(包装) → python(trainer)。
    # 若 trainer 已死而父进程卡住不退，"按进程存在"判据会漏判 → 交叉看主日志 mtime 与 GPU 利用率。
    $mainLog = Join-Path $logDir "$name.log"
    if (Test-Path $mainLog) {
        $ageMin = [Math]::Round(((Get-Date) - (Get-Item $mainLog).LastWriteTime).TotalMinutes, 1)
        Write-Host "  主日志 mtime 停滞：$ageMin 分钟"
        $gpu = $null
        try { $gpu = (nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>$null | Select-Object -First 1) } catch {}
        if ($gpu) { Write-Host "  GPU util：$gpu%" }
        if ($p -and $ageMin -gt 15 -and $gpu -and [int]$gpu -lt 5) {
            Write-Host "  ⚠️  EDGE CASE：进程在、但主日志停滞 >15min 且 GPU 空闲"
            Write-Host "      → 可能 trainer 已死而父进程残留，保险的按进程判据会漏判，请人工确认。"
        }
    }
    if (Test-Path $restartLog) {
        $n = (Select-String -Path $restartLog -Pattern 'restart \d+/\d+' `
             -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Host "  重启日志：$restartLog（历史重启行 $n 条）"
    } else { Write-Host "  重启日志：尚无（未武装或未触发）" }
    if ($ok) { Write-Host "PREFLIGHT=PASS（自动续训前提成立；保险可安全武装）" }
    else { Write-Host "PREFLIGHT=FAIL（切勿武装：重启会从 step 0 重跑并覆盖检查点）" }
    exit $(if ($ok) { 0 } else { 1 })
}

Write-RestartLog "auto-restart armed (max $MaxRestarts) for $Config -> $OutDir"
$restarts = 0
while ($true) {
    if (Test-Path $done) {
        Write-RestartLog "train_results.json present -- training complete, standing down"
        break
    }
    $proc = Get-TrainProc
    if (-not $proc) {
        Start-Sleep -Seconds $GraceSec   # 起跑间隙宽限
        $proc = Get-TrainProc
        if (-not $proc -and -not (Test-Path $done)) {
            if ($restarts -ge $MaxRestarts) {
                Write-RestartLog "DEAD: process gone, restart budget exhausted ($restarts/$MaxRestarts) -- needs human"
                break
            }
            $restarts++
            Write-RestartLog "process gone without train_results.json -- restart $restarts/$MaxRestarts"
            $env:HF_HOME = "$root\.cache\huggingface"
            $env:TORCH_HOME = "$root\.cache\torch"
            $env:PYTHONIOENCODING = 'utf-8'
            $env:HF_HUB_OFFLINE = '1'
            $env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
            Start-Process -FilePath "$root\.venv\Scripts\llamafactory-cli.exe" `
                -ArgumentList 'train', $cfgPath `
                -RedirectStandardOutput "$logPrefix-restart$restarts.log" `
                -RedirectStandardError "$logPrefix-restart$restarts.err.log" `
                -WindowStyle Hidden
            Write-RestartLog "relaunched -> $logPrefix-restart$restarts.log; 等 300s 观察进程与 'Resuming training from' 行"
            Start-Sleep -Seconds 300
            $rl = "$logPrefix-restart$restarts.log"
            if (Test-Path $rl) {
                $resumed = Select-String -Path $rl -Pattern 'Resuming training from' `
                    -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($resumed) { Write-RestartLog "RESUME CONFIRMED: $($resumed.Line.Trim())" }
                else { Write-RestartLog "WARN: 重启日志暂未见 'Resuming training from' —— 若 5 分钟后仍无，可能从零重跑，需人工介入" }
            }
        }
    }
    Start-Sleep -Seconds $IntervalSec
}
