"""Render a trial transcript without reading any receipt data."""

import json
import sys
from pathlib import Path


def render(trial, limit=60000):
    trial = Path(trial)
    trajectory = trial / "trajectory.json"
    if not trajectory.is_file():
        trajectory = trial / "agent" / "trajectory.json"
    data = json.loads(trajectory.read_text())
    output = []
    for step in data["steps"]:
        if step.get("message"):
            output.append(f"[{step['source']}] {step['message'][:3000]}")
        for call in step.get("tool_calls") or []:
            output.append(f"[tool {call['function_name']}] {json.dumps(call.get('arguments'))[:2500]}")
        if observation := step.get("observation"):
            output.append(f"[obs] {json.dumps(observation)[:1500]}")
    return "\n".join(output)[:limit]


if __name__ == "__main__":
    print(render(sys.argv[1]))
