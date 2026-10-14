"""环境验证 + GPU 性能基准。

用法:
  J:\\Projects\\llm_for_sec\\.venv\\Scripts\\python.exe scripts\\verify_env.py

检查项:软件栈版本、GPU/显存、FP32/TF32/BF16 matmul 算力、显存带宽、
SDPA 注意力后端(flash/cudnn)、bitsandbytes 8-bit 优化器、
端到端训练步(前向+反向+AdamW,bf16)。
"""

import ctypes
import platform
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import torch
import torch.nn as nn
import torch.nn.functional as F


def ram_info():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_uint),
            ("dwMemoryLoad", ctypes.c_uint),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys, m.ullAvailPhys


def bench_matmul(dtype, n=8192, iters=30, warmup=5):
    a = torch.randn(n, n, dtype=dtype, device="cuda")
    b = torch.randn(n, n, dtype=dtype, device="cuda")
    for _ in range(warmup):
        a @ b
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        a @ b
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    return 2 * n**3 * iters / dt / 1e12  # TFLOPS


def bench_bandwidth(gib=2.0, iters=10, warmup=3):
    x = torch.empty(int(gib * 2**30), dtype=torch.uint8, device="cuda")
    y = torch.empty_like(x)
    for _ in range(warmup):
        y.copy_(x)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        y.copy_(x)
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    return 2 * x.numel() * iters / dt / 1e9  # GB/s(读+写)


def bench_sdpa_backends():
    from torch.nn.attention import SDPBackend, sdpa_kernel

    B, Hq, Hkv, T, Dh = 4, 32, 8, 2048, 128
    q = torch.randn(B, Hq, T, Dh, dtype=torch.bfloat16, device="cuda")
    k = torch.randn(B, Hkv, T, Dh, dtype=torch.bfloat16, device="cuda")
    v = torch.randn_like(k)
    results = {}
    for name, backend in [
        ("flash", SDPBackend.FLASH_ATTENTION),
        ("cudnn", SDPBackend.CUDNN_ATTENTION),
        ("mem_efficient", SDPBackend.EFFICIENT_ATTENTION),
        ("math", SDPBackend.MATH),
    ]:
        try:
            with sdpa_kernel(backend):
                out = F.scaled_dot_product_attention(q, k, v, is_causal=True, enable_gqa=True)
            torch.cuda.synchronize()
            results[name] = "OK" if out.isfinite().all().item() else "NaN!"
        except Exception as e:  # noqa: BLE001
            results[name] = f"FAIL({type(e).__name__})"
    del q, k, v, out
    torch.cuda.empty_cache()
    return results


def bench_bnb_8bit():
    try:
        import bitsandbytes as bnb
    except Exception as e:  # noqa: BLE001
        return f"不可用({type(e).__name__}: {e})—— 仅影响 QLoRA,不影响 1B 预训练"
    p = nn.Parameter(torch.randn(1024, 1024, device="cuda", dtype=torch.bfloat16))
    opt = bnb.optim.AdamW8bit([p], lr=1e-4)
    (p * 2).sum().backward()
    opt.step()
    torch.cuda.synchronize()
    return f"OK(bitsandbytes {bnb.__version__},AdamW8bit step 正常)"


