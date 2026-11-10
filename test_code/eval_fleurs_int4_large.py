"""
FLEURS 方言评测：Qwen3-ASR-1.7B (INT4/NF4, 全量 GPU)
大数据量版本：每方言 150 条，总耗时约 20 分钟。
脚本：test_code/eval_fleurs_int4_large.py
图表：img/cer_comparison_int4_large.png 等
"""
import os
import json
import time
import re
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import soundfile as sf
import matplotlib.pyplot as plt
from qwen_asr import Qwen3ASRModel

# ========== 配置 ==========
MODEL_PATH = r"e:\Dataset\models\Qwen3-ASR-1.7B"
FLEURS_DIR = r"e:\Dataset\fleurs"
IMG_DIR = r"e:\Dataset\img"
SAMPLES_PER_LANG = 150
DIALECTS = ["mandarin", "cantonese"]
TAG = "int4_large"  # 文件名后缀，与之前的评测区分

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ========== CER 计算 ==========
def cer(ref: str, hyp: str) -> float:
    n = len(ref)
    if n == 0:
        return 0.0 if len(hyp) == 0 else 1.0
    dp = [[0] * (len(hyp) + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp) + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i-1] == hyp[j-1] else 1
            dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)
    return dp[n][len(hyp)] / n

# ========== 文本归一化 ==========
_DIGIT_MAP = {'0':'零','1':'一','2':'二','3':'三','4':'四','5':'五',
              '6':'六','7':'七','8':'八','9':'九'}

def normalize(text: str) -> str:
    text = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z]', '', text)
    result = []
    for ch in text:
        result.append(_DIGIT_MAP.get(ch, ch))
    return ''.join(result)

# ========== 主流程 ==========
print("=" * 60, flush=True)
print(f"Qwen3-ASR-1.7B INT4 评测 (FLEURS, {SAMPLES_PER_LANG} samples/dialect)", flush=True)
print("=" * 60, flush=True)

# 加载模型（INT4，全量 GPU）
print("\n[1/3] Loading model (INT4/NF4, full GPU)...", flush=True)
t0 = time.time()
model = Qwen3ASRModel.from_pretrained(
    MODEL_PATH,
    device_map="cuda:0",
    load_in_4bit=True,
)
import torch
print(f"  Model loaded in {time.time()-t0:.1f}s", flush=True)
print(f"  GPU memory: {torch.cuda.memory_allocated()/1024**3:.2f} GB", flush=True)

# 评测
print(f"\n[2/3] Evaluating {SAMPLES_PER_LANG} samples per dialect...", flush=True)
all_results = {}
total_start = time.time()

for dialect in DIALECTS:
    print(f"\n  --- {dialect} ---", flush=True)
    with open(os.path.join(FLEURS_DIR, dialect, "transcripts.json"), "r", encoding="utf-8") as f:
        records = json.load(f)

    records = records[:SAMPLES_PER_LANG]
    cers = []
    detailed = []
    t_dialect = time.time()

    for idx, rec in enumerate(records):
        wav_path = os.path.join(FLEURS_DIR, dialect, "audio", rec["wav"])
        arr, sr = sf.read(wav_path)
        ref_text = rec["text"]

        t1 = time.time()
        out = model.transcribe((arr, sr))
        elapsed = time.time() - t1

        if isinstance(out, list) and len(out) > 0:
            hyp_text = getattr(out[0], "text", str(out[0]))
        elif isinstance(out, str):
            hyp_text = out
        else:
            hyp_text = getattr(out, "text", str(out))

        ref_norm = normalize(ref_text)
        hyp_norm = normalize(hyp_text)
        c = cer(ref_norm, hyp_norm)
        cers.append(c)
        detailed.append({
            "idx": idx, "cer": round(c, 4), "time": round(elapsed, 1),
            "ref": ref_text, "hyp": hyp_text,
        })
        if idx % 10 == 0:
            print(f"    [{idx:3d}] CER={c*100:6.2f}%  ({elapsed:5.1f}s)", flush=True)

    avg_cer = float(np.mean(cers))
    all_results[dialect] = {
        "avg_cer": avg_cer,
        "cers": cers,
        "detailed": detailed,
    }
    print(f"  >>> {dialect}: avg CER = {avg_cer*100:.2f}%  (n={len(cers)}, {time.time()-t_dialect:.0f}s)", flush=True)

