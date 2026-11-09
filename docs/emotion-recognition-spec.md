# 情感识别模块接口与协作规约

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 状态 | 当前实现契约 |
| 适用范围 | 普通话文本、语音声学摘要、语音模型接入 |
| 默认服务地址 | `http://127.0.0.1:4173` |
| 更新时间 | 2026-11-09 |

> 本文档描述仓库中已经实现并经过测试的接口。文本、语音、视觉、方言和个人基线的长期设想见 [长期需求与规划](emotion-recognition-future-spec.md)，不得把其中未实现的能力当成当前能力。

## 1. 模块边界

情感识别模块负责把用户的一轮普通话输入转换为结构化情绪状态，并向人格建模、回应策略和语音输出模块提供稳定信号。

当前实现负责：

1. 六类情绪分类和概率分布；
2. 效价、唤醒度和情绪强度；
3. ASR 置信度、文本质量、语音声学质量和模型可用性；
4. 最近五轮趋势、低效价持续时间和稳定性；
5. 独立的 `none/watch/urgent` 风险提示；
6. 低置信度时的 `confident/tentative/clarify` 决策建议；
7. 普通话语音转写、SenseVoice 粗粒度情绪和 emotion2vec 概率接入；
8. 方言代码进入接口时的显式普通话 fallback。

当前实现不负责：

1. 抑郁、焦虑等医学诊断；
2. 稳定人格判断或长期用户画像；
3. 陪伴回复生成；
4. 方言 ASR、方言情绪模型或方言 TTS；
5. 自动危机救援；
6. 说话人隔离精度声明。

## 2. 兼容性规则

1. `schema_version` 当前固定为 `"1.0"`。
2. 在 `1.x` 范围内，可以增加字段或枚举值，不得重命名现有字段、改变类型或改变已有字段语义。
3. 删除字段、改变枚举含义、改变取值方向或改变端点时必须升级到新的 schema 主版本，并同时更新测试、SDK 和下游文档。
4. 下游必须忽略未知字段，不能因为新增字段而解析失败。
5. 下游不得只读取 `dominant_emotion.label`。任何强回应都应同时检查 `decision_mode`、`dimensions`、`temporal` 和 `risk`。

## 3. 标签与取值范围

### 3.1 一级情绪

| API 值 | 含义 |
| --- | --- |
| `joy` | 高兴、积极、愉悦 |
| `calm` | 平静、放松、稳定 |
| `sadness` | 悲伤、失落、低落 |
| `anxiety` | 焦虑、担心、不安 |
| `anger_irritation` | 愤怒或烦躁 |
| `neutral` | 没有明显情绪倾向 |

六类概率之和应为 `1.0`，允许浮点舍入误差。

### 3.2 连续维度

| 字段 | 范围 | 含义 |
| --- | ---: | --- |
| `dimensions.valence` | `[-1, 1]` | 负值偏负面，正值偏正面 |
| `dimensions.arousal` | `[0, 1]` | 越高表示越活跃、紧张或高能量 |
| `dimensions.intensity` | `[0, 1]` | 当前情绪表达强度 |

### 3.3 风险

| 值 | 下游处理建议 |
| --- | --- |
| `none` | 按普通情绪流程处理 |
| `watch` | 温和追问，避免轻视，持续关注 |
| `urgent` | 风险优先于普通情绪，进入人工确认的安全流程 |

风险分支独立于情绪分类。`decision_mode=clarify` 不能降低风险等级。

### 3.4 决策模式

| 值 | 当前阈值 | 下游行为 |
| --- | ---: | --- |
| `confident` | `dominant_emotion.confidence >= 0.65` | 可以提供细分类提示 |
| `tentative` | `0.40 <= confidence < 0.65` | 使用“听起来”“可能是”等表达并建议确认 |
| `clarify` | `confidence < 0.40` | 不强行判类，优先开放式追问 |

`confidence` 是当前轮的决策分数，不应被解释为医学概率。阈值是应用策略，不是经真实陪伴场景校准后的科学结论。

`companion_needs` 当前可能包含 `listen`、`company`、`practical_help`、`clarify`、`comfort` 和 `celebrate`。每项都带独立置信度，最多返回两项。

## 4. HTTP 端点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 服务和会话数量健康检查 |
| `GET` | `/api/v1/emotion/capabilities` | 查询模型与 fallback 能力 |
| `POST` | `/api/v1/emotion/sessions` | 创建会话 |
| `POST` | `/api/v1/emotion/turns` | 提交一轮输入并返回情绪状态 |
| `GET` | `/api/v1/emotion/sessions/{session_id}` | 查询会话内最近状态 |
| `DELETE` | `/api/v1/emotion/sessions/{session_id}` | 删除当前进程中的会话 |

默认服务只监听 `127.0.0.1`。如果要跨模块联调，应由项目统一决定是增加同机反代、内部 RPC 还是受控的局域网网关，不得直接把开发服务暴露到公网。

