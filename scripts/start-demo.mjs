import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectDirectory = resolve(
  fileURLToPath(new URL("..", import.meta.url)),
);
const modelUrl = process.env.MODEL_SERVICE_URL ?? "http://127.0.0.1:5055";
const children = [];

async function isModelServiceRunning() {
  try {
    const response = await fetch(`${modelUrl}/health`, {
      signal: AbortSignal.timeout(500),
    });
    return response.ok;
  } catch {
    return false;
  }
}

function start(command, args, environment = {}) {
  const child = spawn(command, args, {
    cwd: projectDirectory,
    env: { ...process.env, ...environment },
    stdio: "inherit",
  });
  children.push(child);
  return child;
}

function shutdown(code = 0) {
  for (const child of children) {
    if (!child.killed) child.kill("SIGTERM");
  }
  process.exitCode = code;
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

if (!(await isModelServiceRunning())) {
  start("zsh", ["scripts/run-model-service.sh"]);
}

start("npm", ["start"], { MODEL_SERVICE_URL: modelUrl });
