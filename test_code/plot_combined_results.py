"""
生成所有优化方式组合效果的对比图表
baseline → 热词 → 去重 → 热词+去重
"""
import json
import numpy as np
import matplotlib.pyplot as plt

IMG_DIR = r"e:\Dataset\img"
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 读取各版本结果
with open(f"{IMG_DIR}/eval_results_bailian.json", "r", encoding="utf-8") as f:
    baseline = json.load(f)
with open(f"{IMG_DIR}/eval_results_bailian_hotwords.json", "r", encoding="utf-8") as f:
    hotwords = json.load(f)
with open(f"{IMG_DIR}/eval_results_bailian_dedup.json", "r", encoding="utf-8") as f:
    dedup = json.load(f)
with open(f"{IMG_DIR}/eval_results_bailian_hotwords_dedup.json", "r", encoding="utf-8") as f:
    both = json.load(f)

dialects = ["mandarin", "cantonese"]
dialect_labels = ["普通话", "粤语"]
methods = ["Baseline\n(无优化)", "热词表", "去重", "热词+去重"]

# 提取 CER
cers = {
    "普通话": [
        baseline["mandarin"]["avg_cer"] * 100,
        hotwords["mandarin"]["avg_cer"] * 100,
        dedup["mandarin"]["avg_after"],
        both["mandarin"]["avg_after"],
    ],
    "粤语": [
        baseline["cantonese"]["avg_cer"] * 100,
        hotwords["cantonese"]["avg_cer"] * 100,
        dedup["cantonese"]["avg_after"],
        both["cantonese"]["avg_after"],
    ],
}

# 图1：分组柱状图 — 各方言各方法的 CER
fig, ax = plt.subplots(figsize=(12, 6))
x = np.arange(len(methods))
width = 0.35
colors = ["#999999", "#DD8452", "#55A868", "#4C72B0"]

for i, (dialect, label) in enumerate(zip(dialects, dialect_labels)):
    offset = (i - 0.5) * width
    bars = ax.bar(x + offset, cers[label], width, label=label, color=colors[i*2+1] if i else colors[0],
                  edgecolor='black', linewidth=0.8)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f"{bar.get_height():.2f}%", ha='center', va='bottom', fontsize=9)

ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title("百炼 Qwen-Audio-3.1-ASR-Flash：各优化方式组合效果对比\n(FLEURS, n=150)", fontsize=14, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(methods, fontsize=11)
ax.legend(fontsize=12)
ax.grid(axis='y', alpha=0.3)
ax.set_ylim(0, 6)
plt.tight_layout()
plt.savefig(f"{IMG_DIR}/cer_all_methods_comparison.png", dpi=150)
plt.close()
print("Saved: cer_all_methods_comparison.png")

# 图2：相对 baseline 的改善幅度
fig, ax = plt.subplots(figsize=(10, 6))
improvements = {}
for dialect in dialect_labels:
    base = cers[dialect][0]
    improvements[dialect] = [(base - c) / base * 100 for c in cers[dialect]]

x = np.arange(len(methods) - 1)  # 去掉 baseline
width = 0.35
method_labels = methods[1:]

for i, dialect in enumerate(dialect_labels):
    offset = (i - 0.5) * width
    imp = improvements[dialect][1:]
    bars = ax.bar(x + offset, imp, width, label=dialect,
                  color="#DD8452" if i == 0 else "#4C72B0", edgecolor='black', linewidth=0.8)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{bar.get_height():+.1f}%", ha='center', va='bottom', fontsize=10)

ax.set_ylabel("相对 Baseline 的 CER 改善幅度 (%)", fontsize=13)
ax.set_title("各优化方式相对 Baseline 的 CER 改善率", fontsize=14, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(method_labels, fontsize=12)
ax.legend(fontsize=12)
ax.grid(axis='y', alpha=0.3)
ax.axhline(y=0, color='black', linewidth=0.5)
plt.tight_layout()
plt.savefig(f"{IMG_DIR}/cer_improvement_rate.png", dpi=150)
plt.close()
print("Saved: cer_improvement_rate.png")

# 图3：粤语逐样本 CER 变化（最能体现优化效果的方言）
fig, ax = plt.subplots(figsize=(16, 6))
yue_base = [c * 100 for c in baseline["cantonese"]["cers"]]
yue_hw = [c * 100 for c in hotwords["cantonese"]["cers"]]
yue_dedup = []
for it in baseline["cantonese"]["detailed"]:
    from opencc import OpenCC
    import re
    cc = OpenCC('t2s')
    def normalize(text):
        text = cc.convert(text)
        text = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z]', '', text)
        dm = {'0':'零','1':'一','2':'二','3':'三','4':'四','5':'五','6':'六','7':'七','8':'八','9':'九'}
        return ''.join(dm.get(ch, ch) for ch in text)
    def cer(ref, hyp):
        n = len(ref)
        if n == 0: return 0.0 if len(hyp) == 0 else 1.0
        dp = [[0]*(len(hyp)+1) for _ in range(n+1)]
        for i in range(n+1): dp[i][0] = i
        for j in range(len(hyp)+1): dp[0][j] = j
        for i in range(1, n+1):
            for j in range(1, len(hyp)+1):
                cost = 0 if ref[i-1]==hyp[j-1] else 1
                dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)
        return dp[n][len(hyp)]/n
    def dedup(text):
        for n in range(4,1,-1):
            pattern = re.compile(r'(.{'+str(n)+r'})\1+')
            text = pattern.sub(lambda m: m.group(1) if not m.group(1).isdigit() else m.group(0), text)
        return text
    ref_norm = normalize(it["ref"])
    hyp_dedup = normalize(dedup(it["hyp"]))
    yue_dedup.append(cer(ref_norm, hyp_dedup) * 100)

ax.plot(range(len(yue_base)), yue_base, alpha=0.4, label="Baseline", color="#999999", linewidth=0.8)
ax.plot(range(len(yue_hw)), yue_hw, alpha=0.6, label="热词表", color="#DD8452", linewidth=0.8)
ax.plot(range(len(yue_dedup)), yue_dedup, alpha=0.8, label="热词+去重", color="#4C72B0", linewidth=0.8)
ax.set_xlabel("样本索引", fontsize=12)
ax.set_ylabel("CER (%)", fontsize=12)
ax.set_title("粤语逐样本 CER 变化（Baseline → 热词 → 热词+去重）", fontsize=14, fontweight='bold')
ax.legend(fontsize=11)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(f"{IMG_DIR}/cer_yue_combined_per_sample.png", dpi=150)
plt.close()
print("Saved: cer_yue_combined_per_sample.png")

# 打印汇总表
print("\n" + "=" * 70)
print("汇总：各优化方式 CER 对比")
print("=" * 70)
print(f"{'方法':<16} {'普通话 CER':>12} {'粤语 CER':>12}")
print("-" * 42)
for i, method in enumerate(["Baseline", "热词表", "去重", "热词+去重"]):
    m_cer = cers["普通话"][i]
    y_cer = cers["粤语"][i]
    print(f"{method:<16} {m_cer:>11.2f}% {y_cer:>11.2f}%")
print("=" * 70)
