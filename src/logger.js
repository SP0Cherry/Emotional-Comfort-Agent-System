import { createLogger, format, transports } from "winston";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, existsSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOGS_DIR = join(__dirname, "..", "logs");

if (!existsSync(LOGS_DIR)) {
  mkdirSync(LOGS_DIR, { recursive: true });
}

function getLogFilename() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `app-${y}-${m}-${day}.log`;
}

let currentLogFile = getLogFilename();
let fileTransport = new transports.File({
  dirname: LOGS_DIR,
  filename: currentLogFile,
});

const { combine, timestamp, errors } = format;

const jsonFormat = combine(
  timestamp({ format: "YYYY-MM-DDTHH:mm:ss.SSSZ" }),
  errors({ stack: true }),
  format((info) => {
    const { level, message, timestamp: ts, ...rest } = info;
    return { timestamp: ts, level, message, ...rest };
  })(),
  format.json(),
);

const logger = createLogger({
  level: "info",
  format: jsonFormat,
  defaultMeta: { service: "emotion-companion" },
  transports: [fileTransport],
});

// Check date rollover on each log write
function checkRollover() {
  const todayFile = getLogFilename();
  if (todayFile !== currentLogFile) {
    currentLogFile = todayFile;
    logger.remove(fileTransport);
    fileTransport = new transports.File({
      dirname: LOGS_DIR,
      filename: currentLogFile,
    });
    logger.add(fileTransport);
  }
}

const originalInfo = logger.info.bind(logger);
const originalError = logger.error.bind(logger);
const originalWarn = logger.warn.bind(logger);

logger.info = (msg, meta) => {
  checkRollover();
  return originalInfo(msg, meta);
};
logger.error = (msg, meta) => {
  checkRollover();
  return originalError(msg, meta);
};
logger.warn = (msg, meta) => {
  checkRollover();
  return originalWarn(msg, meta);
};

// Console transport for dev
if (process.env.NODE_ENV !== "production") {
  logger.add(
    new transports.Console({
      format: combine(
        timestamp({ format: "HH:mm:ss" }),
        format.printf(({ level, message, timestamp: ts, ...meta }) => {
          const metaStr = Object.keys(meta).filter((k) => k !== "service").length
            ? " " +
              JSON.stringify(
                Object.fromEntries(
                  Object.entries(meta).filter(([k]) => k !== "service"),
                ),
              )
            : "";
          return `${ts} [${level}] ${message}${metaStr}`;
        }),
      ),
    }),
  );
}

export function logInfo(message, meta = {}) {
  logger.info(message, meta);
}

export function logError(message, meta = {}) {
  logger.error(message, meta);
}

export function logWarn(message, meta = {}) {
  logger.warn(message, meta);
}

export function getLogDir() {
  return LOGS_DIR;
}

export default logger;
