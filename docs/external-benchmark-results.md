# 外部普通话情绪评测结果

生成时间：2026-11-02T00:59:16.784Z

## 数据

- 来源：Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset
- 许可证：MIT
- 映射后样本：3271
- 测试样本：650
- 校准样本：324
- 说话人隔离：否
- 数据噪声：Original dataset has no speaker IDs and visible label noise. Use as external stress test, not a gold speaker-independent benchmark.

## 测试结果

| 方法 | Accuracy | Macro-F1 | UAR | ECE（原始） | ECE（校准） |
| --- | ---: | ---: | ---: | ---: | ---: |
| rule | 33.7% | 25.2% | 27.2% | 5.1% | 4.7% |
| qwen | 59.4% | 50.8% | 49.7% | 26.5% | 3.7% |
| hybrid | 59.8% | 51.4% | 49.9% | 6.6% | 3.4% |

## 95% Bootstrap 置信区间

| 方法 | Accuracy 区间 | Macro-F1 区间 |
| --- | ---: | ---: |
| rule | 30.0%–37.4% | 22.4%–28.0% |
| qwen | 56.2%–63.1% | 48.1%–53.7% |
| hybrid | 56.8%–63.7% | 48.5%–54.3% |

## 结论限制

- 原始数据没有说话人字段，不能视为说话人隔离测试。
- 原始标签存在可见噪声，部分明显焦虑或难过语句被标为平淡。
- Chinese-Emotion-Small 使用该数据训练，不能作为独立泛化结果。
- 校准参数只在 dev 集拟合，test 集只用于最终报告。
- 本轮不评价语音准确率，因为该数据不含音频。
