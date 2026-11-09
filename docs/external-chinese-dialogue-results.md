# 外部普通话情绪评测结果

生成时间：2026-11-02T14:34:52.692Z

## 数据

- 来源：Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset
- 许可证：MIT
- 映射后样本：3271
- 测试样本：650
- 校准样本：324
- Qwen 平均/P95 延迟：1539.7 / 1778.3 ms
- Qwen 无效输出：0 条
- 说话人隔离：否
- 数据噪声：Original dataset has no speaker IDs and visible label noise. Use as external stress test, not a gold speaker-independent benchmark.

## 测试结果

| 方法 | Accuracy | Macro-F1 | UAR | ECE（原始） | ECE（校准） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 多数类基线 | 26.6% | 8.4% | 20.0% | 5.5% | 5.5% |
| 规则 | 33.7% | 30.3% | 32.7% | 5.1% | 4.7% |
| Qwen | 59.4% | 61.0% | 59.7% | 26.5% | 3.7% |
| 规则 + Qwen | 59.8% | 61.7% | 59.9% | 6.6% | 3.4% |
| 微调 RoBERTa | 63.7% | 59.5% | 63.1% | 8.8% | 8.6% |
| 规则 + 微调 RoBERTa | 64.9% | 62.1% | 64.0% | 14.5% | 7.5% |

## 95% Bootstrap 置信区间

| 方法 | Accuracy 区间 | Macro-F1 区间 |
| --- | ---: | ---: |
| 多数类基线 | 23.4%–30.0% | 7.6%–9.2% |
| 规则 | 30.3%–37.4% | 26.6%–34.2% |
| Qwen | 55.4%–63.4% | 57.2%–64.7% |
| 规则 + Qwen | 55.8%–64.0% | 58.0%–65.2% |
| 微调 RoBERTa | 59.7%–67.2% | 55.7%–63.3% |
| 规则 + 微调 RoBERTa | 61.2%–68.5% | 58.4%–65.4% |

## 规则 + 微调 RoBERTa 逐类指标

| 类别 | 支持数 | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| joy | 123 | 71.3% | 91.1% | 80.0% |
| sadness | 110 | 52.9% | 81.8% | 64.3% |
| anxiety | 108 | 44.7% | 19.4% | 27.1% |
| anger_irritation | 173 | 86.1% | 68.2% | 76.1% |
| neutral | 136 | 66.4% | 59.6% | 62.8% |

### 主要混淆

- 真实 anger_irritation → 预测 sadness：42 条
- 真实 anxiety → 预测 sadness：27 条
- 真实 anxiety → 预测 neutral：27 条
- 真实 neutral → 预测 joy：26 条
- 真实 anxiety → 预测 joy：12 条
- 真实 neutral → 预测 anxiety：12 条
- 真实 anxiety → 预测 anger_irritation：11 条
- 真实 anxiety → 预测 calm：10 条

## 结论限制

- 原始数据没有说话人字段，不能视为说话人隔离测试。
- 原始标签存在可见噪声，部分明显焦虑或难过语句被标为平淡。
- Chinese-Emotion-Small 使用该数据训练，不能作为独立泛化结果。
- 校准参数只在 dev 集拟合，test 集只用于最终报告。
- 本轮不评价语音准确率，因为该数据不含音频。
