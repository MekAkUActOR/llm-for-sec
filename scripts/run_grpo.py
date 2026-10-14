# -*- coding: utf-8 -*-
r"""M3.5 GRPO 发射脚本（草案骨架 v0 —— 默认只打印计划；未经发射评审不得 --run）。

定位：docs/07-m3-preference-recipe.md §3（M3.5 RLVR / GRPO）+
      docs/research/grpo-feasibility.md §3A 主路线：本仓库 LLaMA-Factory
      0.9.6.dev0 **没有 GRPO 阶段**（stage 仅 pt/sft/rm/ppo/dpo/kto），
      故绕开 LF 直用 TRL 0.24 GRPOTrainer；奖励走自有分量式可验证奖励库
      scripts/rlvr_reward.py（防黑不变量：verdict_correct 0.60 > 格式类
      分量和 0.30，测试锁定）。

超参来源：docs/research/grpo-feasibility.md §3A 配置草稿（0.6B @ RTX
      5090 D 24GB，WDDM 保守包络 §2：~12-16 GB，余量 ≥30%）。
      全部标【待 M3 读数】的项在 M3 DPO 完成后定稿。

数据：data/rlvr/tasks-v01.jsonl（2,000 条 = 4 任务型 × 500；gen_rlvr_tasks.py
      产出，与 SFT/heldout 物理隔离，8-gram 游程 ≤30）。行 schema 已 TRL 就绪：
        messages            [system, user] —— TRL conversational prompt
        reward_task_json    {"task_type", "ground_truth"} 的 JSON 串
        reward_pack         政策包 id
      后两列经 TRL reward-func kwargs 对齐传入 grpo_reward_func
      （单样本缺元数据 → None，TRL 0.24 多任务语义）。

关键契约（源码级核实，2026-09-28）：
  - GRPOTrainer 数据集必须含 "prompt" 列（grpo_trainer.py:164），额外列原样
    传奖励函数；conversational prompt 自动过 chat template（:1086）。
  - beta != 0 → 从同一 model_id 再载一份 ref 模型（:434-438），即
    "KL 锚定到 M3 检查点"（docs/07 §3.3，M1.5 知识层保护）随 beta>0 自动成立；
    beta == 0.0 → 官方跳过 ref（:427-429，省 ~1.2 GB）。与 LF DPO 相反
    （DPO 的 ref 开关是 pref_loss，与 beta 无关）——两阶段行为勿混淆。
  - 无 vllm（venv 未装）→ HF generate 路径，use_vllm 必须 False。

已知开口项（发射评审前必须闭环）：
  1) chat template think 机制：M2/M3 全链用 LF qwen3_nothink（chatml 无
     think）；TRL 对 conversational prompt 用 tokenizer 自带模板渲染。
     --plan 会检查 checkpoint 的 tokenizer.chat_template 是否含 think
     块并告警（含则需换 nothink 等价模板或预渲染 str prompt）。
  2) venv trl 两处手工补丁必须在位（scripts/patches/apply_venv_patches.py
     --check；venv 重建/trl 重装后重放——docs/02 §0.1 #8/#9）。
  3) GRPOConfig 字段冒烟在 --plan 内完成（transformers 5.8 × trl 0.24
     实例化层兼容，grpo-feasibility §4.2 遗留项）。

用法（GPU 纪律：--plan 纯 CPU 可在训练期运行；--run 才触 GPU）：
    python scripts/run_grpo.py --plan
    python scripts/run_grpo.py --plan --model <m3-checkpoint> --tasks data/rlvr/tasks-v01.jsonl
    python scripts/run_grpo.py --run   # ！！！发射评审通过后才允许
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))  # rlvr_reward 同目录导入

# ---------------------------------------------------------------- 常量 --------
DEFAULT_MODEL = r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m3-dpo"  # 【待 M3 读数】M3 产物
DEFAULT_TASKS = ROOT / "data" / "rlvr" / "tasks-v01.jsonl"

# 【待 M3 读数】超区块（grpo-feasibility §3A 草稿值，发射评审时逐项定稿）
HP = {
    # ---- 优化 ----
    "learning_rate": 1.0e-6,        # RL 常规低于 DPO 一档；【待 M3 读数】
    "adam_beta2": 0.98,             # GRPO 社区常用（比 0.999 稳）；【待 M3 读数】
    "warmup_steps": 20,
    "lr_scheduler_type": "constant_with_warmup",  # RL 常用恒 LR；【待 M3 读数】
    # ---- GRPO 结构 ----
    "num_generations": 8,           # 每 prompt 组内采样数（组基线的组）
    "generation_batch_size": 64,    # 一个生成批 = 8 prompt × 8 gens
    "per_device_train_batch_size": 8,   # 每 micro-step 8 个 completion
    "max_prompt_length": 1024,      # 任务实测 prompt 短；防御性上限
    "max_completion_length": 512,   # VERDICT 行 + 推理正文；【待 M3 读数】按 M3 实测输出长度
    "temperature": 1.0,             # 采样温度；【待 M3 读数】（格式稳定性 vs 探索）
    "loss_type": "dapo",            # trl 0.24 默认（长度归一化）；【待 M3 读数】
    "scale_rewards": "group",       # 组内标准化（GRPO 原始设计）
    "beta": 0.04,                   # KL 锚到 M3（docs/07 §3.3）；显存紧张 → 0.0 免 ref（-1.2GB）
    "num_train_epochs": 1.0,        # 2,000 prompt × 8 gens ÷ 8/step ≈ 2,000 步；【待 M3 读数】
    # ---- 工程 ----
    "bf16": True,
    "gradient_checkpointing": True,
    "optim": "adamw_torch_fused",
    "logging_steps": 10,
    "save_steps": 200,              # 可中断无损续训纪律（同 M2/M3：全量 checkpoint）
    "save_total_limit": 2,
}

REWARD_COLUMNS = ("reward_task_json", "reward_pack")  # grpo_reward_func 的 kwargs 列


# ---------------------------------------------------------------- 数据 --------
def load_tasks(path: Path):
    """tasks-v01.jsonl → TRL GRPO 数据集行（prompt=conversational messages）。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            rows.append({
                "prompt": t["messages"],          # TRL conversational prompt
                "reward_task_json": t["reward_task_json"],
                "reward_pack": t["reward_pack"],
            })
    return rows


