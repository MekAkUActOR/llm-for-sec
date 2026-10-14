# -*- coding: utf-8 -*-
"""venv trl 补丁 #1：callbacks.py mergekit 顶层 import 改 lazy（PATCH 2026-09-26）。

问题（docs/research/grpo-feasibility.md §1.3 实测）：
    trl/trainer/callbacks.py 顶层 `from ..mergekit_utils import MergeConfig,
    merge_models, upload_model_to_hf` 在 mergekit 未安装时炸整条
    DPOTrainer/GRPOTrainer import 链（mergekit 0.1.4 × 现装 pydantic 死路，
    全依赖安装会连带升级 accelerate/huggingface_hub —— 训练期禁做）。

修法：
    导入下沉到实际使用处（MergeModelCallback.__init__ /
    _merge_and_maybe_push）。该类自身已有 is_mergekit_available 守卫，
    不影响任何功能路径（我们不用 merge 回调）。

基线：PyPI wheel trl-0.24.0-py3-none-any.whl（与 GitHub tag v0.24.0 一致）。
本文件即当时打进 .venv 的手工补丁的机器可重放形式（源-靶逐字节一致）。
"""

NAME = "trl-0.24.0 callbacks.py mergekit lazy-import"
TARGET = r"trl\trainer\callbacks.py"  # 相对 site-packages
TRL_VERSION = "0.24.0"
MARKER = "PATCH 2026-09-26"

# (old, new) 精确替换对；每对要求在目标文件中恰好出现一次。
REPLACEMENTS = [
    # 1) 删除顶层 mergekit_utils import，原位留 PATCH 说明
    (
        """\
from ..import_utils import is_mergekit_available, is_weave_available
from ..mergekit_utils import MergeConfig, merge_models, upload_model_to_hf
from ..models.utils import unwrap_model_for_generation
from .judges import BasePairwiseJudge
from .utils import log_table_to_comet_experiment


if is_rich_available():""",
        """\
from ..import_utils import is_mergekit_available, is_weave_available
from ..models.utils import unwrap_model_for_generation
from .judges import BasePairwiseJudge
from .utils import log_table_to_comet_experiment

# PATCH 2026-09-26: mergekit lazy-import —— 顶层导入 mergekit_utils 会在 mergekit
# 未安装时炸掉整条 DPOTrainer import 链（callbacks -> mergekit_utils -> mergekit）。
# MergeModelCallback 自身已有 is_mergekit_available 守卫，此补丁将导入下沉到
# 实际使用处（__init__ / _merge_and_maybe_push），不影响任何功能路径。


if is_rich_available():""",
    ),
    # 2) MergeModelCallback.__init__ 内 lazy import MergeConfig
    (
        """\
        if not is_mergekit_available():
            raise ImportError(
                "MergeModelCallback requires the `mergekit` extra. To install, run `pip install mergekit`."
            )
        self.merge_config = merge_config or MergeConfig()""",
        """\
        if not is_mergekit_available():
            raise ImportError(
                "MergeModelCallback requires the `mergekit` extra. To install, run `pip install mergekit`."
            )
        from ..mergekit_utils import MergeConfig  # PATCH 2026-09-26: lazy import

        self.merge_config = merge_config or MergeConfig()""",
    ),
    # 3) _merge_and_maybe_push 内 lazy import merge_models / upload_model_to_hf
    (
        """\
        merge_path = os.path.join(checkpoint_path, "merged")

        merge_models(self.merge_config.create(), merge_path)""",
        """\
        merge_path = os.path.join(checkpoint_path, "merged")

        from ..mergekit_utils import merge_models, upload_model_to_hf  # PATCH 2026-09-26: lazy import

        merge_models(self.merge_config.create(), merge_path)""",
    ),
]
