export const EMOTION_LABELS = [
  "joy",
  "calm",
  "sadness",
  "anxiety",
  "anger_irritation",
  "neutral",
];

const EMOTION_ANCHORS = {
  joy: { valence: 0.82, arousal: 0.68 },
  calm: { valence: 0.3, arousal: 0.2 },
  sadness: { valence: -0.72, arousal: 0.3 },
  anxiety: { valence: -0.58, arousal: 0.76 },
  anger_irritation: { valence: -0.72, arousal: 0.84 },
  neutral: { valence: 0, arousal: 0.34 },
};

// This is an intentionally transparent baseline. It validates the product flow
// before a trained text model and the speech branch are connected.
const CUES = [
  { emotion: "joy", phrase: "特别开心", weight: 3.6 },
  { emotion: "joy", phrase: "太开心", weight: 3.4 },
  { emotion: "joy", phrase: "好开心", weight: 3.3 },
  { emotion: "joy", phrase: "很高兴", weight: 3.0 },
  { emotion: "joy", phrase: "开心", weight: 2.6 },
  { emotion: "joy", phrase: "高兴", weight: 2.5 },
  { emotion: "joy", phrase: "快乐", weight: 2.4 },
  { emotion: "joy", phrase: "幸福", weight: 2.7 },
  { emotion: "joy", phrase: "喜欢", weight: 1.8 },
  { emotion: "joy", phrase: "太好了", weight: 3.0 },
  { emotion: "joy", phrase: "好多了", weight: 2.5 },
  { emotion: "joy", phrase: "心里亮堂", weight: 2.6 },
  { emotion: "joy", phrase: "有希望", weight: 2.1 },
  { emotion: "joy", phrase: "期待", weight: 1.8 },
  { emotion: "joy", phrase: "哈哈", weight: 2.1 },
  { emotion: "joy", phrase: "欣慰", weight: 2.2 },
  { emotion: "joy", phrase: "满足", weight: 2.0 },
  { emotion: "joy", phrase: "巴适", weight: 2.5 },
  { emotion: "joy", phrase: "安逸", weight: 1.8 },
  { emotion: "joy", phrase: "得劲", weight: 2.1 },
  { emotion: "joy", phrase: "😊", weight: 2.1 },
  { emotion: "joy", phrase: "😄", weight: 2.4 },
  { emotion: "joy", phrase: "😁", weight: 2.4 },

  { emotion: "calm", phrase: "很平静", weight: 3.0 },
  { emotion: "calm", phrase: "平静", weight: 2.4 },
  { emotion: "calm", phrase: "放松", weight: 2.4 },
  { emotion: "calm", phrase: "踏实", weight: 2.2 },
  { emotion: "calm", phrase: "安心", weight: 2.2 },
  { emotion: "calm", phrase: "舒服", weight: 2.0 },
  { emotion: "calm", phrase: "安稳", weight: 2.0 },
  { emotion: "calm", phrase: "慢慢来", weight: 1.8 },
  { emotion: "calm", phrase: "没事", weight: 1.4 },
  { emotion: "calm", phrase: "还行", weight: 1.3 },
  { emotion: "calm", phrase: "还好", weight: 1.4 },

  { emotion: "sadness", phrase: "不开心", weight: 3.2 },
  { emotion: "sadness", phrase: "很难过", weight: 3.4 },
  { emotion: "sadness", phrase: "难受", weight: 2.8 },
  { emotion: "sadness", phrase: "难过", weight: 2.8 },
  { emotion: "sadness", phrase: "伤心", weight: 2.8 },
  { emotion: "sadness", phrase: "失落", weight: 2.6 },
  { emotion: "sadness", phrase: "委屈", weight: 2.5 },
  { emotion: "sadness", phrase: "孤独", weight: 2.6 },
  { emotion: "sadness", phrase: "想哭", weight: 2.9 },
  { emotion: "sadness", phrase: "没意思", weight: 2.6 },
  { emotion: "sadness", phrase: "莫得意思", weight: 2.8 },
  { emotion: "sadness", phrase: "提不起劲", weight: 2.9 },
  { emotion: "sadness", phrase: "心累", weight: 2.5 },
  { emotion: "sadness", phrase: "疲惫", weight: 2.1 },
  { emotion: "sadness", phrase: "有点累", weight: 2.0 },
  { emotion: "sadness", phrase: "低落", weight: 2.5 },
  { emotion: "sadness", phrase: "不想活", weight: 3.4 },
  { emotion: "sadness", phrase: "不想说", weight: 2.1 },
  { emotion: "sadness", phrase: "不想跟任何人说话", weight: 2.8 },
  { emotion: "sadness", phrase: "算了", weight: 1.4 },
  { emotion: "sadness", phrase: "好攰", weight: 2.6 },
  { emotion: "sadness", phrase: "心淡", weight: 2.4 },
  { emotion: "sadness", phrase: "😢", weight: 2.4 },
  { emotion: "sadness", phrase: "😭", weight: 2.8 },

  { emotion: "anxiety", phrase: "很焦虑", weight: 3.4 },
  { emotion: "anxiety", phrase: "焦虑", weight: 2.9 },
  { emotion: "anxiety", phrase: "担心", weight: 2.5 },
  { emotion: "anxiety", phrase: "紧张", weight: 2.4 },
  { emotion: "anxiety", phrase: "害怕", weight: 2.6 },
  { emotion: "anxiety", phrase: "不安", weight: 2.4 },
  { emotion: "anxiety", phrase: "心慌", weight: 2.8 },
  { emotion: "anxiety", phrase: "慌得很", weight: 3.0 },
  { emotion: "anxiety", phrase: "睡不着", weight: 2.4 },
  { emotion: "anxiety", phrase: "怎么办", weight: 1.8 },
  { emotion: "anxiety", phrase: "压力好大", weight: 2.8 },
  { emotion: "anxiety", phrase: "不踏实", weight: 2.2 },
  { emotion: "anxiety", phrase: "心头紧", weight: 2.8 },
  { emotion: "anxiety", phrase: "好惊", weight: 2.3 },
  { emotion: "anxiety", phrase: "一直想", weight: 1.8 },
  { emotion: "anxiety", phrase: "脑子里全是", weight: 1.9 },

  { emotion: "anger_irritation", phrase: "气死我了", weight: 3.8 },
  { emotion: "anger_irritation", phrase: "气死", weight: 3.4 },
  { emotion: "anger_irritation", phrase: "特别生气", weight: 3.5 },
  { emotion: "anger_irritation", phrase: "很生气", weight: 3.0 },
  { emotion: "anger_irritation", phrase: "生气", weight: 2.8 },
  { emotion: "anger_irritation", phrase: "愤怒", weight: 3.0 },
  { emotion: "anger_irritation", phrase: "烦死了", weight: 3.3 },
  { emotion: "anger_irritation", phrase: "很烦", weight: 2.8 },
  { emotion: "anger_irritation", phrase: "烦得很", weight: 3.0 },
  { emotion: "anger_irritation", phrase: "烦躁", weight: 2.9 },
  { emotion: "anger_irritation", phrase: "讨厌", weight: 2.2 },
  { emotion: "anger_irritation", phrase: "吵架", weight: 2.1 },
  { emotion: "anger_irritation", phrase: "恼火", weight: 2.7 },
  { emotion: "anger_irritation", phrase: "毛焦火辣", weight: 3.0 },
  { emotion: "anger_irritation", phrase: "闹心", weight: 2.4 },
  { emotion: "anger_irritation", phrase: "火大", weight: 2.8 },
  { emotion: "anger_irritation", phrase: "无语", weight: 1.6 },
  { emotion: "anger_irritation", phrase: "过分", weight: 1.7 },
  { emotion: "anger_irritation", phrase: "受不了", weight: 2.4 },
  { emotion: "anger_irritation", phrase: "有什么好高兴的", weight: 2.8 },
];

