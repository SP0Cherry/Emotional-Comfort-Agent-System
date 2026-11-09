import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const labels = [
  "joy",
  "calm",
  "sadness",
  "anxiety",
  "anger_irritation",
  "neutral",
];
const negativeLabels = new Set(["sadness", "anxiety", "anger_irritation"]);
const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const checkpointPath = resolve(
  projectDirectory,
  "outputs",
  "brighter-chinese-finetuned-checkpoint.jsonl",
);
const reportPath = resolve(
  projectDirectory,
  "evaluation",
  "brighter-output-tuning-report.json",
);
const markdownPath = resolve(
  projectDirectory,
  "docs",
  "brighter-output-tuning.md",
);

function parseJsonLines(content) {
  return content
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line));
}

function normalize(values) {
  const total = Object.values(values).reduce(
    (sum, value) => sum + Math.max(0, value),
    0,
  );
  return Object.fromEntries(
    labels.map((label) => [
      label,
      total > 0 ? Math.max(0, values[label] ?? 0) / total : 0,
    ]),
  );
}

function blended(row, weight) {
  return normalize(
    Object.fromEntries(
      labels.map((label) => [
        label,
        row.primary_distribution[label] * (1 - weight) +
          (row.multilabel_distribution?.[label] ?? 0) * weight,
      ]),
    ),
  );
}

function applyBias(distribution, biases) {
  return normalize(
    Object.fromEntries(
      labels.map((label) => [
        label,
        distribution[label] * Math.exp(biases[label] ?? 0),
      ]),
    ),
  );
}

function predict(distribution) {
  return labels.reduce((best, label) =>
    distribution[label] > distribution[best] ? label : best,
  );
}

function metrics(rows, weight, biases = {}) {
  const expected = rows.map((row) => row.label);
  const probabilities = rows.map((row) =>
    applyBias(blended(row, weight), biases),
  );
  const predicted = probabilities.map(predict);
  const correct = expected.filter((label, index) => label === predicted[index]);
  const perClass = {};
  for (const label of labels) {
    const tp = expected.filter(
      (value, index) => value === label && predicted[index] === label,
    ).length;
    const fp = expected.filter(
      (value, index) => value !== label && predicted[index] === label,
    ).length;
    const fn = expected.filter(
      (value, index) => value === label && predicted[index] !== label,
    ).length;
    const precision = tp + fp ? tp / (tp + fp) : 0;
    const recall = tp + fn ? tp / (tp + fn) : 0;
    perClass[label] = {
      support: tp + fn,
      precision,
      recall,
      f1: precision + recall ? (2 * precision * recall) / (precision + recall) : 0,
    };
  }
  const supported = labels.filter((label) => perClass[label].support > 0);
  const macroF1 =
    supported.reduce((sum, label) => sum + perClass[label].f1, 0) /
    Math.max(1, supported.length);
  let tp = 0;
  let fp = 0;
  let fn = 0;
  for (let index = 0; index < expected.length; index += 1) {
    const y = negativeLabels.has(expected[index]);
    const p = negativeLabels.has(predicted[index]);
    if (y && p) tp += 1;
    else if (!y && p) fp += 1;
    else if (y && !p) fn += 1;
  }
  const negativePrecision = tp + fp ? tp / (tp + fp) : 0;
  const negativeRecall = tp + fn ? tp / (tp + fn) : 0;
  return {
    accuracy: correct.length / Math.max(1, rows.length),
    macro_f1: macroF1,
    negative_f1:
      negativePrecision + negativeRecall
        ? (2 * negativePrecision * negativeRecall) /
          (negativePrecision + negativeRecall)
        : 0,
    per_class: perClass,
    predictions: predicted,
    probabilities,
  };
}

function tuneBias(rows, baseWeight) {
  const biases = Object.fromEntries(labels.map((label) => [label, 0]));
  let current = metrics(rows, baseWeight, biases);
  for (const step of [0.2, 0.1, 0.05]) {
    let improved = true;
    while (improved) {
      improved = false;
      for (const label of labels) {
        const original = biases[label];
        const candidates = [original - step, original + step]
          .filter((value) => value >= -0.3 && value <= 0.3);
        let best = original;
        let bestMetrics = current;
        for (const candidate of candidates) {
          const trialBiases = { ...biases, [label]: candidate };
          const trial = metrics(rows, baseWeight, trialBiases);
          const regularized =
            trial.macro_f1 - Math.abs(candidate) * 0.0005;
          const currentRegularized =
            bestMetrics.macro_f1 - Math.abs(best) * 0.0005;
          if (regularized > currentRegularized + 1e-9) {
            best = candidate;
            bestMetrics = trial;
          }
        }
        if (best !== original) {
          biases[label] = best;
          current = bestMetrics;
          improved = true;
        }
      }
    }
  }
  return { biases, metrics: current };
}

const rows = parseJsonLines(await readFile(checkpointPath, "utf8"));
const dev = rows.filter((row) => row.split === "dev");
const test = rows.filter((row) => row.split === "test");
const weights = Array.from({ length: 11 }, (_, index) => index / 20);
const weightResults = weights.map((weight) => ({
  weight,
  dev: (({ predictions, probabilities, ...value }) => value)(
    metrics(dev, weight),
  ),
}));
weightResults.sort(
  (left, right) =>
    right.dev.macro_f1 - left.dev.macro_f1 ||
    right.dev.accuracy - left.dev.accuracy,
);
const selected = weightResults[0];
const tuning = tuneBias(dev, selected.weight);
const testMetrics = metrics(test, selected.weight, tuning.biases);

const report = {
  generated_at: new Date().toISOString(),
  selection_split: "dev",
  test_split_used_for_selection: false,
  weight_search: weightResults,
  selected_weight: selected.weight,
  selected_dev_metrics: selected.dev,
  class_biases: tuning.biases,
  tuned_dev_metrics: (({ predictions, probabilities, ...value }) => value)(
    tuning.metrics,
  ),
  test_metrics: (({ predictions, probabilities, ...value }) => value)(
    testMetrics,
  ),
};
await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");
await writeFile(
  markdownPath,
  `# 微调模型输出策略调参

## Dev 集选择结果

- 多标签融合权重：${selected.weight.toFixed(2)}
- 类别偏置：\`${JSON.stringify(tuning.biases)}\`
- Dev Accuracy：${(tuning.metrics.accuracy * 100).toFixed(1)}%
- Dev Macro-F1：${(tuning.metrics.macro_f1 * 100).toFixed(1)}%

## 未参与调参的 Test

- Accuracy：${(testMetrics.accuracy * 100).toFixed(1)}%
- Macro-F1：${(testMetrics.macro_f1 * 100).toFixed(1)}%
- 负面检测 F1：${(testMetrics.negative_f1 * 100).toFixed(1)}%

测试集没有参与融合权重或类别偏置搜索。
`,
  "utf8",
);
console.log(
  JSON.stringify(
    {
      selected_weight: selected.weight,
      class_biases: tuning.biases,
      dev: report.tuned_dev_metrics,
      test: report.test_metrics,
    },
    null,
    2,
  ),
);
