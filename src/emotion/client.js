import { logInfo, logError } from "../logger.js";

const EMOTION_LABELS_CN = {
  joy: "高兴",
  calm: "平静",
  sadness: "悲伤",
  anxiety: "焦虑",
  anger_irritation: "烦躁",
  neutral: "中性",
};

const RISK_LABELS_CN = {
  none: "无风险",
  watch: "需关注",
  urgent: "高风险",
};

/**
 * Call the emotion recognition service (emotion-recognition-delivery)
 * to analyze the user's text input.
 *
 * @param {Object} opts
 * @param {string} opts.serviceUrl - e.g. http://127.0.0.1:4173
 * @param {string} opts.sessionId - session identifier
 * @param {string} opts.text - user text
 * @param {number} [opts.timeoutMs=8000] - request timeout
 * @returns {Promise<Object>} emotion result with available flag
 */
export async function analyzeEmotion({
  serviceUrl,
  sessionId,
  text,
  timeoutMs = 8000,
}) {
  if (!text || !text.trim()) {
    return { available: false, reason: "empty_text" };
  }

  const startedAt = Date.now();
  logInfo("emotion_request", { sessionId, textLength: text.length });

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const resp = await fetch(
      `${serviceUrl.replace(/\/$/, "")}/api/v1/emotion/turns`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          text: text.trim(),
          dialect: "mandarin",
        }),
        signal: controller.signal,
      },
    );

    clearTimeout(timer);

    if (!resp.ok) {
      throw new Error(`情感服务返回 HTTP ${resp.status}`);
    }

    const data = await resp.json();
    const latencyMs = Date.now() - startedAt;

    const result = {
      available: true,
      dominantEmotion: data.dominant_emotion?.label || "neutral",
      dominantEmotionConfidence: data.dominant_emotion?.confidence || 0,
      emotionDistribution: data.emotion_distribution || {},
      valence: data.dimensions?.valence ?? 0,
      arousal: data.dimensions?.arousal ?? 0,
      intensity: data.dimensions?.intensity ?? 0,
      risk: data.risk || "none",
      decisionMode: data.decision_mode || "clarify",
      companionNeeds: data.companion_needs || [],
      temporal: data.temporal || null,
      latencyMs,
    };

    logInfo("emotion_success", {
      sessionId,
      dominantEmotion: result.dominantEmotion,
      risk: result.risk,
      latencyMs,
    });

    return result;
  } catch (err) {
    const latencyMs = Date.now() - startedAt;
    const isTimeout = err.name === "AbortError";
    logError("emotion_failed", {
      sessionId,
      error: err.message,
      timeout: isTimeout,
      latencyMs,
    });
    return {
      available: false,
      reason: isTimeout ? "timeout" : "service_unavailable",
      error: err.message,
    };
  }
}

/**
 * Get a Chinese label for an emotion code
 */
export function emotionLabelCN(code) {
  return EMOTION_LABELS_CN[code] || code;
}

export function riskLabelCN(code) {
  return RISK_LABELS_CN[code] || code;
}
