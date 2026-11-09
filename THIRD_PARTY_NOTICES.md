# 第三方模型、数据与依赖说明

本文件记录当前情感识别模块使用或评估过的第三方资源。它不替代各项目的原始许可证。

## 1. 项目许可证状态

本仓库当前没有统一的根许可证。此说明不会自动给项目代码增加许可证。团队需要在发布、比赛提交或商业使用前，由负责人确认项目整体许可证。

## 2. 模型

| 资源 | 用途 | 已记录许可证 | 使用注意 |
| --- | --- | --- | --- |
| `hfl/chinese-roberta-wwm-ext` | 多任务分类基座 | 仓库未冻结许可证副本 | 再分发微调权重前核对模型卡 |
| `Qwen/Qwen2.5-1.5B-Instruct` | 文本回退 | Apache-2.0 | 保留版权和许可证声明 |
| `Johnson8187/Chinese-Emotion-Small` | 文本回退 | MIT | 保留版权和许可证声明 |
| `FunAudioLLM/SenseVoiceSmall` | 普通话转写和粗粒度情绪 | 模型卡标为 `model-license` | 比赛、公开发布或商业使用前单独核对 |
| `emotion2vec/emotion2vec_plus_base` | 语音情绪概率 | 模型卡标为 `model-license` | 比赛、公开发布或商业使用前单独核对 |

模型权重不提交到 Git。由团队通过共享盘、Release 资产或内部制品库交接。

## 3. 数据

### Chinese Multi-Emotion Dialogue

- 来源：`Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset`
- 许可证：MIT
- 当前用途：补充训练、650 条同源留出测试和标签噪声分析

### BRIGHTER Mandarin Chinese

- 来源：`brighter-dataset/BRIGHTER-emotion-intensities`
- 许可证：CC-BY-4.0
- 当前用途：训练、dev 校准、1000 条开发和 1449 条密封测试
- 发布要求：保留署名、许可证链接和修改说明

详细的样本数、映射和限制见 [外部数据源记录](docs/external-data-sources.md)。

## 4. 字体与演示

组会 PPT 使用系统字体 `Hiragino Sans GB` 进行渲染。字体文件没有作为项目资产提交。其他电脑打开 PPT 时，如字体不可用，系统可能替换字体。

## 5. 新增第三方资源

新增模型、数据集、图片或字体时，提交者必须补充：

1. 来源链接；
2. 许可证；
3. 使用范围；
4. 是否允许再分发；
5. 必要的署名文本；
6. 对项目结果和复现实验的影响。

无法确认许可证的资源不得进入正式发布路径。
