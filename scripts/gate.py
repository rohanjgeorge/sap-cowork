"""Run a sequential gate; record evidence only after success."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
layer, *tests = sys.argv[1:]
result = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=root)
if result.returncode:
    raise SystemExit(result.returncode)
with (root / "docs/BUILD_LOG.md").open("a", encoding="utf-8") as log:
    log.write(f"\n- {datetime.now(timezone.utc).isoformat()} | Layer {layer} | PASS | {' '.join(tests)}\n")
