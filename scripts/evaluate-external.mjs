import { createHash } from "node:crypto";
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
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
const corpusKey =
  process.env.EXTERNAL_CORPUS ?? "external-chinese-dialogue";
const datasetPath = resolve(
  projectDirectory,
  "evaluation",
  `${corpusKey}.jsonl`,
);
const manifestPath = resolve(
  projectDirectory,
  "evaluation",
  `${corpusKey}-manifest.json`,
);
const checkpointPath = resolve(
  projectDirectory,
  "outputs",
  `${corpusKey}-eval-checkpoint.jsonl`,
);
const reportPath = resolve(
  projectDirectory,
  "evaluation",
  `${corpusKey}-report.json`,
);
const markdownReportPath = resolve(
  projectDirectory,
  "docs",
  `${corpusKey}-results.md`,
);
const limit = Number(process.env.EVAL_LIMIT ?? Number.POSITIVE_INFINITY);

function parseJsonLines(content, label) {
  return content
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .flatMap((line, index) => {
      try {
        return [JSON.parse(line)];
      } catch {
        console.warn(`${label} 第 ${index + 1} 行损坏，已跳过`);
        return [];
      }
    });
}

function sleep(milliseconds) {
  return new Promise((resolvePromise) =>
    setTimeout(resolvePromise, milliseconds),
  );
}

function hashText(value) {
  return createHash("sha256").update(value).digest("hex");
}

function stratifiedTestRows(rows, limit) {
  if (!Number.isFinite(limit) || rows.length <= limit) return rows;
  const groups = new Map();
  for (const row of rows) {
    if (!groups.has(row.label)) groups.set(row.label, []);
    groups.get(row.label).push(row);
  }
  for (const group of groups.values()) {
    group.sort((left, right) =>
      hashText(left.id).localeCompare(hashText(right.id)),
    );
  }

  const labels = [...groups.keys()].sort();
  const quotas = Object.fromEntries(
    labels.map((label) => [label, Math.min(50, groups.get(label).length)]),
  );
  let remaining = limit - Object.values(quotas).reduce((sum, value) => sum + value, 0);
  const remainingCounts = Object.fromEntries(
    labels.map((label) => [
      label,
      groups.get(label).length - quotas[label],
    ]),
  );
  const totalRemaining = Object.values(remainingCounts).reduce(
    (sum, value) => sum + value,
    0,
  );
  const proportionalPool = remaining;
  const fractions = [];
  for (const label of labels) {
    const exact =
      totalRemaining > 0
        ? (proportionalPool * remainingCounts[label]) / totalRemaining
        : 0;
    const whole = Math.min(
      remainingCounts[label],
      Math.floor(exact),
    );
    quotas[label] += whole;
    remaining -= whole;
    fractions.push([label, exact - whole]);
  }
  fractions.sort((left, right) => right[1] - left[1]);
  for (const [label] of fractions) {
    if (remaining <= 0) break;
    if (quotas[label] < groups.get(label).length) {
      quotas[label] += 1;
      remaining -= 1;
    }
  }

  return labels.flatMap((label) => groups.get(label).slice(0, quotas[label]));
}

async function loadCheckpoint() {
  try {
    return new Map(
      parseJsonLines(await readFile(checkpointPath, "utf8"), "检查点").map(
        (row) => [row.id, row],
      ),
    );
  } catch {
    return new Map();
  }
}

async function loadClassifierCheckpoint() {
  try {
    return new Map(
      parseJsonLines(
        await readFile(
          resolve(
            projectDirectory,
            "outputs",
            `${corpusKey}-classifier-checkpoint.jsonl`,
          ),
          "utf8",
        ),
        "分类器检查点",
      ).map((row) => [row.id, row]),
    );
  } catch {
    return new Map();
  }
}

async function loadFinetunedCheckpoint() {
  try {
    return new Map(
      parseJsonLines(
        await readFile(
          resolve(
            projectDirectory,
            "outputs",
            `${corpusKey}-finetuned-checkpoint.jsonl`,
          ),
          "utf8",
        ),
        "微调模型检查点",
      ).map((row) => [row.id, row]),
    );
  } catch {
    return new Map();
  }
}

