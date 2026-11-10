import { logInfo, logError, logWarn } from "../logger.js";

const DASHSCOPE_BASE = "https://dashscope.aliyuncs.com";
const MODEL = "qwen-audio-3.1-asr-flash-filetrans";
const POLL_INTERVAL_MS = 1000;
const POLL_TIMEOUT_MS = 120000;

/**
 * 百炼 filetrans ASR client
 * Flow: upload file -> create job -> poll -> get transcription -> delete file
 */
export async function transcribeAudio({
  apiKey,
  audioBuffer,
  filename = "audio.wav",
  vocabulary = [],
}) {
  if (!apiKey) {
    throw new Error("百炼 ASR api_key 未配置");
  }

  const startedAt = Date.now();
  logInfo("bailian_asr_start", { filename, vocabularyCount: vocabulary.length });

  // 1. Upload file
  const fileId = await uploadFile(apiKey, audioBuffer, filename);
  logInfo("bailian_asr_uploaded", { fileId });

  try {
    // 2. Get file URL
    const fileUrl = await getFileUrl(apiKey, fileId);

    // 3. Create transcription job
    const taskId = await createTranscriptionJob(apiKey, fileUrl, vocabulary);
    logInfo("bailian_asr_job_created", { taskId });

    // 4. Poll job status
    const transcriptionUrl = await pollJob(apiKey, taskId);

    // 5. Download transcription result
    const text = await downloadTranscription(transcriptionUrl);

    const latencyMs = Date.now() - startedAt;
    logInfo("bailian_asr_success", { taskId, latencyMs, textLength: text.length });
    return { text, taskId, latencyMs };
  } finally {
    // 6. Delete uploaded file (best effort)
    try {
      await deleteFile(apiKey, fileId);
    } catch (e) {
      logWarn("bailian_asr_delete_file_failed", { fileId, error: e.message });
    }
  }
}

async function uploadFile(apiKey, buffer, filename) {
  const form = new FormData();
  const blob = new Blob([buffer]);
  form.append("file", blob, filename);
  form.append("purpose", "asr");

  const resp = await fetch(`${DASHSCOPE_BASE}/compatible-mode/v1/files`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    body: form,
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`上传文件失败: HTTP ${resp.status} - ${err.slice(0, 200)}`);
  }

  const data = await resp.json();
  return data.id;
}

async function getFileUrl(apiKey, fileId) {
  const resp = await fetch(
    `${DASHSCOPE_BASE}/compatible-mode/v1/files/${fileId}`,
    {
      headers: { Authorization: `Bearer ${apiKey}` },
    },
  );
  if (!resp.ok) {
    throw new Error(`获取文件URL失败: HTTP ${resp.status}`);
  }
  const data = await resp.json();
  return data.url;
}

async function createTranscriptionJob(apiKey, fileUrl, vocabulary) {
  const body = {
    model: MODEL,
    input: {
      file_urls: [fileUrl],
    },
    parameters: {},
  };
  if (vocabulary && vocabulary.length > 0) {
    body.parameters.vocabulary = vocabulary;
  }

  const resp = await fetch(
    `${DASHSCOPE_BASE}/api/v1/services/audio/asr/transcription`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
  );

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`创建转写任务失败: HTTP ${resp.status} - ${err.slice(0, 300)}`);
  }

  const data = await resp.json();
  return data.output?.task_id;
}

async function pollJob(apiKey, taskId) {
  const startTime = Date.now();
  while (Date.now() - startTime < POLL_TIMEOUT_MS) {
    const resp = await fetch(
      `${DASHSCOPE_BASE}/api/v1/services/audio/asr/transcription/${taskId}`,
      {
        headers: { Authorization: `Bearer ${apiKey}` },
      },
    );
    if (!resp.ok) {
      throw new Error(`查询任务失败: HTTP ${resp.status}`);
    }
    const data = await resp.json();
    const status = data.output?.task_status;

    if (status === "SUCCEEDED") {
      const results = data.output?.results || [];
      if (results.length > 0 && results[0].transcription_url) {
        return results[0].transcription_url;
      }
      throw new Error("任务成功但无转写结果");
    }
    if (status === "FAILED" || status === "CANCELED") {
      const msg = data.output?.message || "任务失败";
      throw new Error(`转写任务${status}: ${msg}`);
    }

    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }
  throw new Error("转写任务超时");
}

async function downloadTranscription(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`下载转写结果失败: HTTP ${resp.status}`);
  }
  const data = await resp.json();
  const transcripts = data.transcripts || [];
  return transcripts
    .map((t) => (typeof t === "string" ? t : t.text || ""))
    .join("");
}

async function deleteFile(apiKey, fileId) {
  await fetch(`${DASHSCOPE_BASE}/compatible-mode/v1/files/${fileId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${apiKey}` },
  });
}
