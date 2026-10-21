# v2 读数段一键驱动（qa-m6；pm 预排：v2 calib+冒烟后 GPU 无竞争窗口）
# 链：v2 dev 推理 -> select-op -> calib 转推荐点 -> v2 主读数 -> v2 QA 点交叉 -> v1-3 效应分解
# 注意：select-op 产物 operating-point-v{k}.json 的 k 自动递增（避开已存 v1/v2）——
#       本脚本跑完后人工核对终名（日志会打印），交叉 run 引用 PRINTED 名。
# 用法：powershell -File scripts\run_v2_readings.ps1 -V2Tag v2 -V13Tag v13 -QaopRunpoint <select-op 产物名>
param([string]$V2Tag = "v2", [string]$V13Tag = "v13", [string]$QaopRunpoint = "")

$ErrorActionPreference = 'Continue'
function Run-Step($name, $cmd) {
  Write-Output "=== [$name] START $(Get-Date -Format HH:mm:ss) ==="
  & .venv\Scripts\python.exe -X utf8 @cmd 2>&1 | Select-Object -Last 3
  if ($LASTEXITCODE -ne 0) { Write-Output "=== [$name] FAILED ==="; exit 1 }
  Write-Output "=== [$name] OK ==="
}

$man = (Get-FileHash data\m6\manifest.json -Algorithm SHA256).Hash.ToLower()

# ① v2 dev 推理（13,389 行 D 波后完整 dev）
Run-Step "v2-dev" @('scripts\m6_infer.py', '--head', "checkpoints\m6-$V2Tag", '--input', "reports\m6\preds\${V2Tag}-dev-in.jsonl", '--output', "reports\m6\preds\${V2Tag}-dev-out.jsonl")

# ② v2 chmirror 推理
Run-Step "v2-chmirror" @('scripts\m6_infer.py', '--head', "checkpoints\m6-$V2Tag", '--input', "reports\m6\preds\${V2Tag}-chmirror-in.jsonl", '--output', "reports\m6\preds\${V2Tag}-chmirror-out.jsonl')

# ③ QA 独立选点（完整 dev + chmirror 双约束；score 饱和任务从 calib 继承）
Run-Step "v2-select-op" @('scripts\m6_acceptance.py', '--mode', 'select-op', '--dev-preds', 'reports\m6\preds', '--dev-preds-prefix', "$V2Tag-", '--dev-labels', "reports\m6\preds\${V2Tag}-dev-labels.jsonl", '--dev-manifest', $man, '--calib-fallback', "checkpoints\m6-$V2Tag\calib.json")

# ④ calib.json -> 推荐点 runpoint（logit 域；schema 校验内嵌）
Run-Step "v2-calib2runpoint" @('scripts\m6_calib_to_runpoint.py', '--calib', "checkpoints\m6-$V2Tag\calib.json", '--out', "reports\m6\operating-point-$V2Tag-recommended.json")

# ⑤ v2 主读数（calib 推荐点）
Run-Step "v2-run-main" @('scripts\m6_acceptance.py', '--mode', 'run', '--tag', $V2Tag, '--head', "checkpoints\m6-$V2Tag", '--runpoint', "reports\m6\operating-point-$V2Tag-recommended.json")

# ⑥ v2 QA 点交叉验证（⑬；runpoint 名 = select-op 日志打印的产物，若未传则跳过留人工）
if ($QaopRunpoint -ne "" -and (Test-Path "reports\m6\$QaopRunpoint")) {
  Run-Step "v2-run-qaop" @('scripts\m6_acceptance.py', '--mode', 'run', '--tag', "$V2Tag-qaop", '--head', "checkpoints\m6-$V2Tag", '--runpoint', "reports\m6\$QaopRunpoint")
} else {
  Write-Output "=== [v2-run-qaop] SKIPPED（QaopRunpoint 未指定/不存在——select-op 日志打印后补跑）==="
}

# ⑦ v1-3 效应分解段（⑧ 数据效应 v1-3-v1-2）
Run-Step "v13-dev" @('scripts\m6_infer.py', '--head', "checkpoints\m6-v1-3", '--input', "reports\m6\preds\v13-dev-in.jsonl", '--output', 'reports\m6\preds\v13-dev-out.jsonl')
Run-Step "v13-calib2runpoint" @('scripts\m6_calib_to_runpoint.py', '--calib', 'checkpoints\m6-v1-3\calib.json', '--out', "reports\m6\operating-point-$V13Tag-recommended.json")
Run-Step "v13-run-main" @('scripts\m6_acceptance.py', '--mode', 'run', '--tag', $V13Tag, '--head', 'checkpoints\m6-v1-3', '--runpoint', "reports\m6\operating-point-$V13Tag-recommended.json")

# ⑧ ⑪ suppression A/B（strong-too 变体：OOD 行的 default-PASS 修复路径对照）
Run-Step "v2-strongtoo-variant" @('scripts\m6_make_variant.py', '--base', "reports\m6\operating-point-$V2Tag-recommended.json", '--out', "reports\m6\operating-point-$V2Tag-strongtoo.json", '--suppression', 'strong-too')
Run-Step "v2-run-strongtoo" @('scripts\m6_acceptance.py', '--mode', 'run', '--tag', "$V2Tag-strongtoo", '--head', "checkpoints\m6-$V2Tag", '--runpoint', "reports\m6\operating-point-$V2Tag-strongtoo.json")

Write-Output "=== V2 READINGS CHAIN DONE $(Get-Date -Format HH:mm:ss) ==="