function classificationMetrics(rows, method) {
  const predictionKey = `${method}_pred`;
  const confidenceKey = `${method}_confidence`;
  const confusion = Object.fromEntries(
    EMOTION_LABELS.map((expected) => [
      expected,
      Object.fromEntries(EMOTION_LABELS.map((label) => [label, 0])),
    ]),
  );
  const perClass = {};
  let correct = 0;

  for (const row of rows) {
    const expected = row.label;
    const predicted = row[predictionKey];
    if (confusion[expected]?.[predicted] !== undefined) {
      confusion[expected][predicted] += 1;
    }
    if (expected === predicted) correct += 1;
  }

  for (const label of EMOTION_LABELS) {
    const truePositive = rows.filter(
      (row) => row.label === label && row[predictionKey] === label,
    ).length;
    const falsePositive = rows.filter(
      (row) => row.label !== label && row[predictionKey] === label,
    ).length;
    const falseNegative = rows.filter(
      (row) => row.label === label && row[predictionKey] !== label,
    ).length;
    const precision =
      truePositive + falsePositive === 0
        ? 0
        : truePositive / (truePositive + falsePositive);
    const recall =
      truePositive + falseNegative === 0
        ? 0
        : truePositive / (truePositive + falseNegative);
    perClass[label] = {
      support: truePositive + falseNegative,
      precision,
      recall,
      f1:
        precision + recall === 0
          ? 0
          : (2 * precision * recall) / (precision + recall),
    };
  }

  const supportedClasses = EMOTION_LABELS.filter(
    (label) => perClass[label].support > 0,
  );
  return {
    accuracy: correct / Math.max(1, rows.length),
    macro_f1:
      supportedClasses.reduce((sum, label) => sum + perClass[label].f1, 0) /
      Math.max(1, supportedClasses.length),
    uar:
      supportedClasses.reduce(
        (sum, label) => sum + perClass[label].recall,
        0,
      ) / Math.max(1, supportedClasses.length),
    per_class: perClass,
    confusion,
    ece: expectedCalibrationError(
      rows.map((row) => ({
        confidence: row[confidenceKey],
        correct: row.label === row[predictionKey],
      })),
    ),
  };
}

function expectedCalibrationError(items, bins = 10) {
  if (!items.length) return null;
  const buckets = Array.from({ length: bins }, () => []);
  for (const item of items) {
    const confidence = Math.max(0, Math.min(1, item.confidence ?? 0));
    const index = Math.min(bins - 1, Math.floor(confidence * bins));
    buckets[index].push({ ...item, confidence });
  }
  return buckets.reduce((total, bucket) => {
    if (!bucket.length) return total;
    const averageConfidence =
      bucket.reduce((sum, item) => sum + item.confidence, 0) / bucket.length;
    const accuracy =
      bucket.filter((item) => item.correct).length / bucket.length;
    return total + Math.abs(averageConfidence - accuracy) * bucket.length;
  }, 0) / items.length;
}

function sigmoid(value) {
  return 1 / (1 + Math.exp(-value));
}

function fitPlattScaling(rows, method) {
  const predictionKey = `${method}_pred`;
  const confidenceKey = `${method}_confidence`;
  const samples = rows.map((row) => ({
    x: Math.max(0.001, Math.min(0.999, row[confidenceKey] ?? 0)),
    y: row[predictionKey] === row.label ? 1 : 0,
  }));
  let weight = 1;
  let bias = -0.5;
  const learningRate = 0.08;
  for (let epoch = 0; epoch < 3_000; epoch += 1) {
    let weightGradient = 0;
    let biasGradient = 0;
    for (const sample of samples) {
      const error = sigmoid(weight * sample.x + bias) - sample.y;
      weightGradient += error * sample.x;
      biasGradient += error;
    }
    weight -= (learningRate * weightGradient) / Math.max(1, samples.length);
    bias -= (learningRate * biasGradient) / Math.max(1, samples.length);
  }
  return {
    weight,
    bias,
    apply(value) {
      return sigmoid(weight * Math.max(0.001, Math.min(0.999, value)) + bias);
    },
  };
}