total_time = time.time() - total_start
print(f"\n  Total eval time: {total_time:.0f}s ({total_time/60:.1f} min)", flush=True)

# 保存结果 JSON
os.makedirs(IMG_DIR, exist_ok=True)
with open(os.path.join(IMG_DIR, f"eval_results_{TAG}.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# ========== 作图 ==========
print("\n[3/3] Generating plots...", flush=True)

# 图1：平均 CER 柱状图
fig, ax = plt.subplots(figsize=(8, 5))
dialect_labels = ["普通话 (Mandarin)", "粤语 (Cantonese)"]
avg_cers = [all_results[d]["avg_cer"] * 100 for d in DIALECTS]
colors = ["#4C72B0", "#DD8452"]
bars = ax.bar(dialect_labels, avg_cers, color=colors, width=0.5, edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title(f"Qwen3-ASR-1.7B (INT4) 各方言平均 CER 对比\n(FLEURS, 每方言 {SAMPLES_PER_LANG} 条, {total_time/60:.0f}分钟)", fontsize=13, fontweight='bold')
ax.set_ylim(0, max(avg_cers) * 1.3)
for bar, val in zip(bars, avg_cers):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2, f"{val:.2f}%",
            ha='center', va='bottom', fontsize=12, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_comparison_{TAG}.png"), dpi=150)
plt.close()
print(f"  Saved: cer_comparison_{TAG}.png", flush=True)

# 图2：CER 分布箱线图
fig, ax = plt.subplots(figsize=(8, 5))
data = [all_results[d]["cers"] for d in DIALECTS]
bp = ax.boxplot(data, labels=dialect_labels, patch_artist=True, widths=0.5,
                medianprops=dict(color='red', linewidth=2))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_ylabel("CER", fontsize=13)
ax.set_title(f"各方言 CER 分布 (箱线图, n={SAMPLES_PER_LANG})", fontsize=13, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_boxplot_{TAG}.png"), dpi=150)
plt.close()
print(f"  Saved: cer_boxplot_{TAG}.png", flush=True)

# 图3：CER 分布直方图
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
for ax, d, color, label in zip(axes, DIALECTS, colors, dialect_labels):
    cers_pct = [c * 100 for c in all_results[d]["cers"]]
    ax.hist(cers_pct, bins=20, color=color, alpha=0.7, edgecolor='black')
    ax.axvline(all_results[d]["avg_cer"]*100, color='red', linestyle='--', linewidth=2,
               label=f"平均 CER={all_results[d]['avg_cer']*100:.2f}%")
    ax.set_xlabel("CER (%)", fontsize=12)
    ax.set_ylabel("样本数", fontsize=12)
    ax.set_title(label, fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
plt.suptitle(f"CER 分布直方图 (每方言 {SAMPLES_PER_LANG} 条)", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_histogram_{TAG}.png"), dpi=150)
plt.close()
print(f"  Saved: cer_histogram_{TAG}.png", flush=True)

# 图4：逐样本 CER 折线图
fig, ax = plt.subplots(figsize=(14, 5))
for d, color in zip(DIALECTS, colors):
    cers = all_results[d]["cers"]
    ax.plot(range(len(cers)), [c*100 for c in cers], marker='o', markersize=2,
            label=dialect_labels[DIALECTS.index(d)], color=color, alpha=0.6, linewidth=0.8)
ax.set_xlabel("样本索引", fontsize=12)
ax.set_ylabel("CER (%)", fontsize=12)
ax.set_title(f"逐样本 CER 对比 (n={SAMPLES_PER_LANG}/dialect)", fontsize=13, fontweight='bold')
ax.legend(fontsize=11)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_per_sample_{TAG}.png"), dpi=150)
plt.close()
print(f"  Saved: cer_per_sample_{TAG}.png", flush=True)

print("\n" + "=" * 60, flush=True)
print("评测完成！", flush=True)
for d in DIALECTS:
    print(f"  {d:12s}: CER = {all_results[d]['avg_cer']*100:.2f}%", flush=True)
print(f"\n图表保存在: {IMG_DIR}", flush=True)
print(f"  cer_comparison_{TAG}.png")
print(f"  cer_boxplot_{TAG}.png")
print(f"  cer_histogram_{TAG}.png")
print(f"  cer_per_sample_{TAG}.png")
print("=" * 60, flush=True)
