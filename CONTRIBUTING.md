# 协作指南

本仓库是多人项目。提交代码前，先确认改动属于哪个模块，并阅读该模块的接口和限制。

## 1. 开始工作

```bash
git switch main
git pull --ff-only
git switch -c feature/<module>-<topic>
```

示例：

```text
feature/emotion-add-context-window
feature/personality-profile-schema
fix/emotion-session-expiry
```

## 2. 修改范围

优先只修改自己负责的目录：

| 范围 | 主要内容 |
| --- | --- |
| `src/`、`public/`、`test/` | 情感识别服务、页面和测试 |
| `scripts/`、`evaluation/` | 训练、评测和数据构建 |
| `docs/` | 接口、实验、限制和交接记录 |
| `outputs/` | 指定要交付的最终 PPT 或小型结果文件 |

需要修改其他模块时，先在 issue、PR 或群聊中说明原因。

## 3. 开发规则

1. 使用 Node.js 20 以上。
2. 不引入不必要的框架和大依赖。
3. 不提交 `.env`、Token、用户录音、虚拟环境、模型缓存和完整模型权重。
4. 不在代码中写死用户主目录或绝对路径。
5. 新功能必须有测试或可复现的评测记录。
6. 文档中的数字必须能回溯到报告或评测文件。
7. 不把同源留出结果写成跨数据集泛化结果。
8. 不把规则 fallback 写成原生方言能力。

## 4. 提交前检查

```bash
npm test
git diff --check
git status --short
```

涉及页面时再人工检查：

- 桌面宽度和窄屏是否溢出；
- 浏览器控制台是否有错误；
- 模型不可用时页面是否能降级；
- 低置信度是否显示确认或澄清状态；
- 方言 fallback 是否有明确提示。

涉及接口时：

- 更新 [接口规约](docs/emotion-recognition-spec.md)；
- 明确是否需要升级 `schema_version`；
- 同时修改服务端、测试和消费方；
- 保留旧字段的兼容期。

## 5. 提交信息

建议使用：

```text
feat(emotion): add session trend summary
fix(emotion): handle expired session lookup
docs(emotion): define integration contract
test(emotion): cover dialect fallback
```

一个提交只解决一类问题。不要把模型、数据和页面重构混在同一提交中。

## 6. 合并条件

- 自动测试通过；
- 没有无关的格式化改动；
- 没有密钥、私有数据和大二进制文件；
- 接口变更已由下游确认；
- 至少一名非作者评审；
- 文档与实现一致。

## 7. 评测数据

修改 `evaluation/` 或标签映射时，必须记录：

- 数据来源；
- 许可证；
- 原始样本数；
- 映射后样本数；
- train/dev/test 划分方式；
- 是否参与提示词、阈值或模型选择；
- 文件哈希或 manifest。

密封测试在最终评估前不得用于调试。

## 8. 重要文档

- [当前接口规约](docs/emotion-recognition-spec.md)
- [跨模块协作契约](docs/team-integration-contract.md)
- [交付报告](docs/emotion-recognition-delivery-report.md)
- [长期规划](docs/emotion-recognition-future-spec.md)
- [第三方依赖与数据说明](THIRD_PARTY_NOTICES.md)
