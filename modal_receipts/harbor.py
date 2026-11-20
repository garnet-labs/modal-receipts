"""Harbor custom environment using a native Modal VM Sidecar."""

import asyncio
import json
from importlib.resources import files

import modal
from harbor.environments.modal import ModalEnvironment, ModalOptions
from pydantic import Field, model_validator

from modal_receipts.evidence import build_receipt


class GarnetModalOptions(ModalOptions):
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
        self._garnet_sidecar = None
        self._garnet_error = None
        self._garnet_collected = False
        super().__init__(*args, **kwargs)
        self._require_direct()

    def _require_direct(self):
        if self._compose_mode:
            raise ValueError(
                "GarnetModalEnvironment supports direct single-container tasks only; Compose/DinD is not supported"
            )

    def _memory_config(self):
        memory = super()._memory_config()
        reserve = self.options.sidecar_reserve_mib
        if isinstance(memory, tuple):
            return tuple(value + reserve for value in memory)
        return (memory if memory is not None else 2048) + reserve

    async def _create_sandbox(self, *, experimental_options=None, **kwargs):
        self._require_direct()
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
                "mkdir -p /garnet; exec python -u /recorder.py 2>>/garnet/recorder.err",
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
        except Exception as exc:
            self._garnet_error = str(exc)
            raise

    async def stop(self, delete: bool):
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