## 5. 单轮分析请求

### 5.1 请求

```http
POST /api/v1/emotion/turns
Content-Type: application/json
```

```json
{
  "session_id": "sess-demo-001",
  "turn_id": 1,
  "text": "明天要答辩了，我一直睡不着，担心会搞砸。",
  "asr_confidence": 0.82,
  "dialect": "mandarin",
  "speech_features": {
    "duration_ms": 3200,
    "speech_ratio": 0.72,
    "mean_db": -22,
    "variation_db": 11,
    "mean_pitch_hz": 218,
    "pitch_variation_hz": 54,
    "pause_count": 2,
    "clipping_ratio": 0
  }
}
```

### 5.2 输入字段

| 字段 | 必需 | 类型 | 约束 |
| --- | --- | --- | --- |
| `session_id` | 否 | string | `[A-Za-z0-9_-]`，1～80 字符；省略时自动生成 |
| `turn_id` | 否 | integer | 必须不小于当前 `nextTurnId`；省略时自动递增 |
| `text` | 条件必需 | string | 最多 500 字符；无语音输入时不能为空 |
| `asr_confidence` | 否 | number | `[0, 1]`，默认 `0.95` |
| `dialect` | 否 | string | 字母开头，最多 32 字符，可含数字、下划线、连字符 |
| `speech_features` | 否 | object/null | 浏览器提取的声学摘要 |
| `speech_audio_base64` | 否 | string | 仅支持 WAV base64，解码后不超过 4.5 MiB |

整个 JSON 请求体不超过 8 MiB，必须使用 `application/json`。

### 5.3 声学摘要

| 字段 | 类型 | 服务端约束 |
| --- | --- | --- |
| `duration_ms` | integer | 截断到 `0～120000` |
| `speech_ratio` | number | 截断到 `[0, 1]` |
| `mean_db` | number | 截断到 `[-90, 0]` |
| `variation_db` | number | 截断到 `[0, 60]` |
| `mean_pitch_hz` | number | 截断到 `[0, 600]` |
| `pitch_variation_hz` | number | 截断到 `[0, 300]` |
| `pause_count` | integer | 截断到 `0～100` |
| `clipping_ratio` | number | 截断到 `[0, 1]` |

声学摘要只作为质量和唤醒度证据，不单独决定正负情绪。语音少于 200 ms 时，该分支返回不可用，不应把短音频当成可靠结论。

### 5.4 方言 fallback

`mandarin` 和 `zh-CN` 是原生支持值。其他安全格式的语言代码可以进入接口，但必须返回：

```json
{
  "dialect": {
    "code": "mandarin",
    "used": "mandarin",
    "requested": "sichuan",
    "supported": false,
    "mode": "fallback",
    "calibrated": false,
    "warning": "当前仅提供普通话模型，方言请求已回退，结果未作方言校准。"
  }
}
```

下游不得把这个响应显示为“四川话情绪识别成功”。

## 6. 单轮分析响应

```json
{
  "schema_version": "1.0",
  "request_id": "req-4a7a6f58-6b7a-4ea1-97aa-6c6a4af48b8b",
  "session_id": "sess-demo-001",
  "turn_id": 1,
  "timestamp": "2026-11-09T08:00:00.000Z",
  "status": "ok",
  "decision_mode": "confident",
  "dominant_emotion": {
    "label": "anxiety",
    "confidence": 0.82
  },
  "emotion_distribution": {
    "joy": 0.02,
    "calm": 0.04,
    "sadness": 0.12,
    "anxiety": 0.71,
    "anger_irritation": 0.07,
    "neutral": 0.04
  },
  "dimensions": {
    "valence": -0.52,
    "arousal": 0.68,
    "intensity": 0.77
  },
  "temporal": {
    "window_turns": 1,
    "trend": "insufficient_data",
    "low_valence_duration_s": 0,
    "stability": 1
  },
  "companion_needs": [
    {
      "label": "comfort",
      "confidence": 0.76
    }
  ],
  "risk": {
    "level": "none",
    "reasons": [],
    "confidence": 0.9,
    "matched_phrase": null
  },
  "quality": {
    "overall": 0.82,
    "text": 0.82,
    "speech": 0.65,
    "vision": null
  },
  "evidence": {
    "text": [
      "文本线索：睡不着",
      "文本线索：担心"
    ],
    "speech": [
      "语音有效占比：72%",
      "平均音量：-22 dB"
    ],
    "vision": []
  },
  "recognized_text": "明天要答辩了，我一直睡不着，担心会搞砸。",
  "dialect": {
    "code": "mandarin",
    "used": "mandarin",
    "requested": "mandarin",
    "supported": true,
    "mode": "native",
    "calibrated": false,
    "warning": null
  },
  "latency_ms": 236
}
```

