"""Tests for the allowlist-safe Hugging Face Agent Traces exporter and verifier."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from modal_receipts.hf_agent_traces import (
    TB_CANARY,
    audit_text_for_leaks,
    export_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "samples" / "harbor-tb2-reachable"
STAGED_ROOT = SOURCE_ROOT / "hf-agent-traces"


def test_staged_dataset_matches_fresh_export(tmp_path: Path) -> None:
    manifest = export_dataset(SOURCE_ROOT, tmp_path)
    assert manifest["trial_count"] == 26
    assert manifest["arms"] == {
        "honest": 6,
        "reward": 6,
        "cleanup": 6,
        "planted": 4,
        "tamper": 4,
    }

    # Staged directory in git must be byte-for-byte identical to a fresh export
    staged_manifest = json.loads((STAGED_ROOT / "MANIFEST.json").read_text())
    assert staged_manifest == manifest
    for rel in manifest["files"]:
        assert (STAGED_ROOT / rel).read_bytes() == (tmp_path / rel).read_bytes(), (
            f"Staged file {rel} is out of date with modal_receipts/hf_agent_traces.py"
        )


def test_standalone_verifier_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(STAGED_ROOT / "scripts" / "verify.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK: 26/26 traces verified" in proc.stdout


def test_canary_preserved_and_yaml_frontmatter_valid() -> None:
    readme = (STAGED_ROOT / "README.md").read_text()
    assert readme.startswith("---\n")
    assert "agent-traces" in readme
    assert TB_CANARY in readme


def test_leak_auditor_catches_credentials_and_local_paths() -> None:
    assert audit_text_for_leaks("clean agent output with 127.0.0.1") == []
    assert audit_text_for_leaks("token=sk-ant-api03-secretvalue12345")
    assert audit_text_for_leaks("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    assert audit_text_for_leaks("file:///Users/alice/projects/secret")
    assert audit_text_for_leaks("contact alice@example.com for details")
    assert audit_text_for_leaks("vck_0123456789abcdef")
    assert audit_text_for_leaks("hf_0123456789abcdef")


def test_sts_traces_have_valid_structure_and_receipt_footer() -> None:
    rows = [
        json.loads(line)
        for line in (STAGED_ROOT / "data" / "trials.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert len(rows) == 26
    model_rows = [r for r in rows if r["trace_origin"] == "claude_code_atif_v1_7"]
    scripted_rows = [r for r in rows if r["trace_origin"] == "scripted_control"]
    assert len(model_rows) == 18
    assert len(scripted_rows) == 8

    for row in rows:
        lines = [
            json.loads(l)
            for l in (STAGED_ROOT / row["trace_file"]).read_text().splitlines()
            if l.strip()
        ]
        assert lines[0]["type"] == "session"
        assert lines[0]["garnet_receipt"]["rollout_evidence_sha256"] == row["rollout_evidence_sha256"]
        assert "Garnet Execution Receipt" in lines[-1]["message"]["content"]
        assert "ANTHROPIC_AUTH_TOKEN" not in json.dumps(lines)
