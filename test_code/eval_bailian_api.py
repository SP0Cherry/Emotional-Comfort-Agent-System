"""
百炼 Qwen-Audio-3.1-ASR-Flash-Filetrans 评测（对照实验）
并发上传 + 提交 + 轮询，150 条/方言，含繁简归一化。
脚本：test_code/eval_bailian_api.py
结果：img/eval_results_bailian.json, 对比图表 img/*_bailian*.png
"""
import os
import json
import time
import re
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import requests
import dashscope
from opencc import OpenCC
import matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor, as_completed

# ========== 配置 ==========
API_KEY = "sk-ws-H.YRLMMXL.u6yo.MEUCIBZ6vfiLEfN1ap4QIakxfbKE4J1R8mdCI_7qgkMWMjUcAiEArjFxogvupG4htwcY1-Z12ofKyYuxrjObPJDbmbJwO5o"
MODEL = "qwen-audio-3.1-asr-flash-filetrans"
FLEURS_DIR = r"e:\Dataset\fleurs"
IMG_DIR = r"e:\Dataset\img"
SAMPLES_PER_LANG = 150
DIALECTS = ["mandarin", "cantonese"]
MAX_WORKERS = 12  # 并发数

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

cc = OpenCC('t2s')
client = dashscope.Client(api_key=API_KEY, region="cn-beijing")

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

# ========== 单条处理 ==========
def process_one(args):
    idx, wav_path, ref_text = args
    try:
        # 上传
        upload_resp = client.files.upload(file_path=wav_path, purpose="asr")
        file_info = client.files.get(file_id=upload_resp.file_id)
        file_url = file_info.model_extra['url']

        # 提交任务
        job = client.audio.asr.jobs.create(model=MODEL, file_urls=[file_url])
        task_id = job.task_id

        # 轮询
        while True:
            job = client.audio.asr.jobs.fetch(task_id=task_id)
            if job.status == "SUCCEEDED":
                break
            elif job.status in ("FAILED", "CANCELED"):
                return idx, ref_text, "", f"job_{job.status}"
            time.sleep(1)

        # 下载结果
        trans_url = job.results[0].transcription_url
        resp = requests.get(trans_url, timeout=30)
        result_json = resp.json()
        transcripts = result_json.get('transcripts', [])
        hyp_text = ''.join(t.get('text', '') for t in transcripts if isinstance(t, dict))

        # 删除上传的文件（清理）
        try:
            client.files.delete(file_id=upload_resp.file_id)
        except:
            pass

        return idx, ref_text, hyp_text, "ok"
    except Exception as e:
        return idx, ref_text, "", f"error:{str(e)[:100]}"

# ========== 主流程 ==========
print("=" * 60)
print(f"百炼 {MODEL} 评测 (FLEURS, {SAMPLES_PER_LANG} samples/dialect, {MAX_WORKERS} workers)")
print("=" * 60)

all_results = {}
total_start = time.time()

for dialect in DIALECTS:
    print(f"\n  --- {dialect} ---")
    with open(os.path.join(FLEURS_DIR, dialect, "transcripts.json"), "r", encoding="utf-8") as f:
        records = json.load(f)
    records = records[:SAMPLES_PER_LANG]

    tasks = [(i, os.path.join(FLEURS_DIR, dialect, "audio", r["wav"]), r["text"])
             for i, r in enumerate(records)]

    detailed = [None] * len(tasks)
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_one, t): t[0] for t in tasks}
        for future in as_completed(futures):
            idx, ref, hyp, status = future.result()
            ref_norm = normalize(ref)
            hyp_norm = normalize(hyp)
            c = cer(ref_norm, hyp_norm)
            detailed[idx] = {
                "idx": idx, "cer": round(c, 4), "ref": ref, "hyp": hyp, "status": status,
            }
            done += 1
            if done % 15 == 0:
                elapsed = time.time() - t0
                print(f"    [{done:3d}/{len(tasks)}] CER={c*100:6.2f}%  ({elapsed:.0f}s, {status})", flush=True)

    cers = [d["cer"] for d in detailed if d]
    avg_cer = float(np.mean(cers))
    all_results[dialect] = {
        "avg_cer": avg_cer,
        "cers": cers,
        "detailed": detailed,
    }
    print(f"  >>> {dialect}: avg CER = {avg_cer*100:.2f}%  (n={len(cers)}, {time.time()-t0:.0f}s)", flush=True)

total_time = time.time() - total_start
print(f"\n  Total eval time: {total_time:.0f}s ({total_time/60:.1f} min)")

