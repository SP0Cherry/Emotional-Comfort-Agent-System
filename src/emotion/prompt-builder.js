import { emotionLabelCN, riskLabelCN } from "./client.js";

/**
 * Build an emotion context string to inject into the LLM prompt.
 * Returns a short Chinese description of the user's current emotional state.
 */
export function buildEmotionContext(emotion) {
  if (!emotion || !emotion.available) {
    return "";
  }

  const parts = [];
  parts.push(`用户当前情绪：${emotionLabelCN(emotion.dominantEmotion)}（置信度 ${(emotion.dominantEmotionConfidence * 100).toFixed(0)}%）`);

  if (emotion.valence !== undefined) {
    const valenceDesc =
      emotion.valence > 0.3
        ? "偏积极"
        : emotion.valence < -0.3
          ? "偏消极"
          : "中性";
    parts.push(`情绪效价：${valenceDesc}（${emotion.valence.toFixed(2)}）`);
  }

  if (emotion.risk && emotion.risk !== "none") {
    parts.push(`风险等级：${riskLabelCN(emotion.risk)}`);
  }

  if (emotion.decisionMode === "clarify") {
    parts.push("情绪判断置信度较低，建议先温和追问确认用户感受");
  }

  if (Array.isArray(emotion.companionNeeds) && emotion.companionNeeds.length > 0) {
    const needs = emotion.companionNeeds
      .map((n) => (typeof n === "string" ? n : n.need || n.type))
      .filter(Boolean);
    if (needs.length) {
      parts.push(`陪伴需求：${needs.join("、")}`);
    }
  }

  return parts.join("；");
}

/**
 * Build the full system prompt combining persona and emotion context.
 */
export function buildSystemPrompt({ personaPrompt, emotion }) {
  const base =
    personaPrompt +
    "\n\n你的角色是情感抚慰陪伴者，需要耐心倾听用户的心声，给予温暖、共情的回应。" +
    "用简洁、口语化的中文回复，不要使用医学术语，不要给出诊断结论。" +
    "当用户表达负面情绪时，先共情再安抚；当用户表达积极情绪时，给予肯定和鼓励。";

  const emotionContext = buildEmotionContext(emotion);
  if (emotionContext) {
    return `${base}\n\n【当前情感信号】\n${emotionContext}\n\n请根据以上情感信号调整你的回复方式。`;
  }
  return base;
}