# ---------------------------------------------------------------- 配置 --------
def build_config(args) -> "GRPOConfig":  # noqa: F821  延迟 import（--plan 不强求）
    from trl import GRPOConfig

    return GRPOConfig(
        output_dir=args.output_dir,
        # ---- 优化【待 M3 读数】----
        learning_rate=HP["learning_rate"],
        adam_beta2=HP["adam_beta2"],
        warmup_steps=HP["warmup_steps"],
        lr_scheduler_type=HP["lr_scheduler_type"],
        # ---- GRPO 结构【待 M3 读数】----
        num_generations=HP["num_generations"],
        generation_batch_size=HP["generation_batch_size"],
        per_device_train_batch_size=HP["per_device_train_batch_size"],
        max_prompt_length=HP["max_prompt_length"],
        max_completion_length=HP["max_completion_length"],
        temperature=HP["temperature"],
        loss_type=HP["loss_type"],
        scale_rewards=HP["scale_rewards"],
        beta=HP["beta"],                    # >0：TRL 自动从同 model_id 载 ref（KL 锚=M3）
        num_train_epochs=HP["num_train_epochs"],
        # ---- 工程 ----
        bf16=HP["bf16"],
        gradient_checkpointing=HP["gradient_checkpointing"],
        optim=HP["optim"],
        logging_steps=HP["logging_steps"],
        save_steps=HP["save_steps"],        # 全量 checkpoint（save_only_model 默认 False）
        save_total_limit=HP["save_total_limit"],
        report_to="none",
        use_vllm=False,                     # venv 无 vllm——HF generate 路径（勿开）
        seed=args.seed,
    )


