# 外部普通话情绪数据源记录

## 1. 已使用：Chinese Multi-Emotion Dialogue

- 地址：https://huggingface.co/datasets/Johnson8187/Chinese_Multi-Emotion_Dialogue_Dataset
- 许可证：MIT
- 原始样本：4159
- 六类可映射样本：3271
- 测试样本：650
- 标签来源：人工标注，但存在可见噪声
- 分组：无对话 ID 或说话人 ID
- 用途：外部压力测试和标签噪声分析
- 限制：Chinese-Emotion-Small 曾使用该数据训练，不能作为它的独立泛化结果

## 2. 已使用：BRIGHTER Mandarin Chinese

- 地址：https://huggingface.co/datasets/brighter-dataset/BRIGHTER-emotion-intensities
- 许可证：CC-BY-4.0
- 官方划分：dev 200 条，test 2642 条
- 六类映射后：dev 190 条，test 2449 条
- 测试抽样：按类别最低配额分层抽取 1000 条
- 标签：六种情绪的人类强度评分
- 标签规则：取 anger、disgust、fear、joy、sadness 中最高强度；全零为 neutral；并列和仅 surprise 样本排除
- 分组：没有说话人 ID
- 限制：没有 calm 标签，anxiety 测试样本仅 39 条，无法完成可靠的说话人隔离评测

## 3. 未使用：Basis Global Emotions

- 地址：https://huggingface.co/datasets/basis-ai/basis-global-emotions
- 类型：包含普通话真实说话人的大规模多语言语音情绪数据
- 访问状态：需要登录并接受门控许可
- 未使用原因：没有用户登录授权，不绕过访问控制
- 后续价值：若能合法获得访问，适合做 SenseVoice 与 emotion2vec 的正式语音评测

## 4. 未使用：Robot-EQ

- 地址：https://huggingface.co/datasets/Tongji-Emotion/Robot-EQ
- 许可：CC-BY-NC-4.0
- 内容：机器人行为判断、社交规范、空间理解
- 未使用原因：任务标签不是六类说话人情绪，不能直接作为情感识别基准

## 评测约束

1. 缺少说话人分组时只能报告外部压力测试，不宣称说话人隔离。
2. 标签映射必须在模型推理前确定，不能根据预测反向修改 gold label。
3. dev 只用于校准，test 不参与阈值或提示词调优。
4. 无音频文本数据不能用于语音准确率结论。