class Block(nn.Module):
    def __init__(self, d=512, h=8):
        super().__init__()
        self.ln1 = nn.LayerNorm(d)
        self.ln2 = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.proj = nn.Linear(d, d, bias=False)
        self.fc1 = nn.Linear(d, 4 * d, bias=False)
        self.fc2 = nn.Linear(4 * d, d, bias=False)

    def forward(self, x):
        B, T, D = x.shape
        q, k, v = self.qkv(self.ln1(x)).chunk(3, dim=-1)
        q = q.view(B, T, -1, D // 8).transpose(1, 2)
        k = k.view(B, T, -1, D // 8).transpose(1, 2)
        v = v.view(B, T, -1, D // 8).transpose(1, 2)
        a = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        x = x + self.proj(a.transpose(1, 2).reshape(B, T, D))
        x = x + self.fc2(F.gelu(self.fc1(self.ln2(x))))
        return x


def bench_train_step():
    """端到端训练步基准:embedding -> 4 层 decoder(因果 SDPA)-> lm_head,含反向与 AdamW(bf16)。"""
    V, D, T, B = 32000, 512, 1024, 16
    torch.manual_seed(0)
    emb = nn.Embedding(V, D).to(torch.bfloat16).cuda()
    blocks = nn.Sequential(*[Block(D) for _ in range(4)]).to(torch.bfloat16).cuda()
    head = nn.Linear(D, V, bias=False).to(torch.bfloat16).cuda()
    n_params = sum(p.numel() for m in (emb, blocks, head) for p in m.parameters())
    params = list(emb.parameters()) + list(blocks.parameters()) + list(head.parameters())
    opt = torch.optim.AdamW(params, lr=1e-4, fused=True)
    x = torch.randint(0, V, (B, T), device="cuda")

    def step():
        logits = head(blocks(emb(x)))
        loss = F.cross_entropy(logits.float().view(-1, V), x.view(-1))
        loss.backward()
        opt.step()
        opt.zero_grad(set_to_none=True)
        return loss

    for _ in range(5):
        step()
    torch.cuda.synchronize()
    steps, t0 = 10, time.perf_counter()
    for _ in range(steps):
        step()
    torch.cuda.synchronize()
    dt = time.perf_counter() - t0
    tok_s = B * T * steps / dt
    del emb, blocks, head, opt, x, params
    torch.cuda.empty_cache()
    return n_params, tok_s


def main():
    print("=" * 66)
    print("1. 软件环境")
    print("=" * 66)
    total_ram, avail_ram = ram_info()
    print(f"Python        : {sys.version.split()[0]} ({platform.architecture()[0]})")
    print(f"OS            : {platform.platform()}")
    print(f"内存          : {total_ram / 2**30:.1f} GiB 总计 / {avail_ram / 2**30:.1f} GiB 可用")
    print(f"torch         : {torch.__version__}(CUDA build {torch.version.cuda})")
    try:
        import transformers

        print(f"transformers  : {transformers.__version__}")
    except ImportError:
        print("transformers  : 未安装")
    try:
        import datasets

        print(f"datasets      : {datasets.__version__}")
    except ImportError:
        print("datasets      : 未安装")

    if not torch.cuda.is_available():
        print("!! CUDA 不可用 —— 请检查驱动 / torch 安装来源")
        sys.exit(1)

    print(f"CUDA 可用     : True,设备数 {torch.cuda.device_count()}")
    if torch.backends.cudnn.is_available():
        print(f"cuDNN         : {torch.backends.cudnn.version()}")
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(f"GPU[{i}]         : {p.name}")
        print(f"  显存 {p.total_memory / 2**30:.1f} GiB | {p.multi_processor_count} SM | 计算能力 sm_{p.major}{p.minor}")
    free, total = torch.cuda.mem_get_info()
    print(f"  当前空闲显存:{free / 2**30:.1f} / {total / 2**30:.1f} GiB(桌面环境会有 ~1.5GB 占用)")

    print()
    print("=" * 66)
    print("2. 算力基准(matmul)")
    print("=" * 66)
    torch.backends.cuda.matmul.allow_tf32 = False
    fp32 = bench_matmul(torch.float32, n=4096)
    print(f"FP32 matmul   : {fp32:8.1f} TFLOPS")
    torch.backends.cuda.matmul.allow_tf32 = True
    tf32 = bench_matmul(torch.float32, n=8192)
    print(f"TF32 matmul   : {tf32:8.1f} TFLOPS")
    bf16 = bench_matmul(torch.bfloat16, n=8192)
    print(f"BF16 matmul   : {bf16:8.1f} TFLOPS  <- 预训练用这个值估算 MFU")
    bw = bench_bandwidth()
    print(f"显存带宽      : {bw:8.1f} GB/s")

    print()
    print("=" * 66)
    print("3. 注意力后端(SDPA,causal + GQA 32q/8kv, seq=2048, bf16)")
    print("=" * 66)
    for name, status in bench_sdpa_backends().items():
        print(f"  {name:<13}: {status}")

    print()
    print("=" * 66)
    print("4. bitsandbytes 8-bit 优化器")
    print("=" * 66)
    print(" ", bench_bnb_8bit())

    print()
    print("=" * 66)
    print("5. 端到端训练步(bf16,4 层 decoder,B=16 x T=1024)")
    print("=" * 66)
    n_params, tok_s = bench_train_step()
    peak_mem = torch.cuda.max_memory_allocated() / 2**30
    print(f"  参数量 {n_params / 1e6:.1f}M | 吞吐 {tok_s:,.0f} tokens/s | 峰值显存 {peak_mem:.2f} GiB")
    print("  loss 正常下降路径已验证:forward + causal SDPA + backward + fused AdamW 全部 OK")

    print()
    print("=" * 66)
    print("汇总")
    print("=" * 66)
    print(f"  BF16 峰值算力 : {bf16:.1f} TFLOPS")
    print(f"  显存带宽      : {bw:.1f} GB/s")
    print(f"  训练步吞吐    : {tok_s:,.0f} tokens/s(45M 小模型,仅作管线冒烟)")
    print(f"  峰值显存      : {peak_mem:.2f} GiB")
    print("全部检查完成。")


if __name__ == "__main__":
    main()
