import { readFile } from "node:fs/promises";
import process from "node:process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  EMOTION_LABELS,
  analyzeText,
  fuseSemanticModel,
} from "../src/emotion-engine.js";
import { createLocalModelClient } from "../src/model-client.js";

const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const corpusNames = (
  process.env.CORPORA ??
  "mandarin-regression,mandarin-challenge,mandarin-holdout"
).split(",");
const modelClient = createLocalModelClient();

function macroF1(results) {
  const scores = [];
  for (const label of EMOTION_LABELS) {
    const truePositive = results.filter(
      (item) => item.expected === label && item.predicted === label,
    ).length;
    const falsePositive = results.filter(
      (item) => item.expected !== label && item.predicted === label,
    ).length;
    const falseNegative = results.filter(
      (item) => item.expected === label && item.predicted !== label,
    ).length;
    const precision =
      truePositive + falsePositive === 0
        ? 0
        : truePositive / (truePositive + falsePositive);
    const recall =
      truePositive + falseNegative === 0
        ? 0
        : truePositive / (truePositive + falseNegative);
    scores.push(
      precision + recall === 0
        ? 0
        : (2 * precision * recall) / (precision + recall),
    );
  }
  return scores.reduce((sum, value) => sum + value, 0) / scores.length;
}

for (const corpusName of corpusNames) {
  const corpus = JSON.parse(
    await readFile(
      resolve(projectDirectory, "evaluation", `${corpusName}.json`),
      "utf8",
    ),
  );
  const rows = [];

  for (const item of corpus) {
    const rule = analyzeText({
      text: item.text,
      asrConfidence: 1,
      dialect: "mandarin",
    });
    let semanticModel;
    try {
      semanticModel = await modelClient.analyzeText(item.text);
    } catch (error) {
      throw new Error(`模型服务不可用：${error.message}`);
    }
    const hybrid = fuseSemanticModel(rule, semanticModel);
    rows.push({
      expected: item.expected,
      rule: rule.dominant_emotion.label,
      model: semanticModel.predicted_mapped,
      hybrid: hybrid.dominant_emotion.label,
      text: item.text,
    });
  }

  const summarize = (key) => {
    const results = rows.map((row) => ({
      expected: row.expected,
      predicted: row[key],
    }));
    const correct = results.filter(
      (item) => item.expected === item.predicted,
    ).length;
    return {
      accuracy: correct / results.length,
      macro_f1: macroF1(results),
    };
  };

  console.log(`\n${corpusName} (${rows.length} 条)`);
  for (const [name, key] of [
    ["规则", "rule"],
    ["文本模型", "model"],
    ["规则 + 模型", "hybrid"],
  ]) {
    const metrics = summarize(key);
    console.log(
      `${name}: Accuracy ${(metrics.accuracy * 100).toFixed(1)}%, Macro-F1 ${(metrics.macro_f1 * 100).toFixed(1)}%`,
    );
  }

  const hybridErrors = rows.filter(
    (row) => row.expected !== row.hybrid,
  );
  if (hybridErrors.length) {
    console.log("融合错误：");
    for (const error of hybridErrors) {
      console.log(
        `- ${error.expected} -> ${error.hybrid}（规则 ${error.rule}，模型 ${error.model}）：${error.text}`,
      );
    }
  }
}