const INTENSIFIERS = [
  "非常",
  "特别",
  "真的",
  "太",
  "超级",
  "越来越",
  "一直",
  "实在",
  "简直",
];

const NEED_CUES = [
  { need: "listen", phrases: ["听我说", "我想说", "陪我聊", "想聊聊"], confidence: 0.76 },
  { need: "company", phrases: ["陪我", "别走", "一个人", "没人陪"], confidence: 0.73 },
  { need: "practical_help", phrases: ["帮我", "怎么办", "不知道怎么", "给我建议"], confidence: 0.68 },
  { need: "clarify", phrases: ["不知道怎么说", "说不清楚"], confidence: 0.6 },
];

const URGENT_RISK_PHRASES = [
  "不想活了",
  "好想死",
  "想去死",
  "我要去死",
  "想自杀",
  "准备自杀",
  "结束生命",
  "伤害自己",
  "割腕",
  "跳楼",
  "吞药",
  "活不下去了",
];

const WATCH_RISK_PHRASES = [
  "活着没意思",
  "撑不下去",
  "熬不下去",
  "没有希望",
  "看不到希望",
  "没人需要我",
  "不如消失",
  "消失算了",
  "特别没用",
  "觉得自己没用",
  "一切都是我的错",
];

function clamp(value, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value));
}

function round(value, digits = 3) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function countOccurrences(text, phrase) {
  let count = 0;
  let from = 0;
  while (from < text.length) {
    const index = text.indexOf(phrase, from);
    if (index === -1) break;
    count += 1;
    from = index + phrase.length;
  }
  return count;
}

function isNegated(text, index) {
  const prefix = text.slice(Math.max(0, index - 8), index);
  if (
    /(?:不怎么|不太|并不|没有(?:那么|这么|特别)?|没(?:那么|这么|特别)?|不(?:那么|这么|特别)?|不是)$/.test(
      prefix,
    )
  ) {
    return true;
  }
  if (/(?:特别|分别|区别|告别|性别|级别)$/.test(prefix)) return false;
  return /(?:不|没|别)$/.test(prefix);
}

