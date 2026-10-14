# Re-measure long-context needle with the expanded instrument (8 depths x 2 variants
# = 16 trials/cell -> 64 trials total at lens 16k,32k).
# The legacy 12-trial reports are archived first so history is not overwritten.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remeasure_needle64.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$legacy = "$root\reports\legacy-needle12"
New-Item -ItemType Directory -Force -Path $legacy | Out-Null
foreach ($f in Get-ChildItem "$root\reports\longctx-*.json" -ErrorAction SilentlyContinue) {
  $dst = Join-Path $legacy $f.Name
  if (-not (Test-Path $dst)) { Copy-Item $f.FullName $dst }
}
Write-Host "[needle64] legacy reports archived to reports\legacy-needle12"

$models = [ordered]@{
  m25full = 'qwen3-06b-sec-m25-full'
  m2full  = 'qwen3-06b-sec-m2-full'
  m2calib = 'qwen3-06b-sec-m2-calib'
  m15     = 'qwen3-06b-sec-m15'
}
foreach ($tag in $models.Keys) {
  $m = "$root\checkpoints\$($models[$tag])"
  if (-not (Test-Path $m)) { Write-Host "[needle64] SKIP $tag"; continue }
  Write-Host "`n[needle64] === $tag (16 trials/cell) ==="
  & $py scripts\probe_longctx.py --model $m --name $tag `
      --lens 16384,32768 --n-docs 4 2>&1 |
    Select-String -Pattern 'needle 16|needle 32|report ->|Traceback' |
    ForEach-Object { $_.Line }
  if ($LASTEXITCODE -ne 0) { Write-Host "[needle64] ERROR on $tag (rc=$LASTEXITCODE)" }
}
Write-Host "`n[needle64] ALL DONE"
