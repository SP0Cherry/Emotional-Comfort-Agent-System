# 多人协作与跨模块集成契约

| 项目 | 内容 |
| --- | --- |
| 版本 | v1.0 |
| 状态 | 自本模块交付起生效 |
| 更新日期 | 2026-11-09 |

本文档约束情感识别模块与其他模块的协作方式。接口字段的正式定义见 [情感识别模块接口与协作规约](emotion-recognition-spec.md)。

## 1. 模块责任

| 模块 | 主要输入 | 主要输出 | 当前边界 |
| --- | --- | --- | --- |
| 情感识别 | 文本、WAV、声学摘要、会话 ID | 情绪分布、连续维度、趋势、风险、决策建议 | 当前只支持普通话 |
| 人格建模 | 多轮情绪状态、时间窗口 | 长期偏好或交互风格 | 不得从单轮情绪推断人格 |
| 回应策略 | 情绪状态、风险、人格状态 | 回复意图和策略 | 必须支持 `clarify` |
| 方言输出 | 回复内容、情绪韵律控制 | 方言语音 | 当前没有正式方言模型 |

模块负责人对以下内容负责：

1. 自己模块的代码、测试、文档和评测口径；
2. 不兼容变更的迁移说明；
3. 接口不可用时的降级行为；
4. 数据来源、许可和隐私边界；
5. 在共享分支上处理他人评审意见。

## 2. 接口稳定等级

### 2.1 稳定字段

以下字段已经进入跨模块契约：

- `schema_version`
- `request_id`
- `session_id`
- `turn_id`
- `timestamp`
- `status`
- `decision_mode`
- `dominant_emotion`
- `emotion_distribution`
- `dimensions`
- `temporal`
- `companion_needs`
- `risk`
- `quality`
- `evidence`
- `dialect`
- `latency_ms`

修改这些字段的类型或语义必须获得下游模块确认，并升级 schema 主版本。

### 2.2 调试字段

以下字段用于模型排障和展示，下游不得依赖它们的内部细节：

- `semantic_model`
- `speech_model`
- `speech_analysis`
- `recognized_text`

这些字段可以增加内容，但不得影响稳定字段的解释。

## 3. 枚举与阈值

1. 六类情绪只使用 `joy/calm/sadness/anxiety/anger_irritation/neutral`。
2. 不得新增 `anger`、`irritated` 等同义别名作为正式输出。
3. 风险等级只使用 `none/watch/urgent`。
4. 趋势只使用 `improving/stable/worsening/fluctuating/insufficient_data`。
5. 决策模式只使用 `confident/tentative/clarify`。
6. `confidence` 不能当作医学诊断概率。
7. 下游不得自行修改情感识别的置信度阈值，再把结果称为本模块结论。若需要不同产品策略，应在回应层单独配置并注明来源。

## 4. 集成优先级

回应策略建议按以下顺序处理：

1. `risk.level=urgent`：进入高优先级安全流程；
2. `risk.level=watch`：温和追问并持续关注；
3. `decision_mode=clarify`：不输出强情绪断言；
4. `decision_mode=tentative`：使用不确定表达；
5. 正常情绪策略：结合主情绪、分布、连续维度、趋势和陪伴需求。

`urgent` 与 `clarify` 同时出现时，风险优先，但语言仍需避免夸张和诊断化。

## 5. 空值与降级

下游必须显式处理以下情况：

- `speech_analysis=null`
- `semantic_model.available=false`
- `speech_model.available=false`
- `quality.speech=null`
- `status=partial`
- `trend=insufficient_data`
- `dialect.supported=false`

模型不可用不等于服务不可用。只有 `status=error` 或 HTTP 错误码才表示本轮无法得到结构化结果。

## 6. 会话状态

1. 调用方应复用同一 `session_id` 才能在五轮窗口内形成趋势。
2. 用户主动清空对话时，应调用 `DELETE` 删除当前会话。
3. 服务重启会清空内存会话，调用方不得假定状态永久存在。
4. 共享内存存储仅适合单机联调，不适合多副本生产部署。
5. 若迁移到持久化存储，必须新增数据保留和删除策略，保持对外端点不变。

## 7. 方言扩展

当前只真正实现普通话：

- `mandarin` 和 `zh-CN` 返回 `mode=native`；
- 其他语言代码返回 `mode=fallback`、`supported=false`；
- 不得将普通话结果标注成方言原生结果；
- 新增方言必须同时提供方言 ASR、情绪模型或校准器、目标域测试和降级策略；
- 方言扩展不得改变现有通用字段语义。

## 8. 数据与评测约定

1. 训练、验证和测试不得混用。
2. BRIGHTER 官方 test 的前 1000 条用于开发和错误分析，后 1449 条作为密封测试。
3. 650 条同源独立留出测试不能称为跨数据集泛化。
4. 两套公开数据都没有说话人字段，因此当前不能声明说话人隔离评测。
5. 任何标签映射调整都要在推理前冻结，不能根据模型预测反向修改 gold label。
6. 新增或替换评测数据时必须更新 manifest、样本数、来源和许可证。
7. 不能用回归集或挑战集的结果冒充公开数据留出集结果。

## 9. 隐私与安全

1. 默认服务只监听回环地址。
2. 原始音频只在本地 WAV 路径中处理，推理后不持久化。
3. 会话只存储结构化状态，不存储原文本数据库。
4. 不提交 `.env`、访问令牌、完整模型权重或用户私有录音。
5. 风险规则只用于原型提示，不替代人工核查、紧急资源或医疗流程。
6. 若新增云模型、持久化日志、遥测或跨机传输，必须单独做隐私评审。

## 10. 分支与评审流程

建议采用：

1. 从最新 `main` 创建 `feature/<module>-<topic>` 或 `fix/<module>-<topic>` 分支；
2. 一个提交只解决一个可说明的问题；
3. 涉及接口变更时，同时提交代码、测试、接口文档和迁移说明；
4. 至少一名非作者评审后才能合并；
5. 合并前运行与改动相关的测试；
6. 不直接在他人负责的模块中改写业务逻辑，确需修改时先在 issue 或群聊中说明；
7. 不强制推送共享分支，不覆盖其他人的提交历史。

## 11. 合并检查清单

### 代码

- [ ] `npm test` 通过
- [ ] 新增端点或字段有测试
- [ ] 没有硬编码本机绝对路径
- [ ] 没有提交模型、虚拟环境、缓存或密钥

### 文档

- [ ] 当前接口与 [接口规约](emotion-recognition-spec.md) 一致
- [ ] 不兼容变更已升级 schema
- [ ] 评测限制没有被省略
- [ ] 数据来源和许可证可追溯

### 联调

- [ ] 下游处理 `partial` 和空模态
- [ ] 下游处理 `clarify`
- [ ] 风险优先于普通情绪
- [ ] 方言 fallback 未被误标为原生支持

## 12. 冲突处理

字段含义发生冲突时，按以下顺序确认：

1. 当前代码与自动测试；
2. [当前接口规约](emotion-recognition-spec.md)；
3. [验收报告](emotion-recognition-delivery-report.md)；
4. [长期需求与规划](emotion-recognition-future-spec.md)。

长期规划不能覆盖当前实现契约。发现文档与代码不一致时，应在同一变更中修复，不能只更新其中一侧。
