# 普通话多任务模型交接

| 项目 | 内容 |
| --- | --- |
| 模型目录 | `models/brighter-johnson-multitask/` |
| 基座 | `hfl/chinese-roberta-wwm-ext` |
| 输出 | 五类主情绪、多标签、负面检测、强度 |
| 权重大小 | 约 390 MiB |
| 默认运行设备 | Apple MPS，失败时由服务层回退 |

模型权重不进入 Git。接手者需要从团队共享盘、GitHub Release 资产或内部制品库取得目录，并放到上述路径。

## 1. 必需文件

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `model.pt` | 390 MiB | `cb51805812a55754f903dde1df5a2e4abd69a98a38459391cb7ab47f2ad459fe` |
| `tokenizer.json` | 429 KiB | `519f3bcfdcf0a69ab248d5b68bb25d83d3a237f4c19d41668725fbd3eeb3ab34` |
| `vocab.txt` | 107 KiB | `45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c` |
| `tokenizer_config.json` | 1.2 KiB | `bc3788b020afe8d772684fc7a5f64cbb562f1b816d2585858558d3df8b95bbf7` |
| `special_tokens_map.json` | 695 B | `5d5b662e421ea9fac075174bb0688ee0d9431699900b90662acd44b2a350503a` |
| `training_config.json` | 617 B | `f9e44d5d456e7ea254703b1652b6483a49e6ab9d89b68734f0b47f2afb75ba08` |
| `metrics.json` | 7.9 KiB | `8a14395841ff1c6229cf3d84d7e58dfff02a68881c333ed4448c765b3e1022ac` |
| `sealed-predictions.jsonl` | 420 KiB | `ae95c4169a881f1b55164b9282580d8b0bf5899c6366d9ec2d798cd5507ac75c` |

## 2. 校验

在仓库根目录执行：

```bash
shasum -a 256 models/brighter-johnson-multitask/model.pt
```

结果必须与上表一致。

目录应至少包含：

```text
models/brighter-johnson-multitask/
├── metrics.json
├── model.pt
├── sealed-predictions.jsonl
├── special_tokens_map.json
├── tokenizer.json
├── tokenizer_config.json
├── training_config.json
└── vocab.txt
```

## 3. 加载检查

```bash
PRELOAD_FINETUNED=1 zsh scripts/run-model-service.sh
curl http://127.0.0.1:5055/health
```

响应中的 `text_finetuned.ready` 必须为 `true`。

再检查模块能力：

```bash
curl http://127.0.0.1:4173/api/v1/emotion/capabilities
```

## 4. 回退行为

如果模型目录不存在或加载失败：

1. Node 服务仍应启动；
2. 普通分类应回退到 Qwen 或专用文本分类器；
3. 模型都不可用时，规则分支仍应返回结果；
4. 响应必须体现 `partial` 或模型 `available=false`；
5. 不得返回伪造的微调模型结果。

## 5. 训练与指标

重新训练：

```bash
npm run finetune:multitask
```

关键结果：

- 1000 条同集：Accuracy 76.5%，Macro-F1 66.0%；
- 1449 条密封：Accuracy 80.2%，Macro-F1 75.2%；
- 负面 F1：90.3%，Recall 93.4%；
- 650 条同源留出：Accuracy 91.8%，Macro-F1 91.5%，焦虑 F1 88.9%。

详细实验见 [微调结果](finetuned-model-results.md)。

## 6. 禁止事项

1. 不提交 `model.pt` 到普通 Git。
2. 不把模型与未经确认的许可证资源一起公开发布。
3. 不把该模型写成跨方言模型。
4. 不用 1449 条密封集继续调参。
5. 不把 650 条同源结果写成跨数据集泛化。
