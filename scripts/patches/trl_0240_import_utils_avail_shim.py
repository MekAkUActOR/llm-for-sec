# -*- coding: utf-8 -*-
"""venv trl 补丁 #2：import_utils.py 的 _avail() 契约 shim（PATCH 2026-09-26）。

问题：
    transformers 5.8 的 `_is_package_available` 返回
    `(bool, version|None)` 元组（即使 return_version=False 也返回二元组）；
    trl 0.24 按旧契约（纯 bool）编写——元组在布尔上下文恒真，
    14 个可用性守卫（deepspeed/fastapi/joblib/liger_kernel/llm_blender/
    math_verify/mergekit/pydantic/requests/unsloth/uvicorn/vllm/vllm_ascend/
    weave）全部失效。直接后果：is_mergekit_available() 恒真 → 补丁 #1 修完
    import 链后 judges.py 顶层 import llm_blender 仍会炸（守卫没拦住）。

修法：
    `_avail()` shim 兼容两种契约：元组解包取 bool；纯 bool 原样
    （version 补 None）。14 个守卫赋值改经 shim。

基线：PyPI wheel trl-0.24.0-py3-none-any.whl。
本文件即当时打进 .venv 的手工补丁的机器可重放形式（源-靶逐字节一致）。
"""

NAME = "trl-0.24.0 import_utils.py _avail() contract shim"
TARGET = r"trl\import_utils.py"  # 相对 site-packages
TRL_VERSION = "0.24.0"
MARKER = "PATCH 2026-09-26"

REPLACEMENTS = [
    # 1) 在 transformers import 与常量区之间插入 _avail shim
    (
        """\
from transformers.utils.import_utils import _is_package_available


LIGER_KERNEL_MIN_VERSION = "0.5.8\"""",
        """\
from transformers.utils.import_utils import _is_package_available


# PATCH 2026-09-26: transformers 5.8 的 _is_package_available 返回 (bool, version|None)
# 元组；trl 0.24 按旧契约（纯 bool）编写——元组在布尔上下文恒真，可用性守卫
# 全部失效（judges.py 顶层 import llm_blender 炸 DPOTrainer import 链）。
# shim 兼容两种契约：元组解包，bool 原样（version 补 None）。
def _avail(pkg: str, return_version: bool = False):
    r = _is_package_available(pkg, return_version=return_version)
    if isinstance(r, tuple):
        ok, ver = r
    else:
        ok, ver = r, None
    return (ok, ver) if return_version else ok


LIGER_KERNEL_MIN_VERSION = "0.5.8\"""",
    ),
    # 2) 14 个守卫赋值改走 _avail（整个赋值块一次替换，防半套状态）
    (
        """\
# Use same as transformers.utils.import_utils
_deepspeed_available = _is_package_available("deepspeed")
_fastapi_available = _is_package_available("fastapi")
_joblib_available = _is_package_available("joblib")
_liger_kernel_available, _liger_kernel_version = _is_package_available("liger_kernel", return_version=True)
_llm_blender_available = _is_package_available("llm_blender")
_math_verify_available = _is_package_available("math_verify")
_mergekit_available = _is_package_available("mergekit")
_pydantic_available = _is_package_available("pydantic")
_requests_available = _is_package_available("requests")
_unsloth_available = _is_package_available("unsloth")
_uvicorn_available = _is_package_available("uvicorn")
_vllm_available, _vllm_version = _is_package_available("vllm", return_version=True)
_vllm_ascend_available = _is_package_available("vllm_ascend")
_weave_available = _is_package_available("weave")""",
        """\
# Use same as transformers.utils.import_utils
_deepspeed_available = _avail("deepspeed")
_fastapi_available = _avail("fastapi")
_joblib_available = _avail("joblib")
_liger_kernel_available, _liger_kernel_version = _avail("liger_kernel", return_version=True)
_llm_blender_available = _avail("llm_blender")
_math_verify_available = _avail("math_verify")
_mergekit_available = _avail("mergekit")
_pydantic_available = _avail("pydantic")
_requests_available = _avail("requests")
_unsloth_available = _avail("unsloth")
_uvicorn_available = _avail("uvicorn")
_vllm_available, _vllm_version = _avail("vllm", return_version=True)
_vllm_ascend_available = _avail("vllm_ascend")
_weave_available = _avail("weave")""",
    ),
]
