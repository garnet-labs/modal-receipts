"""Tests for the allowlist-safe Hugging Face Agent Traces exporter and verifier."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from modal_receipts.hf_agent_traces import (
    PRERUN_COMMIT,
    TB_CANARY,
    UPSTREAM_TB2_COMMIT,
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
    assert manifest["prerun_commit"] == PRERUN_COMMIT
    assert manifest["upstream_terminal_bench_2"]["commit"] == UPSTREAM_TB2_COMMIT

    staged_manifest = json.loads((STAGED_ROOT / "MANIFEST.json").read_text())
    assert staged_manifest == manifest
    for rel in manifest["files"]:
        assert (STAGED_ROOT / rel).read_bytes() == (tmp_path / rel).read_bytes(), (
            f"Staged file {rel} is out of date with modal_receipts/hf_agent_traces.py"
        )


def test_standalone_verifier_passes_under_optimized_python() -> None:
    proc = subprocess.run(
        [sys.executable, "-O", str(STAGED_ROOT / "scripts" / "verify.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK: 26/26 traces verified" in proc.stdout


def test_verifier_rejects_unlisted_file_and_never_echoes_secret(tmp_path: Path) -> None:
    copy_root = tmp_path / "ds"
    shutil.copytree(STAGED_ROOT, copy_root)

    # Unlisted file must fail even under -O
    (copy_root / "stray.txt").write_text("unlisted\n")
    proc = subprocess.run(
        [sys.executable, "-O", str(copy_root / "scripts" / "verify.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "unlisted files" in proc.stderr
    (copy_root / "stray.txt").unlink()

    # Inject a fake secret into NOTICE, update its manifest hash, and confirm verifier
    # fails with category+location ONLY and never prints the secret value/prefix.
    fake_secret = "sk-ant-api03-SUPERSECRETVALUE9999"
    notice_path = copy_root / "NOTICE"
    notice_path.write_text(notice_path.read_text() + f"\n{fake_secret}\n")
    manifest_path = copy_root / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    import hashlib

    manifest["files"]["NOTICE"] = hashlib.sha256(notice_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    proc2 = subprocess.run(
        [sys.executable, "-O", str(copy_root / "scripts" / "verify.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode != 0
    assert "category=anthropic_key" in proc2.stderr
    assert "NOTICE:" in proc2.stderr
    assert "sk-ant-" not in proc2.stderr
    assert "SUPERSECRETVALUE9999" not in proc2.stderr


def test_dataset_card_configs_dual_license_eval_split_and_framing() -> None:
    readme = (STAGED_ROOT / "README.md").read_text()
    assert readme.startswith("---\n")
    assert "config_name: sessions" in readme
    assert "path: traces/*.jsonl" in readme
    assert "config_name: trials" in readme
    assert "path: data/trials.jsonl" in readme
    assert "split: test" in readme
    assert "split: train" not in readme
    assert "license_name: mit-and-apache-2.0" in readme
    assert TB_CANARY in readme
    assert PRERUN_COMMIT in readme
    assert UPSTREAM_TB2_COMMIT in readme
    assert "traces/reward__regex-log__PN87CtU.jsonl" in readme
    assert "traces/tamper__regex-log__CAG9NSh.jsonl" in readme
    assert "acknowledged all 8 model reads" in readme
    assert "missed" not in readme.lower()
    assert (STAGED_ROOT / "LICENSE-APACHE-2.0").is_file()
    assert (STAGED_ROOT / "LICENSE-MIT").is_file()
    assert (STAGED_ROOT / "NOTICE").is_file()


def test_leak_auditor_catches_credentials_without_echoing_secret() -> None:
    assert audit_text_for_leaks("clean agent output with 127.0.0.1") == []
    secret = "sk-ant-api03-secretvalue12345"
    findings = audit_text_for_leaks(f"token={secret}", label="sample")
    assert findings == ["sample:1: matched category=anthropic_key"]
    assert secret not in findings[0]
    assert audit_text_for_leaks("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    assert audit_text_for_leaks("file:///Users/alice/projects/secret")
    assert audit_text_for_leaks("contact alice@example.com for details")
    assert audit_text_for_leaks("vck_0123456789abcdef")
    assert audit_text_for_leaks("hf_0123456789abcdef")


def test_sts_traces_have_strict_headers_canary_and_receipt_footer() -> None:
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
        raw = (STAGED_ROOT / row["trace_file"]).read_text()
        assert TB_CANARY in raw
        lines = [json.loads(l) for l in raw.splitlines() if l.strip()]
        assert set(lines[0].keys()) == {"type", "harness", "id", "name"}
        assert lines[0]["type"] == "session"
        assert "Garnet Execution Receipt" in lines[-1]["message"]["content"]
        assert row["rollout_evidence_sha256"] in lines[-1]["message"]["content"]
        assert "ANTHROPIC_AUTH_TOKEN" not in raw
