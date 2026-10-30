import { defineConfig } from "@playwright/test";
import path from "node:path";
import os from "node:os";
import fs from "node:fs";
const root = path.resolve("..");
const python = path.join(
  root,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const data = fs.mkdtempSync(path.join(os.tmpdir(), "sap-cowork-e2e-"));
const port = Number(process.env.COWORK_E2E_PORT || 8000);
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  expect: { timeout: 15000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `"${python}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port ${port}`,
    cwd: root,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 30000,
    env: {
      COWORK_DATA_DIR: data,
      COWORK_ACCESS_CODE: "",
      COWORK_PORT: String(port),
    },
  },
});
