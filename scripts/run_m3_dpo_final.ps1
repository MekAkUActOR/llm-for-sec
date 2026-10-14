# M3 DPO 发射器（起点 soup-a050；判据见 reports/m3-dpo-preregistration.md）
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_m3_dpo_final.ps1
#   powershell ... -File scripts\run_m3_dpo_final.ps1 -DryRun
[CmdletBinding()]
param(
  [switch]$DryRun,
  # 默认只校验数据身份（sha256）；确需重算混料才显式加此开关
  [switch]$RebuildData
)
$ErrorActionPreference = 'Continue'
$root = 'J:\Projects\llm_for_sec'
$py = "$root\.venv\Scripts\python.exe"
$cli = "$root\.venv\Scripts\llamafactory-cli.exe"
$env:HF_HOME = "$root\.cache\huggingface"
$env:HF_HUB_OFFLINE = '1'
$env:PYTHONIOENCODING = 'utf-8'
# 优化器表（docs/01 §11.7）：8bit AdamW 只有在 expandable_segments 下才不抖动
$env:PYTORCH_CUDA_ALLOC_CONF = 'expandable_segments:True'
Set-Location $root
$logdir = "$root\reports\logs"
New-Item -ItemType Directory -Force -Path $logdir | Out-Null

$base = "$root\checkpoints\soup-needlefix-a050"
$ds = "$root\data\lf\dpo_m3_final.jsonl"
$cfg = "$root\configs\m3-dpo-final.yaml"
$outdir = "$root\checkpoints\qwen3-06b-sec-m3-dpo"

Write-Host "[m3] ===== 发射前硬校验 ====="
$fail = 0
foreach ($p in @($base, $ds, $cfg)) {
  if (-not (Test-Path $p)) { Write-Host "[m3] ✗ 缺 $p"; $fail = 1 }
}
if ($fail) { Write-Host "[m3] 前置缺失，中止"; exit 2 }

# 1) 起点必须是 accepted 产物（不得用 discarded 权重作基线，docs/01 §11 规则 4）
$status = & $py -c "import sys; sys.path.insert(0, r'$root\scripts'); import m25_exit_verdict as m; print(m.ARTIFACT_STATUS.get('soup-a050','MISSING'))" 2>&1
Write-Host "[m3] 起点产物状态 = $status（要求 accepted）"
if ("$status".Trim() -ne 'accepted') { Write-Host "[m3] ✗ 起点非 accepted，中止"; exit 2 }

# 2) 数据身份校验（★默认**只校验、不重建**：2026-09-30 看门狗发现原实现无条件重跑
#    build_m3_final_mix.py，导致"冻结数据"在发射前 11 s 被重新生成——构建脚本若有
#    非确定性改动不会被拦住。现改为比对 sha256，确需重算才加 -RebuildData）
$DS_SHA256 = 'c272ff9d0f8583982322f691736bac82f571af8c2be73c6087e2081882445b07'
if ($RebuildData) {
  $chk = ((& $py "$root\scripts\build_m3_final_mix.py" 2>&1 |
    Select-String -Pattern 'M3-FINAL-MIX=' | ForEach-Object { $_.Line }) -join ' ').Trim()
  Write-Host "[m3] 混料重建 = $chk"
  if ("$chk" -notmatch 'PASS') { Write-Host "[m3] ✗ 混料断言未过，中止"; exit 2 }
}
$got = (Get-FileHash $ds -Algorithm SHA256).Hash.ToLower()
Write-Host "[m3] 数据 sha256 = $got"
if ($got -ne $DS_SHA256) {
  Write-Host "[m3] ✗ 与冻结身份不一致（期望 $DS_SHA256）；确需更新请加 -RebuildData 并同步改本常量"
  exit 2
}
$rows = (Get-Content $ds | Measure-Object -Line).Lines
Write-Host "[m3] 数据行数 = $rows（期望 28,842）；总步数 = $([Math]::Ceiling($rows/16))"
if ($rows -ne 28842) { Write-Host "[m3] ✗ 行数不符，中止"; exit 2 }

# 3) venv 补丁 + trl DPO 冒烟
$patch = & $py "$root\scripts\patches\apply_venv_patches.py" 2>&1 | Select-Object -Last 1
Write-Host "[m3] venv 补丁 = $patch"
& $py -c "from trl import DPOTrainer, DPOConfig; import trl; print('trl', trl.__version__, 'OK')" 2>&1 |
  Select-Object -Last 1 | ForEach-Object { Write-Host "[m3] trl 冒烟 = $_" }

# 4) GPU 严格串行：无 GPU 作业进程 + 显存 < 2048 MiB
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'llamafactory|probe_|baseline_eval|score_heldout|train ' }
if ($procs) {
  Write-Host "[m3] ✗ 仍有 GPU 作业进程（docs/01 §11.7 规则 5），中止："
  $procs | ForEach-Object { Write-Host ("        " + $_.ProcessId + " " + $_.CommandLine.Substring(0, [Math]::Min(100, $_.CommandLine.Length))) }
  exit 2
}
$used = [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', '')
Write-Host "[m3] 显存占用 = $used MiB（要求 <2048；WDDM 桌面基线会漂移到 ~1.4 GB）"
if ($used -ge 2048) { Write-Host "[m3] ✗ 显存未清空，中止"; exit 2 }

Write-Host "[m3] 起点 = $base"
Write-Host "[m3] 数据 = dpo_m3_final.jsonl（28,842 行）；输出 = $outdir"
if ($DryRun) { Write-Host "[m3] DRY RUN：前置全过，未启动训练"; exit 0 }

Write-Host "[m3] ===== 启动 M3 DPO（1,802 步，预计 1.5–3 h）====="
$t0 = Get-Date
& $cli train $cfg 2>&1 | Tee-Object -FilePath "$logdir\m3-dpo-run.log"
$code = $LASTEXITCODE
$dt = (Get-Date) - $t0
Write-Host "[m3] exit=$code  用时=$($dt.ToString('hh\:mm\:ss'))"
if ($code -eq 0) {
  Write-Host "[m3] 落盘检查："
  Get-ChildItem $outdir -Directory | Select-Object -ExpandProperty Name
  Write-Host "[m3] ALL DONE"
} else {
  Write-Host "[m3] ★训练非零退出；检查点仍可用于续跑（save_steps=100）"
}
