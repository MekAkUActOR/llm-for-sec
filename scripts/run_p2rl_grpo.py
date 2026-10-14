# -*- coding: utf-8 -*-
r"""P2-RL GRPO 发射脚本（复制改造自 scripts/run_grpo.py M3.5 骨架）。

规格唯一权威：reports/p2rl-grpo-preregistration.md §2（trl 0.24 参数面实测）/ §5
（反 reward-hacking 三防线）/ §7（训练配置草案）/ §8（发射前闭环清单）。

与 M3.5 骨架的差异（逐项对应规格）：
  1. 奖励 = scripts/p2rl_reward.py 五分量 B/C/H/V/D（callable 注入——trl 的
     reward_funcs 若传 str 会被解释为 RM 模型路径 ✗，规格 §2.2 实测）；
  2. 池 = data/rlvr/p2rl-pool-v01.jsonl（p2rl_build_pool.py 产出）：**预渲染
     ChatML 串 prompt**（TRL 对 str prompt 原样使用）——训练/评测渲染零漂移
     = 规格 §7.4 开口项①的解法；soup checkpoint 的 chat_template.jinja 含
     Qwen3 think 机制，str prompt 直接绕开；
  3. 20 条逐字节 parity 发射门（--dry-run 内）：池预渲染串 vs
     secfm.eval.promptfmt.chat_prompt（§8.4）；
  4. 熵/零方差即停监控（防线②）：trl 原生 entropy 指标 + 零方差组率自算
     （callback：每组 k=8 奖励 std=0 占比），即停线 = 滚动 3 窗均值熵 <
     早段参考（step 10–50）×0.35，或零方差组率 >50% 连续 3 窗（任一触发
     即杀训练，回滚至上一 checkpoint——save_steps=25 + save_total_limit=20
     全覆盖，规则 43.5）；
  5. --dry-run（= M3.5 骨架的 --plan，纯 CPU：trl 反射核实 + 配置冒烟 +
     池装载 + 奖励接线 + parity 门 + watchdog 自检 + 步数估算），不触 GPU。

trl 参数面（§2 反射核实，2026-10-08 源码级；本脚本 --dry-run 会再反射一遍
fail-closed 核对）：trl 0.24.0 · transformers 5.8.0 · GRPOTrainer(model,
reward_funcs, args, train_dataset, eval_dataset, processing_class,
reward_processing_classes, callbacks, optimizers, peft_config) ·
GRPOConfig 关键默认 num_generations=8 / beta=0.0 / loss_type="dapo" /
scale_rewards="group" / mask_truncated_completions=False / use_vllm=False /
log_completions=False。

用法（GPU 纪律：--dry-run 纯 CPU 可在训练期运行；--run 才触 GPU）：
    python scripts/run_p2rl_grpo.py --dry-run
    python scripts/run_p2rl_grpo.py --run   # ！！！发射评审通过后才允许
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))  # p2rl_reward 同目录导入
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------- 常量 --------
# 起点：谱系正式起点（v023 判决「回退起点」✓；与 P2.9 数据臂同起点 ⇒ 臂间可比）
DEFAULT_MODEL = r"J:\Projects\llm_for_sec\checkpoints\soup-needlefix-a050"
DEFAULT_POOL = ROOT / "data" / "rlvr" / "p2rl-pool-v01.jsonl"
DEFAULT_OUTPUT = r"J:\Projects\llm_for_sec\checkpoints\qwen3-06b-sec-p2rl-grpo-v1"

# §7.1 训练配置（全部实参钉死；发射评审只读不改）
HP = {
    # ---- GRPO 结构 ----
    "num_generations": 8,            # k=8 ✓（m5-plan v4）
    "generation_batch_size": 64,     # 8 prompt × 8 gens
    "per_device_train_batch_size": 8,
    "gradient_accumulation_steps": 1,
    "max_prompt_length": 2048,       # 默认 512 截多轮骨架 ✗；池 p99=455 兜底
    "max_completion_length": 512,    # == 门禁评测 mnt512 ✓
    "temperature": 1.0,
    "beta": 0.04,                    # KL 锚=起点 checkpoint（自动 ref）；紧张→0.0（-1.2GB）
    "loss_type": "dapo",
    "scale_rewards": "group",
    "num_iterations": 1,             # 严格 on-policy
    "mask_truncated_completions": False,  # 截断交给奖励罚（D 分量），不静默丢弃
    "use_vllm": False,               # venv 无 vllm（实测）——HF generate 路径
    "log_completions": True,         # 采样审计轨迹（reward-hacking 取证）
    # ---- 优化 ----
    "learning_rate": 3.0e-6,        # ★R2 唯一改动（2026-10-14）：1e-6→3e-6——一轮 kl 末值 0.0024≈未训（m5-launch §3.2 遥测 / m5-gates §5 判读）；其余 25 字段逐字不动（预注册 reports/p2rl-round2-preregistration.md）
    "lr_scheduler_type": "constant_with_warmup",
    "warmup_steps": 20,
    "adam_beta2": 0.98,
    "optim": "adamw_torch_fused",
    "max_steps": 300,                # 探针规模；后备变量② 500（§10）
    "bf16": True,
    "gradient_checkpointing": True,
    # ---- 工程与纪律 ----
    "logging_steps": 5,              # 防线②滚动窗口粒度
    "save_steps": 25,                # 病态起点定位分辨率 25 步（m3 教训）
    "save_total_limit": 20,          # ★规则 43.5（§7.3 核算：300/25=12 档，500 步亦不丢档）
    "report_to": "none",
}
LAUNCH_SEED = 20261008
PARITY_SAMPLE_N = 20   # §8.4 渲染 parity 门样本数


# ============================================================ 防线② 监控 =====
class CollapseWatchdog:
    """熵塌缩 / 零方差组率即停（规格 §5 防线②，纯逻辑可注入自检）。

    即停线（任一触发即杀训练）：
      - 滚动 3 个 logging 窗口的均值熵 < 早段参考（step 10–50 均值）× 0.35；
      - 零方差组率（每组 k=8 奖励 std=0 占比）> 50% 连续 3 窗。
    触发后动作：should_training_stop=True + 回滚指令（上一 checkpoint，
    save_steps=25 全覆盖保障可回滚，规则 43.5）。
    """

    ENTROPY_FLOOR_RATIO = 0.35
    ZERO_VAR_TRIGGER = 0.50
    WINDOW = 3
    REF_LO, REF_HI = 10, 50   # 早段参考窗（step 10–50 均值）

    def __init__(self, k: int = 8):
        self.k = k
        self._ref: list[float] = []      # 早段参考熵样本
        self._ent_window: list[float] = []   # 滚动熵窗口
        self._zv_streak = 0              # 零方差连窗计数
        self._pending: list[float] = []  # 奖励残组（跨窗携带）
        self.stats = {"windows": 0, "think_leak": 0, "truncated": 0,
                      "rewards_seen": 0}

    # ---- 熵 / 零方差观测（每 logging 步一调）----
    def observe(self, step: int, entropy: float | None,
                zero_var_rate: float | None) -> str | None:
        """返回触发原因（str）或 None。entropy/zero_var_rate 缺项则跳过该轴。"""
        self.stats["windows"] += 1
        if entropy is not None:
            if self.REF_LO <= step <= self.REF_HI:
                self._ref.append(float(entropy))
            elif step > self.REF_HI:
                self._ent_window.append(float(entropy))
                if len(self._ent_window) > self.WINDOW:
                    self._ent_window.pop(0)
                if len(self._ent_window) == self.WINDOW and self._ref:
                    ref = sum(self._ref) / len(self._ref)
                    cur = sum(self._ent_window) / self.WINDOW
                    if cur < ref * self.ENTROPY_FLOOR_RATIO:
                        return (f"entropy collapse: 3-窗均值 {cur:.4f} < "
                                f"早段参考 {ref:.4f}×{self.ENTROPY_FLOOR_RATIO}"
                                f"（step {step}）——杀训练，回滚上一 checkpoint")
        if zero_var_rate is not None:
            if zero_var_rate > self.ZERO_VAR_TRIGGER:
                self._zv_streak += 1
                if self._zv_streak >= self.WINDOW:
                    return (f"zero-variance groups: 组率 {zero_var_rate:.2f} "
                            f"> {self.ZERO_VAR_TRIGGER} 连续 {self._zv_streak} 窗"
                            f"（step {step}）——杀训练，回滚上一 checkpoint")
            else:
                self._zv_streak = 0
        return None

    # ---- 奖励流观测（reward proxy 每批一调）----
    def record_rewards(self, rewards: list, completions=None,
                       completion_ids=None) -> None:
        vals = [r for r in (rewards or []) if r is not None]
        self.stats["rewards_seen"] += len(vals)
        buf = self._pending + vals
        n_groups = 0
        n_zero = 0
        for i in range(0, len(buf) - self.k + 1, self.k):
            grp = buf[i:i + self.k]
            n_groups += 1
            if len(set(grp)) == 1:
                n_zero += 1
        self._pending = buf[len(buf) - len(buf) % self.k:] if n_groups else buf
        self.last_zero_var_rate = (n_zero / n_groups) if n_groups else None
        # 辅助监控（登记不设闸，§5）：think 泄漏 + 截断率
        if completions:
            for c in completions:
                t = c if isinstance(c, str) else (
                    c[-1].get("content", "") if isinstance(c, list) and c
                    and isinstance(c[-1], dict) else str(c))
                if "<think>" in (t or ""):
                    self.stats["think_leak"] += 1
        if completion_ids:
            for ids in completion_ids:
                if isinstance(ids, list) and len(ids) >= HP[
                        "max_completion_length"]:
                    self.stats["truncated"] += 1

    def drain_zero_var_rate(self) -> float | None:
        rate = getattr(self, "last_zero_var_rate", None)
        self.last_zero_var_rate = None
        return rate


def make_reward_proxy(func, watchdog: CollapseWatchdog):
    """奖励函数包装：原样转发返回值，旁路记录零方差/think 泄漏/截断遥测。"""
    def proxy(completions, prompts=None, **kwargs):
        rewards = func(completions, prompts=prompts, **kwargs)
        watchdog.record_rewards(rewards, completions,
                                kwargs.get("completion_ids"))
        return rewards
    return proxy


def make_callback(watchdog: CollapseWatchdog):
    """TrainerCallback 工厂（延迟 import transformers，--dry-run 不强求）。"""
    from transformers import TrainerCallback

    class CollapseWatchdogCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            logs = logs or {}
            rate = watchdog.drain_zero_var_rate()
            reason = watchdog.observe(state.global_step,
                                      logs.get("entropy"), rate)
            if state.global_step % 50 == 0 or rate is not None:
                print(f"[watchdog] step={state.global_step} "
                      f"entropy={logs.get('entropy')} zv={rate} "
                      f"stats={watchdog.stats}")
            if reason:
                print(f"[watchdog] ★即停触发：{reason}")
                control.should_training_stop = True
            return control

    return CollapseWatchdogCallback()


# ============================================================ 数据装载 --------
def load_pool(path: Path) -> list[dict]:
    """池 jsonl → TRL GRPO 数据集行（prompt=预渲染 ChatML 串，§7.4①）。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            rows.append({
                "prompt": t["prompt"],              # str：TRL 原样使用 ✗
                "p2rl_task_json": t["p2rl_task_json"],
                "reward_pack": t["reward_pack"],
            })
    return rows


