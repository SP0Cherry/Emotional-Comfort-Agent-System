# 微调模型输出策略调参

## Dev 集选择结果

- 多标签融合权重：0.50
- 类别偏置：`{"joy":0,"calm":0,"sadness":0,"anxiety":0,"anger_irritation":0,"neutral":0}`
- Dev Accuracy：78.4%
- Dev Macro-F1：72.7%

## 未参与调参的 Test

- Accuracy：76.1%
- Macro-F1：63.0%
- 负面检测 F1：86.9%

测试集没有参与融合权重或类别偏置搜索。
