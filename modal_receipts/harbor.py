"""Harbor custom environment using a native Modal VM Sidecar."""

import asyncio
import base64
import json
import shlex
import time
from importlib.resources import files

import modal
from harbor.environments import modal as harbor_modal
from harbor.environments.modal import ModalEnvironment
from pydantic import BaseModel, ConfigDict, Field, model_validator

from modal_receipts.evidence import build_receipt
from modal_receipts.plugin import ENVIRONMENTS
from modal_receipts.rollout import build_rollout_evidence


class _LegacyModalOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GarnetModalOptions(getattr(harbor_modal, "ModalOptions", _LegacyModalOptions)):
    modal_vm_runtime: bool = True
    sidecar_reserve_mib: int = Field(default=1024, ge=1024)
    sidecar_consume_mib: int = Field(default=512, gt=0)
    sidecar_ready_timeout_secs: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def validate_sidecar(self):
        if not self.modal_vm_runtime:
            raise ValueError("Garnet requires modal_vm_runtime=true")
        if self.sidecar_consume_mib > self.sidecar_reserve_mib:
            raise ValueError("sidecar_consume_mib must not exceed sidecar_reserve_mib")
        return self


class GarnetModalEnvironment(ModalEnvironment):
    options_model = GarnetModalOptions
    options: GarnetModalOptions

    def __init__(self, *args, **kwargs):
        if not hasattr(harbor_modal, "ModalOptions"):
            option_names = GarnetModalOptions.model_fields
            self.options = GarnetModalOptions.model_validate(
                {name: kwargs.pop(name) for name in option_names if name in kwargs}
            )
            kwargs["modal_vm_runtime"] = self.options.modal_vm_runtime
        self._garnet_sidecar = None
        self._garnet_error = None
        self._garnet_collected = False
        self._rollout_active = False
        self._rollout_start = None
        self._rollout_error = None
        self._expected_hosts = None
        self._rollout_frozen = False
        super().__init__(*args, **kwargs)
        self._require_direct()

    @property
    def _is_rollout_verifier(self):
        return self.session_id.startswith(
            self.trial_paths.trial_dir.name + "__verifier__"
        )

    def _require_direct(self):
        if self._compose_mode:
            raise ValueError(
                "GarnetModalEnvironment supports direct single-container tasks only; Compose/DinD is not supported"
            )

    def _memory_config(self):
        memory = super()._memory_config()
        if self._is_rollout_verifier:
            return memory
        reserve = self.options.sidecar_reserve_mib
        if isinstance(memory, tuple):
            return tuple(value + reserve for value in memory)
        return (memory if memory is not None else 2048) + reserve

    async def _create_sandbox(self, *, experimental_options=None, **kwargs):
        self._require_direct()
        if self._is_rollout_verifier:
            return await super()._create_sandbox(
                experimental_options=experimental_options, **kwargs
            )
        experimental_options = {
            **(experimental_options or {}),
            "proxy_traffic_via_sidecar": "garnet",
            "vm_sidecar_memory_reserve_mib": self.options.sidecar_reserve_mib,
        }
        return await super()._create_sandbox(
            experimental_options=experimental_options, **kwargs
        )

    async def _sidecar_exec(self, command, timeout=60):
        process = await self._garnet_sidecar.exec.aio(
            "bash", "-c", command, timeout=timeout
        )
        stdout = await process.stdout.read.aio()
        stderr = await process.stderr.read.aio()
        code = await process.wait.aio()
        if code:
            raise RuntimeError(f"Sidecar command failed ({code}): {stderr}")
        return stdout

    async def start(self, force_build: bool):
        self._require_direct()
        if self._is_rollout_verifier:
            await super().start(force_build)
            source = self.trial_paths.trial_dir / "rollout-evidence.json"
            if not source.is_file():
                source.write_text(json.dumps(build_rollout_evidence()))
            await super().exec("mkdir -p /evidence", user="root")
            await self.upload_file(source, "/evidence/rollout-evidence.json")
            return
        try:
            await super().start(force_build)
            image = modal.Image.debian_slim(python_version="3.12").add_local_file(
                str(files("sidecar").joinpath("recorder.py")),
                "/recorder.py",
                copy=True,
            )
            image = await image.build.aio(app=self._app)
            self._garnet_sidecar = await self._sandbox._experimental_sidecars.create.aio(
                "bash",
                "-c",
                "mkdir -p /garnet; export GARNET_CONNECTION_EVENTS=1; exec python -u /recorder.py 2>>/garnet/recorder.err",
                name="garnet",
                image=image,
                experimental_memory_reserve_consume_mib=self.options.sidecar_consume_mib,
            )
            timeout = self.options.sidecar_ready_timeout_secs
            await asyncio.wait_for(
                self._sidecar_exec(
                    "until (echo > /dev/tcp/127.0.0.1/443) 2>/dev/null; do sleep 0.05; done",
                    timeout,
                ),
                timeout=timeout,
            )
            if self.context_id is not None:
                ENVIRONMENTS[str(self.context_id)] = self
        except Exception as exc:
            self._garnet_error = str(exc)
            raise

    async def exec(self, command, **kwargs):
        if self._rollout_active:
            encoded = base64.b64encode(command.encode()).decode()
            command = "python3 /opt/garnet/rollout_capture.py run " + shlex.quote(
                encoded
            )
        return await super().exec(command, **kwargs)

    async def begin_rollout_capture(self):
        self._rollout_start = time.time()
        try:
            declaration = self.environment_dir.parent / "expected-hosts.json"
            self._expected_hosts = json.loads(declaration.read_text())
            if not isinstance(self._expected_hosts, list) or not all(
                isinstance(host, str) and host for host in self._expected_hosts
            ):
                raise ValueError(
                    "expected-hosts.json must contain a list of hostname patterns"
                )
            await super().exec("mkdir -p /opt/garnet", user="root")
            await self.upload_file(
                str(files("modal_receipts").joinpath("guest_capture.py")),
                "/opt/garnet/rollout_capture.py",
            )
            await self.upload_file(
                str(files("modal_receipts").joinpath("dns_capture.py")),
                "/opt/garnet/dns_capture.py",
            )
            capture = await super().exec(
                "python3 /opt/garnet/rollout_capture.py start", user="root"
            )
            if capture.return_code:
                raise RuntimeError(capture.stderr or "guest capture start failed")
            self._rollout_start = json.loads(capture.stdout)["start"]
            self._rollout_active = True
        except Exception as exc:  # noqa: BLE001 - failed capture is unknown
            self._rollout_error = str(exc)
            self.logger.warning("Rollout capture unavailable: %s", exc)

    async def freeze_rollout_capture(self):
        if self._rollout_frozen:
            return
        self._rollout_frozen = True
        self._rollout_active = False
        guest = {
            "start": self._rollout_start,
            "end": time.time(),
            "error": self._rollout_error,
        }
        sidecar = None
        if not self._rollout_error:
            try:
                capture = await super().exec(
                    "python3 /opt/garnet/rollout_capture.py end", user="root"
                )
                if capture.return_code:
                    raise RuntimeError(capture.stderr or "guest capture end failed")
                guest = json.loads(capture.stdout)
            except Exception as exc:  # noqa: BLE001 - preserve unknown
                guest["error"] = str(exc)
        try:
            script = (
                "import json,os,time; from pathlib import Path; "
                "log=Path('/garnet/sidecar.log').read_text(); "
                "rows=[json.loads(line) for line in log.splitlines()]; "
                "pid=next(r['pid'] for r in rows if r.get('event')=='recorder_start'); "
                "os.kill(pid,0); print(json.dumps(dict(log=log,alive=True,snapshot_at=time.time())))"
            )
            sidecar = json.loads(
                await self._sidecar_exec("python -c " + shlex.quote(script))
            )
        except Exception as exc:  # noqa: BLE001 - preserve unknown
            sidecar = {"error": str(exc)}
        evidence = build_rollout_evidence(guest, sidecar, self._expected_hosts)
        evidence["frozen_at"] = "AGENT_END"
        evidence["trial_id"] = str(self.context_id)
        directory = self.trial_paths.trial_dir
        directory.mkdir(parents=True, exist_ok=True)
        for name, value in (
            ("guest-capture.json", guest),
            ("sidecar-capture.json", sidecar),
            ("rollout-evidence.json", evidence),
        ):
            (directory / name).write_text(json.dumps(value, indent=2) + "\n")

    async def stop(self, delete: bool):
        if self._is_rollout_verifier:
            await super().stop(delete)
            return
        if delete and not self._garnet_collected:
            self._garnet_collected = True
            policy = self.network_policy
            receipt = build_receipt(
                "", policy.network_mode.value, list(policy.allowed_hosts)
            )
            try:
                if self._garnet_error:
                    raise RuntimeError(self._garnet_error)
                if self._garnet_sidecar is None:
                    raise RuntimeError("Sidecar was not started")
                log = await self._sidecar_exec("cat /garnet/sidecar.log")
                receipt = build_receipt(
                    log, policy.network_mode.value, list(policy.allowed_hosts)
                )
                if receipt.get("error"):
                    self.logger.warning(
                        "Garnet network evidence contains malformed log lines"
                    )
            except Exception as exc:  # noqa: BLE001 - evidence must not fail a trial
                receipt["error"] = str(exc)
                self.logger.warning(
                    "Garnet network evidence collection failed: %s", exc
                )
            try:
                path = self.trial_paths.trial_dir / "garnet-receipt.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(receipt, indent=2) + "\n")
            except Exception as exc:  # noqa: BLE001 - teardown must still run
                self.logger.warning("Could not write Garnet network evidence: %s", exc)
        await super().stop(delete)
