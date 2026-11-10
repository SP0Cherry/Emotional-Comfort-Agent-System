# 情感抚慰陪伴原型系统 - 任务报告

## 一、项目概述

本项目基于已有的 **ASR 方言识别模块**（`../ASR/`）和 **普通话情感识别模块**（`../emotion-recognition-delivery/`），构建了一个面向中老年人的情感抚慰对话原型系统。系统提供 Web 对话界面，支持语音/文字输入、多会话管理、年龄段人格选择、用户自填 API 配置、全链路日志记录，并将情感识别结果注入 agent 回复策略。

## 二、系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器前端 (public/)                   │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ 会话列表  │  │   对话消息区      │  │  设置/人格弹窗  │  │
│  └──────────┘  └──────────────────┘  └───────────────┘  │
│         │           │          │                         │
│    新建/切换/删除   文字发送    语音输入                    │
│         │           │          │                         │
│    Web Speech API   │    录音生成WAV                       │
│         │           │          │                         │
└─────────┼───────────┼──────────┼─────────────────────────┘
          │           │          │
          ▼           ▼          ▼
┌─────────────────────────────────────────────────────────┐
│              Node.js 后端 (src/, 端口 5173)              │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ 会话/配置存储 │  │  Agent 编排器  │  │   日志系统     │  │
│  │ (JSON文件)   │  │ (orchestrator)│  │ (winston JSON) │  │
│  └─────────────┘  └──────┬───────┘  └────────────────┘  │
│                          │                               │
│          ┌───────────────┼───────────────┐               │
│          ▼               ▼               ▼               │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│   │ ASR 百炼    │  │ 情感识别    │  │  LLM 调用   │        │
│   │ (filetrans) │  │ (HTTP 4173)│  │ (OpenAI兼容)│        │
│   └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────┘
          │               │               │
          ▼               ▼               ▼
   百炼云端ASR    emotion-recognition   用户配置的
   (qwen-audio    -delivery 服务        LLM 端点
    3.1-asr)       (localhost:4173)
```

### 2.2 目录结构

```
emotion-companion/
├── src/
│   ├── server.js              # Express 服务入口，所有 REST 路由
│   ├── config-store.js        # 配置读写 (data/config.json)
│   ├── session-store.js       # 会话读写 (data/sessions/*.json)
│   ├── persona-store.js       # 人格配置读写 (data/personas.json)
│   ├── logger.js              # winston 结构化日志
│   ├── asr/
│   │   ├── bailian.js         # 百炼 filetrans ASR 客户端
│   │   └── hotwords.js        # 热词表加载与扁平化
│   ├── emotion/
│   │   ├── client.js          # 情感识别 HTTP 客户端 + 降级
│   │   └── prompt-builder.js  # 情感信号 → LLM prompt
│   ├── llm/
│   │   └── client.js          # OpenAI 兼容 chat completions 客户端
│   └── agent/
│       └── orchestrator.js    # 单轮对话编排（情感→prompt→LLM）
├── public/
│   ├── index.html             # 页面结构
│   ├── styles.css             # 样式
│   └── app.js                 # 前端逻辑（会话/消息/语音/设置）
├── data/                      # 运行时数据（.gitignore）
│   ├── config.json
│   ├── personas.json
│   └── sessions/
├── logs/                      # 日志文件（.gitignore）
├── package.json
├── .gitignore
└── report.md                  # 本报告
```

## 三、模块复用与改动

### 3.1 ASR 模块（`../ASR/`）

**复用内容：**
- `hotwords/cantonese_elderly.json`：直接作为默认热词表，通过 `src/asr/hotwords.js` 读取并扁平化为百炼 vocabulary 格式（414 个词条，12 个分类）。
- 百炼 filetrans 调用流程：参考 `test_code/eval_bailian_api.py` 的上传→提交→轮询→取结果→删除流程，用 Node.js `fetch` + REST API 重新实现（不使用 Python）。

**改动：** 无。ASR 模块的源码和数据均未修改。

### 3.2 情感识别模块（`../emotion-recognition-delivery/`）

**复用内容：**
- HTTP 接口 `POST /api/v1/emotion/turns`：通过 `src/emotion/client.js` 直接调用，传入 `session_id` 和 `text`，解析返回的 `dominant_emotion`、`dimensions`、`risk`、`decision_mode`、`companion_needs`。
- 端口 4173 的 Node 服务和其依赖的 Python 模型服务（端口 5055）保持原样运行。

**改动：** 无。情感模块源码未修改，通过其稳定的 HTTP 契约接入。

## 四、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 架构 | B/S，Node.js + Express | 与情感模块技术栈一致，单后端编排三个 HTTP 调用 |
| 前端 | 原生 HTML/CSS/JS | 原型无需框架，降低复杂度 |
| 存储 | JSON 文件 | 原型无需数据库，便于查阅和手动编辑 |
| LLM | OpenAI 兼容协议 | 覆盖百炼/DeepSeek/OpenRouter 等主流服务 |
| ASR | Web Speech + 百炼双引擎 | Web Speech 零配置即用，百炼支持方言热词 |
| 人格 | JSON 配置 + 热加载 | 年龄段可改、不耦合业务逻辑 |
| 日志 | winston JSON + 日期滚动 | 结构化便于分析，按日滚动避免单文件过大 |

## 五、核心流程

### 5.1 单轮对话流程

1. 用户输入文字（或语音转文字）
2. `orchestrator.processTurn()` 调用情感识别服务
3. 根据会话选定的年龄段人格加载 prompt
4. 拼装 system prompt = 人格 prompt + 抚慰角色设定 + 情感信号
5. 加载该会话历史（隔离），加上当前用户消息
6. 调用用户配置的 LLM 接口
7. 持久化用户消息和 assistant 回复
8. 返回回复 + 情感结果给前端展示

### 5.2 降级策略

- **情感服务不可用**：`emotion.available = false`，prompt 不含情感信号，对话继续
- **LLM 调用失败**：返回友好错误提示，不崩溃
- **百炼 ASR 未配置 key**：提示用户去设置页填写

## 六、运行方式

### 6.1 前置条件

1. 启动情感识别模块的 Python 模型服务（端口 5055）
2. 启动情感识别模块的 Node 服务（端口 4173）：`cd ../emotion-recognition-delivery && npm start`
3. 准备 LLM API（OpenAI 兼容）和可选的百炼 ASR API key

### 6.2 启动本系统

```bash
cd emotion-companion
npm install
npm start
```

打开浏览器访问 `http://127.0.0.1:5173`。

