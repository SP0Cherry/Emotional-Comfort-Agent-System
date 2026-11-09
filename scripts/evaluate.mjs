import { readFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { EMOTION_LABELS, analyzeText } from "../src/emotion-engine.js";

const scriptDirectory = resolve(fileURLToPath(import.meta.url), "..");
const corpusArgument = process.argv.find((argument) =>
  argument.startsWith("--corpus="),
);
const corpusName = corpusArgument
  ? corpusArgument.slice("--corpus=".length)
  : "mandarin-regression";
if (!/^[a-z0-9-]+$/.test(corpusName)) {
  throw new Error("语料名称只能包含小写字母、数字和连字符");
}
const fixturePath = resolve(
  scriptDirectory,
  "..",
  "evaluation",
  `${corpusName}.json`,
);
const cases = JSON.parse(await readFile(fixturePath, "utf8"));

const results = cases.map((item) => {
  const startedAt = performance.now();
  const analysis = analyzeText({
    text: item.text,
    asrConfidence: 1,
    dialect: "mandarin",
  });
  const latencyMs = performance.now() - startedAt;

  return {
    text: item.text,
    expected: item.expected,
    predicted: analysis.dominant_emotion.label,
    confidence: analysis.dominant_emotion.confidence,
    latency_ms: latencyMs,
  };
});

const correct = results.filter((item) => item.expected === item.predicted).length;
const accuracy = correct / results.length;
const classMetrics = {};
const confusion = Object.fromEntries(
  EMOTION_LABELS.map((expected) => [
    expected,
    Object.fromEntries(EMOTION_LABELS.map((label) => [label, 0])),
  ]),
);

for (const expected of EMOTION_LABELS) {
  const truePositive = results.filter(
    (item) => item.expected === expected && item.predicted === expected,
  ).length;
  const falsePositive = results.filter(
    (item) => item.expected !== expected && item.predicted === expected,
  ).length;
  const falseNegative = results.filter(
    (item) => item.expected === expected && item.predicted !== expected,
  ).length;
  const precision =
    truePositive + falsePositive === 0
      ? 0
      : truePositive / (truePositive + falsePositive);
  const recall =
    truePositive + falseNegative === 0
      ? 0
      : truePositive / (truePositive + falseNegative);
  const f1 =
    precision + recall === 0
      ? 0
      : (2 * precision * recall) / (precision + recall);

  classMetrics[expected] = { precision, recall, f1 };
}

for (const item of results) {
  confusion[item.expected][item.predicted] += 1;
}

const macroF1 =
  Object.values(classMetrics).reduce((sum, item) => sum + item.f1, 0) /
  EMOTION_LABELS.length;
const meanLatency =
  results.reduce((sum, item) => sum + item.latency_ms, 0) / results.length;
const sortedLatencies = results
  .map((item) => item.latency_ms)
  .sort((left, right) => left - right);
const p95Latency =
  sortedLatencies[
    Math.min(
      sortedLatencies.length - 1,
      Math.floor(sortedLatencies.length * 0.95),
    )
  ];

const report = {
  corpus: basename(fixturePath, ".json"),
  sample_count: results.length,
  note: "行为回归集，不是说话人隔离的正式精度评测集。",
  accuracy,
  macro_f1: macroF1,
  mean_latency_ms: Number(meanLatency.toFixed(3)),
  p95_latency_ms: Number(p95Latency.toFixed(3)),
  class_metrics: Object.fromEntries(
    Object.entries(classMetrics).map(([label, metrics]) => [
      label,
      Object.fromEntries(
        Object.entries(metrics).map(([name, value]) => [
          name,
          Number(value.toFixed(3)),
        ]),
      ),
    ]),
  ),
  confusion,
  errors: results.filter((item) => item.expected !== item.predicted),
};

if (process.argv.includes("--json")) {
  console.log(JSON.stringify(report, null, 2));
} else {
  console.log(`${report.corpus}：${report.sample_count} 条`);
  console.log(`Accuracy：${(accuracy * 100).toFixed(1)}%`);
  console.log(`Macro-F1：${(macroF1 * 100).toFixed(1)}%`);
  console.log(`平均延迟：${report.mean_latency_ms.toFixed(3)} ms`);
  console.log(`P95 延迟：${report.p95_latency_ms.toFixed(3)} ms`);
  console.log("");
  console.log("类别\tPrecision\tRecall\tF1");
  for (const label of EMOTION_LABELS) {
    const metrics = report.class_metrics[label];
    console.log(
      `${label}\t${(metrics.precision * 100).toFixed(1)}%\t${(metrics.recall * 100).toFixed(1)}%\t${(metrics.f1 * 100).toFixed(1)}%`,
    );
  }
  if (report.errors.length) {
    console.log("");
    console.log("错误案例：");
    for (const error of report.errors) {
      console.log(
        `- ${error.expected} -> ${error.predicted}: ${error.text}`,
      );
    }
  }
}