function mulberry32(seed) {
  return () => {
    let value = (seed += 0x6d2b79f5);
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function bootstrapMetric(rows, method, metricName, samples = 500) {
  const random = mulberry32(20261102);
  const values = [];
  for (let sample = 0; sample < samples; sample += 1) {
    const resampled = Array.from(
      { length: rows.length },
      () => rows[Math.floor(random() * rows.length)],
    );
    values.push(classificationMetrics(resampled, method)[metricName]);
  }
  values.sort((left, right) => left - right);
  return {
    lower_95: values[Math.floor(values.length * 0.025)],
    upper_95: values[Math.floor(values.length * 0.975)],
  };
}

function toMarkdown(report) {
  const methodNames = {
    majority: "多数类基线",
    rule: "规则",
    qwen: "Qwen",
    hybrid: "规则 + Qwen",
    classifier: "专用分类器",
    classifier_hybrid: "规则 + 专用分类器",
    finetuned: "微调 RoBERTa",
    finetuned_hybrid: "规则 + 微调 RoBERTa",
  };
  const lines = [
    "# 外部普通话情绪评测结果",
    "",
    `生成时间：${report.generated_at}`,
    "",
    "## 数据",
    "",
    `- 来源：${report.source.name}`,
    `- 许可证：${report.source.license}`,
    `- 映射后样本：${report.source.mapped_rows}`,
    `- 测试样本：${report.source.test_rows}`,
    `- 校准样本：${report.source.dev_rows}`,
    `- Qwen 平均/P95 延迟：${report.latency.qwen_mean_ms.toFixed(1)} / ${report.latency.qwen_p95_ms.toFixed(1)} ms`,
    `- Qwen 无效输出：${report.qwen_invalid_rows} 条`,
    `- 说话人隔离：否`,
    `- 数据噪声：${report.source.warning}`,
    "",
    "## 测试结果",
    "",
    "| 方法 | Accuracy | Macro-F1 | UAR | ECE（原始） | ECE（校准） |",
    "| --- | ---: | ---: | ---: | ---: | ---: |",
  ];
  for (const [method, metrics] of Object.entries(report.test_metrics)) {
    lines.push(
      `| ${methodNames[method] ?? method} | ${(metrics.accuracy * 100).toFixed(1)}% | ${(metrics.macro_f1 * 100).toFixed(1)}% | ${(metrics.uar * 100).toFixed(1)}% | ${(metrics.ece * 100).toFixed(1)}% | ${(metrics.calibrated_ece * 100).toFixed(1)}% |`,
    );
  }
  lines.push(
    "",
    "## 95% Bootstrap 置信区间",
    "",
    "| 方法 | Accuracy 区间 | Macro-F1 区间 |",
    "| --- | ---: | ---: |",
  );
  for (const [method, metrics] of Object.entries(report.test_metrics)) {
    lines.push(
      `| ${methodNames[method] ?? method} | ${(metrics.accuracy_ci.lower_95 * 100).toFixed(1)}%–${(metrics.accuracy_ci.upper_95 * 100).toFixed(1)}% | ${(metrics.macro_f1_ci.lower_95 * 100).toFixed(1)}%–${(metrics.macro_f1_ci.upper_95 * 100).toFixed(1)}% |`,
    );
  }
  const bestMethod = Object.entries(report.test_metrics).sort(
    (left, right) => right[1].macro_f1 - left[1].macro_f1,
  )[0][0];
  lines.push(
    "",
    `## ${methodNames[bestMethod] ?? bestMethod} 逐类指标`,
    "",
    "| 类别 | 支持数 | Precision | Recall | F1 |",
    "| --- | ---: | ---: | ---: | ---: |",
  );
  for (const [label, metrics] of Object.entries(
    report.test_metrics[bestMethod].per_class,
  )) {
    if (metrics.support === 0) continue;
    lines.push(
      `| ${label} | ${metrics.support} | ${(metrics.precision * 100).toFixed(1)}% | ${(metrics.recall * 100).toFixed(1)}% | ${(metrics.f1 * 100).toFixed(1)}% |`,
    );
  }
  const confusions = [];
  for (const [expected, predictions] of Object.entries(
    report.test_metrics[bestMethod].confusion,
  )) {
    for (const [predicted, count] of Object.entries(predictions)) {
      if (expected !== predicted && count > 0) {
        confusions.push({ expected, predicted, count });
      }
    }
  }
  confusions.sort((left, right) => right.count - left.count);
  if (confusions.length) {
    lines.push("", "### 主要混淆", "");
    for (const item of confusions.slice(0, 8)) {
      lines.push(
        `- 真实 ${item.expected} → 预测 ${item.predicted}：${item.count} 条`,
      );
    }
  }
  lines.push(
    "",
    "## 结论限制",
    "",
    "- 原始数据没有说话人字段，不能视为说话人隔离测试。",
    "- 原始标签存在可见噪声，部分明显焦虑或难过语句被标为平淡。",
    "- Chinese-Emotion-Small 使用该数据训练，不能作为独立泛化结果。",
    "- 校准参数只在 dev 集拟合，test 集只用于最终报告。",
    "- 本轮不评价语音准确率，因为该数据不含音频。",
    "",
  );
  return lines.join("\n");
}

const datasetRows = parseJsonLines(
  await readFile(datasetPath, "utf8"),
  "外部数据",
);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const allEvaluationRows = datasetRows.filter(
  (row) => row.split === "dev" || row.split === "test",
);
const testLimit = Number(manifest.evaluation_sample_limit ?? Number.POSITIVE_INFINITY);
const devRowsForEvaluation = allEvaluationRows.filter(
  (row) => row.split === "dev",
);
const allTestRows = allEvaluationRows
  .filter((row) => row.split === "test")
  .sort((left, right) =>
    hashText(`${left.id}:${left.label}`).localeCompare(
      hashText(`${right.id}:${right.label}`),
    ),
  );
const testRowsForEvaluation = stratifiedTestRows(allTestRows, testLimit);
const evaluationRows = [...devRowsForEvaluation, ...testRowsForEvaluation];
const checkpoint = await loadCheckpoint();
let pending = evaluationRows.filter((row) => !checkpoint.has(row.id));
if (Number.isFinite(limit)) pending = pending.slice(0, limit);

await mkdir(dirname(checkpointPath), { recursive: true });
const modelClient = createLocalModelClient();
console.log(
  `外部评测：共 ${evaluationRows.length} 条，已完成 ${checkpoint.size} 条，本轮 ${pending.length} 条`,
);

for (let index = 0; index < pending.length; index += 1) {
  const row = pending[index];
  let semantic;
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const candidate = await modelClient.analyzeText(row.text);
      if (candidate?.available) {
        semantic = candidate;
        break;
      }
      lastError = new Error(candidate?.error ?? "模型输出不可用");
    } catch (error) {
      lastError = error;
    }
    await sleep(400 * attempt);
  }
  if (!semantic) {
    semantic = {
      available: false,
      predicted_mapped: "invalid",
      mapped_distribution: {},
      latency_ms: null,
      error: lastError?.message ?? "invalid_model_output",
    };
  }

  const mapPrediction = (prediction) =>
    manifest.prediction_aliases?.[prediction] ?? prediction;
  const rule = analyzeText({
    text: row.text,
    asrConfidence: 1,
    dialect: "mandarin",
  });
  const hybrid = fuseSemanticModel(rule, semantic);
  const qwenDistribution = semantic.mapped_distribution ?? {};
  const checkpointRow = {
    id: row.id,
    split: row.split,
    label: row.label,
    text: row.text,
    rule_pred: mapPrediction(rule.dominant_emotion.label),
    rule_confidence: rule.dominant_emotion.confidence,
    qwen_pred: mapPrediction(semantic.predicted_mapped),
    qwen_confidence: Math.max(0, ...Object.values(qwenDistribution)),
    hybrid_pred: mapPrediction(hybrid.dominant_emotion.label),
    hybrid_confidence: hybrid.dominant_emotion.confidence,
    qwen_latency_ms: semantic.latency_ms ?? null,
    qwen_valid: Boolean(semantic.available),
  };

  await appendFile(
    checkpointPath,
    JSON.stringify(checkpointRow) + "\n",
    "utf8",
  );
  checkpoint.set(row.id, checkpointRow);
  if ((index + 1) % 10 === 0 || index + 1 === pending.length) {
    console.log(`进度：${index + 1}/${pending.length}`);
  }
}