function collectCueMatches(text) {
  const matches = [];

  for (const cue of CUES) {
    let from = 0;
    while (from < text.length) {
      const index = text.indexOf(cue.phrase, from);
      if (index === -1) break;

      if (!isNegated(text, index)) {
        matches.push({ ...cue, index });
      }
      from = index + Math.max(1, cue.phrase.length);
    }
  }

  return matches.sort((a, b) => a.index - b.index);
}

function softmax(logits) {
  const max = Math.max(...Object.values(logits));
  const exponentials = Object.fromEntries(
    Object.entries(logits).map(([label, value]) => [label, Math.exp(value - max)]),
  );
  const total = Object.values(exponentials).reduce((sum, value) => sum + value, 0);

  return Object.fromEntries(
    Object.entries(exponentials).map(([label, value]) => [label, value / total]),
  );
}

function detectRisk(text) {
  for (const phrase of URGENT_RISK_PHRASES) {
    if (text.includes(phrase)) {
      return {
        level: "urgent",
        reasons: ["self_harm_or_immediate_danger"],
        confidence: 0.96,
        matched_phrase: phrase,
      };
    }
  }

  for (const phrase of WATCH_RISK_PHRASES) {
    if (text.includes(phrase)) {
      return {
        level: "watch",
        reasons: ["hopelessness_or_self_devaluation"],
        confidence: 0.72,
        matched_phrase: phrase,
      };
    }
  }

  return {
    level: "none",
    reasons: [],
    confidence: 0.9,
    matched_phrase: null,
  };
}

function detectCompanionNeeds(text, distribution) {
  const needs = [];

  for (const cue of NEED_CUES) {
    const matched = cue.phrases.find((phrase) => text.includes(phrase));
    if (matched) {
      needs.push({ label: cue.need, confidence: cue.confidence });
    }
  }

  const negativeMass =
    distribution.sadness + distribution.anxiety + distribution.anger_irritation;

  if (negativeMass > 0.55) {
    needs.push({
      label: "comfort",
      confidence: round(Math.min(0.86, 0.48 + negativeMass * 0.3)),
    });
  }

  if (distribution.joy > 0.55) {
    needs.push({ label: "celebrate", confidence: round(distribution.joy) });
  }

  const unique = new Map();
  for (const need of needs) {
    const previous = unique.get(need.label);
    if (!previous || previous.confidence < need.confidence) {
      unique.set(need.label, need);
    }
  }

  return [...unique.values()]
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 2);
}

