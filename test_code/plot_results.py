"""从 eval_results_int4_large.json 重新生成图表（修复 matplotlib labels 参数问题）"""
import json
import os
import numpy as np
import matplotlib.pyplot as plt

IMG_DIR = r"e:\Dataset\img"
TAG = "int4_large"
DIALECTS = ["mandarin", "cantonese"]

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

with open(os.path.join(IMG_DIR, f"eval_results_{TAG}.json"), "r", encoding="utf-8") as f:
    all_results = json.load(f)

dialect_labels = ["普通话 (Mandarin)", "粤语 (Cantonese)"]
colors = ["#4C72B0", "#DD8452"]
avg_cers = [all_results[d]["avg_cer"] * 100 for d in DIALECTS]

# 图1：平均 CER 柱状图
fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(dialect_labels, avg_cers, color=colors, width=0.5, edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title("Qwen3-ASR-1.7B (INT4) 各方言平均 CER 对比\n(FLEURS, 每方言 150 条)", fontsize=13, fontweight='bold')
ax.set_ylim(0, max(avg_cers) * 1.3)
for bar, val in zip(bars, avg_cers):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, f"{val:.2f}%",
            ha='center', va='bottom', fontsize=12, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_comparison_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_comparison_{TAG}.png")

# 图2：CER 分布箱线图（修复：labels -> tick_labels）
fig, ax = plt.subplots(figsize=(8, 5))
data = [all_results[d]["cers"] for d in DIALECTS]
bp = ax.boxplot(data, tick_labels=dialect_labels, patch_artist=True, widths=0.5,
                medianprops=dict(color='red', linewidth=2))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_ylabel("CER", fontsize=13)
ax.set_title("各方言 CER 分布 (箱线图, n=150)", fontsize=13, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_boxplot_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_boxplot_{TAG}.png")

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
plt.suptitle("CER 分布直方图 (每方言 150 条)", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_histogram_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_histogram_{TAG}.png")

# 图4：逐样本 CER 折线图
fig, ax = plt.subplots(figsize=(14, 5))
for d, color in zip(DIALECTS, colors):
    cers = all_results[d]["cers"]
    ax.plot(range(len(cers)), [c*100 for c in cers], marker='o', markersize=2,
            label=dialect_labels[DIALECTS.index(d)], color=color, alpha=0.6, linewidth=0.8)
ax.set_xlabel("样本索引", fontsize=12)
ax.set_ylabel("CER (%)", fontsize=12)
ax.set_title("逐样本 CER 对比 (n=150/dialect)", fontsize=13, fontweight='bold')
ax.legend(fontsize=11)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_per_sample_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_per_sample_{TAG}.png")

print("\n=== 评测结果汇总 ===")
for d in DIALECTS:
    print(f"  {d:12s}: CER = {all_results[d]['avg_cer']*100:.2f}%  (n={len(all_results[d]['cers'])})")