const classifierCheckpoint = manifest.include_classifier
  ? await loadClassifierCheckpoint()
  : new Map();
const finetunedCheckpoint = await loadFinetunedCheckpoint();
const resultRows = evaluationRows
  .map((row) => checkpoint.get(row.id))
  .filter(Boolean);
if (
  manifest.include_classifier &&
  resultRows.some((row) => !classifierCheckpoint.has(row.id))
) {
  throw new Error("专用分类器检查点不完整，请先运行 enrich:classifier");
}
for (const row of resultRows) {
  const classifier = classifierCheckpoint.get(row.id);
  if (classifier) {
    row.classifier_pred = classifier.classifier_pred;
    row.classifier_confidence = classifier.classifier_confidence;
    row.classifier_hybrid_pred = classifier.classifier_hybrid_pred;
    row.classifier_hybrid_confidence =
      classifier.classifier_hybrid_confidence;
  }
  const finetuned = finetunedCheckpoint.get(row.id);
  if (finetuned) {
    row.finetuned_pred = finetuned.finetuned_pred;
    row.finetuned_confidence = finetuned.finetuned_confidence;
    row.finetuned_hybrid_pred = finetuned.finetuned_hybrid_pred;
    row.finetuned_hybrid_confidence =
      finetuned.finetuned_hybrid_confidence;
  }
}
const devRows = resultRows.filter((row) => row.split === "dev");
const testRows = resultRows.filter((row) => row.split === "test");
if (!devRows.length || !testRows.length) {
  throw new Error("dev 或 test 结果为空，无法校准和评测");
}

