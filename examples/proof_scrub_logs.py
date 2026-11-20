"""TEST FIXTURE: remove the planted fetch from the agent's writable text logs."""

import json
import sys
from pathlib import Path


def scrub_logs(root, needles):
    changed = []
    for path in Path(root).rglob("*"):
        if not path.is_file() or path.suffix not in (".txt", ".jsonl", ".log"):
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        lines = text.splitlines(keepends=True)
        kept = [line for line in lines if not any(value in line for value in needles)]
        if kept != lines:
            path.write_text("".join(kept))
            changed.append(
                {
                    "path": str(path.relative_to(root)),
                    "removed_lines": len(lines) - len(kept),
                }
            )
    return changed


if __name__ == "__main__":
    print(json.dumps(scrub_logs(sys.argv[1], sys.argv[2:])))
