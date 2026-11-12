# 情感识别模块交付报告

| 项目 | 内容 |
| --- | --- |
| 交付版本 | 0.6.0 |
| 交付日期 | 2026-11-09 |
| 模块 | 普通话情感识别 |
| 默认入口 | `http://127.0.0.1:4173` |
| 接口版本 | `schema_version=1.0` |

## 1. 交付目标

本次交付提供一个可运行、可评测、可联调的普通话情感识别模块。它把用户文本、浏览器声学摘要和本地语音模型结果转换为结构化情绪状态，为团队成员接手、联调和后续方言扩展提供稳定边界。

更完整的验收稿：

- [接口与协作规约](emotion-recognition-spec.md)
- [多人协作与跨模块集成契约](team-integration-contract.md)
- [模型权重交接](model-handoff.md)
- [两周阶段报告](two-week-group-meeting-report.md)
- [技术问答稿](group-meeting-technical-qa.md)
- [组会答辩 PPT](../outputs/情感识别模块_三周组会汇报_v3.pptx)

## 2. 已交付能力

### 2.1 运行与接口

- 本地 Web 调试页面；
- Node HTTP API；
- 文本、声学摘要和 WAV 输入；
- 会话创建、查询和删除；
- 最近五轮趋势；
- 独立风险提示；
- 模型状态与方言 fallback；
- 模型不可用时的规则回退。

### 2.2 模型链路

- 默认文本主模型：本地多任务微调 `hfl/chinese-roberta-wwm-ext`；
- 文本回退：Qwen2.5-1.5B-Instruct 与 `Chinese-Emotion-Small`；
- 语音转写与粗粒度情绪：SenseVoiceSmall；
- 语音情绪概率：emotion2vec+base；
- 规则、模型、声学摘要的质量受限融合。

### 2.3 数据与评测

- BRIGHTER 中文官方 train/dev/test；
- Chinese Multi-Emotion Dialogue；
- 1000 条同集开发测试；
- 1449 条 BRIGHTER 密封测试；
- 650 条另一套数据同源留出测试；
- 错误分析、置信度取舍和失败实验记录。

## 3. 关键结果

### 3.1 同一 1000 条测试

| 方法 | Accuracy | Macro-F1 |
| --- | ---: | ---: |
| 多数类基线 | 40.8% | 11.6% |
| 规则 | 29.6% | 24.3% |
| Qwen 少样本提示 | 45.3% | 44.3% |
| Chinese-Emotion-Small | 44.4% | 38.0% |
| 组合微调 RoBERTa | 76.5% | 66.0% |

### 3.2 1449 条密封测试

| 指标 | 结果 |
| --- | ---: |
| Accuracy | 80.2% |
| Macro-F1 | 75.2% |
| 负面检测 F1 | 90.3% |
| 负面检测 Recall | 93.4% |
| 负面检测 Precision | 87.4% |

### 3.3 另一套同源留出测试

650 条样本：

- Accuracy：91.8%
- Macro-F1：91.5%
- 焦虑 F1：88.9%
- 焦虑 Recall：92.6%

该结果不是跨数据集泛化。它还帮助补足了焦虑训练样本，从 34 条提升到 428 条。

## 4. 没有采用的方案

| 方案 | 结果 | 处理 |
| --- | --- | --- |
| 固定 70/30 多标签融合 | Macro-F1 63.8%，低于主头 66.0% | 未上线 |
| dev 搜索多标签权重 | dev 72.7%，test 63.0% | 未上线 |
| 中性门控层级分类 | 密封 Accuracy 79.8%，低于扁平 80.2% | 未上线 |

保留这些负结果，便于后续同学区分“没有尝试”和“验证后无效”。

## 5. 运行环境

参考环境：

- Apple M5；
- 16 GB 统一内存；
- macOS；
- Node.js 20 以上；
- Python 3.9；
- PyTorch MPS；
- FunASR，用于 SenseVoice。

一键启动：

```bash
npm run demo
```

仅运行规则与服务：

```bash
npm start
```

自动测试：

```bash
npm test
```

模型服务默认位于 `http://127.0.0.1:5055`，网页和 API 默认位于 `http://127.0.0.1:4173`。

## 6. 模型交付

完整模型的体积超过普通 GitHub 仓库的提交限制，因此没有放入 Git。当前本机模型位于：

```text
models/brighter-johnson-multitask/
```

主要文件：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `model.pt` | 390 MiB | `cb51805812a55754f903dde1df5a2e4abd69a98a38459391cb7ab47f2ad459fe` |
| `metrics.json` | 7.9 KiB | `8a14395841ff1c6229cf3d84d7e58dfff02a68881c333ed4448c765b3e1022ac` |
| `training_config.json` | 617 B | `f9e44d5d456e7ea254703b1652b6483a49e6ab9d89b68734f0b47f2afb75ba08` |

协作约定：

1. 不把 `model.pt` 直接提交到 Git；
2. 通过团队共享盘、GitHub Release 资产或内部制品库交接；
3. 交接时同时提供 `tokenizer.json`、`vocab.txt`、`tokenizer_config.json` 和 `special_tokens_map.json`；
4. 使用文件哈希校验完整性；
5. 模型缺失时服务必须仍能通过规则和远程回退路径启动。

### 6.1 重新训练

训练脚本：

```bash
npm run finetune:multitask
```

训练配置：

- 3 epoch；
- batch size 8；
- max length 192；
- 冻结前 6 层；
- learning rate `2e-5`；
- 外部样本权重 `0.5`；
- 主分类、多标签、负面检测和强度回归联合训练。

完整配置和指标见 [本地多任务 RoBERTa 微调结果](finetuned-model-results.md)。

## 7. 验证记录

交付前执行：

```bash
npm test
```

覆盖范围：

- 页面与健康接口；
- 会话生命周期；
- 文本与语音声学摘要；
- 模型适配器融合；
- 方言 fallback；
- 风险规则；
- 多轮趋势；
- 低信息输入。

自动化测试只证明功能和接口行为，不证明真实场景准确率。

## 8. 当前限制

1. 没有说话人字段，不能声明说话人隔离评测。
2. 公开数据与真实陪伴对话存在领域差异。
3. `calm` 没有稳定的公开监督标签，主要由规则保留。
4. 密封测试没有焦虑样本，焦虑能力依赖另一套同源测试。
5. 风险分支没有正式标注集，只能用于演示级安全提醒。
6. 方言只有接口 fallback，没有方言 ASR、情绪模型或校准。
7. 会话存储在内存中，服务重启后丢失。
8. 当前置信度决策阈值仍需目标域数据校准。

## 9. 下一阶段

1. 采集 300～500 条真实陪伴对话，以无监督域适配和不确定性筛选为主，不安排人工标注；
2. 建立说话人分组和跨数据集测试；
3. 加入最近多轮上下文，验证指代和情绪变化；
4. 在目标数据上校准文本与语音置信度；
5. 为 `calm` 和风险分支补充标注；
6. 普通话验收通过后再扩展方言 ASR、情绪模型和 TTS。

## 10. 接手方式

新同学应先阅读：

1. 根目录 [README](../README.md)；
2. [接口与协作规约](emotion-recognition-spec.md)；
3. [多人协作与跨模块集成契约](team-integration-contract.md)；
4. [本地模型集成说明](model-integration.md)；
5. [公开数据源记录](external-data-sources.md)。

然后运行：

```bash
npm install
npm test
npm start
```

需要完整多模态演示时再运行：

```bash
npm run demo
```
