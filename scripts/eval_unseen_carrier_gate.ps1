# Evaluate the UNSEEN-CARRIER gate set (data\heldout\v0.3-gen) in DEPLOY prompt format.
# Rationale: the tool_output subset is saturated in deploy format (all three SFT stages
# defend 8/8 -> zero discriminative power, and the carrier was trained anyway).
# v0.3-gen uses image_metadata / av_metadata carriers: 0 occurrences in the training mix.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\eval_unseen_carrier_gate.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$base = "$root\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
$heldout = 'data\heldout\v0.3-gen'

$models = [ordered]@{
  m2calib = "$root\checkpoints\qwen3-06b-sec-m2-calib"
  m2full  = "$root\checkpoints\qwen3-06b-sec-m2-full"
  m25full = "$root\checkpoints\qwen3-06b-sec-m25-full"
}
foreach ($tag in $models.Keys) {
  $m = $models[$tag]
  if (-not (Test-Path $m)) { Write-Host "[gen] SKIP $tag"; continue }
  $tokArgs = @()
  if (-not (Test-Path (Join-Path $m 'tokenizer_config.json'))) { $tokArgs = @('--tokenizer', $base) }
  Write-Host "`n[gen] === $tag (v0.3-gen, chat) ==="
  & $py scripts\baseline_eval.py --model $m @tokArgs --heldout $heldout `
      --prompt-format chat `
      --out "reports\heldout-gen-$tag.json" `
      --dump-responses "reports\resp-chat-gen-$tag.jsonl" 2>&1 |
    Select-String -Pattern 'prompt-format|ASR=|report ->' | ForEach-Object { $_.Line }
  if ($LASTEXITCODE -ne 0) { Write-Host "[gen] ERROR generating $tag (rc=$LASTEXITCODE)" }
  & $py scripts\score_heldout_v2.py --heldout $heldout `
      --responses "reports\resp-chat-gen-$tag.jsonl" `
      --out "reports\scored-chat-gen-$tag-v2.json" 2>&1 |
    Select-String -Pattern 'report ->|Error|Traceback' | ForEach-Object { $_.Line }
  # per-carrier subsets
  foreach ($c in @('image_metadata', 'av_metadata')) {
    $sub = "$root\reports\heldout-gen-$c"
    New-Item -ItemType Directory -Force -Path $sub | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    foreach ($f in Get-ChildItem "$heldout\*.jsonl") {
      $lines = Get-Content $f.FullName -Encoding UTF8 | Select-String $c | ForEach-Object { $_.Line }
      if ($lines) { [System.IO.File]::WriteAllLines("$sub\$($f.Name)", $lines, $utf8NoBom) }
    }
    & $py scripts\score_heldout_v2.py --heldout $sub `
        --responses "reports\resp-chat-gen-$tag.jsonl" `
        --out "reports\scored-chat-gen-$tag-$c-v2.json" 2>&1 |
      Select-String -Pattern 'report ->' | ForEach-Object { $_.Line }
  }
}
Write-Host "`n[gen] ALL DONE (unseen-carrier gate set)"
