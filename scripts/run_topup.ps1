# C-path targeted top-up: two dosage variants from m2-calib (see
# reports/c-path-topup-preregistration.md for the frozen acceptance criteria).
#   e1 = 1 epoch (~206 steps, ~5 min)   e2 = 2 epochs (~412 steps, ~10 min)
# This LLaMA-Factory build does NOT accept "yaml + --key value" overrides
# (HfArgumentParser rejects them), so each variant gets its own generated yaml.
# Interruptible: re-running the same command auto-resumes from the latest
# checkpoint (save_only_model=false keeps optimizer/scheduler/RNG state).
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_topup.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$env:HF_HOME = "$root\.cache\huggingface"
$env:TORCH_HOME = "$root\.cache\torch"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
$cli = "$root\.venv\Scripts\llamafactory-cli.exe"
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$tplPath = "$root\configs\m3base-topup.yaml"
$tpl = [System.IO.File]::ReadAllText($tplPath, [System.Text.Encoding]::UTF8)
$doTrainPath = "$root\configs\m3base-topup.yaml"

$variants = @(
  @{ name = 'e1'; epochs = '1.0'; out = 'qwen3-06b-sec-m3base-topup-e1' },
  @{ name = 'e2'; epochs = '2.0'; out = 'qwen3-06b-sec-m3base-topup-e2' }
)
foreach ($v in $variants) {
  $cfgPath = "$root\configs\m3base-topup-$($v.name).yaml"
  $cfg = $tpl -replace '(?m)^num_train_epochs:.*$', "num_train_epochs: $($v.epochs)"
  $cfg = $cfg -replace '(?m)^# doctrain:.*$', ''
  # output_dir 由模板行替换（模板指向 e1，这里改成对应变体）
  $cfg = $cfg -replace '(?m)^output_dir:.*$', "output_dir: J:\Projects\llm_for_sec\checkpoints\$($v.out)"
  [System.IO.File]::WriteAllText($cfgPath, $cfg, $utf8)
  $out = "$root\checkpoints\$($v.out)"
  Write-Host "`n[topup] === variant $($v.name) (epochs=$($v.epochs)) -> $($v.out) ==="
  Write-Host "[topup] config: $cfgPath"
  & $cli train $cfgPath 2>&1 |
    Tee-Object -FilePath "$logdir\topup-$($v.name).log" |
    Select-String -Pattern "running training|total_optimization_steps|train_runtime|Saving model checkpoint|Error|Traceback|OutOfMemory|error:|'loss'" |
    ForEach-Object { $_.Line }
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[topup] FAIL rcode=$LASTEXITCODE on variant $($v.name); stopping (fail-fast)"
    break
  }
  Write-Host "[topup] variant $($v.name) done"
}
Write-Host "`n[topup] ALL DONE"