export function analyzeText({
  text,
  asrConfidence = 0.95,
  dialect = "mandarin",
}) {
  const normalized = String(text ?? "").trim();
  const safeAsrConfidence = clamp(Number(asrConfidence) || 0.95, 0.05, 1);
  const dialectCode =
    dialect === "zh-CN" ? "mandarin" : String(dialect || "mandarin");

  if (!normalized) {
    return {
      status: "insufficient_data",
      dominant_emotion: { label: "neutral", confidence: 0.1 },
      emotion_distribution: Object.fromEntries(
        EMOTION_LABELS.map((label) => [label, label === "neutral" ? 1 : 0]),
      ),
      dimensions: { valence: 0, arousal: 0.2, intensity: 0.1 },
      companion_needs: [],
      risk: {
        level: "none",
        reasons: [],
        confidence: 0.2,
      },
      quality: {
        overall: safeAsrConfidence,
        text: safeAsrConfidence,
        speech: null,
        vision: null,
      },
      evidence: { text: [], speech: [], vision: [] },
      dialect: { code: dialectCode, calibrated: false },
    };
  }

  const cues = collectCueMatches(normalized);
  const intensifierCount = INTENSIFIERS.reduce(
    (sum, word) => sum + countOccurrences(normalized, word),
    0,
  );
  const exclamationCount = (normalized.match(/[!！]/g) ?? []).length;
  const intensityMultiplier = 1 + Math.min(0.6, intensifierCount * 0.16);

  const scores = {
    joy: 0.02,
    calm: 0.04,
    sadness: 0.04,
    anxiety: 0.04,
    anger_irritation: 0.04,
    neutral: 0.78,
  };

  for (const cue of cues) {
    scores[cue.emotion] += cue.weight * intensityMultiplier;
  }

  if (cues.some((cue) => cue.emotion !== "neutral")) {
    scores.neutral *= 0.68;
  }

  const distributionRaw = softmax(
    Object.fromEntries(
      Object.entries(scores).map(([label, score]) => [label, score * 1.32]),
    ),
  );
  const smoothedDistribution = Object.fromEntries(
    Object.entries(distributionRaw).map(([label, probability]) => [
      label,
      probability * 0.86 + 0.14 / EMOTION_LABELS.length,
    ]),
  );
  const distribution = Object.fromEntries(
    Object.entries(smoothedDistribution).map(([label, value]) => [
      label,
      round(value),
    ]),
  );

  const dominant = EMOTION_LABELS.reduce((best, label) =>
    distribution[label] > distribution[best] ? label : best,
  );

  const dominantConfidence =
    cues.length === 0
      ? Math.min(0.34, 0.18 + safeAsrConfidence * 0.1)
      : distribution[dominant] *
        (0.84 + 0.16 * Math.min(1, cues.length / 3)) *
        safeAsrConfidence;

  let valence = EMOTION_LABELS.reduce(
    (sum, label) => sum + distribution[label] * EMOTION_ANCHORS[label].valence,
    0,
  );
  let arousal = EMOTION_LABELS.reduce(
    (sum, label) => sum + distribution[label] * EMOTION_ANCHORS[label].arousal,
    0,
  );

  arousal += Math.min(0.18, exclamationCount * 0.06);
  if (/(.)\1{2,}/u.test(normalized)) {
    arousal += 0.04;
    valence = valence > 0 ? valence + 0.02 : valence - 0.02;
  }

  const intensity =
    cues.length === 0
      ? Math.min(0.28, 0.12 + safeAsrConfidence * 0.1)
      : clamp(
          0.05 +
            distribution[dominant] * 0.38 +
            clamp(dominantConfidence) * 0.2 +
            Math.min(0.14, cues.length * 0.035) +
            Math.min(0.12, intensifierCount * 0.06) +
            Math.min(0.1, exclamationCount * 0.04),
        );

  const risk = detectRisk(normalized);
  const companionNeeds = detectCompanionNeeds(normalized, distribution);

  const evidence = {
    text: [
      ...new Set(cues.slice(0, 4).map((cue) => `文本线索：${cue.phrase}`)),
      ...(intensifierCount > 0
        ? [`表达强度：${INTENSIFIERS.filter((word) => normalized.includes(word)).join("、")}`]
        : []),
      ...(risk.matched_phrase ? [`风险线索：${risk.matched_phrase}`] : []),
    ],
    speech: [],
    vision: [],
  };

  return {
    status: "ok",
    dominant_emotion: {
      label: dominant,
      confidence: round(clamp(dominantConfidence, 0.05, 0.97)),
    },
    emotion_distribution: distribution,
    dimensions: {
      valence: round(clamp(valence, -1, 1)),
      arousal: round(clamp(arousal)),
      intensity: round(intensity),
    },
    companion_needs: companionNeeds,
    risk: {
      level: risk.level,
      reasons: risk.reasons,
      confidence: risk.confidence,
    },
    quality: {
      overall: round(safeAsrConfidence),
      text: round(safeAsrConfidence),
      speech: null,
      vision: null,
    },
    evidence,
    dialect: {
      code: dialectCode,
      calibrated: false,
    },
  };
}

function normalizeDistribution(distribution) {
  const total = Object.values(distribution).reduce((sum, value) => sum + value, 0);
  if (total <= 0) {
    return Object.fromEntries(
      EMOTION_LABELS.map((label) => [label, label === "neutral" ? 1 : 0]),
    );
  }

  return Object.fromEntries(
    EMOTION_LABELS.map((label) => [label, distribution[label] / total]),
  );
}

function normalizeRange(value, minimum, maximum) {
  if (!Number.isFinite(value)) return 0;
  return clamp((value - minimum) / (maximum - minimum));
}

export function analyzeSpeech(features) {
  if (!features || typeof features !== "object") return null;

  const durationMs = clamp(Number(features.duration_ms) || 0, 0, 120_000);
  if (durationMs < 200) {
    return {
      available: false,
      reason: "speech_too_short",
      quality: 0,
      evidence: [],
    };
  }

  const speechRatio = clamp(Number(features.speech_ratio) || 0);
  const meanDb = clamp(Number(features.mean_db) || -60, -90, 0);
  const variationDb = clamp(Number(features.variation_db) || 0, 0, 60);
  const meanPitchHz = clamp(Number(features.mean_pitch_hz) || 0, 0, 600);
  const pitchVariationHz = clamp(
    Number(features.pitch_variation_hz) || 0,
    0,
    300,
  );
  const pauseCount = clamp(Number(features.pause_count) || 0, 0, 100);
  const clippingRatio = clamp(Number(features.clipping_ratio) || 0, 0, 1);

  const durationScore = normalizeRange(durationMs, 250, 1_600);
  const speechRatioScore =
    speechRatio >= 0.12 && speechRatio <= 0.92
      ? 1
      : clamp(speechRatio / 0.12);
  const clippingScore = 1 - clamp(clippingRatio * 8);
  const quality = round(
    clamp(
      durationScore * 0.32 +
        speechRatioScore * 0.42 +
        clippingScore * 0.2 +
        normalizeRange(meanDb, -58, -24) * 0.06,
    ),
  );

  const energyScore = normalizeRange(meanDb, -52, -18);
  const variationScore = normalizeRange(variationDb, 1, 18);
  const pitchVariationScore = normalizeRange(pitchVariationHz, 5, 90);
  const pauseRate = pauseCount / Math.max(1, durationMs / 1_000);
  const continuityScore = 1 - clamp(pauseRate / 2.5);

  const activation = round(
    clamp(
      energyScore * 0.38 +
        variationScore * 0.26 +
        pitchVariationScore * 0.26 +
        continuityScore * 0.1,
    ),
  );

  let acousticHint = "moderate_activation";
  if (quality >= 0.32 && activation >= 0.66) {
    acousticHint = "high_activation";
  } else if (quality >= 0.32 && activation <= 0.34) {
    acousticHint = "low_activation";
  }

  const evidence = [
    `语音有效占比：${Math.round(speechRatio * 100)}%`,
    `平均音量：${Math.round(meanDb)} dB`,
  ];
  if (meanPitchHz > 0) {
    evidence.push(
      `平均音高：${Math.round(meanPitchHz)} Hz，波动 ${Math.round(pitchVariationHz)} Hz`,
    );
  }
  if (pauseCount > 0) {
    evidence.push(`检测到约 ${Math.round(pauseCount)} 次明显停顿`);
  }

  return {
    available: quality >= 0.2,
    reason: quality >= 0.2 ? null : "low_audio_quality",
    quality,
    activation,
    acoustic_hint: acousticHint,
    features: {
      duration_ms: Math.round(durationMs),
      speech_ratio: round(speechRatio),
      mean_db: round(meanDb, 1),
      variation_db: round(variationDb, 1),
      mean_pitch_hz: round(meanPitchHz, 1),
      pitch_variation_hz: round(pitchVariationHz, 1),
      pause_count: Math.round(pauseCount),
      clipping_ratio: round(clippingRatio),
    },
    evidence,
  };
}

