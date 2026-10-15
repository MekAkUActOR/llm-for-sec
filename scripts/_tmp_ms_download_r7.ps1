# _tmp_ms_download_r7.ps1 -- Plan A (Lead authorized 2026-10-16 01:14):
# kill-switched mirror download replaced by direct ModelScope fetch into HF cache layout.
# Fail-closed: ANY file size/sha256 mismatch -> stop, exit 1, report (no partial cache fill).
# sha256 anchors (dual): 5 shards byte-identical to HF trees\49e3418f...json lfs_sha256
# (verified 2026-10-16 01:12); small files anchored on ModelScope API Sha256, sizes
# cross-checked against HF trees manifest. 3 files already in snapshot are re-verified
# in place before any download starts.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ROOT  = 'J:\Projects\llm_for_sec'
$STAGE = "$ROOT\.cache\ms-staging\qwen3-8b"
$SNAP  = "$ROOT\.cache\huggingface\hub\models--Qwen--Qwen3-8B-Base\snapshots\49e3418fbbbca6ecbdf9608b4d22e5a407081db4"
$BASE  = 'https://modelscope.cn/models/Qwen/Qwen3-8B-Base/resolve/master'

$EXISTING = @(
  @{ n = 'config.json';           s = 729;      sha = '3bd01d7ad7a2e203ecbbe84e24087a51c6d2a108ee4bcc42d0016bf49564983a' },
  @{ n = 'generation_config.json'; s = 138;     sha = '8c970692323e3ea0e9b8b0a4dca79388d31226e41f83c9fd6014804280ebf6e8' },
  @{ n = 'merges.txt';            s = 1671853;  sha = '8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5' }
)
$DOWNLOAD = @(
  @{ n = 'model-00001-of-00005.safetensors'; s = 3996250744; sha = '9983f1b9ef2f60e7c3730d9bc11ada914e6ec630639b5b020a89bd158cd0446b' },
  @{ n = 'model-00002-of-00005.safetensors'; s = 3993160032; sha = '9aa12339835bf7a093d3d0b0a0d2d77f8538301cfc7f8e7ec7a585858ebf7a1f' },
  @{ n = 'model-00003-of-00005.safetensors'; s = 3959604768; sha = 'c7dd5a191c8da555def0714550375b3c0117751add408fcdda0c2a79ac0186bc' },
  @{ n = 'model-00004-of-00005.safetensors'; s = 3187841392; sha = 'ad8b708792105133e03fe19e2d56c89c709f677f01285f8b3ede8947d59fd9fe' },
  @{ n = 'model-00005-of-00005.safetensors'; s = 1244659840; sha = 'fbf24915d47ea030bb68ab0b9488f4515a907185baa6dc26837c9c3f2326a550' },
  @{ n = 'model.safetensors.index.json';     s = 32878;      sha = 'cd39d5e44c5aadfd1954b598883aea1c4a98822a2f7723d214ef2278b7fec2e4' },
  @{ n = 'tokenizer.json';                   s = 7031645;    sha = 'c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539' },
  @{ n = 'tokenizer_config.json';            s = 9678;       sha = '3c04ed3ca964ea2f6b2b5faf0dc4d31aec1cb1e8b4bcf63f402d295046b422b5' },
  @{ n = 'vocab.json';                       s = 2776833;    sha = 'ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910' }
)

function Fail([string]$msg) { Write-Output "MS-CACHE-FILL=FAIL: $msg"; exit 1 }

# --- Phase 0: re-verify 3 existing snapshot files in place ---
foreach ($f in $EXISTING) {
  $p = Join-Path $SNAP $f.n
  if (-not (Test-Path $p)) { Fail "existing file missing: $($f.n)" }
  if ((Get-Item $p).Length -ne $f.s) { Fail "existing size mismatch: $($f.n)" }
  $h = (Get-FileHash $p -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $f.sha) { Fail "existing sha mismatch: $($f.n) = $h" }
  Write-Output "[OK-existing] $($f.n) sha=$($h.Substring(0,16))..."
}

# --- Phase 1: download 9 files to staging with resume + verify ---
New-Item -ItemType Directory -Force -Path $STAGE | Out-Null
foreach ($f in $DOWNLOAD) {
  $dst = Join-Path $STAGE $f.n
  $done = $false
  for ($attempt = 1; $attempt -le 4; $attempt++) {
    if (Test-Path $dst) {
      $sz = (Get-Item $dst).Length
      if ($sz -eq $f.s) { $done = $true; break }
      if ($sz -gt $f.s) { Remove-Item $dst -Force }  # oversize -> corrupt, restart
    }
    $have = 0
    if (Test-Path $dst) { $have = (Get-Item $dst).Length }
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')] dl $($f.n) attempt $attempt (have $have / $($f.s) bytes)"
    & curl.exe -sL --noproxy '*' --fail --retry 8 --retry-delay 3 -C - -o "$dst" "$BASE/$($f.n)"
    if ($LASTEXITCODE -eq 0 -and (Test-Path $dst) -and (Get-Item $dst).Length -eq $f.s) { $done = $true; break }
    $have = 0
    if (Test-Path $dst) { $have = (Get-Item $dst).Length }
    Write-Output "  curl rc=$LASTEXITCODE size=$have -- retrying in 5s"
    Start-Sleep -Seconds 5
  }
  if (-not $done) { Fail "download failed after 4 attempts: $($f.n)" }
  $h = (Get-FileHash $dst -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $f.sha) { Fail "staged sha mismatch: $($f.n) = $h (want $($f.sha))" }
  Write-Output "[OK-staged] $($f.n) sha=$($h.Substring(0,16))... size=$($f.s)"
}

# --- Phase 2: place all 9 into snapshot dir (plain files; refs/main already points here) ---
foreach ($f in $DOWNLOAD) {
  $src = Join-Path $STAGE $f.n
  $dst = Join-Path $SNAP $f.n
  if (Test-Path $dst) { Fail "target already exists, refusing overwrite: $($f.n)" }
  Move-Item $src $dst
  $h2 = (Get-FileHash $dst -Algorithm SHA256).Hash.ToLower()
  if ($h2 -ne $f.sha) { Fail "post-move sha mismatch: $($f.n)" }
  Write-Output "[OK-placed] $($f.n)"
}

# --- Phase 3: final inventory ---
$expected = @($EXISTING + $DOWNLOAD) | ForEach-Object { $_.n } | Sort-Object
$actual = @(Get-ChildItem $SNAP -File | Select-Object -ExpandProperty Name | Sort-Object)
$diff = Compare-Object $expected $actual
if ($diff) { Fail "snapshot inventory mismatch: $($diff | Out-String)" }
$total = (Get-ChildItem $SNAP -File | Measure-Object Length -Sum).Sum
$refOk = ((Get-Content "$ROOT\.cache\huggingface\hub\models--Qwen--Qwen3-8B-Base\refs\main" -Raw).Trim() -eq '49e3418fbbbca6ecbdf9608b4d22e5a407081db4')
if (-not $refOk) { Fail 'refs/main does not point to snapshot revision' }
Write-Output "MS-CACHE-FILL=OK: 12 files in snapshot, total $([math]::Round($total/1GB,3)) GB, refs/main verified"
