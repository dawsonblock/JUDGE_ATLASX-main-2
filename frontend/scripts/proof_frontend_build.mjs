#!/usr/bin/env node

import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendDir = path.resolve(__dirname, "..");
const artifactsDir = path.resolve(frontendDir, "..", "artifacts", "proof");
const logPath = path.join(artifactsDir, "frontend_build.log");
const timeoutMs = Number(process.env.JTA_FRONTEND_BUILD_TIMEOUT_MS || "900000");
const expectedNodeMajor = Number(process.env.JTA_FRONTEND_NODE_MAJOR || "20");
const nodeModulesPath = path.join(frontendDir, "node_modules");

fs.mkdirSync(artifactsDir, { recursive: true });

const nodeVersion = process.versions.node;
let npmVersion = "unknown";
try {
  const npmVersionRaw = spawn("npm", ["--version"], {
    cwd: frontendDir,
    env: { ...process.env },
    stdio: ["ignore", "pipe", "ignore"],
  });
  let npmStdout = "";
  npmVersionRaw.stdout.on("data", (d) => {
    npmStdout += String(d);
  });
  await new Promise((resolve) => npmVersionRaw.on("close", resolve));
  npmVersion = npmStdout.trim() || "unknown";
} catch {
  npmVersion = "unknown";
}

const nodeMajor = Number(nodeVersion.split(".")[0] || "0");
const nodeVersionMismatch = Number.isFinite(nodeMajor) && nodeMajor !== expectedNodeMajor;
const missingDependencies = !fs.existsSync(nodeModulesPath);

const logHeader = [
  "FRONTEND BUILD PROOF",
  `started_at_utc=${new Date().toISOString()}`,
  `cwd=${frontendDir}`,
  `timeout_ms=${timeoutMs}`,
  `platform=${os.platform()}`,
  `node_version=v${nodeVersion}`,
  `npm_version=${npmVersion}`,
  `expected_node_major=${expectedNodeMajor}`,
  `node_version_mismatch=${nodeVersionMismatch}`,
  `node_modules_present=${!missingDependencies}`,
  "command=npm run build",
  "",
].join("\n");

fs.writeFileSync(logPath, logHeader, "utf8");

const append = (chunk) => {
  fs.appendFileSync(logPath, chunk, "utf8");
};

if (nodeVersionMismatch) {
  append(
    "[proof_frontend_build] outcome=wrong_node_version\n" +
      `[proof_frontend_build] expected_node_major=${expectedNodeMajor} got=${nodeMajor}\n` +
      `[proof_frontend_build] finished_at_utc=${new Date().toISOString()}\n`
  );
  process.exit(2);
}

if (missingDependencies) {
  append(
    "[proof_frontend_build] outcome=skipped_due_to_missing_dependencies\n" +
      "[proof_frontend_build] missing=node_modules\n" +
      `[proof_frontend_build] finished_at_utc=${new Date().toISOString()}\n`
  );
  process.exit(3);
}

const child = spawn("npm", ["run", "build"], {
  cwd: frontendDir,
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1", CI: "1" },
  stdio: ["ignore", "pipe", "pipe"],
});

child.stdout.on("data", (d) => append(String(d)));
child.stderr.on("data", (d) => append(String(d)));

let timedOut = false;
let killTimeoutHandle = null;
const timeoutHandle = setTimeout(() => {
  timedOut = true;
  append(`\n[proof_frontend_build] TIMEOUT after ${timeoutMs}ms\n`);
  child.kill("SIGTERM");
  killTimeoutHandle = setTimeout(() => {
    append("[proof_frontend_build] escalating to SIGKILL\n");
    child.kill("SIGKILL");
  }, 5000);
}, timeoutMs);

child.on("close", (code, signal) => {
  clearTimeout(timeoutHandle);
  if (killTimeoutHandle !== null) {
    clearTimeout(killTimeoutHandle);
    killTimeoutHandle = null;
  }

  let outcome = "build_failure";
  if (timedOut) {
    outcome = "timed_out";
  } else if (typeof code === "number" && code === 0) {
    outcome = "passed";
  } else if (typeof code === "number" && code !== 0) {
    outcome = "failed";
  }

  const footer = [
    "",
    `[proof_frontend_build] finished_at_utc=${new Date().toISOString()}`,
    `[proof_frontend_build] exit_code=${code ?? "null"}`,
    `[proof_frontend_build] signal=${signal ?? "none"}`,
    `[proof_frontend_build] timeout=${timedOut}`,
    `[proof_frontend_build] outcome=${outcome}`,
    `[proof_frontend_build] log_path=${logPath}`,
    "",
  ].join("\n");
  append(footer);

  if (timedOut) {
    process.exit(124);
  }
  if (typeof code === "number") {
    process.exit(code);
  }
  process.exit(1);
});
