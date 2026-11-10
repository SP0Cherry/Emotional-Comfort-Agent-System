import { logInfo, logError } from "../logger.js";

/**
 * Call an OpenAI-compatible chat completions endpoint.
 *
 * @param {Object} opts
 * @param {string} opts.baseUrl - e.g. https://dashscope.aliyuncs.com/compatible-mode/v1
 * @param {string} opts.apiKey
 * @param {string} opts.model
 * @param {Array} opts.messages - [{role, content}]
 * @param {number} [opts.temperature=0.7]
 * @param {number} [opts.timeoutMs=60000]
 * @returns {Promise<string>} assistant reply text
 */
export async function chatCompletion({
  baseUrl,
  apiKey,
  model,
  messages,
  temperature = 0.7,
  timeoutMs = 60000,
}) {
  if (!baseUrl || !apiKey || !model) {
    throw new Error("LLM 配置不完整：需要 base_url、api_key、model");
  }

  const url = `${baseUrl.replace(/\/$/, "")}/chat/completions`;
  const startedAt = Date.now();

  logInfo("llm_request", { model, messageCount: messages.length });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages,
        temperature,
      }),
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`LLM 接口返回 HTTP ${resp.status}: ${errText.slice(0, 300)}`);
    }

    const data = await resp.json();
    const reply = data.choices?.[0]?.message?.content || "";
    const latencyMs = Date.now() - startedAt;

    logInfo("llm_success", {
      model,
      latencyMs,
      replyLength: reply.length,
    });

    return reply.trim();
  } catch (err) {
    clearTimeout(timer);
    const latencyMs = Date.now() - startedAt;
    const isTimeout = err.name === "AbortError";
    logError("llm_failed", {
      model,
      error: err.message,
      timeout: isTimeout,
      latencyMs,
    });
    if (isTimeout) {
      throw new Error("LLM 请求超时，请稍后重试");
    }
    throw err;
  }
}