function buildAcousticDistribution(textAnalysis, speechAnalysis) {
  const hint = speechAnalysis.acoustic_hint;
  const valence = textAnalysis.dimensions.valence;
  const distribution = {
    joy: 0.06,
    calm: 0.08,
    sadness: 0.08,
    anxiety: 0.06,
    anger_irritation: 0.06,
    neutral: 0.66,
  };

  if (hint === "high_activation") {
    distribution.neutral = 0.24;
    if (valence < -0.12) {
      if (
        textAnalysis.emotion_distribution.anger_irritation >
        textAnalysis.emotion_distribution.anxiety
      ) {
        distribution.anger_irritation = 0.38;
        distribution.anxiety = 0.2;
      } else {
        distribution.anxiety = 0.38;
        distribution.anger_irritation = 0.2;
      }
      distribution.sadness = 0.08;
    } else if (valence > 0.12) {
      distribution.joy = 0.42;
      distribution.calm = 0.1;
    } else {
      distribution.anxiety = 0.24;
      distribution.anger_irritation = 0.18;
      distribution.joy = 0.14;
    }
  } else if (hint === "low_activation") {
    distribution.neutral = 0.34;
    if (valence < -0.12) {
      distribution.sadness = 0.42;
      distribution.calm = 0.09;
    } else if (valence > 0.12) {
      distribution.calm = 0.38;
      distribution.joy = 0.14;
    } else {
      distribution.calm = 0.28;
      distribution.sadness = 0.2;
    }
  }

  return normalizeDistribution(distribution);
}

export function fuseModalities(textAnalysis, speechAnalysis) {
  if (!speechAnalysis || !speechAnalysis.available) {
    return {
      ...textAnalysis,
      speech_analysis: speechAnalysis ?? null,
    };
  }

  const speechWeight = clamp(0.08 + speechAnalysis.quality * 0.22, 0, 0.3);
  const acousticDistribution = buildAcousticDistribution(
    textAnalysis,
    speechAnalysis,
  );
  const textHasConclusion = textAnalysis.status === "ok";
  const blendedRaw = Object.fromEntries(
    EMOTION_LABELS.map((label) => [
      label,
      textHasConclusion
        ? textAnalysis.emotion_distribution[label] * (1 - speechWeight) +
          acousticDistribution[label] * speechWeight
        : label === "neutral"
          ? 0.58
          : 0.084,
    ]),
  );
  const distribution = Object.fromEntries(
    Object.entries(normalizeDistribution(blendedRaw)).map(([label, value]) => [
      label,
      round(value),
    ]),
  );
  const dominant = EMOTION_LABELS.reduce((best, label) =>
    distribution[label] > distribution[best] ? label : best,
  );

  const acousticTarget = EMOTION_LABELS.reduce((best, label) =>
    acousticDistribution[label] > acousticDistribution[best] ? label : best,
  );
  const textDominant = textAnalysis.dominant_emotion.label;
  const conflict =
    textHasConclusion &&
    acousticTarget !== textDominant &&
    speechAnalysis.quality >= 0.45;

  const confidence = textHasConclusion
    ? clamp(
        textAnalysis.dominant_emotion.confidence * 0.94 +
          speechAnalysis.quality * 0.025 -
          (conflict ? 0.045 : 0),
        0.05,
        0.95,
      )
    : clamp(speechAnalysis.quality * 0.34, 0.05, 0.34);

  const arousal =
    textAnalysis.dimensions.arousal * (1 - speechWeight * 0.7) +
    speechAnalysis.activation * speechWeight * 0.7;
  const intensity = clamp(
    textAnalysis.dimensions.intensity * 0.9 +
      speechAnalysis.activation * speechAnalysis.quality * 0.16,
  );
  const overallQuality = clamp(
    textAnalysis.quality.text * 0.62 + speechAnalysis.quality * 0.38,
  );

  return {
    ...textAnalysis,
    status: textHasConclusion ? "ok" : "partial",
    dominant_emotion: {
      label: textHasConclusion ? dominant : "neutral",
      confidence: round(confidence),
    },
    emotion_distribution: distribution,
    dimensions: {
      ...textAnalysis.dimensions,
      arousal: round(arousal),
      intensity: round(intensity),
    },
    quality: {
      ...textAnalysis.quality,
      overall: round(overallQuality),
      speech: speechAnalysis.quality,
    },
    evidence: {
      ...textAnalysis.evidence,
      speech: speechAnalysis.evidence,
    },
    speech_analysis: speechAnalysis,
  };
}

