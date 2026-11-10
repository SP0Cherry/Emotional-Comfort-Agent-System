"""
百炼热词实验：创建预编译热词表 → 重跑评测 → 对比 CER
Workspace ID: ws-vvwjxlys9t9fchpc
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
WORKSPACE_ID = "ws-vvwjxlys9t9fchpc"
MODEL = "qwen-audio-3.1-asr-flash-filetrans"
FLEURS_DIR = r"e:\Dataset\fleurs"
IMG_DIR = r"e:\Dataset\img"
SAMPLES_PER_LANG = 150
DIALECTS = ["mandarin", "cantonese"]
MAX_WORKERS = 12

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

# ========== 1. 提取热词 ==========
print("=" * 60)
print("步骤 1: 从 FLEURS 提取热词")
print("=" * 60)

paren_re = re.compile(r'[（(]([^（）()]+)[）)]')
ascii_word_re = re.compile(r'[A-Za-z][A-Za-z0-9\s\-]*[A-Za-z0-9]')

hotword_counter = {}
for dialect in DIALECTS:
    with open(f"{FLEURS_DIR}/{dialect}/transcripts.json", "r", encoding="utf-8") as f:
        records = json.load(f)
    for r in records:
        text = r["text"]
        for m in paren_re.findall(text):
            m = m.strip()
            if re.search(r'[A-Za-z]', m) and len(m) <= 60:
                hotword_counter[m] = hotword_counter.get(m, 0) + 1
        text_no_paren = paren_re.sub('', text)
        for m in ascii_word_re.findall(text_no_paren):
            m = m.strip()
            if 2 <= len(m) <= 40:
                hotword_counter[m] = hotword_counter.get(m, 0) + 1

# 过滤：去掉纯数字、超长、超片段、含特殊字符
valid_hotwords = []
for word, count in hotword_counter.items():
    if re.match(r'^[\d\s\-]+$', word):
        continue
    if len(word) < 2 or len(word) > 40:
        continue
    if len(word.split()) > 7:
        continue
    # 只允许字母、数字、空格、连字符、点号
    if not re.match(r'^[A-Za-z0-9\s\.\-]+$', word):
        continue
    # 含非 ASCII（这里都是 ASCII），长度不超过 15 字符
    # 纯 ASCII 空格分隔片段不超过 7 个（已检查）
    valid_hotwords.append((word, count))

# 按频率排序，取全部
valid_hotwords.sort(key=lambda x: -x[1])
print(f"提取到 {len(valid_hotwords)} 个有效热词")
for word, count in valid_hotwords[:15]:
    print(f"  {count:3d}  {word}")

# 构建热词列表，权重 4
vocabulary = [{"text": w, "weight": 4} for w, _ in valid_hotwords]
print(f"热词列表长度: {len(vocabulary)}")

# ========== 2. 创建预编译热词表 ==========
print("\n" + "=" * 60)
print("步骤 2: 创建预编译热词表")
print("=" * 60)

prefix = "fleurs01"  # 仅数字和小写字母，不超过 10 字符
try:
    vocab_resp = client.audio.vocabularies.create(
        target_model=MODEL,
        prefix=prefix,
        vocabulary=vocabulary,
        workspace=WORKSPACE_ID,
    )
    vocabulary_id = vocab_resp.vocabulary_id
    print(f"热词表创建成功! vocabulary_id = {vocabulary_id}")
except Exception as e:
        print(f"创建失败: {type(e).__name__}: {str(e)[:200]}")
        # 如果已存在，尝试列出
        try:
            existing = client.audio.vocabularies.list(prefix=prefix, workspace=WORKSPACE_ID)
            vocab_list = getattr(existing, 'vocabularies', [])
            print(f"已有热词表数量: {len(vocab_list)}")
            if vocab_list and len(vocab_list) > 0:
                vocabulary_id = vocab_list[0].vocabulary_id
                print(f"使用已有热词表: {vocabulary_id}")
            else:
                raise RuntimeError("无已有热词表")
        except Exception as e2:
            print(f"查询也失败: {e2}")
            exit(1)

# ========== 3. 重跑评测（带热词）==========
print("\n" + "=" * 60)
print(f"步骤 3: 重跑评测 (vocabulary_id={vocabulary_id})")
print("=" * 60)

def process_one(args):
    idx, wav_path, ref_text = args
    try:
        upload_resp = client.files.upload(file_path=wav_path, purpose="asr")
        file_info = client.files.get(file_id=upload_resp.file_id)
        file_url = file_info.model_extra['url']

        job = client.audio.asr.jobs.create(
            model=MODEL,
            file_urls=[file_url],
            parameters={"vocabulary_id": vocabulary_id},
            workspace=WORKSPACE_ID,
        )
        task_id = job.task_id

        while True:
            job = client.audio.asr.jobs.fetch(task_id=task_id, workspace=WORKSPACE_ID)
            if job.status == "SUCCEEDED":
                break
            elif job.status in ("FAILED", "CANCELED"):
                return idx, ref_text, "", f"job_{job.status}"
            time.sleep(1)

        trans_url = job.results[0].transcription_url
        resp = requests.get(trans_url, timeout=30)
        result_json = resp.json()
        transcripts = result_json.get('transcripts', [])
        hyp_text = ''.join(t.get('text', '') for t in transcripts if isinstance(t, dict))

        try:
            client.files.delete(file_id=upload_resp.file_id)
        except:
            pass

        return idx, ref_text, hyp_text, "ok"
    except Exception as e:
        return idx, ref_text, "", f"error:{str(e)[:100]}"

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
                print(f"    [{done:3d}/{len(tasks)}] CER={c*100:6.2f}%  ({elapsed:.0f}s)", flush=True)

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
with open(os.path.join(IMG_DIR, "eval_results_bailian_hotwords.json"), "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)

# ========== 4. 对比作图 ==========
print("\n" + "=" * 60)
print("步骤 4: 生成对比图表")
print("=" * 60)

with open(os.path.join(IMG_DIR, "eval_results_bailian.json"), "r", encoding="utf-8") as f:
    baseline_results = json.load(f)

dialect_labels = ["普通话 (Mandarin)", "粤语 (Cantonese)"]
baseline_cers = [baseline_results[d]["avg_cer"] * 100 for d in DIALECTS]
hotword_cers = [all_results[d]["avg_cer"] * 100 for d in DIALECTS]

# 图1：加热词前后 CER 对比
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(DIALECTS))
width = 0.35
bars1 = ax.bar(x - width/2, baseline_cers, width, label="无热词 (Baseline)", color="#999999", edgecolor='black', linewidth=0.8)
bars2 = ax.bar(x + width/2, hotword_cers, width, label="预编译热词表", color="#DD8452", edgecolor='black', linewidth=0.8)
ax.set_ylabel("平均 CER (%)", fontsize=13)
ax.set_title(f"百炼 ASR：热词表对 CER 的影响 (FLEURS, n={SAMPLES_PER_LANG})", fontsize=13, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(dialect_labels, fontsize=12)
ax.legend(fontsize=11)
ax.grid(axis='y', alpha=0.3)
for bars in [bars1, bars2]:
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2, f"{bar.get_height():.2f}%",
                ha='center', va='bottom', fontsize=10)
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "cer_hotwords_comparison.png"), dpi=150)
plt.close()
print("  Saved: cer_hotwords_comparison.png")

# 图2：逐样本 CER 对比
fig, axes = plt.subplots(1, 2, figsize=(16, 5))
for ax, d in zip(axes, DIALECTS):
    base_c = [c * 100 for c in baseline_results[d]["cers"]]
    hw_c = [c * 100 for c in all_results[d]["cers"]]
    ax.plot(range(len(base_c)), base_c, alpha=0.5, label="无热词", color="#999999", linewidth=0.8)
    ax.plot(range(len(hw_c)), hw_c, alpha=0.8, label="有热词", color="#DD8452", linewidth=0.8)
    ax.set_xlabel("样本索引", fontsize=11)
    ax.set_ylabel("CER (%)", fontsize=11)
    ax.set_title(dialect_labels[DIALECTS.index(d)], fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
plt.suptitle("逐样本 CER 对比：无热词 vs 有热词 (n=150)", fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "cer_hotwords_per_sample.png"), dpi=150)
plt.close()
print("  Saved: cer_hotwords_per_sample.png")

# 图3：热词表内容概览
fig, ax = plt.subplots(figsize=(12, 6))
top_words = [w for w, _ in valid_hotwords[:20]]
top_counts = [c for _, c in valid_hotwords[:20]]
y_pos = np.arange(len(top_words))
ax.barh(y_pos, top_counts, color="#4C72B0", edgecolor='black', linewidth=0.5)
ax.set_yticks(y_pos)
ax.set_yticklabels(top_words, fontsize=9)
ax.set_xlabel("在 FLEURS 中的出现次数", fontsize=11)
ax.set_title(f"热词表 Top 20 (共 {len(valid_hotwords)} 个热词)", fontsize=13, fontweight='bold')
ax.grid(axis='x', alpha=0.3)
ax.invert_yaxis()
plt.tight_layout()
plt.savefig(os.path.join(IMG_DIR, "hotwords_top20.png"), dpi=150)
plt.close()
print("  Saved: hotwords_top20.png")

print("\n" + "=" * 60)
print("热词实验完成！")
print(f"  热词表 ID: {vocabulary_id}")
print(f"  热词数量: {len(valid_hotwords)}")
for d in DIALECTS:
    base = baseline_results[d]['avg_cer'] * 100
    hw = all_results[d]['avg_cer'] * 100
    print(f"  {d:12s}: {base:.2f}% -> {hw:.2f}%  (Δ={base-hw:+.2f}%)")
print(f"\n图表保存在: {IMG_DIR}")
print("=" * 60)
