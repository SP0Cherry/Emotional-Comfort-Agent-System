import { chatCompletion } from "../llm/client.js";
import { analyzeEmotion } from "../emotion/client.js";
import { buildSystemPrompt } from "../emotion/prompt-builder.js";
import { getSession, appendMessage, updateSession } from "../session-store.js";
import { getPersona } from "../persona-store.js";
import { loadConfig } from "../config-store.js";
import { logInfo, logError } from "../logger.js";

const MAX_HISTORY_TURNS = 20; // keep last 20 turns (40 messages) in LLM context

/**
 * Process one user turn:
 *   text -> emotion -> system prompt (persona + emotion) + history -> LLM -> reply
 *
 * @param {string} sessionId
 * @param {string} userText
 * @returns {Promise<{reply: string, emotion: Object}>}
 */
export async function processTurn(sessionId, userText) {
  const startedAt = Date.now();
  logInfo("turn_start", { sessionId, textLength: userText.length });

  if (!userText || !userText.trim()) {
    throw new Error("输入不能为空");
  }

  const session = await getSession(sessionId);
  if (!session) {
    throw new Error("会话不存在");
  }

  const config = await loadConfig();

  // 1. Emotion analysis
  let emotion = { available: false };
  try {
    emotion = await analyzeEmotion({
      serviceUrl: config.emotion.service_url,
      sessionId,
      text: userText,
      timeoutMs: config.emotion.timeout_ms,
    });
  } catch (err) {
    logError("emotion_call_unexpected", { sessionId, error: err.message });
  }

  // 2. Build system prompt with persona + emotion
  const persona = session.personaId
    ? await getPersona(session.personaId)
    : null;
  const personaPrompt = persona?.prompt || "你是一位温暖的陪伴者。";
  const systemPrompt = buildSystemPrompt({ personaPrompt, emotion });

  // 3. Build message history (isolate per session)
  const historyMessages = buildHistoryMessages(session.messages);
  const messages = [
    { role: "system", content: systemPrompt },
    ...historyMessages,
    { role: "user", content: userText },
  ];

  // 4. Call LLM
  let reply;
  try {
    reply = await chatCompletion({
      baseUrl: config.llm.base_url,
      apiKey: config.llm.api_key,
      model: config.llm.model,
      temperature: config.llm.temperature,
      messages,
    });
  } catch (err) {
    logError("llm_call_failed", { sessionId, error: err.message });
    throw new Error(`生成回复失败：${err.message}`);
  }

  // 5. Persist messages
  await appendMessage(sessionId, {
    role: "user",
    content: userText,
    emotion: emotion.available
      ? {
          dominantEmotion: emotion.dominantEmotion,
          risk: emotion.risk,
          valence: emotion.valence,
        }
      : null,
  });
  await appendMessage(sessionId, { role: "assistant", content: reply });

  const latencyMs = Date.now() - startedAt;
  logInfo("turn_complete", {
    sessionId,
    latencyMs,
    emotionAvailable: emotion.available,
    replyLength: reply.length,
  });

  return { reply, emotion };
}

function buildHistoryMessages(storedMessages) {
  // Keep only user/assistant messages, truncate to last MAX_HISTORY_TURNS
  const conversation = storedMessages.filter(
    (m) => m.role === "user" || m.role === "assistant",
  );
  const truncated = conversation.slice(-MAX_HISTORY_TURNS * 2);
  return truncated.map((m) => ({ role: m.role, content: m.content }));
}

/**
 * Set the persona for a session.
 */
export async function setSessionPersona(sessionId, personaId) {
  const persona = await getPersona(personaId);
  if (!persona) {
    throw new Error("人格不存在");
  }
  const updated = await updateSession(sessionId, { personaId });
  if (!updated) {
    throw new Error("会话不存在");
  }
  return updated;
}