const MODEL_LABELS_CN = {
  joy: "高兴",
  calm: "平静",
  sadness: "悲伤",
  anxiety: "焦虑",
  anger_irritation: "烦躁",
  neutral: "中性",
};

function normalizeEmotionDistribution(values) {
  const safeValues = Object.fromEntries(
    EMOTION_LABELS.map((label) => [
      label,
      clamp(Number(values?.[label]) || 0),
    ]),
  );
  return normalizeDistribution(safeValues);
}

function dimensionsFromDistribution(distribution, intensity) {
  return {
    valence: round(
      clamp(
        EMOTION_LABELS.reduce(
          (sum, label) =>
            sum + distribution[label] * EMOTION_ANCHORS[label].valence,
          0,
        ),
        -1,
        1,
      ),
    ),
    arousal: round(
      EMOTION_LABELS.reduce(
        (sum, label) =>
          sum + distribution[label] * EMOTION_ANCHORS[label].arousal,
        0,
      ),
    ),
    intensity: round(intensity),
  };
}

export function fuseSemanticModel(analysis, semanticModel) {
  if (!semanticModel?.available || !semanticModel.mapped_distribution) {
    return {
      ...analysis,
      semantic_model: semanticModel ?? null,
    };
  }

  const modelDistribution = normalizeEmotionDistribution(
    semanticModel.mapped_distribution,
  );
  const modelConfidence = Math.max(...Object.values(modelDistribution));
  const ruleConfidence =
    analysis.status === "ok" ? analysis.dominant_emotion.confidence : 0;
  const ruleHasExplicitCue = analysis.evidence.text.some((item) =>
    item.startsWith("文本线索："),
  );

  let modelWeight;
  if (ruleHasExplicitCue) modelWeight = 0.08;
  else if (analysis.status !== "ok") modelWeight = 0.6;
  else if (ruleConfidence >= 0.55) modelWeight = 0.22;
  else if (ruleConfidence >= 0.38) modelWeight = 0.35;
  else modelWeight = 0.55;

  const blended = Object.fromEntries(
    EMOTION_LABELS.map((label) => [
      label,
      analysis.emotion_distribution[label] * (1 - modelWeight) +
        modelDistribution[label] * modelWeight,
    ]),
  );
  const distribution = Object.fromEntries(
    Object.entries(normalizeDistribution(blended)).map(([label, value]) => [
      label,
      round(value),
    ]),
  );
  const dominant = EMOTION_LABELS.reduce((best, label) =>
    distribution[label] > distribution[best] ? label : best,
  );
  const agrees = dominant === analysis.dominant_emotion.label;
  const confidence = agrees
    ? clamp(
        analysis.dominant_emotion.confidence * 0.78 +
          modelConfidence * 0.18 +
          0.02,
        0.05,
        0.9,
      )
    : ruleConfidence < 0.38
      ? clamp(modelConfidence * 0.68, 0.05, 0.72)
      : clamp(ruleConfidence * 0.8, 0.05, 0.82);

  return {
    ...analysis,
    dominant_emotion: {
      label: dominant,
      confidence: round(confidence),
    },
    emotion_distribution: distribution,
    dimensions: dimensionsFromDistribution(
      distribution,
      (analysis.dimensions.intensity + modelConfidence) / 2,
    ),
    evidence: {
      ...analysis.evidence,
      text: [
        ...analysis.evidence.text,
        `模型判断：${MODEL_LABELS_CN[semanticModel.predicted_mapped] ?? semanticModel.predicted_mapped}`,
      ],
    },
    semantic_model: {
      available: true,
      model_id: semanticModel.model_id,
      device: semanticModel.device,
      predicted_raw: semanticModel.predicted_raw,
      predicted_mapped: semanticModel.predicted_mapped,
      confidence: round(modelConfidence),
      raw_scores: semanticModel.raw_scores,
      mapped_distribution: Object.fromEntries(
        Object.entries(modelDistribution).map(([label, value]) => [
          label,
          round(value),
        ]),
      ),
      latency_ms: semanticModel.latency_ms,
    },
  };
}

