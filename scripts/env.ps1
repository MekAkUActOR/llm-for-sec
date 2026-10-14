# llm_for_sec 训练环境激活(PowerShell)
# 用法:. J:\Projects\llm_for_sec\scripts\env.ps1
# 注意:若提示执行策略错误,先执行一次
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# 或改用 scripts\env.bat

$ProjectRoot = "J:\Projects\llm_for_sec"

# HuggingFace / torch 缓存指向 J: 盘(已同时写入用户级环境变量)
$env:HF_HOME = "$ProjectRoot\.cache\huggingface"
$env:TORCH_HOME = "$ProjectRoot\.cache\torch"
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"
$env:PYTHONIOENCODING = "utf-8"

# 激活虚拟环境
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

Write-Host "[llm_for_sec] 训练环境已激活" -ForegroundColor Green
python --version
python -c "import torch; print(f'torch {torch.__version__} | CUDA available: {torch.cuda.is_available()}')"
