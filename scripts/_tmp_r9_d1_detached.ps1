# _tmp_r9_d1_detached.ps1 -- D1 诊断探针分离式运行（GPU 纪律：WMI + 心跳 + rc 哨兵）
$ErrorActionPreference = 'Continue'
$ROOT = 'J:\Projects\llm_for_sec'
$hb = "$ROOT\reports\logs\d1-prefill-r9-heartbeat.log"
$rcFile = "$ROOT\reports\logs\d1-prefill-r9-rc.txt"
$U8 = [System.Text.UTF8Encoding]::new($false)
function HB([string]$msg) { [System.IO.File]::AppendAllText($hb, "$msg`r`n", $U8); Write-Host $msg }
function GpuLine {
  $g = & nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader 2>$null
  if (-not $g) { return 'gpu=NA' }
  return 'gpu=[' + ($g -join ' | ').Trim() + ']'
}
if (Test-Path $rcFile) { Remove-Item $rcFile -Force }
HB "D1-HEARTBEAT-START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') wrapper_pid=$PID mode=detached-wmi"
Set-Location $ROOT
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = "$ROOT\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
$env:PYTHONUNBUFFERED = '1'
$proc = Start-Process "$ROOT\.venv\Scripts\python.exe" `
  -ArgumentList '-X','utf8',"$ROOT\scripts\_tmp_r9_d1_prefill_probe.py" `
  -RedirectStandardOutput "$ROOT\reports\logs\d1-prefill-r9-stdout.log" `
  -RedirectStandardError "$ROOT\reports\logs\d1-prefill-r9-stderr.log" `
  -PassThru -WindowStyle Hidden
$null = $proc.Handle  # PS5.1 PassThru Handle pin（r7/r8/r9 教训）
HB "D1-SPAWNED pid=$($proc.Id) start=$(Get-Date -Format 'HH:mm:ss') $(GpuLine)"
while (-not $proc.HasExited) {
  Start-Sleep -Seconds 120
  $done = (Select-String -Path "$ROOT\reports\logs\d1-prefill-r9-stdout.log" -Pattern '^\[(\d+)/80\]' -ErrorAction SilentlyContinue | Select-Object -Last 1).Matches[0].Groups[1].Value
  HB "D1-HEARTBEAT $(Get-Date -Format 'HH:mm:ss') pid=$($proc.Id) alive=$(-not $proc.HasExited) progress=$done/80 $(GpuLine)"
}
$rc = $proc.ExitCode
HB "D1-HEARTBEAT-END $(Get-Date -Format 'HH:mm:ss') pid=$($proc.Id) exit=$rc"
[System.IO.File]::WriteAllText($rcFile, "D1-RC=$rc`r`nfinished=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", $U8)
HB "D1-RC-SENTINEL-WRITTEN $rcFile"