def load_pool_full(path: Path) -> list[dict]:
    """池 jsonl 全列装载（parity 门需要 messages/policy_pack/lang）。"""
    return [json.loads(l) for l in
            Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


# ============================================================ 配置 ------------
def build_config(args) -> "GRPOConfig":  # noqa: F821  延迟 import（--dry-run 冒烟）
    from trl import GRPOConfig
    return GRPOConfig(
        output_dir=args.output_dir,
        # ---- GRPO 结构（§7.1）----
        num_generations=HP["num_generations"],
        generation_batch_size=HP["generation_batch_size"],
        per_device_train_batch_size=HP["per_device_train_batch_size"],
        gradient_accumulation_steps=HP["gradient_accumulation_steps"],
        max_prompt_length=HP["max_prompt_length"],
        max_completion_length=HP["max_completion_length"],
        temperature=HP["temperature"],
        beta=HP["beta"],
        loss_type=HP["loss_type"],
        scale_rewards=HP["scale_rewards"],
        num_iterations=HP["num_iterations"],
        mask_truncated_completions=HP["mask_truncated_completions"],
        use_vllm=HP["use_vllm"],
        log_completions=HP["log_completions"],
        # ---- 优化（§7.1）----
        learning_rate=HP["learning_rate"],
        lr_scheduler_type=HP["lr_scheduler_type"],
        warmup_steps=HP["warmup_steps"],
        adam_beta2=HP["adam_beta2"],
        optim=HP["optim"],
        max_steps=HP["max_steps"],
        bf16=HP["bf16"],
        gradient_checkpointing=HP["gradient_checkpointing"],
        # ---- 工程与纪律（§7.1）----
        logging_steps=HP["logging_steps"],
        save_steps=HP["save_steps"],
        save_total_limit=HP["save_total_limit"],
        report_to=HP["report_to"],
        seed=args.seed,
    )


# ============================================================ parity 门 ------
def parity_gate(full_rows: list[dict], n: int = PARITY_SAMPLE_N,
                seed: int = LAUNCH_SEED) -> dict:
    """§8.4 渲染 parity 门：抽 n 条池样本，预渲染串逐字节核对。

    - 全部行：prompt == render_chatml(messages)（自洽）；
    - 单轮行：prompt == promptfmt.chat_prompt(query, pack, lang)（与评测
      渲染入口逐字节一致——规格 §7.4① 发射门原文口径）；
    - 多轮行：头部 system 段 + 尾部末轮 user 段与 chat_prompt 输出逐字节
      一致（promptfmt 无多轮入口，按头尾拼装核对，中间历史段由
      render_chatml 同一函数生成）。
    """
    from p2rl_build_pool import render_chatml
    from secfm.eval.promptfmt import chat_prompt
    rng = random.Random(seed)
    multi = [r for r in full_rows if len(r["messages"]) > 2]
    single = [r for r in full_rows if len(r["messages"]) == 2]
    sample = (rng.sample(single, min(n // 2, len(single))) +
              rng.sample(multi, min(n - n // 2, len(multi))))
    n_single = n_multi = 0
    for r in sample:
        msgs = r["messages"]
        assert r["prompt"] == render_chatml(msgs), r["id"]
        last_user = [m for m in msgs if m["role"] == "user"][-1]
        if len(msgs) == 2:
            assert r["prompt"] == chat_prompt(
                msgs[1]["content"], pack=r["policy_pack"], lang=r["lang"]), \
                f"单轮 parity 破坏: {r['id']}"
            n_single += 1
        else:
            head = chat_prompt("", pack=r["policy_pack"], lang=r["lang"],
                               with_system=True).split("<|im_start|>user")[0]
            assert r["prompt"].startswith(head), r["id"]
            tail = chat_prompt(last_user["content"], pack=r["policy_pack"],
                               lang=r["lang"], with_system=False)
            assert r["prompt"].endswith(tail), r["id"]
            n_multi += 1
    return {"sampled": len(sample), "single_turn": n_single,
            "multi_turn": n_multi}


# ============================================================ watchdog 自检 --
def watchdog_self_check() -> dict:
    """§8.7 熵/零方差监控 callback 自检（构造注入测试，纯逻辑）。"""
    # 1) 健康熵序列：全程 1.0 → 不触发
    wd = CollapseWatchdog(k=8)
    trig = None
    for step in range(5, 301, 5):
        trig = trig or wd.observe(step, 1.0, 0.0)
    assert trig is None, f"健康序列误触发: {trig}"
    # 2) 熵塌缩：早段参考 1.0，step 55 起跌到 0.2 → 3 窗后触发
    wd = CollapseWatchdog(k=8)
    trig = None
    for step in range(5, 301, 5):
        ent = 1.0 if step <= 50 else 0.2
        trig = trig or wd.observe(step, ent, 0.0)
        if trig:
            break
    assert trig and "entropy collapse" in trig, f"熵塌缩未触发: {trig}"
    # 3) 零方差组率：>50% 连续 3 窗 → 触发
    wd = CollapseWatchdog(k=8)
    trig = None
    for step in range(5, 301, 5):
        trig = trig or wd.observe(step, 1.0, 0.7)
        if trig:
            break
    assert trig and "zero-variance" in trig, f"零方差未触发: {trig}"
    # 4) 零方差 2 窗后恢复 → 不触发（streak 复位）
    wd = CollapseWatchdog(k=8)
    trig = None
    for step, zv in zip(range(5, 301, 5), [0.0] * 9 + [0.7, 0.7] + [0.0] * 40):
        trig = trig or wd.observe(step, 1.0, zv)
    assert trig is None, f"两窗尖峰误触发: {trig}"
    # 5) record_rewards：std=0 组计数 + think 泄漏 + 截断遥测
    wd = CollapseWatchdog(k=8)
    wd.record_rewards([0.5] * 8 + [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                      completions=["x" * 10] * 16,
                      completion_ids=[[1] * 512] * 16)
    assert wd.last_zero_var_rate == 0.5, wd.last_zero_var_rate
    wd.record_rewards([0.1, 0.2] * 4,
                      completions=["<think>ponder</think>ok"] * 8,
                      completion_ids=None)
    assert wd.stats["think_leak"] == 8 and wd.stats["truncated"] == 16
    return {"healthy_no_trigger": True, "entropy_collapse_trigger": True,
            "zero_var_trigger": True, "streak_reset": True,
            "telemetry": wd.stats}


# ============================================================ dry-run --------
def dry_run(args) -> int:
    """纯 CPU 干跑：配置校验 + 池装载 + 奖励接线 + parity 门 + 监控自检。"""
    import datasets

    # 1) venv trl 补丁在位性（文件标记轻量预检，沿 M3.5 骨架）
    trl_dir = None
    for cand in (ROOT / ".venv" / "Lib" / "site-packages" / "trl",
                 Path(sys.prefix) / "Lib" / "site-packages" / "trl"):
        if cand.is_dir():
            trl_dir = cand
            break
    if trl_dir is None:
        print("[dry-run] 警告：未找到 site-packages/trl（补丁在位性无法预检）")
    else:
        for rel in ("import_utils.py", r"trainer\callbacks.py"):
            n_ = (trl_dir / rel).read_text(encoding="utf-8").count(
                "PATCH 2026-09-26")
            expect = 1 if rel == "import_utils.py" else 3
            print(f"[dry-run] trl 补丁标记 {rel}: {n_}/{expect} "
                  f"{'OK' if n_ == expect else '!! 缺失——先跑 scripts/patches/apply_venv_patches.py'}")

    # 2) trl 参数面反射核实（规格 §2——不猜 ✗；字段缺失 = fail-closed）
    import dataclasses
    import trl
    import transformers
    from trl import GRPOConfig, GRPOTrainer
    print(f"[dry-run] trl {trl.__version__} · transformers "
          f"{transformers.__version__}")
    fields = {f.name: f.default for f in dataclasses.fields(GRPOConfig)}
    missing = [k for k in HP if k not in fields]
    assert not missing, f"GRPOConfig 缺规格字段（trl 版本漂移？）: {missing}"
    sig_params = set(
        __import__("inspect").signature(GRPOTrainer.__init__).parameters)
    for p in ("model", "reward_funcs", "args", "train_dataset",
              "processing_class", "callbacks"):
        assert p in sig_params, f"GRPOTrainer.__init__ 缺参数 {p}"
    defaults_note = {k: fields[k] for k in (
        "num_generations", "beta", "loss_type", "scale_rewards",
        "mask_truncated_completions", "use_vllm", "log_completions")}
    print(f"[dry-run] 反射 OK：HP {len(HP)} 字段全在 GRPOConfig；"
          f"GRPOTrainer 签名含 reward_funcs/callbacks ✓")
    print(f"[dry-run] §2 默认值对照（信息性）：{defaults_note}")

    # 3) GRPOConfig 实例化冒烟（transformers 5.8 × trl 0.24，§7.4③）
    cfg = build_config(args)
    print(f"[dry-run] GRPOConfig OK：lr={cfg.learning_rate} beta={cfg.beta} "
          f"gens={cfg.num_generations} gen_bs={cfg.generation_batch_size} "
          f"pdtbs={cfg.per_device_train_batch_size} "
          f"loss={cfg.loss_type} scale={cfg.scale_rewards} "
          f"max_steps={cfg.max_steps} "
          f"save={cfg.save_steps}/keep{cfg.save_total_limit} "
          f"vllm={cfg.use_vllm} log_comp={cfg.log_completions}")
    print(f"[dry-run] ref 模型：{'挂（beta>0，KL 锚=起点 checkpoint，+~1.2GB）'
          if cfg.beta != 0.0 else '免（beta=0，省 ~1.2GB，无 KL 锚）'}")

    # 4) 池装载（str prompt + reward kwargs 列）
    pool_path = Path(args.pool)
    assert pool_path.is_file(), f"池不存在: {pool_path}（先跑 p2rl_build_pool.py）"
    full_rows = load_pool_full(pool_path)
    rows = load_pool(pool_path)
    ds = datasets.Dataset.from_list(rows)
    for col in ("prompt", "p2rl_task_json", "reward_pack"):
        assert col in ds.column_names, f"池缺列 {col}"
    assert ds.num_rows == 3000, f"池行数 {ds.num_rows} != 3000"
    assert all(isinstance(p, str) and p.startswith("<|im_start|>")
               for p in ds["prompt"][:50]), "prompt 非预渲染 ChatML 串"
    print(f"[dry-run] 池装载：{pool_path.name} → {ds.num_rows} 行，"
          f"列 = {ds.column_names}（prompt=预渲染 ChatML str ✓）")

    # 5) 奖励接线（callable 注入 + 防黑不变量 + 双样本冒烟）
    from p2rl_reward import NON_B_WEIGHT_SUM, W_B, grpo_reward_func
    assert W_B > NON_B_WEIGHT_SUM, "防黑不变量 I 破坏"
    smoke = grpo_reward_func(
        ["正文可判读的回答文本，逐项核对完毕，结论如下。\nVERDICT: " +
         json.dumps({"action": "answer", "verdict": "clean",
                     "confidence": 0.9, "findings": ["无"],
                     "policy": "default"}, ensure_ascii=False)] * 2,
        p2rl_task_json=[full_rows[0]["p2rl_task_json"],
                        full_rows[-1]["p2rl_task_json"]],
        reward_pack=[full_rows[0]["reward_pack"], full_rows[-1]["reward_pack"]])
    assert len(smoke) == 2 and all(isinstance(x, float) for x in smoke)
    print(f"[dry-run] reward_funcs = [p2rl_reward.grpo_reward_func]（callable "
          f"注入 ✓）；不变量 I：w_B={W_B} > 其余和={NON_B_WEIGHT_SUM} ✓；"
          f"双样本冒烟 = {smoke}")

    # 6) 渲染 parity 门（§8.4，20 条逐字节）
    par = parity_gate(full_rows, PARITY_SAMPLE_N)
    print(f"[dry-run] parity 门：抽样 {par['sampled']} 条（单轮 "
          f"{par['single_turn']} + 多轮 {par['multi_turn']}）逐字节一致 ✓")

    # 7) 熵/零方差监控自检（§8.7 构造注入）
    wsc = watchdog_self_check()
    ok = (wsc["healthy_no_trigger"] and wsc["entropy_collapse_trigger"]
          and wsc["zero_var_trigger"] and wsc["streak_reset"])
    assert ok, f"watchdog 自检失败: {wsc}"
    print(f"[dry-run] watchdog 自检 OK（健康不触发/熵塌缩触发/零方差触发/"
          f"streak 复位；遥测示例 {wsc['telemetry']}）")

    # 8) 步数与 checkpoint 核算（§7.3）
    steps = HP["max_steps"]
    ckpts = steps // HP["save_steps"]
    prompts_seen = steps * HP["per_device_train_batch_size"] // HP[
        "num_generations"]
    assert ckpts <= HP["save_total_limit"], "save_total_limit 不足以保留全部档"
    print(f"[dry-run] 步数核算：{steps} 步 × "
          f"{HP['per_device_train_batch_size']} completions/步 ÷ k="
          f"{HP['num_generations']} ≈ {prompts_seen} prompt（池 3000 的 "
          f"{prompts_seen / 3000:.0%}）；checkpoint {ckpts} 个（save_steps="
          f"{HP['save_steps']}）≤ save_total_limit={HP['save_total_limit']} ✓")

    # 9) chat template think 预警（§7.4①——str prompt 已绕开，登记不阻塞）
    mp = Path(args.model)
    tpl = ""
    jinja = mp / "chat_template.jinja"
    tc = mp / "tokenizer_config.json"
    if jinja.is_file():
        tpl = jinja.read_text(encoding="utf-8")
    elif tc.is_file():
        tpl = json.loads(tc.read_text(encoding="utf-8")).get(
            "chat_template", "") or ""
    else:
        print(f"[dry-run] 模型路径/chat template 不存在（占位检查跳过）: {mp}")
    if tpl:
        has_think = "think" in tpl
        print(f"[dry-run] 起点 chat_template 含 think 机制: {has_think} "
              f"{'（已用预渲染 str prompt 绕开——训练/评测渲染零漂移 ✓）'
              if has_think else '(与 qwen3_nothink 一致)'}")

    print("[dry-run] 全绿：配置冒烟 + 池装载 + 奖励接线 + parity 门 + "
          "watchdog 自检 + 步数核算（未触 GPU、未训练）。"
          "发射评审通过后：--run")
    return 0


# ============================================================ 发射 ------------
def run(args) -> int:
    """实际训练入口——仅在发射评审通过后调用（GPU 独占纪律，规则 45.2）。"""
    import torch
    from datasets import Dataset as HFDataset
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import GRPOTrainer

    from p2rl_reward import grpo_reward_func

    mp = Path(args.model)
    if not mp.is_dir():
        raise SystemExit(f"[FATAL] 模型路径不存在: {mp}")
    pool_path = Path(args.pool)
    if not pool_path.is_file():
        raise SystemExit(f"[FATAL] 池不存在: {pool_path}（先跑 p2rl_build_pool.py）")

    # 发射门复核（--dry-run 的核心断言在发射路径再走一遍，防漂移）
    parity_gate(load_pool_full(pool_path), PARITY_SAMPLE_N)
    watchdog_self_check()

    tokenizer = AutoTokenizer.from_pretrained(mp)
    model = AutoModelForCausalLM.from_pretrained(
        mp, dtype=torch.bfloat16,
        attn_implementation="sdpa",  # 本机 flash ✗（M0 审计），sdpa=cudnn 已验证
    )
    # 2026-10-14 勘误修复 ②（父代理批准方案 b）：trl 0.24 GRPOTrainer.__init__ L406 在
    # super().__init__ 之前写 model.warnings_issued["estimate_tokens"]——该属性是
    # transformers 4.x PreTrainedModel 的，5.8 全包已移除（grep 零命中）⇒ AttributeError
    # 首发必炸（attempt-1 现场：reports/logs/m5b-grpo-train-attempt1-warnings-issued.log）。
    # 调用侧垫片：预设空 dict 满足 trl 的写入语义（告警抑制标志位）；transformers 5.8
    # 侧无人读该 dict ⇒ 功能无损。HP/奖励/watchdog/LAUNCH_APPROVED 安全闸零触碰 ✗✓。
    model.warnings_issued = {}
    train_ds = HFDataset.from_list(load_pool(pool_path))
    cfg = build_config(args)
    wd = CollapseWatchdog(k=HP["num_generations"])
    trainer = GRPOTrainer(
        model=model,
        reward_funcs=[make_reward_proxy(grpo_reward_func, wd)],  # callable 注入
        args=cfg,
        train_dataset=train_ds,
        processing_class=tokenizer,
        callbacks=[make_callback(wd)],  # 防线②：熵/零方差即停
    )
    # 2026-10-14 勘误修复（父代理批准方案 a）：原 `resume_from_checkpoint=True` 在
    # transformers 5.8 语义 = "必须找到 checkpoint"（trainer.py L1405-1408：bool True
    # ⇒ get_last_checkpoint(output_dir)，返回 None ⇒ raise ValueError）——output_dir
    # 无档时首发必炸（本脚本 --run 从未真跑过，--dry-run 不覆盖 train() 调用，故未
    # 暴露）。改为自适应：有档 ⇒ 续训（保留原「可中断续训（save_steps 全量档）」
    # 语义）；无档 ⇒ fresh 首发。HP/奖励/watchdog/LAUNCH_APPROVED 安全闸零触碰 ✗✓。
    from transformers.trainer_utils import get_last_checkpoint  # 延迟 import（--dry-run 不强求）
    last_ckpt = (get_last_checkpoint(args.output_dir)
                 if Path(args.output_dir).is_dir() else None)
    trainer.train(resume_from_checkpoint=last_ckpt)
    trainer.save_model()
    return 0


# ============================================================ CLI -------------
# 发射评审开关：预注册 §8 清单全绿 + 发射评审通过后置 True（当前 = False，
# 即 --run 一律拒绝；这是刻意的安全闸，评审时改这一行并重跑 --dry-run 复核）。
# 2026-10-13 置 True（按上注设计路径，闸逻辑不动 ✗）：所有者已批准 M5 双臂发射
# + spotcheck 门闭环（60 行已批 ✓）；§8 清单 ①–⑦ 全绿（p2rl-impl.md §5 表，
# 2026-10-08）+ ⑧ GPU Guard/PREFLIGHT 于发射日执行；launch_audit A2/B2/C2 PASS
# （2026-10-13，reports/launch-audit-m5-launch.json）。
LAUNCH_APPROVED = True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="P2-RL GRPO 发射脚本（默认 --dry-run 干跑，不触 GPU）")
    ap.add_argument("--dry-run", "--plan", dest="mode", action="store_true",
                    default=True, help="干跑配置校验（CPU，不触 GPU，默认）")
    ap.add_argument("--run", dest="mode", action="store_false",
                    help="实际训练（！！发射评审通过后才允许）")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="起点 checkpoint（谱系正式起点 soup-needlefix-a050）")
    ap.add_argument("--pool", default=str(DEFAULT_POOL),
                    help="P2-RL 池 jsonl（默认 data/rlvr/p2rl-pool-v01.jsonl）")
    ap.add_argument("--output-dir", default=DEFAULT_OUTPUT,
                    help="输出目录（§7.1：qwen3-06b-sec-p2rl-grpo-v1）")
    ap.add_argument("--seed", type=int, default=LAUNCH_SEED)
    args = ap.parse_args(argv)

    if not args.mode:  # --run
        if not LAUNCH_APPROVED:
            print("!! 发射评审未通过，--run 被拒（预注册 §8 清单须全绿）。")
            print("!! 流程：单测全绿 → 池隔离扫描绿 → parity 门绿 → "
                  "watchdog 自检绿 → 发射评审 → 置 LAUNCH_APPROVED=True。")
            return 1
        return run(args)
    return dry_run(args)


if __name__ == "__main__":
    sys.exit(main())
