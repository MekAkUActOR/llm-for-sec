# S0 re-measurement: heldout v0.2.1 in DEPLOY prompt format (chat), four SFT stages.
# Why: all previous behavior gates were collected with the M0-era raw-completion judge
# (see reports/ab-promptformat.md). This run produces the corrected G1/G3/G4 footings.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\remeasure_chat_format.ps1
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$base = "$root\.cache\huggingface\hub\models--Qwen--Qwen3-0.6B-Base\snapshots\da87bfb608c14b7cf20ba1ce41287e8de496c0cd"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$models = [ordered]@{
  m15     = "$root\checkpoints\qwen3-06b-sec-m15"
  m2calib = "$root\checkpoints\qwen3-06b-sec-m2-calib"
  m2full  = "$root\checkpoints\qwen3-06b-sec-m2-full"
  m25full = "$root\checkpoints\qwen3-06b-sec-m25-full"
}
$heldout = 'data\heldout\v0.2.1'
$sub = 'reports\heldout-tooloutput-subset'

foreach ($tag in $models.Keys) {
  $m = $models[$tag]
  if (-not (Test-Path $m)) { Write-Host "[chat] SKIP $tag (missing $m)"; continue }
  $tokArgs = @()
  if (-not (Test-Path (Join-Path $m 'tokenizer_config.json'))) {
    $tokArgs = @('--tokenizer', $base)
  }
  Write-Host "`n[chat] === $tag (heldout full, chat) ==="
  & $py scripts\baseline_eval.py --model $m @tokArgs --heldout $heldout `
      --prompt-format chat `
      --out "reports\heldout-chat-$tag.json" `
      --dump-responses "reports\resp-chat-$tag.jsonl" 2>&1 |
    Select-String -Pattern 'prompt-format|ASR=|report ->' | ForEach-Object { $_.Line }
  & $py scripts\score_heldout_v2.py --heldout $heldout `
      --responses "reports\resp-chat-$tag.jsonl" `
      --out "reports\scored-chat-$tag-v2.json" 2>&1 |
    Select-String -Pattern 'report ->' | ForEach-Object { $_.Line }

  Write-Host "[chat] === $tag (tool_output subset, chat) ==="
  & $py scripts\score_heldout_v2.py --heldout $sub `
      --responses "reports\resp-chat-$tag.jsonl" `
      --out "reports\scored-chat-$tag-tooloutput-v2.json" 2>&1 |
    Select-String -Pattern 'report ->' | ForEach-Object { $_.Line }
}

Write-Host "`n[chat] ALL DONE (deploy-format re-measurement)"
