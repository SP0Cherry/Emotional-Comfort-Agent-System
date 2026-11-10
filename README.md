# 工作简介

本工作区用于 **Qwen 系列 ASR 模型的汉语方言识别能力评测**，包含数据集准备与模型评测两部分。

## 一、已完成工作

### 1. KeSpeech 数据集准备

[KeSpeech](https://openreview.net/forum?id=b3Zoeq2sCLq) 是一个开源的普通话及其八大方言语音数据集。

- **数据规模**：27,237 个说话人，976,054 条音频，总大小 174.4 GB
- **音频格式**：16 kHz / 16-bit / 单声道 / PCM WAV
- **方言覆盖**：Beijing, Ji-Lu, Jiang-Huai, Jiao-Liao, Lan-Yin, Mandarin, Southwestern, Wu, Yue 等八大方言区
- **任务划分**：train_phase1, train_phase2, dev_phase1, dev_phase2, test
- **标注文件**：`wav.scp`, `text`, `utt2spk`, `utt2subdialect`, `spk2utt`
- **存储路径**：`e:\Dataset\KeSpeech\`

### 2. FLEURS 数据集初步评测

使用 Google **FLEURS** 多语言语音数据集的中文子集，对 Qwen 系列 ASR 模型进行初步评测。

- **评测方言**：普通话 (zh-CN) 150 条、粤语 (yue) 150 条
- **评测指标**：CER (Character Error Rate)
- **存储路径**：`e:\Dataset\fleurs\`

## 二、评测结果摘要

### 本地模型：Qwen3-ASR-1.7B (INT4 量化)

| 方言 | 原始 CER | 繁简归一化后 CER |
|------|---------|----------------|
| 普通话 | 4.98% | **4.98%** |
| 粤语 | 34.00% | **5.81%** |

> 粤语原始 CER 虚高系繁简字符差异所致，归一化后与普通话几乎持平。

### 云端 API：百炼 Qwen-Audio-3.1-ASR-Flash

| 方言 | Baseline CER | 热词+去重后 CER |
|------|-------------|----------------|
| 普通话 | 4.96% | **4.85%** |
| 粤语 | 3.37% | **3.16%** |

### 本地 vs 云端对比

| 维度 | 本地 Qwen3-ASR-1.7B (INT4) | 百炼 Qwen-Audio-3.1-ASR-Flash |
|------|---------------------------|-------------------------------|
| 普通话 CER | 4.98% | 4.96% (优化后 4.85%) |
| 粤语 CER | 5.81% | 3.37% (优化后 3.16%) |
| 推理速度 | 3.9 秒/条 (本地 GPU) | 300 条 1.8 分钟 (并发) |
| 显存占用 | 2.2 GB (INT4) | 无硬件需求 |
| 数据隐私 | 数据不出本地 | 音频上传云端 |

详细评测报告见 [report.md](report.md)。

## 三、目录结构

```
e:\Dataset\
├── KeSpeech\          # KeSpeech 数据集（已解压完成）
│   ├── Audio\         # 音频文件（按说话人分目录）
│   └── Tasks\ASR\     # ASR 标注文件
├── fleurs\            # FLEURS 评测数据集
│   ├── mandarin\      # 普通话
│   └── cantonese\     # 粤语
├── models\            # 模型权重
├── hotwords\          # 热词表
├── img\               # 评测图表
├── test_code\         # 评测脚本
└── report.md          # 详细评测报告
```

## 四、后续计划

使用 KeSpeech 数据集（八大方言）对 Qwen3-ASR 进行更全面的方言识别能力评测。
