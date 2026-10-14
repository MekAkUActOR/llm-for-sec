@echo off
REM llm_for_sec 训练环境激活(cmd / Windows Terminal)
REM 用法:J:\Projects\llm_for_sec\scripts\env.bat

set HF_HOME=J:\Projects\llm_for_sec\.cache\huggingface
set TORCH_HOME=J:\Projects\llm_for_sec\.cache\torch
set HF_HUB_ENABLE_HF_TRANSFER=1
set PYTHONIOENCODING=utf-8

call J:\Projects\llm_for_sec\.venv\Scripts\activate.bat

echo [llm_for_sec] training env ready
python --version
python -c "import torch; print(f'torch {torch.__version__} | CUDA available: {torch.cuda.is_available()}')"