# ---------------------------------------------------------------- 计划 --------
def plan(args) -> int:
    """纯 CPU：数据装载 + 配置实例化 + 奖励接线自检 + template 预警。不触 GPU。"""
    import datasets

    # 1) venv trl 补丁在位性（不 import trl 也能查文件标记——轻量预检）
    trl_dir = None
    for cand in (ROOT / ".venv" / "Lib" / "site-packages" / "trl",
                 Path(sys.prefix) / "Lib" / "site-packages" / "trl"):
        if cand.is_dir():
            trl_dir = cand
            break
    if trl_dir is None:
        print("[plan] 警告：未找到 site-packages/trl（补丁在位性无法预检）")
    else:
        for rel in ("import_utils.py", r"trainer\callbacks.py"):
            n = (trl_dir / rel).read_text(encoding="utf-8").count("PATCH 2026-09-26")
            expect = 1 if rel == "import_utils.py" else 3
            print(f"[plan] trl 补丁标记 {rel}: {n}/{expect} "
                  f"{'OK' if n == expect else '!! 缺失——先跑 scripts/patches/apply_venv_patches.py'}")

    # 2) 任务装载 → TRL 数据集
    rows = load_tasks(Path(args.tasks))
    ds = datasets.Dataset.from_list(rows)
    print(f"[plan] 任务集: {args.tasks} -> {len(ds)} 行，列 = {ds.column_names}")

    # 3) 奖励接线（import 即冒烟 trl；防黑不变量断言）
    from rlvr_reward import DEFAULT_WEIGHTS, FORMAT_COMPONENTS, grpo_reward_func
    assert DEFAULT_WEIGHTS["verdict_correct"] > sum(
        DEFAULT_WEIGHTS[k] for k in FORMAT_COMPONENTS), "防黑不变量破坏：格式满分+行为错会得正分"
    print(f"[plan] reward_funcs = [rlvr_reward.grpo_reward_func]，权重 = {DEFAULT_WEIGHTS}")

    # 4) GRPOConfig 实例化冒烟（transformers 5.8 × trl 0.24 兼容性，feasibility §4.2）
    cfg = build_config(args)
    print(f"[plan] GRPOConfig OK：lr={cfg.learning_rate} beta={cfg.beta} "
          f"gens={cfg.num_generations} gen_bs={cfg.generation_batch_size} "
          f"loss={cfg.loss_type} scale={cfg.scale_rewards} vllm={cfg.use_vllm}")
    print(f"[plan] ref 模型：{'挂（beta>0，KL 锚=M3 产物，+~1.2GB）' if cfg.beta != 0.0 else '免（beta=0，省 ~1.2GB，无 KL 锚）'}")

    # 5) model 路径与 chat template think 预警（只读文件，不加载权重）
    mp = Path(args.model)
    if not mp.is_dir():
        print(f"[plan] 模型路径不存在（预期——占位【待 M3 读数】）: {mp}")
    else:
        tc = mp / "tokenizer_config.json"
        if tc.is_file():
            tpl = json.loads(tc.read_text(encoding="utf-8")).get("chat_template", "") or ""
            has_think = "think" in tpl
            print(f"[plan] checkpoint chat_template 含 think 块: {has_think} "
                  f"{'!! 开口项 1：需换 nothink 模板或预渲染 str prompt' if has_think else '(与 qwen3_nothink 训练分布一致)'}")

    # 6) 每 epoch 步数估算
    steps = len(ds) * HP["num_generations"] // HP["per_device_train_batch_size"]
    print(f"[plan] 步数估算：{len(ds)} prompt × {HP['num_generations']} gens ÷ "
          f"{HP['per_device_train_batch_size']}/step ≈ {steps} 步/epoch "
          f"(save_steps={HP['save_steps']} → ~{steps // HP['save_steps']} 个 checkpoint)")
    print("[plan] 计划完成（未触 GPU、未训练）。发射评审通过后：--run")
    return 0


# ---------------------------------------------------------------- 发射 --------
def run(args) -> int:
    """实际训练入口——仅在发射评审通过后调用。"""
    import torch
    from datasets import Dataset as HFDataset
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import GRPOTrainer

    from rlvr_reward import grpo_reward_func

    mp = Path(args.model)
    if not mp.is_dir():
        raise SystemExit(f"[FATAL] 模型路径不存在: {mp}（【待 M3 读数】占位未更新？）")

    tokenizer = AutoTokenizer.from_pretrained(mp)
    model = AutoModelForCausalLM.from_pretrained(
        mp,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",   # 本机 flash ✗（M0 审计），sdpa=cudnn 已验证
    )
    train_ds = HFDataset.from_list(load_tasks(Path(args.tasks)))
    cfg = build_config(args)

    trainer = GRPOTrainer(
        model=model,
        reward_funcs=[grpo_reward_func],   # 数据集额外列 → kwargs 对齐传入
        args=cfg,
        train_dataset=train_ds,
        processing_class=tokenizer,
    )
    trainer.train(resume_from_checkpoint=True)  # 可中断续训（save_steps 全量 checkpoint）
    trainer.save_model()
    return 0


# ---------------------------------------------------------------- CLI ---------
# 发射评审开关：M3 读数落地 + 发射评审通过后置 True（当前草案 = False，
# 即 --run 一律拒绝；这是刻意的安全闸，评审时改这一行并跑 --plan 复核）。
LAUNCH_APPROVED = False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="M3.5 GRPO 发射脚本（草案；默认只打印计划不训练）")
    ap.add_argument("--plan", action="store_true", help="只打印计划（CPU，不触 GPU）")
    ap.add_argument("--run", action="store_true",
                    help="实际训练（！！发射评审通过后才允许）")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="M3 产物 checkpoint 路径【待 M3 读数】")
    ap.add_argument("--tasks", default=str(DEFAULT_TASKS),
                    help="RLVR 任务 jsonl（默认 data/rlvr/tasks-v01.jsonl）")
    ap.add_argument("--output-dir",
                    default=r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-m35-grpo",
                    help="输出目录【待 M3 读数】")
    ap.add_argument("--seed", type=int, default=20261001)
    args = ap.parse_args(argv)

    if args.run:
        if not LAUNCH_APPROVED:
            print("!! 发射评审未通过，--run 被拒（草案骨架；见 LAUNCH_APPROVED 注释）。")
            print("!! 流程：M3 读数落地 → 超参定稿 → 发射评审 → 置 LAUNCH_APPROVED=True。")
            return 1
        return run(args)
    return plan(args)  # 默认（含 --plan）均走计划模式：CPU、不训练


if __name__ == "__main__":
    sys.exit(main())
