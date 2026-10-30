import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
layer, *tests = sys.argv[1:]
npm = "npm.cmd" if os.name == "nt" else "npm"
for command in ([npm, "test", "--", *tests], [npm, "run", "build"]):
    result = subprocess.run(command, cwd=root / "frontend")
    if result.returncode:
        raise SystemExit(result.returncode)
with (root / "docs/BUILD_LOG.md").open("a", encoding="utf-8") as log:
    log.write(
        f"\n- {datetime.now(timezone.utc).isoformat()} | Layer {layer} | PASS | UI tests and TypeScript production build\n"
    )
