# Stage evaluation chain (S0, 2026-09-30) -- generic, fail-fast, exit-code checked.
#
# Why this exists: the M2.5 one-shot chain (scripts\post_m25_eval.ps1) never checked
# exit codes and unconditionally printed "ALL DONE" (review-2026-09-30.md I3), and it
# silently fell back to an older probe version (I4). This chain replaces it for M3+.
#
# Contract:
#   * every python step is checked; a real failure ABORTS the chain (no "ALL DONE");
#   * the probe version must exist -- no silent fallback;
#   * behavior readings default to DEPLOY prompt format (--prompt-format chat);
#   * the verdict runner exit code is interpreted, not swallowed:
#       0 = PASS, 1 = completed but not PASS, >=2 = runner error (abort).
#
# Run:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stage_eval_chain.ps1 `
#       -Tag m25full -Bases "m15,m2full" -ProbeVer v0.3
param(
  [Parameter(Mandatory = $true)][string]$Tag,
  [Parameter(Mandatory = $true)][string]$Model,
  [string]$Heldout = 'data\heldout\v0.2.1',
  [string]$ProbeVer = 'v0.3',
  [string]$Bases = 'm15,m2full',
  [string]$Suffix = 'chat-',
  [string]$SubsetCarrier = 'tool_output',
  [string]$Tokenizer = '',
  [switch]$SkipPpl,
  [switch]$SkipLongctx,
  [switch]$LegacySingleTrack
)
$ErrorActionPreference = 'Stop'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$logDir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = "$logDir\stage-eval-$Tag.log"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$script:Steps = @()
function Record([string]$name, [string]$status, [string]$detail) {
  $script:Steps += [pscustomobject]@{ Step = $name; Status = $status; Detail = $detail }
  Write-Host ("[{0}] {1} -- {2}" -f $status, $name, $detail)
}

function Invoke-Py {
  param([string]$Name, [string[]]$PyArgs, [int[]]$OkCodes = @(0))
  $out = & $py @PyArgs 2>&1
  $rc = $LASTEXITCODE
  $out | Tee-Object -FilePath $log -Append | Out-Null
  if ($OkCodes -contains $rc) {
    Record $Name 'OK' "rc=$rc"
    return $rc
  }
  Record $Name 'ERROR' "rc=$rc -- chain aborted"
  Write-Host ($out | Select-Object -Last 25 | Out-String)
  throw "step failed: $Name (rc=$rc)"
}

# --- 0. preflight ---------------------------------------------------------
if (-not (Test-Path $py)) { throw "venv python missing: $py" }
if (-not (Test-Path $Model)) { throw "model dir missing: $Model" }
if (-not (Test-Path $Heldout)) { throw "heldout dir missing: $Heldout" }
$probeDir = "data\probes\$ProbeVer"
if (-not (Test-Path $probeDir)) {
  throw "probe version '$ProbeVer' not found at $probeDir -- refusing to fall back (I4)"
}
$tokArgs = @()
if (-not (Test-Path (Join-Path $Model 'tokenizer_config.json'))) {
  if (-not $Tokenizer) {
    throw "model has no tokenizer_config.json; pass -Tokenizer <path>"
  }
  $tokArgs = @('--tokenizer', $Tokenizer)
}
Record 'preflight' 'OK' "model=$Model probe=$ProbeVer heldout=$Heldout suffix=$Suffix"

# --- 1. heldout (deploy format) -------------------------------------------
$resp = "reports\resp-$Suffix$Tag.jsonl"
$scored = "reports\scored-$Suffix$Tag-v2.json"
Invoke-Py 'heldout.generate' @(
  'scripts\baseline_eval.py', '--model', $Model
) + $tokArgs + @(
  '--heldout', $Heldout, '--prompt-format', 'chat',
  '--out', "reports\heldout-$Suffix$Tag.json", '--dump-responses', $resp
) | Out-Null
Invoke-Py 'heldout.score' @(
  'scripts\score_heldout_v2.py', '--heldout', $Heldout,
  '--responses', $resp, '--out', $scored
) | Out-Null

# --- 2. carrier subset (generalization/gate subset) -----------------------
$sub = "reports\heldout-$SubsetCarrier-subset"
New-Item -ItemType Directory -Force -Path $sub | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$subCount = 0
foreach ($f in Get-ChildItem "$Heldout\*.jsonl") {
  $lines = Get-Content $f.FullName -Encoding UTF8 |
    Select-String $SubsetCarrier | ForEach-Object { $_.Line }
  if ($lines) {
    [System.IO.File]::WriteAllLines("$sub\$($f.Name)", $lines, $utf8NoBom)
    $subCount += $lines.Count
  }
}
if ($subCount -eq 0) { throw "no '$SubsetCarrier' items found in $Heldout" }
Invoke-Py 'subset.score' @(
  'scripts\score_heldout_v2.py', '--heldout', $sub,
  '--responses', $resp, '--out', "reports\scored-$Suffix$Tag-$SubsetCarrier-v2.json"
) | Out-Null

# --- 3. PPL probes (gate + clean) ----------------------------------------
if (-not $SkipPpl) {
  Invoke-Py 'ppl.probe' @(
    'scripts\probe_ppl.py', '--model', $Model
  ) + $tokArgs + @(
    '--name', "$Tag-$ProbeVer", '--probes', $probeDir,
    '--out', "reports\ppl-$Tag-$ProbeVer.json"
  ) | Out-Null
  foreach ($b in ($Bases -split ',')) {
    $bp = "reports\ppl-$b-$ProbeVer.json"
    if (Test-Path $bp) {
      Invoke-Py "ppl.compare.$b" @(
        'scripts\compare_ppl.py', $bp, "reports\ppl-$Tag-$ProbeVer.json"
      ) | Out-Null
    } else {
      Record "ppl.compare.$b" 'SKIP' "baseline $bp missing"
    }
  }
}

# --- 4. long-context needle ----------------------------------------------
if (-not $SkipLongctx) {
  Invoke-Py 'longctx.probe' @(
    'scripts\probe_longctx.py', '--model', $Model, '--name', $Tag
  ) | Out-Null
  foreach ($b in ($Bases -split ',')) {
    $bl = "reports\longctx-$b.json"
    if (Test-Path $bl) {
      Invoke-Py "longctx.compare.$b" @(
        'scripts\probe_longctx.py', '--compare', $bl, "reports\longctx-$Tag.json"
      ) | Out-Null
    }
  }
}

# --- 5. verdict (v2) ------------------------------------------------------
$vArgs = @('scripts\m25_exit_verdict.py', '--tag', $Tag, '--suffix', $Suffix,
           '--out-name', "stage-verdict")
if ($LegacySingleTrack) { $vArgs += '--legacy-single-track' }
$vrc = Invoke-Py 'verdict' $vArgs @(0, 1)
if ($vrc -eq 1) { Record 'verdict' 'WARN' 'completed but VERDICT is not PASS' }

# --- 6. readout -----------------------------------------------------------
Invoke-Py 'readout' @(
  'scripts\m25_readout_numbers.py', '--suffix', $Suffix, '--verdict', 'stage-verdict'
) | Out-Null

# --- summary -------------------------------------------------------------
Write-Host ""
Write-Host "==================== stage eval summary ($Tag) ===================="
$script:Steps | Format-Table -AutoSize | Out-String | Write-Host
$bad = @($script:Steps | Where-Object { $_.Status -eq 'ERROR' })
if ($bad.Count -gt 0) {
  Write-Host "ALL DONE = FALSE ($($bad.Count) failed step(s))"
  exit 1
}
Write-Host "ALL DONE = TRUE (log: $log)"
exit 0
