import { appendFile, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  analyzeText,
  fuseSemanticModel,
} from "../src/emotion-engine.js";
import { createLocalModelClient } from "../src/model-client.js";

const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const corpusKey =
  process.env.EXTERNAL_CORPUS ?? "external-chinese-dialogue";
const manifestPath = resolve(
  projectDirectory,
  "evaluation",
  `${corpusKey}-manifest.json`,
);
const predictionsPath = resolve(
  projectDirectory,
  "outputs",
  `${corpusKey}-eval-checkpoint.jsonl`,
);
const outputPath = resolve(
  projectDirectory,
  "outputs",
  `${corpusKey}-finetuned-checkpoint.jsonl`,
);

function parseJsonLines(content) {
  return content
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .flatMap((line) => {
      try {
        return [JSON.parse(line)];
      } catch {
        return [];
      }
    });
}

async function optionalRows(path) {
  try {
    return parseJsonLines(await readFile(path, "utf8"));
  } catch {
    return [];
  }
}

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const rows = parseJsonLines(await readFile(predictionsPath, "utf8"));
const existing = new Map(
  (await optionalRows(outputPath)).map((row) => [row.id, row]),
);
const pending = rows.filter((row) => !existing.has(row.id));
const client = createLocalModelClient();

for (const [index, row] of pending.entries()) {
  const semantic = await client.analyzeFinetuned(row.text);
  if (!semantic?.available) {
    throw new Error(`${row.id} 微调模型推理失败`);
  }
  const rule = analyzeText({
    text: row.text,
    asrConfidence: 1,
    dialect: "mandarin",
  });
  const hybrid = fuseSemanticModel(rule, semantic);
  const mapPrediction = (prediction) =>
    manifest.prediction_aliases?.[prediction] ?? prediction;
  const result = {
    id: row.id,
    split: row.split,
    label: row.label,
    finetuned_pred: mapPrediction(semantic.predicted_mapped),
    finetuned_confidence: Math.max(
      0,
      ...Object.values(semantic.mapped_distribution ?? {}),
    ),
    finetuned_hybrid_pred: mapPrediction(hybrid.dominant_emotion.label),
    finetuned_hybrid_confidence: hybrid.dominant_emotion.confidence,
    finetuned_latency_ms: semantic.latency_ms,
    primary_distribution: semantic.mapped_distribution,
    multilabel_distribution: semantic.multilabel_distribution,
  };
  await appendFile(outputPath, JSON.stringify(result) + "\n", "utf8");
  existing.set(row.id, result);
  if ((index + 1) % 100 === 0 || index + 1 === pending.length) {
    console.log(`微调模型进度：${index + 1}/${pending.length}`);
  }
}

console.log(`微调模型检查点完成：${existing.size}/${rows.length}`);