### 6.3 配置

在界面右上角点击 ⚙ 进入设置：
- **LLM 配置**：填写 base_url（如 `https://dashscope.aliyuncs.com/compatible-mode/v1`）、api_key、model（如 `qwen-plus`）
- **百炼 ASR**：填写 api_key，热词表路径默认 `../ASR/hotwords/cantonese_elderly.json`
- **人格配置**：可编辑三个年龄段的 prompt

## 七、REST API 一览

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/sessions` | 会话列表 |
| POST | `/api/sessions` | 新建会话 |
| GET | `/api/sessions/:id` | 会话历史 |
| DELETE | `/api/sessions/:id` | 删除会话 |
| POST | `/api/sessions/:id/messages` | 发送消息（返回 reply + emotion） |
| PUT | `/api/sessions/:id/persona` | 切换会话人格 |
| GET/PUT | `/api/config` | 读取/保存配置 |
| POST | `/api/config/test-llm` | LLM 连通性测试 |
| POST | `/api/config/test-asr` | ASR 配置测试 |
| GET/PUT | `/api/personas` | 人格配置读写 |
| POST | `/api/asr/bailian` | 百炼 ASR 转写（audio/wav） |
| GET | `/api/hotwords` | 当前热词表信息 |
| POST | `/api/logs/frontend` | 前端错误上报 |
| GET | `/api/health` | 健康检查 |

## 八、已知限制

1. **仅文字输出**：未实现 TTS 语音合成
2. **情感模块仅支持普通话**：方言情绪识别走情感模块的 fallback，未作方言校准
3. **百炼 ASR 延迟**：filetrans 为轮询模式，短语音也需数秒
4. **API key 明文存储**：`data/config.json` 未加密，原型阶段可接受
5. **无用户鉴权**：单用户本地原型，无登录/多租户
6. **Web Speech API 兼容性**：依赖浏览器，方言识别质量有限

## 九、测试与验证结果

| 验证项 | 结果 |
|--------|------|
| 服务启动与健康检查 | ✓ |
| 会话 CRUD | ✓ |
| 配置读写持久化 | ✓ |
| 人格配置读写 | ✓ |
| 热词表加载（414 词） | ✓ |
| 多会话隔离 | ✓ |
| 端到端消息流程（LLM 错误友好处理） | ✓ |
| 情感服务降级 | ✓ |
| 前端错误上报到日志 | ✓ |
| 页面加载无 JS 错误 | ✓ |
| 语音输入 UI（Web Speech / 百炼切换） | ✓ |
