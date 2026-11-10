"""
后处理去重实验：对百炼评测结果应用去重规则，重新计算 CER
"""
import json
import re
import numpy as np
from opencc import OpenCC
import matplotlib.pyplot as plt

IMG_DIR = r"e:\Dataset\img"
cc = OpenCC('t2s')

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

_DIGIT_MAP = {'0':'零','1':'一','2':'二','3':'三','4':'四','5':'五',
              '6':'六','7':'七','8':'八','9':'九'}

def normalize(text: str) -> str:
    text = cc.convert(text)
    text = re.sub(r'[^\u4e00-\u9fff0-9a-zA-Z]', '', text)
    return ''.join(_DIGIT_MAP.get(ch, ch) for ch in text)

# ========== 去重后处理 ==========
def deduplicate(text: str) -> str:
    """检测并移除连续重复的 2-4 字词（排除纯数字）"""
    for n in range(4, 1, -1):  # 从长到短，避免 "滑雪者滑雪者" 被 "滑雪" 部分匹配
        # 匹配 n 个字符的连续重复（至少重复 2 次）
        pattern = re.compile(r'(.{' + str(n) + r'})\1+')
        def replacer(m):
            chunk = m.group(1)
            # 排除纯数字（如 2020, 1100）
            if chunk.isdigit():
                return m.group(0)
            return chunk
        text = pattern.sub(replacer, text)
    return text

# ========== 加载数据并应用去重 ==========
print("=" * 60)
print("后处理去重实验")
print("=" * 60)

# 对比 baseline（无热词）和 hotwords 两个版本
for version in ["bailian", "bailian_hotwords"]:
    print(f"\n--- 版本: {version} ---")
    with open(f"{IMG_DIR}/eval_results_{version}.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    results = {}
    for dialect in ["mandarin", "cantonese"]:
        detailed = data[dialect]["detailed"]
        original_cers = []
        dedup_cers = []
        changed_samples = []

        for it in detailed:
            ref_norm = normalize(it["ref"])
            hyp_orig = it["hyp"]
            hyp_dedup = deduplicate(hyp_orig)

            c_orig = cer(ref_norm, normalize(hyp_orig))
            c_dedup = cer(ref_norm, normalize(hyp_dedup))

            original_cers.append(c_orig)
            dedup_cers.append(c_dedup)

            if hyp_orig != hyp_dedup:
                changed_samples.append({
                    "cer_before": c_orig,
                    "cer_after": c_dedup,
                    "hyp_before": hyp_orig,
                    "hyp_after": hyp_dedup,
                })

        avg_orig = np.mean(original_cers) * 100
        avg_dedup = np.mean(dedup_cers) * 100
        results[dialect] = {
            "avg_before": avg_orig,
            "avg_after": avg_dedup,
            "changed_count": len(changed_samples),
            "changed_samples": changed_samples,
        }
        print(f"  {dialect:12s}: {avg_orig:.2f}% -> {avg_dedup:.2f}%  (Δ={avg_orig-avg_dedup:+.2f}%)")
        print(f"    被去重修改的样本数: {len(changed_samples)}")
        for cs in changed_samples[:5]:
            print(f"      CER {cs['cer_before']*100:.1f}% -> {cs['cer_after']*100:.1f}%")
            print(f"      前: {cs['hyp_before'][:60]}")
            print(f"      后: {cs['hyp_after'][:60]}")

    # 保存去重后的结果
    out_file = f"{IMG_DIR}/eval_results_{version}_dedup.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  结果保存到: {out_file}")

# ========== 作图 ==========
print("\n" + "=" * 60)
print("生成图表")
print("=" * 60)

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
dialect_labels = ["普通话", "粤语"]

for ax, version in zip(axes, ["bailian", "bailian_hotwords"]):
    with open(f"{IMG_DIR}/eval_results_{version}.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    before = [data[d]["avg_cer"] * 100 for d in ["mandarin", "cantonese"]]
    # 从去重结果中读取
    with open(f"{IMG_DIR}/eval_results_{version}_dedup.json", "r", encoding="utf-8") as f:
        dedup_data = json.load(f)
    after = [dedup_data[d]["avg_after"] for d in ["mandarin", "cantonese"]]

    x = np.arange(2)
    width = 0.35
    bars1 = ax.bar(x - width/2, before, width, label="原始", color="#999999", edgecolor='black', linewidth=0.8)
    bars2 = ax.bar(x + width/2, after, width, label="去重后", color="#55A868", edgecolor='black', linewidth=0.8)
    ax.set_ylabel("平均 CER (%)", fontsize=12)
    title = "无热词版" if version == "bailian" else "热词版"
    ax.set_title(f"{title}：去重前后 CER 对比", fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(dialect_labels, fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    for bars in [bars1, bars2]:
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, f"{bar.get_height():.2f}%",
                    ha='center', va='bottom', fontsize=9)

plt.suptitle("后处理去重对 CER 的影响 (FLEURS, n=150)", fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(f"{IMG_DIR}/cer_dedup_comparison.png", dpi=150)
plt.close()
print(f"  Saved: cer_dedup_comparison.png")

print("\n" + "=" * 60)
print("完成！")
print("=" * 60)