export function applyFinetunedSemanticModel(analysis, semanticModel) {
  if (!semanticModel?.available || !semanticModel.mapped_distribution) {
    return fuseSemanticModel(analysis, semanticModel);
  }

  const modelDistribution = normalizeEmotionDistribution(
    semanticModel.mapped_distribution,
  );
  const modelConfidence = Math.max(...Object.values(modelDistribution));
  const explicitCalm =
    analysis.dominant_emotion.label === "calm" &&
    analysis.dominant_emotion.confidence >= 0.35 &&
    analysis.evidence.text.some((item) => item.startsWith("文本线索："));
  const protectExplicitEmotion =
    analysis.dominant_emotion.label !== "neutral" &&
    analysis.dominant_emotion.confidence >= 0.5 &&
    semanticModel.predicted_mapped === "neutral" &&
    analysis.evidence.text.some((item) => item.startsWith("文本线索："));

  if (explicitCalm || protectExplicitEmotion) {
    return {
      ...analysis,
      semantic_model: {
        ...semanticModel,
        available: true,
        confidence: round(modelConfidence),
        mapped_distribution: Object.fromEntries(
          Object.entries(modelDistribution).map(([label, value]) => [
            label,
            round(value),
          ]),
        ),
      },
    };
  }

  const dominant = EMOTION_LABELS.reduce((best, label) =>
    modelDistribution[label] > modelDistribution[best] ? label : best,
  );
  return {
    ...analysis,
    dominant_emotion: {
      label: dominant,
      confidence: round(clamp(modelConfidence, 0.05, 0.95)),
    },
    emotion_distribution: Object.fromEntries(
      Object.entries(modelDistribution).map(([label, value]) => [
        label,
        round(value),
      ]),
    ),
    dimensions: dimensionsFromDistribution(
      modelDistribution,
      (analysis.dimensions.intensity + modelConfidence) / 2,
    ),
    evidence: {
      ...analysis.evidence,
      text: [
        ...analysis.evidence.text,
        `微调模型判断：${MODEL_LABELS_CN[semanticModel.predicted_mapped] ?? semanticModel.predicted_mapped}`,
      ],
    },
    semantic_model: {
      ...semanticModel,
      available: true,
      confidence: round(modelConfidence),
      mapped_distribution: Object.fromEntries(
        Object.entries(modelDistribution).map(([label, value]) => [
          label,
          round(value),
        ]),
      ),
    },
  };
}

const SPEECH_MODEL_DISTRIBUTIONS = {
  happy: { joy: 0.72, calm: 0.08, sadness: 0.02, anxiety: 0.02, anger_irritation: 0.01, neutral: 0.15 },
  sad: { joy: 0.01, calm: 0.03, sadness: 0.72, anxiety: 0.1, anger_irritation: 0.02, neutral: 0.12 },
  angry: { joy: 0.01, calm: 0.02, sadness: 0.03, anxiety: 0.08, anger_irritation: 0.74, neutral: 0.12 },
  fearful: { joy: 0.02, calm: 0.02, sadness: 0.08, anxiety: 0.72, anger_irritation: 0.04, neutral: 0.12 },
  disgusted: { joy: 0, calm: 0.02, sadness: 0.04, anxiety: 0.06, anger_irritation: 0.72, neutral: 0.16 },
  surprised: { joy: 0.3, calm: 0.04, sadness: 0.02, anxiety: 0.2, anger_irritation: 0.04, neutral: 0.4 },
  neutral: { joy: 0.02, calm: 0.22, sadness: 0.03, anxiety: 0.03, anger_irritation: 0.02, neutral: 0.68 },
};

function distributionFromEmotion2vec(scores) {
  if (!scores || typeof scores !== "object") return null;
  const mapped = {
    joy: Number(scores.happy) || 0,
    calm: (Number(scores.neutral) || 0) * 0.28,
    sadness: Number(scores.sad) || 0,
    anxiety:
      (Number(scores.fearful) || 0) +
      (Number(scores.surprised) || 0) * 0.1,
    anger_irritation:
      (Number(scores.angry) || 0) +
      (Number(scores.disgusted) || 0) * 0.75,
    neutral:
      (Number(scores.neutral) || 0) * 0.52 +
      (Number(scores.other) || 0) * 0.3 +
      (Number(scores.unknown) || 0) * 0.2,
  };
  const total = Object.values(mapped).reduce((sum, value) => sum + value, 0);
  if (total <= 0) return null;
  return normalizeDistribution(mapped);
}

