# -*- coding: utf-8 -*-
r"""重放 .venv 内的 trl 手工补丁（幂等：检测已打则跳过）。

背景（PATCH 2026-09-26，2026-09-28 导出为可重放形式）：
    今晚打进 `.venv\Lib\site-packages\trl` 的两处手工补丁在 venv 重建或
    trl 重装后即丢失，且丢失后 M3 DPO / M3.5 GRPO 的 import 链直接断裂
    （docs/research/grpo-feasibility.md §1.3、docs/02-m0-base-audit.md §0.1 #8/#9）。
    本脚本把补丁以「带完整上下文的精确替换对」形式重放：

        trl_0240_callbacks_mergekit_lazy.py   callbacks.py mergekit 顶层 import 改 lazy
        trl_0240_import_utils_avail_shim.py   import_utils.py 加 _avail() 契约 shim

何时需要重放：
    ① venv 重建（uv venv / 虚拟环境复制后）；
    ② trl 卸载重装（pip/uv 任何形式，包括同版本重装——会覆盖 site-packages 文件）；
    ③ 升级 transformers 前先确认补丁是否仍必要（transformers 修回纯 bool 契约后
      #2 可退役；trl 升到自带两修复的版本后两者均可退役）。

用法（任意 python 均可，不要求 venv 本身可用）：
    python scripts\patches\apply_venv_patches.py                # 应用/校验（默认 venv）
    python scripts\patches\apply_venv_patches.py --venv PATH    # 指定其他 venv 根
    python scripts\patches\apply_venv_patches.py --check        # 只报状态不改文件
    python scripts\patches\apply_venv_patches.py --site-packages PATH   # 直接指 site-packages

行为：
    - 每个补丁逐对检查：目标文本含全部「新」块且不含「旧」块 → 已打，跳过；
    - 否则按序应用（每对要求旧块恰好出现一次），写回时保留原行尾风格；
    - 应用后 compile() 语法自检 + PATCH 标记计数自检；
    - 版本不匹配（非 trl 0.24.0）默认拒绝应用（--force 可强试）。
    - 任何补丁失败 → 退出码 1（发射前校验语义：状态不健康即失败）。

GPU 纪律：纯文本操作，不 import torch/trl，不触 GPU，可在训练运行中使用。
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

PATCH_MODULES = [
    "trl_0240_callbacks_mergekit_lazy.py",
    "trl_0240_import_utils_avail_shim.py",
]

HERE = Path(__file__).resolve().parent


def load_patch_module(fname: str):
    spec = importlib.util.spec_from_file_location(fname[:-3], HERE / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # noqa: SLF001  纯数据模块，无副作用
    return mod


def find_site_packages(args: argparse.Namespace) -> Path:
    if args.site_packages:
        sp = Path(args.site_packages).resolve()
    else:
        venv = Path(args.venv).resolve() if args.venv else HERE.parent.parent / ".venv"
        sp = venv / "Lib" / "site-packages"  # Windows venv 布局
    if not sp.is_dir():
        raise SystemExit(f"[FATAL] site-packages 不存在: {sp}")
    return sp


def installed_trl_version(sp: Path) -> str | None:
    for d in sp.glob("trl-*.dist-info"):
        m = re.match(r"trl-(\d[^+]*)\.dist-info", d.name)
        if m:
            return m.group(1)
    return None


def adapt_line_endings(anchor: str, text: str) -> str:
    r"""锚点按目标文件行尾风格适配（trl wheel 为 LF；防御 CRLF 环境）。"""
    if "\r\n" in text and "\r\n" not in anchor:
        return anchor.replace("\n", "\r\n")
    return anchor


def apply_one(mod, sp: Path, check_only: bool, force: bool) -> tuple[str, str]:
    """返回 (状态, 详情)。状态 ∈ ok-applied / ok-already / error / skipped-version。"""
    target = sp / mod.TARGET
    label = f"{mod.TARGET}  [{mod.NAME}]"
    if not target.is_file():
        return "error", f"{label}: 目标文件不存在"

    with open(target, "r", encoding="utf-8", newline="") as f:  # newline=''：不翻译行尾
        text = f.read()

    olds = [adapt_line_endings(o, text) for o, _ in mod.REPLACEMENTS]
    news = [adapt_line_endings(n, text) for _, n in mod.REPLACEMENTS]

    already = all(n in text for n in news) and not any(o in text for o in olds)
    if already:
        return "ok-already", f"{label}: 已打过（{len(news)} 处替换全部在位），跳过"

    if any(o in text for o in olds) and any(n in text for n in news):
        return "error", f"{label}: 半套状态（部分旧块与部分新块并存），需人工检查"

    if not any(o in text for o in olds):
        return "error", f"{label}: 未打过且找不到任何锚点——文件与 trl {mod.TRL_VERSION} 基线不符"

    ver = installed_trl_version(sp)
    if ver != mod.TRL_VERSION and not force:
        return ("skipped-version",
                f"{label}: 已装 trl {ver} ≠ 补丁基线 {mod.TRL_VERSION}，拒绝应用（--force 可强试）")

    new_text = text
    for i, (old, new) in enumerate(zip(olds, news), 1):
        cnt = new_text.count(old)
        if cnt != 1:
            return "error", f"{label}: 第 {i} 对锚点出现 {cnt} 次（要求恰 1 次），中止未写入"
        new_text = new_text.replace(old, new)

    try:
        compile(new_text, str(target), "exec")  # 语法自检（不执行）
    except SyntaxError as e:
        return "error", f"{label}: 应用后语法检查失败: {e}"

    marker_cnt = new_text.count(mod.MARKER)
    expected_markers = sum(1 for _, n in mod.REPLACEMENTS if mod.MARKER in n)
    if marker_cnt < expected_markers:
        return "error", f"{label}: PATCH 标记计数异常（{marker_cnt} < {expected_markers}）"

    if check_only:
        return "error", f"{label}: --check 模式发现未应用的补丁（上面为将要进行的替换）"

    with open(target, "w", encoding="utf-8", newline="") as f:  # newline=''：保留行尾
        f.write(new_text)
    return "ok-applied", f"{label}: 已应用 {len(news)} 处替换（PATCH 标记 {marker_cnt} 处）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="重放 .venv trl 手工补丁（幂等）")
    ap.add_argument("--venv", default=None, help="venv 根目录（默认 <项目>/.venv）")
    ap.add_argument("--site-packages", default=None, help="直接指定 site-packages（测试用）")
    ap.add_argument("--check", action="store_true", help="只报状态，不写文件（有未打补丁则退出 1）")
    ap.add_argument("--force", action="store_true", help="版本不匹配时仍尝试应用")
    args = ap.parse_args(argv)

    sp = find_site_packages(args)
    ver = installed_trl_version(sp)
    mode = "CHECK" if args.check else "APPLY"
    print(f"[apply_venv_patches] mode={mode}  site-packages={sp}  trl={ver}")
    print()

    failures = 0
    for fname in PATCH_MODULES:
        mod = load_patch_module(fname)
        status, detail = apply_one(mod, sp, args.check, args.force)
        print(f"  [{status}] {detail}")
        if status not in ("ok-applied", "ok-already"):
            failures += 1

    print()
    if failures:
        print(f"结果：{failures} 个补丁未就绪 —— venv 对 M3/M3.5 不可用，先修复再发射")
        return 1
    print("结果：全部补丁在位 —— trl import 链健康（M3 DPO / M3.5 GRPO 前提满足）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
