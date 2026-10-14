# T6 procurement downloads (M2.5 staging): Devign + CVEfixes raw artifacts
# Network facts (recon 2026-09-28): github.com:443 dead (timeout), but
# codeload.github.com + api.github.com alive; Zenodo slow (1.3 MB/s, 12 GB zip
# ~2.6 h -> deferred); hf-mirror.com ~1.2 MB/s. Downloads use curl.exe
# (schannel) per project convention (python urllib TLS flaky on this network).
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = "J:\Projects\llm_for_sec"
$raw = "$root\data\corpora\raw\t6"
New-Item -ItemType Directory -Force -Path "$raw\devign", "$raw\cvefixes", "$raw\devign-lines" | Out-Null

function Get-File($url, $out, $minMB) {
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt $minMB * 1MB)) {
        Write-Output "[skip] $out already present"
        return
    }
    Write-Output "[get ] $url"
    curl.exe -sS -L --retry 4 --retry-delay 5 -C - -o $out $url
    if ($LASTEXITCODE -ne 0) { Write-Output "[FAIL rc=$LASTEXITCODE] $url"; exit 1 }
    $len = [math]::Round((Get-Item $out).Length / 1MB, 1)
    Write-Output "[ ok ] $out ${len}MB"
}

# 1) Devign (original FFmpeg/Qemu release, MIT) via codeload tarball
#    repo epicosy/devign = active mirror of the Devign paper code+data
#    (soarsmu/Devign and software-research/Devign both 404 as of 2026-09-28)
#    HEAD provenance: da611bf392d81936e6ac8973556f9eed6612dd4f (2024-01-19)
Get-File "https://codeload.github.com/epicosy/devign/tar.gz/refs/heads/master" "$raw\devign\devign-master.tar.gz" 5
tar -xzf "$raw\devign\devign-master.tar.gz" -C "$raw\devign"
Write-Output "[extract] devign tarball done"

# 2) CVEfixes v1.0.8 commit-level records via hf-mirror (hitoshura25/cvefixes)
#    canonical data: Zenodo DOI 10.5281/zenodo.13118970, CC-BY-4.0
Get-File "https://hf-mirror.com/datasets/hitoshura25/cvefixes/resolve/main/data/train-00000-of-00003.parquet" "$raw\cvefixes\train-00000-of-00003.parquet" 100
Get-File "https://hf-mirror.com/datasets/hitoshura25/cvefixes/resolve/main/data/train-00001-of-00003.parquet" "$raw\cvefixes\train-00001-of-00003.parquet" 100
Get-File "https://hf-mirror.com/datasets/hitoshura25/cvefixes/resolve/main/data/train-00002-of-00003.parquet" "$raw\cvefixes\train-00002-of-00003.parquet" 100

# 3) Devign line-annotated derivative (DetectVul FGCS 2024) via hf-mirror
Get-File "https://hf-mirror.com/datasets/DetectVul/devign/resolve/main/data/train-00000-of-00001-396a063c42dfdb0a.parquet" "$raw\devign-lines\train.parquet" 20
Get-File "https://hf-mirror.com/datasets/DetectVul/devign/resolve/main/data/validation-00000-of-00001-5d4ba937305086b9.parquet" "$raw\devign-lines\validation.parquet" 2
Get-File "https://hf-mirror.com/datasets/DetectVul/devign/resolve/main/data/test-00000-of-00001-e0e162fa10729371.parquet" "$raw\devign-lines\test.parquet" 2

Write-Output "ALL DOWNLOADS DONE"
