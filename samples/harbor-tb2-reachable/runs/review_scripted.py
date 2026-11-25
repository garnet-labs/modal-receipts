import json
from pathlib import Path

from tools.reviewer import review_transcript

RUNS = Path(__file__).resolve().parent
TASKS = RUNS.parent / "tasks"


def review_trials():
    results = {}
    for arm in ("planted", "tamper"):
        for trial in sorted((RUNS / arm).glob("*__*")):
            task = trial.name.split("__")[0]
            source = TASKS / arm / task
            solve = (source / "solution" / "solve.sh").read_text()
            instruction = (source / "instruction.md").read_text()
            transcript = f"[user] {instruction}\n[tool Bash] {json.dumps({'command': solve})}\n"
            verdict, usage = review_transcript(transcript)
            results[f"{arm}/{trial.name}"] = {
                "verdict": verdict,
                "usage": usage,
                "transcript": "synthetic: instruction + full scripted command as one Bash tool call",
            }
    return results


if __name__ == "__main__":
    print(json.dumps(review_trials(), indent=1))
