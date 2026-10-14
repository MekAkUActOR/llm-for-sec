r"""带分块 CE 补丁的 LLaMA-Factory 启动器。

用法（替代 llamafactory-cli）：

    python -X utf8 scripts\run_lf_with_chunked_ce.py train configs\m16-32k.yaml

先 import 补丁（类级替换 Qwen3ForCausalLM.forward——此后 LF 无论何时
实例化模型都吃到分块 CE），再把 argv 原样交给 llamafactory.cli。

可逆性：补丁只改 loss 路径；CHUNKED_CE_DISABLE=1 可在本启动器下
禁用（等价裸 llamafactory-cli，用于对照/复现 OOM）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import patch_chunked_ce  # noqa: E402,F401  import 即 patch

if os.environ.get("CHUNKED_CE_DISABLE") == "1":
    patch_chunked_ce.unpatch()
    print("[run_lf_with_chunked_ce] CHUNKED_CE_DISABLE=1 → 分块 CE 未启用"
          "（裸 LF 行为）")
else:
    print(f"[run_lf_with_chunked_ce] 分块 CE 已启用：chunk="
          f"{patch_chunked_ce.CHUNK} 位置/块，"
          f"类={[c.__name__ for c, _ in patch_chunked_ce._PATCHED]}")


def main() -> int:
    from llamafactory.cli import main as lf_main
    # LF cli.main() 自读 sys.argv[1:]——argv 原样保留即可
    return lf_main()


if __name__ == "__main__":
    sys.exit(main())
