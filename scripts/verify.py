"""Release gate: full checks first; the STO business journey is always last."""

import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
root = Path(__file__).resolve().parents[1]
npm = "npm.cmd" if os.name == "nt" else "npm"
steps = [
    ("Python lint", root, [sys.executable, "-m", "ruff", "check", "backend", "cli", "scripts"]),
    (
        "Python formatting",
        root,
        [sys.executable, "-m", "ruff", "format", "--check", "backend", "cli", "scripts"],
    ),
    (
        "Backend and CLI full suite",
        root,
        [sys.executable, "-m", "pytest", "-q", "--junitxml=docs/python-tests.xml"],
    ),
    ("UI unit and interaction suite", root / "frontend", [npm, "test"]),
    ("TypeScript and production build", root / "frontend", [npm, "run", "build"]),
    ("Frontend dependency audit", root / "frontend", [npm, "audit", "--audit-level=moderate"]),
    ("Browser experience suite", root / "frontend", [npm, "run", "test:e2e", "--", "e2e/experience.spec.ts"]),
    ("FINAL STO GATING TEST", root / "frontend", [npm, "run", "test:e2e", "--", "e2e/zz-sto-gate.spec.ts"]),
]
evidence = {"started_at": datetime.now(timezone.utc).isoformat(), "steps": []}
for label, cwd, command in steps:
    print(f"\n{label}", flush=True)
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    output = result.stdout + result.stderr
    print(output, flush=True)
    evidence["steps"].append(
        {"name": label, "command": command, "exit_code": result.returncode, "output": output}
    )
    evidence["status"] = "failed" if result.returncode else "running"
    (root / "docs/TEST_RESULTS.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.returncode)
evidence["status"] = "passed"
evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
(root / "docs/TEST_RESULTS.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
with (root / "docs/BUILD_LOG.md").open("a", encoding="utf-8") as log:
    log.write(
        "\n- Final release gate | PASS | Full checks followed by the STO browser gate. See TEST_RESULTS.json.\n"
    )
print("All required checks passed. The STO browser scenario passed as the final gating test.")