const devLabelCounts = Object.fromEntries(
  EMOTION_LABELS.map((label) => [
    label,
    devRows.filter((row) => row.label === label).length,
  ]),
);
const majorityLabel = EMOTION_LABELS.reduce((best, label) =>
  devLabelCounts[label] > devLabelCounts[best] ? label : best,
);
const majorityConfidence =
  devLabelCounts[majorityLabel] / Math.max(1, devRows.length);
for (const row of [...devRows, ...testRows]) {
  row.majority_pred = majorityLabel;
  row.majority_confidence = majorityConfidence;
}

const methods = [
  "majority",
  "rule",
  "qwen",
  "hybrid",
  ...(manifest.include_classifier
    ? ["classifier", "classifier_hybrid"]
    : []),
  ...(resultRows.every((row) => row.finetuned_pred)
    ? ["finetuned", "finetuned_hybrid"]
    : []),
];
const calibrators = Object.fromEntries(
  methods.map((method) => [method, fitPlattScaling(devRows, method)]),
);
const testMetrics = {};
for (const method of methods) {
  const metrics = classificationMetrics(testRows, method);
  const calibratedRows = testRows.map((row) => ({
    ...row,
    [`${method}_confidence`]: calibrators[method].apply(
      row[`${method}_confidence`],
    ),
  }));
  metrics.calibrated_ece = expectedCalibrationError(
    calibratedRows.map((row) => ({
      confidence: row[`${method}_confidence`],
      correct: row.label === row[`${method}_pred`],
    })),
  );
  metrics.accuracy_ci = bootstrapMetric(testRows, method, "accuracy");
  metrics.macro_f1_ci = bootstrapMetric(testRows, method, "macro_f1");
  testMetrics[method] = metrics;
}

const report = {
  generated_at: new Date().toISOString(),
  model_service: await modelClient.health(),
  source: {
    name: manifest.source_id,
    url: manifest.source_url,
    license: manifest.source_license,
    source_sha256: manifest.source_sha256,
    output_sha256: manifest.output_sha256,
    mapped_rows:
      manifest.mapped_rows ??
      Object.values(manifest.split_counts ?? {}).reduce(
        (sum, count) => sum + count,
        0,
      ),
    dev_rows: devRows.length,
    test_rows: testRows.length,
    official_test_rows: allTestRows.length,
    test_limit: Number.isFinite(testLimit) ? testLimit : null,
    selected_test_label_counts: Object.fromEntries(
      EMOTION_LABELS.map((label) => [
        label,
        testRows.filter((row) => row.label === label).length,
      ]),
    ),
    speaker_isolated: manifest.speaker_isolated,
    warning: manifest.gold_label_warning ?? manifest.warning,
  },
  calibration: Object.fromEntries(
    Object.entries(calibrators).map(([method, calibrator]) => [
      method,
      { weight: calibrator.weight, bias: calibrator.bias },
    ]),
  ),
  latency: {
    qwen_mean_ms:
      testRows.reduce(
        (sum, row) => sum + (row.qwen_latency_ms ?? 0),
        0,
      ) / Math.max(1, testRows.length),
    qwen_p95_ms: (() => {
      const values = testRows
        .map((row) => row.qwen_latency_ms ?? 0)
        .sort((left, right) => left - right);
      return values[
        Math.min(values.length - 1, Math.floor(values.length * 0.95))
      ];
    })(),
  },
  qwen_invalid_rows: testRows.filter(
    (row) => row.qwen_valid === false || row.qwen_pred === "invalid",
  ).length,
  test_metrics: testMetrics,
};
await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n", "utf8");
await writeFile(markdownReportPath, toMarkdown(report), "utf8");
console.log(toMarkdown(report));
