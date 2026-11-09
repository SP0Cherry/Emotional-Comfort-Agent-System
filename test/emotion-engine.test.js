import assert from "node:assert/strict";
import test from "node:test";

import {
  EMOTION_LABELS,
  analyzeSpeech,
  analyzeText,
  applyFinetunedSemanticModel,
  calculateTemporal,
  fuseModalities,
  fuseSemanticModel,
  fuseSpeechModel,
} from "../src/emotion-engine.js";

test("recognizes explicit happiness", () => {
  const result = analyzeText({ text: "今天答辩顺利，我特别开心！" });

  assert.equal(result.dominant_emotion.label, "joy");
  assert.ok(result.dimensions.valence > 0.3);
  assert.ok(result.dominant_emotion.confidence > 0.4);
});

test("recognizes sustained low mood language", () => {
  const result = analyzeText({
    text: "最近做什么都提不起劲，心里很难受。",
  });

  assert.equal(result.dominant_emotion.label, "sadness");
  assert.ok(result.dimensions.valence < -0.2);
  assert.ok(result.companion_needs.some((need) => need.label === "comfort"));
});

test("recognizes anxiety from mixed worry cues", () => {
  const result = analyzeText({
    text: "明天要答辩了，我一直睡不着，担心会搞砸。",
  });

  assert.equal(result.dominant_emotion.label, "anxiety");
  assert.ok(result.dimensions.arousal > 0.4);
});

test("recognizes anger and irritation", () => {
  const result = analyzeText({
    text: "他怎么能这样说，气死我了！",
  });

  assert.equal(result.dominant_emotion.label, "anger_irritation");
  assert.ok(result.dimensions.arousal > 0.5);
});

test("recognizes calm language", () => {
  const result = analyzeText({
    text: "我现在很平静，也慢慢放松下来了。",
  });

  assert.equal(result.dominant_emotion.label, "calm");
});

test("keeps ambiguous text low-confidence and neutral", () => {
  const result = analyzeText({ text: "嗯，我知道了。" });

  assert.equal(result.dominant_emotion.label, "neutral");
  assert.ok(result.dominant_emotion.confidence < 0.4);
});

test("handles negated positive language", () => {
  const result = analyzeText({ text: "今天不开心。" });

  assert.equal(result.dominant_emotion.label, "sadness");
});

test("does not treat the 别 in 特别 as negation", () => {
  const result = analyzeText({ text: "一想到结果就特别紧张。" });

  assert.equal(result.dominant_emotion.label, "anxiety");
});

test("recognizes short anger expression at the end of a sentence", () => {
  const result = analyzeText({ text: "我快气死了。" });

  assert.equal(result.dominant_emotion.label, "anger_irritation");
});

test("every distribution contains six normalized probabilities", () => {
  const result = analyzeText({ text: "有一点点累。" });
  const values = Object.values(result.emotion_distribution);

  assert.deepEqual(Object.keys(result.emotion_distribution), EMOTION_LABELS);
  assert.equal(values.length, 6);
  assert.ok(Math.abs(values.reduce((sum, value) => sum + value, 0) - 1) < 0.002);
});

test("returns insufficient data for empty text", () => {
  const result = analyzeText({ text: "   " });

  assert.equal(result.status, "insufficient_data");
  assert.equal(result.dominant_emotion.confidence, 0.1);
});

test("marks explicit immediate self-harm language as urgent", () => {
  const result = analyzeText({ text: "我真的不想活了。" });

  assert.equal(result.risk.level, "urgent");
  assert.deepEqual(result.risk.reasons, ["self_harm_or_immediate_danger"]);
});

test("marks indirect hopelessness as watch", () => {
  const result = analyzeText({ text: "我觉得自己特别没用，活着没意思。" });

  assert.equal(result.risk.level, "watch");
  assert.equal(result.risk.reasons[0], "hopelessness_or_self_devaluation");
});

test("calculates a worsening trend over successive turns", () => {
  const states = [
    {
      timestamp: "2026-11-01T10:00:00.000Z",
      dimensions: { valence: -0.1, arousal: 0.3, intensity: 0.2 },
    },
    {
      timestamp: "2026-11-01T10:00:20.000Z",
      dimensions: { valence: -0.4, arousal: 0.4, intensity: 0.5 },
    },
    {
      timestamp: "2026-11-01T10:00:50.000Z",
      dimensions: { valence: -0.7, arousal: 0.5, intensity: 0.7 },
    },
  ];
  const temporal = calculateTemporal(states);

  assert.equal(temporal.trend, "worsening");
  assert.equal(temporal.window_turns, 3);
  assert.equal(temporal.low_valence_duration_s, 30);
});

test("returns insufficient trend data for the first turn", () => {
  const temporal = calculateTemporal([
    {
      timestamp: "2026-11-01T10:00:00.000Z",
      dimensions: { valence: -0.3, arousal: 0.4, intensity: 0.4 },
    },
  ]);

  assert.equal(temporal.trend, "insufficient_data");
  assert.equal(temporal.window_turns, 1);
});

test("derives high activation and quality from energetic speech features", () => {
  const speech = analyzeSpeech({
    duration_ms: 2800,
    speech_ratio: 0.76,
    mean_db: -21,
    variation_db: 12,
    mean_pitch_hz: 205,
    pitch_variation_hz: 58,
    pause_count: 1,
    clipping_ratio: 0,
  });

  assert.equal(speech.available, true);
  assert.equal(speech.acoustic_hint, "high_activation");
  assert.ok(speech.quality > 0.6);
  assert.ok(speech.evidence.length >= 3);
});