实际响应还可能包含 `semantic_model`、`speech_model` 和 `speech_analysis`。这些字段用于调试和模型追踪，下游不得依赖其内部文本格式。

### 6.1 状态枚举

| 状态 | 含义 |
| --- | --- |
| `ok` | 至少一个有效输入，并取得可用分析结果 |
| `partial` | 只有文本或部分模态可用，但仍能返回结果 |
| `insufficient_data` | 有效信息不足 |
| `error` | 无法产生结果 |

当前服务在文本请求没有可用语音时通常返回 `partial`。下游必须允许 `partial` 结果进入对话流程。

### 6.2 趋势

`temporal` 使用最近五轮状态。

| 字段 | 说明 |
| --- | --- |
| `window_turns` | 当前窗口实际轮数，`0～5` |
| `trend` | `improving/stable/worsening/fluctuating/insufficient_data` |
| `low_valence_duration_s` | 连续低效价持续时间，秒 |
| `stability` | `[0, 1]`，越高表示窗口内效价越稳定 |

不足两轮数据时，`trend` 必须为 `insufficient_data`。

## 7. 会话接口

### 7.1 创建会话

```http
POST /api/v1/emotion/sessions
```

返回 `201`：

```json
{
  "session_id": "sess-04c7a415-85a6-4166-b307-2705c53f8f34",
  "created_at": "2026-11-09T08:00:00.000Z"
}
```

### 7.2 查询会话

```http
GET /api/v1/emotion/sessions/{session_id}
```

返回 `session_id`、`created_at`、`turns` 和最近状态数组。会话不存在或过期时返回 `404 session_not_found`。

### 7.3 删除会话

```http
DELETE /api/v1/emotion/sessions/{session_id}
```

成功返回 `204`。删除是幂等动作，不存在的会话也返回 `204`。

当前会话只在进程内存中保存：

- 最多 200 个会话；
- 每个会话最多保留 20 个状态；
- 4 小时无访问后过期；
- 服务重启后全部丢失。

多人联调阶段如果要求持久化，必须先定义用户授权、保留周期、删除审计和数据库迁移，不能直接把现有内存存储替换成无期限日志。

## 8. 错误契约

错误统一返回：

```json
{
  "error": {
    "code": "invalid_text",
    "message": "text 必须是字符串"
  }
}
```

| HTTP | 常见代码 | 含义 |
| ---: | --- | --- |
| `400` | `invalid_json`、`invalid_body` | JSON 或请求体结构无效 |
| `404` | `session_not_found`、`api_not_found` | 会话或端点不存在 |
| `409` | `invalid_turn_id` | 轮次编号不是递增整数 |
| `413` | `payload_too_large`、`speech_audio_too_large` | 请求或音频过大 |
| `415` | `unsupported_media_type` | 单轮接口未使用 JSON |
| `422` | `empty_text`、`text_too_long`、`invalid_dialect` | 字段不符合约束 |
| `500` | `internal_error` | 未分类服务错误 |

模型超时或不可用通常不返回 HTTP 500，而是回退到规则或文本路径，并通过 `semantic_model.available=false`、`speech_model.available=false` 或 `partial` 状态暴露降级。

## 9. 跨模块消费规则

### 9.1 人格建模模块

可以消费多轮趋势、稳定性、陪伴需求线索和连续情绪维度。不得把单轮 `anxiety` 直接解释成“焦虑型人格”，也不得使用情绪识别结果做医学标签。

### 9.2 回应策略模块

建议按以下顺序决策：

1. 先看 `risk.level`；
2. 再看 `decision_mode`；
3. 再结合 `dominant_emotion`、`companion_needs` 和最近趋势；
4. 最后才选择安慰、庆祝、澄清或转移话题。

`clarify` 状态下不应生成“你现在很焦虑”这类强判断。

### 9.3 方言 TTS 模块

可以使用 `valence`、`arousal`、`intensity` 和 `temporal.stability` 调整语速、音高范围、力度和停顿。任何情绪标签到具体声学参数的映射由 TTS 模块负责并在目标方言上听感校准，情感识别模块不直接输出固定音高或语速。

## 10. 质量与验收

当前模块级验收：

1. `npm test` 全部通过；
2. 六类概率非负且和约为 1；
3. 会话轮次自动递增；
4. 空文本、超长文本、非法会话和非法轮次被拒绝；
5. 模型不可用时仍可由规则返回；
6. 方言请求返回明确 fallback；
7. 风险信号独立于普通情绪；
8. 文档中的端点、字段与测试保持一致。

研究结果不等同于产品精度。当前外部评测没有说话人字段，不能称为说话人隔离评测；风险规则也没有正式标注集，只能用于原型提示。

## 11. 版本记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-11-09 | 按实际代码冻结当前 HTTP 端点、字段、错误和跨模块协作规则 |
