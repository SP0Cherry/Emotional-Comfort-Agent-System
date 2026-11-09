# 情感模型夜间执行状态

最后更新：2026-11-02 16:45（Asia/Shanghai）

## 当前可用基线

- 规则 + 微调 RoBERTa（默认）+ Qwen2.5-1.5B（回退）+ SenseVoiceSmall + emotion2vec+base
- 29 项测试通过
- 服务：`npm run demo`
- 页面：`http://127.0.0.1:4173`
- 方言接口：普通话 fallback

## 模型选型结果

| 语料 | 规则 | Qwen | 规则 + Qwen |
| --- | ---: | ---: | ---: |
| 36 条回归集 | 100% | 86.1% | 97.2% |
| 7 条开发挑战集 | 100% | 57.1% | 100% |
| 10 条全新留出集 | 40% | 90% | 90% |

- Qwen 热推理约 1.3～1.8 秒；
- SenseVoice 示例音频约 0.61 秒；
- emotion2vec 示例音频约 0.19 秒；
- 三模型端到端约 2.49 秒；
- 模型服务优先加载本地缓存，不依赖启动时网络。
- 模型缓存约 6.2 GB，项目内两个虚拟环境约 1.34 GB；
- 三模型常驻进程 RSS 约 639 MB（MPS 共享内存不完全计入 RSS）。
- 当前微调 RoBERTa 与两个语音模型常驻进程 RSS 约 3.0 GB。
- 同一 1000 条 BRIGHTER 测试：微调 RoBERTa Accuracy 75.3%，Macro-F1 66.9%。
- 未参与调参的 1449 条 BRIGHTER 密封测试：Accuracy 78.3%，Macro-F1 60.2%。

## 当前限制

- Qwen 对 `neutral`/`calm` 仍有混淆
- 没有真实用户语音评测集
- 没有正式置信度校准
- 微调模型训练集仅 34 条焦虑，密封测试没有焦虑样本

## 已完成

1. 完成 Qwen 文本选型；
2. 完成 emotion2vec+base 语音情绪接入；
3. 完成三模型融合、置信度限制和整轮联调；
4. 完成全新留出集与错误分析；
5. 完成数据采集规范、清单校验器和文本微调入口；
6. 完成模型说明、接口规约、阶段报告和工作清单。
7. 完成 BRIGHTER 官方 train 多任务微调并接入默认推理路径。
8. 完成 1449 条密封测试和同集公平对照。

## 环境门槛

真实说话人数据采集、方言模型训练和正式置信度校准需要真人录音与标注，不能在无人参与的本晚任务中伪造。工具入口已准备：

```bash
npm run validate:data -- data/emotion-samples.jsonl
npm run finetune:text -- data/emotion-samples.jsonl
```