test("derives low activation from quiet, broken speech", () => {
  const speech = analyzeSpeech({
    duration_ms: 4200,
    speech_ratio: 0.42,
    mean_db: -43,
    variation_db: 2,
    mean_pitch_hz: 145,
    pitch_variation_hz: 8,
    pause_count: 5,
    clipping_ratio: 0,
  });

  assert.equal(speech.available, true);
  assert.equal(speech.acoustic_hint, "low_activation");
  assert.ok(speech.activation < 0.35);
});

test("fuses speech quality and evidence without hiding missing vision", () => {
  const text = analyzeText({
    text: "最近真的很烦，什么都不想干。",
    asrConfidence: 0.82,
  });
  const speech = analyzeSpeech({
    duration_ms: 2600,
    speech_ratio: 0.74,
    mean_db: -19,
    variation_db: 14,
    mean_pitch_hz: 220,
    pitch_variation_hz: 65,
    pause_count: 1,
    clipping_ratio: 0,
  });
  const fused = fuseModalities(text, speech);

  assert.equal(fused.status, "ok");
  assert.equal(fused.quality.vision, null);
  assert.ok(fused.quality.speech > 0.6);
  assert.ok(fused.evidence.speech.length >= 3);
  assert.ok(Math.abs(
    Object.values(fused.emotion_distribution).reduce(
      (sum, value) => sum + value,
      0,
    ) - 1,
  ) < 0.002);
});

test("rejects speech that is too short to support an acoustic conclusion", () => {
  const speech = analyzeSpeech({
    duration_ms: 120,
    speech_ratio: 0.8,
    mean_db: -20,
    variation_db: 8,
    mean_pitch_hz: 180,
    pitch_variation_hz: 30,
    pause_count: 0,
    clipping_ratio: 0,
  });

  assert.equal(speech.available, false);
  assert.equal(speech.reason, "speech_too_short");
});

test("uses a semantic model to recover paraphrased positive text", () => {
  const ruleAnalysis = analyzeText({
    text: "雨停了，事情也办成了，心里亮堂多了。",
  });
  const modelAnalysis = {
    available: true,
    model_id: "test-text-model",
    device: "cpu",
    predicted_raw: "happy",
    predicted_mapped: "joy",
    latency_ms: 12,
    raw_scores: { happy: 0.92 },
    mapped_distribution: {
      joy: 0.92,
      calm: 0,
      sadness: 0.01,
      anxiety: 0.01,
      anger_irritation: 0.01,
      neutral: 0.05,
    },
  };
  const fused = fuseSemanticModel(ruleAnalysis, modelAnalysis);

  assert.equal(fused.dominant_emotion.label, "joy");
  assert.equal(fused.semantic_model.model_id, "test-text-model");
  assert.ok(fused.evidence.text.some((item) => item.includes("模型判断")));
});

test("uses SenseVoice emotion tags as bounded speech evidence", () => {
  const textAnalysis = analyzeText({
    text: "我不知道该怎么办。",
  });
  const fused = fuseSpeechModel(textAnalysis, {
    available: true,
    model_id: "test-speech-model",
    emotion_tag: "fearful",
    text: "我不知道该怎么办。",
    latency_ms: 100,
  });

  assert.equal(fused.speech_model.mapped_emotion, "anxiety");
  assert.ok(fused.quality.speech > 0);
  assert.ok(fused.evidence.speech.some((item) => item.includes("SenseVoice")));
});

test("prefers emotion2vec probabilities when available", () => {
  const textAnalysis = analyzeText({
    text: "我现在不知道该做什么。",
  });
  const fused = fuseSpeechModel(textAnalysis, {
    available: true,
    model_id: "SenseVoiceSmall",
    emotion_tag: "neutral",
    text: "我现在不知道该做什么。",
    emotion2vec: {
      top_label: "sad",
      top_score: 0.82,
      scores: {
        angry: 0.01,
        disgusted: 0.01,
        fearful: 0.04,
        happy: 0.01,
        neutral: 0.06,
        other: 0.02,
        sad: 0.82,
        surprised: 0.02,
        unknown: 0.01,
      },
    },
  });

  assert.ok(fused.evidence.speech.some((item) => item.includes("emotion2vec")));
  assert.ok(fused.emotion_distribution.sadness > 0.2);
});

test("lets the fine-tuned model lead while preserving explicit calm", () => {
  const neutralRule = analyzeText({ text: "这件事终于有了结果。" });
  const angerModel = {
    available: true,
    provider: "finetuned",
    model_id: "test-finetuned",
    predicted_mapped: "anger_irritation",
    mapped_distribution: {
      joy: 0.03,
      calm: 0,
      sadness: 0.08,
      anxiety: 0.06,
      anger_irritation: 0.79,
      neutral: 0.04,
    },
  };
  const directed = applyFinetunedSemanticModel(neutralRule, angerModel);
  assert.equal(directed.dominant_emotion.label, "anger_irritation");

  const calmRule = analyzeText({ text: "我现在真的很平静。" });
  const neutralModel = {
    ...angerModel,
    predicted_mapped: "neutral",
    mapped_distribution: {
      joy: 0.04,
      calm: 0,
      sadness: 0.04,
      anxiety: 0.04,
      anger_irritation: 0.04,
      neutral: 0.8,
    },
  };
  const preserved = applyFinetunedSemanticModel(calmRule, neutralModel);
  assert.equal(preserved.dominant_emotion.label, "calm");

  const anxietyRule = analyzeText({
    text: "明天要答辩了，我一直睡不着，担心会搞砸。",
  });
  const protectedAnxiety = applyFinetunedSemanticModel(
    anxietyRule,
    neutralModel,
  );
  assert.equal(protectedAnxiety.dominant_emotion.label, "anxiety");
});
