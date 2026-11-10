"""
繁简归一化后重新计算 CER（不重跑模型，直接用已有 JSON 结果）
对粤语的繁体 ref 和简体 hyp 统一转简体后重算 CER。
输出图表带 _normalized 后缀，与之前的区分开。
"""
import json
import os
import re
import numpy as np
import matplotlib.pyplot as plt
from opencc import OpenCC

IMG_DIR = r"e:\Dataset\img"
SRC_JSON = os.path.join(IMG_DIR, "eval_results_int4_large.json")
TAG = "int4_normalized"

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 繁简转换器：繁体 -> 简体
cc = OpenCC('t2s')

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

_DIGIT_MAP = {'0':'零','1':'一','2':'二','3':'三','4':'四','5':'五',
              '6':'六','7':'七','8':'八','9':'九'}

def normalize(text: str) -> str:
    # 1. 繁体转简体
    text = cc.convert(text)
    # 2. 去标点
    text = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z]', '', text)
    # 3. 阿拉伯数字转中文
    result = []
    for ch in text:
        result.append(_DIGIT_MAP.get(ch, ch))
    return ''.join(result)

# 读取已有结果
with open(SRC_JSON, "r", encoding="utf-8") as f:
    all_results = json.load(f)

DIALECTS = ["mandarin", "cantonese"]
dialect_labels = ["普通话 (Mandarin)", "粤语 (Cantonese)"]
colors = ["#4C72B0", "#DD8452"]

print("重新计算 CER（繁简归一化 + 数字归一化）...")
for d in DIALECTS:
    new_cers = []
    for item in all_results[d]["detailed"]:
        ref_norm = normalize(item["ref"])
        hyp_norm = normalize(item["hyp"])
        c = cer(ref_norm, hyp_norm)
        new_cers.append(c)
        item["cer_normalized"] = round(c, 4)
    all_results[d]["cers_normalized"] = new_cers
    all_results[d]["avg_cer_normalized"] = float(np.mean(new_cers))
    old = all_results[d]["avg_cer"] * 100
    new = all_results[d]["avg_cer_normalized"] * 100
    print(f"  {d:12s}: {old:.2f}% -> {new:.2f}%  (Δ={old-new:+.2f}%)")

# 保存
with open(os.path.join(IMG_DIR, f"eval_results_{TAG}.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# ===== 作图 =====
avg_cers = [all_results[d]["avg_cer_normalized"] * 100 for d in DIALECTS]
avg_cers_old = [all_results[d]["avg_cer"] * 100 for d in DIALECTS]

# 图1：归一化前后对比柱状图
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(DIALECTS))
width = 0.35
bars1 = ax.bar(x - width/2, avg_cers_old, width, label="原始 CER", color="#999999", edgecolor='black', linewidth=0.8)
bars2 = ax.bar(x + width/2, avg_cers, width, label="繁简归一化后 CER", color=colors, edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title("繁简归一化对 CER 的影响 (Qwen3-ASR-1.7B INT4, FLEURS, n=150)", fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(dialect_labels, fontsize=12)
ax.legend(fontsize=11)
ax.grid(axis='y', alpha=0.3)
for bars in [bars1, bars2]:
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, f"{bar.get_height():.2f}%",
                ha='center', va='bottom', fontsize=10)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_normalized_comparison_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_normalized_comparison_{TAG}.png")

# 图2：归一化后的平均 CER 柱状图
fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(dialect_labels, avg_cers, color=colors, width=0.5, edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title("Qwen3-ASR-1.7B (INT4) 各方言 CER（繁简归一化后）\nFLEURS, 每方言 150 条", fontsize=13, fontweight='bold')
ax.set_ylim(0, max(avg_cers) * 1.3)
for bar, val in zip(bars, avg_cers):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2, f"{val:.2f}%",
            ha='center', va='bottom', fontsize=12, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_comparison_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_comparison_{TAG}.png")

# 图3：归一化后 CER 分布箱线图
fig, ax = plt.subplots(figsize=(8, 5))
data = [all_results[d]["cers_normalized"] for d in DIALECTS]
bp = ax.boxplot(data, tick_labels=dialect_labels, patch_artist=True, widths=0.5,
                medianprops=dict(color='red', linewidth=2))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_ylabel("CER", fontsize=13)
ax.set_title("各方言 CER 分布（繁简归一化后, n=150）", fontsize=13, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_boxplot_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_boxplot_{TAG}.png")

# 图4：归一化前后逐样本 CER 对比（粤语）
fig, ax = plt.subplots(figsize=(14, 5))
yue_old = [c * 100 for c in all_results["cantonese"]["cers"]]
yue_new = [c * 100 for c in all_results["cantonese"]["cers_normalized"]]
ax.plot(range(len(yue_old)), yue_old, alpha=0.5, label="原始 CER", color="#999999", linewidth=0.8)
ax.plot(range(len(yue_new)), yue_new, alpha=0.8, label="归一化后 CER", color=colors[1], linewidth=1)
ax.set_xlabel("样本索引", fontsize=12)
ax.set_ylabel("CER (%)", fontsize=12)
ax.set_title("粤语 CER：繁简归一化前后逐样本对比 (n=150)", fontsize=13, fontweight='bold')
ax.legend(fontsize=11)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, f"cer_yue_normalized_{TAG}.png"), dpi=150)
plt.close()
print(f"Saved: cer_yue_normalized_{TAG}.png")

print("\n=== 繁简归一化后最终结果 ===")
for d in DIALECTS:
    print(f"  {d:12s}: CER = {all_results[d]['avg_cer_normalized']*100:.2f}%  (n={len(all_results[d]['cers_normalized'])})")