export function fuseSpeechModel(analysis, speechModel) {
  if (!speechModel?.available) {
    return {
      ...analysis,
      speech_model: speechModel ?? null,
    };
  }

  const tag = String(speechModel.emotion_tag ?? "unknown").toLowerCase();
  const emotion2vecDistribution = distributionFromEmotion2vec(
    speechModel.emotion2vec?.scores,
  );
  const tagDistribution =
    emotion2vecDistribution ?? SPEECH_MODEL_DISTRIBUTIONS[tag];
  const speechEvidence = [
    ...(speechModel.text ? [`SenseVoice 转写：${speechModel.text}`] : []),
    `SenseVoice 情绪标签：${tag}`,
  ];
  if (speechModel.emotion2vec?.top_label) {
    speechEvidence.push(
      `emotion2vec：${speechModel.emotion2vec.top_label} · ${Math.round(
        speechModel.emotion2vec.top_score * 100,
      )}%`,
    );
  }

  if (!tagDistribution) {
    return {
      ...analysis,
      quality: {
        ...analysis.quality,
        speech: Math.max(analysis.quality.speech ?? 0, 0.45),
      },
      evidence: {
        ...analysis.evidence,
        speech: [...analysis.evidence.speech, ...speechEvidence],
      },
      speech_model: {
        ...speechModel,
        mapped_emotion: null,
      },
    };
  }

  const speechWeight = emotion2vecDistribution
    ? analysis.dominant_emotion.confidence < 0.38
      ? 0.34
      : 0.16
    : analysis.dominant_emotion.confidence < 0.38
      ? 0.24
      : 0.12;
  const blended = Object.fromEntries(
    EMOTION_LABELS.map((label) => [
      label,
      analysis.emotion_distribution[label] * (1 - speechWeight) +
        tagDistribution[label] * speechWeight,
    ]),
  );
  const distribution = Object.fromEntries(
    Object.entries(normalizeDistribution(blended)).map(([label, value]) => [
      label,
      round(value),
    ]),
  );
  const dominant = EMOTION_LABELS.reduce((best, label) =>
    distribution[label] > distribution[best] ? label : best,
  );

  return {
    ...analysis,
    dominant_emotion: {
      label: dominant,
      confidence: round(
        clamp(
          analysis.dominant_emotion.confidence * 0.94 +
            distribution[dominant] * 0.04,
          0.05,
          0.9,
        ),
      ),
    },
    emotion_distribution: distribution,
    dimensions: dimensionsFromDistribution(
      distribution,
      analysis.dimensions.intensity,
    ),
    quality: {
      ...analysis.quality,
      speech: Math.max(analysis.quality.speech ?? 0, 0.55),
    },
    evidence: {
      ...analysis.evidence,
      speech: [...analysis.evidence.speech, ...speechEvidence],
    },
    speech_model: {
      ...speechModel,
      mapped_emotion: dominant,
    },
  };
}

export function calculateTemporal(states) {
  if (!Array.isArray(states) || states.length === 0) {
    return {
      window_turns: 0,
      trend: "insufficient_data",
      low_valence_duration_s: 0,
      stability: 0,
    };
  }

  const window = states.slice(-5);
  const current = window.at(-1);
  const previous = window.slice(0, -1);

  let trend = "insufficient_data";
  if (previous.length >= 1) {
    const previousAverage =
      previous.reduce((sum, state) => sum + state.dimensions.valence, 0) /
      previous.length;
    const delta = current.dimensions.valence - previousAverage;
    const changes = window.slice(1).map(
      (state, index) =>
        state.dimensions.valence - window[index].dimensions.valence,
    );
    const valenceRange =
      Math.max(...window.map((state) => state.dimensions.valence)) -
      Math.min(...window.map((state) => state.dimensions.valence));
    const signChanges = changes.slice(1).filter((change, index) => {
      return Math.sign(change) !== Math.sign(changes[index]) && Math.abs(change) > 0.08;
    }).length;

    if (valenceRange >= 0.45 && signChanges >= 1) {
      trend = "fluctuating";
    } else if (delta > 0.08) {
      trend = "improving";
    } else if (delta < -0.08) {
      trend = "worsening";
    } else {
      trend = "stable";
    }
  }

  let lowValenceStart = null;
  for (let index = window.length - 1; index >= 0; index -= 1) {
    if (window[index].dimensions.valence < -0.18) {
      lowValenceStart = index;
    } else {
      break;
    }
  }

  const lowValenceDuration =
    lowValenceStart === null
      ? 0
      : Math.max(
          0,
          (new Date(current.timestamp).getTime() -
            new Date(window[lowValenceStart].timestamp).getTime()) /
            1000,
        );

  const mean =
    window.reduce((sum, state) => sum + state.dimensions.valence, 0) /
    window.length;
  const variance =
    window.reduce(
      (sum, state) => sum + (state.dimensions.valence - mean) ** 2,
      0,
    ) / window.length;
  const stability = round(clamp(1 - Math.sqrt(variance) / 0.7));

  return {
    window_turns: window.length,
    trend,
    low_valence_duration_s: Math.round(lowValenceDuration),
    stability,
  };
}

export function emptyTemporal() {
  return calculateTemporal([]);
}
