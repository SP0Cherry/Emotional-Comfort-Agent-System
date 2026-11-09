const DEFAULT_BASE_URL = "http://127.0.0.1:5055";

async function fetchJson(url, options = {}, timeoutMs = 1_500) {
  const response = await fetch(url, {
    ...options,
    signal: AbortSignal.timeout(timeoutMs),
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.error ?? payload.detail ?? `HTTP ${response.status}`;
    throw new Error(`本地模型服务错误：${detail}`);
  }
  return payload;
}

export function createLocalModelClient({
  baseUrl = process.env.MODEL_SERVICE_URL ?? DEFAULT_BASE_URL,
  textTimeoutMs = 6_000,
  speechTimeoutMs = 12_000,
} = {}) {
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");

  return {
    async health() {
      try {
        return await fetchJson(`${normalizedBaseUrl}/health`, {}, 800);
      } catch {
        return {
          status: "unavailable",
          text_model: { ready: false },
          speech_model: { ready: false },
        };
      }
    },

    async analyzeText(text) {
      return fetchJson(
        `${normalizedBaseUrl}/v1/text`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
        textTimeoutMs,
      );
    },

    async analyzeClassifier(text) {
      return fetchJson(
        `${normalizedBaseUrl}/v1/text-classifier`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
        textTimeoutMs,
      );
    },

    async analyzeFinetuned(text) {
      return fetchJson(
        `${normalizedBaseUrl}/v1/text-finetuned`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
        textTimeoutMs,
      );
    },

    async analyzeSpeech(audio) {
      return fetchJson(
        `${normalizedBaseUrl}/v1/speech`,
        {
          method: "POST",
          headers: { "Content-Type": "audio/wav" },
          body: audio,
        },
        speechTimeoutMs,
      );
    },
  };
}