# 保存
os.makedirs(IMG_DIR, exist_ok=True)
with open(os.path.join(IMG_DIR, "eval_results_bailian.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# ========== 作图（与本地模型对比）==========
print("\n  Generating comparison plots...")
with open(os.path.join(IMG_DIR, "eval_results_int4_normalized.json"), "r", encoding="utf-8") as f:
    local_results = json.load(f)

dialect_labels = ["普通话 (Mandarin)", "粤语 (Cantonese)"]
bailian_cers = [all_results[d]["avg_cer"] * 100 for d in DIALECTS]
local_cers = [local_results[d]["avg_cer_normalized"] * 100 for d in DIALECTS]

# 图1：本地 vs 百炼 CER 对比
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(DIALECTS))
width = 0.35
bars1 = ax.bar(x - width/2, local_cers, width, label="本地 Qwen3-ASR-1.7B (INT4)", color="#4C72B0", edgecolor='black', linewidth=0.8)
bars2 = ax.bar(x + width/2, bailian_cers, width, label="百炼 Qwen-Audio-3.1-ASR-Flash", color="#DD8452", edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title("本地模型 vs 百炼 API CER 对比 (FLEURS, n=150, 繁简归一化)", fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(dialect_labels, fontsize=12)
ax.legend(fontsize=11)
ax.grid(axis='y', alpha=0.3)
for bars in [bars1, bars2]:
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2, f"{bar.get_height():.2f}%",
                ha='center', va='bottom', fontsize=10)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "cer_comparison_bailian.png"), dpi=150)
plt.close()
print("  Saved: cer_comparison_bailian.png")

# 图2：百炼各方言平均 CER
fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(dialect_labels, bailian_cers, color=["#4C72B0", "#DD8452"], width=0.5, edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title(f"百炼 Qwen-Audio-3.1-ASR-Flash 各方言 CER\n(FLEURS, 每方言 {SAMPLES_PER_LANG} 条, 繁简归一化)", fontsize=13, fontweight='bold')
ax.set_ylim(0, max(bailian_cers) * 1.3)
for bar, val in zip(bars, bailian_cers):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2, f"{val:.2f}%",
            ha='center', va='bottom', fontsize=12, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "cer_comparison_bailian_only.png"), dpi=150)
plt.close()
print("  Saved: cer_comparison_bailian_only.png")

# 图3：百炼 CER 分布箱线图
fig, ax = plt.subplots(figsize=(8, 5))
data = [all_results[d]["cers"] for d in DIALECTS]
bp = ax.boxplot(data, tick_labels=dialect_labels, patch_artist=True, widths=0.5,
                medianprops=dict(color='red', linewidth=2))
for patch, color in zip(bp['boxes'], ["#4C72B0", "#DD8452"]):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)
ax.set_ylabel("CER", fontsize=13)
ax.set_title(f"百炼各方言 CER 分布 (箱线图, n={SAMPLES_PER_LANG})", fontsize=13, fontweight='bold')
ax.grid(axis='y', alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "cer_boxplot_bailian.png"), dpi=150)
plt.close()
print("  Saved: cer_boxplot_bailian.png")

# 图4：逐样本 CER 对比（本地 vs 百炼）
fig, axes = plt.subplots(1, 2, figsize=(16, 5))
for ax, d, color in zip(axes, DIALECTS, ["#4C72B0", "#DD8452"]):
    local_c = [c * 100 for c in local_results[d]["cers_normalized"]]
    bailian_c = [c * 100 for c in all_results[d]["cers"]]
    ax.plot(range(len(local_c)), local_c, alpha=0.5, label="本地 INT4", color=color, linewidth=0.8)
    ax.plot(range(len(bailian_c)), bailian_c, alpha=0.8, label="百炼 API", color="green", linewidth=0.8)
    ax.set_xlabel("样本索引", fontsize=11)
    ax.set_ylabel("CER (%)", fontsize=11)
    ax.set_title(dialect_labels[DIALECTS.index(d)], fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
plt.suptitle("逐样本 CER 对比：本地 INT4 vs 百炼 API (n=150)", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "cer_per_sample_bailian.png"), dpi=150)
plt.close()
print("  Saved: cer_per_sample_bailian.png")

print("\n" + "=" * 60)
print("百炼评测完成！")
for d in DIALECTS:
    print(f"  {d:12s}: CER = {all_results[d]['avg_cer']*100:.2f}%")
print(f"\n图表保存在: {IMG_DIR}")
print("=" * 60)
