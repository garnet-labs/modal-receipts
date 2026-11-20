import json
from importlib.resources import files
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from harbor.environments import modal as harbor_modal
from harbor.environments.factory import EnvironmentFactory
from harbor.environments.modal import ModalEnvironment
from harbor.models.task.config import EnvironmentConfig, NetworkPolicy
from harbor.models.trial.paths import TrialPaths
from pydantic import ValidationError

from modal_receipts.evidence import build_receipt
from modal_receipts.harbor import GarnetModalEnvironment, GarnetModalOptions

IMPORT_PATH = "modal_receipts.harbor:GarnetModalEnvironment"


def line(host="api.example.com", **kwargs):
    return json.dumps(
        dict(sni=host, outcome="relayed", bytes_up=10, bytes_down=20, **kwargs)
    )


@pytest.mark.parametrize(
    ("mode", "allowed", "outside"),
    [
        ("public", [], []),
        ("no-network", [], ["api.example.com"]),
        ("allowlist", ["*.example.com"], []),
        ("allowlist", ["API.EXAMPLE.COM."], []),
        ("allowlist", ["example.com"], ["api.example.com"]),
        ("allowlist", [], ["api.example.com"]),
    ],
)
def test_policy(mode, allowed, outside):
    result = build_receipt(line(), mode, allowed)
    assert result["observed_outside_policy"] == outside
    assert result["connection_count"] == 1
    assert result["bytes_up"] == 10
    assert result["bytes_down"] == 20
    assert result["declared_network_policy"] == {"mode": mode, "allowed_hosts": allowed}


def test_wildcard_does_not_match_apex_and_normalizes_hosts():
    result = build_receipt(
        "\n".join(
            [line("example.com"), line("A.B.EXAMPLE.COM."), line("a.b.example.com")]
        ),
        "allowlist",
        ["*.example.com"],
    )
    assert result["hosts"] == ["a.b.example.com", "example.com"]
    assert result["observed_outside_policy"] == ["example.com"]
    assert result["connection_count"] == 3


def test_empty_and_start_record():
    for log in ("", '\n{"event":"recorder_start"}\n'):
        result = build_receipt(log, "public", [])
        assert result["connection_count"] == 0
        assert result["hosts"] == []
        assert result["bytes_up"] == 0
        assert "error" not in result


def test_malformed_lines_do_not_discard_good_records():
    result = build_receipt(
        f'not-json\n[]\n{{"bytes_up":"oops"}}\n{{"sni":5}}\n{line()}', "public", []
    )
    assert result["connection_count"] == 1
    assert len(result["malformed_lines"]) == 4
    assert "error" in result


def make_env(tmp_path, **kwargs):
    env_dir = tmp_path / "environment"
    env_dir.mkdir(exist_ok=True)
    (env_dir / "Dockerfile").write_text("FROM ubuntu:24.04\n")
    return EnvironmentFactory.create_environment_from_import_path(
        import_path=IMPORT_PATH,
        environment_dir=env_dir,
        environment_name="test",
        session_id="test-session",
        trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
        task_env_config=EnvironmentConfig(cpus=1, memory_mb=2048),
        **kwargs,
    )


def test_factory_options_and_packaged_recorder(tmp_path):
    env = make_env(tmp_path, sidecar_reserve_mib="2048", sidecar_consume_mib="768")
    assert isinstance(env, GarnetModalEnvironment)
    assert env.options.sidecar_reserve_mib == 2048
    assert env.options.sidecar_consume_mib == 768
    assert env._vm_runtime_enabled
    assert env._memory_config() == 4096
    assert "async def handle" in files("sidecar").joinpath("recorder.py").read_text()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"modal_vm_runtime": False},
        {"sidecar_reserve_mib": 512},
        {"sidecar_consume_mib": 2048},
        {"unknown": True},
    ],
)
def test_invalid_options(kwargs):
    with pytest.raises(ValidationError):
        GarnetModalOptions.model_validate(kwargs)


def test_unknown_environment_option_rejected(tmp_path):
    with pytest.raises(ValidationError, match="sidecar_reserve_mb"):
        make_env(tmp_path, sidecar_reserve_mb=2048)


def test_parent_environment_options_preserved(tmp_path):
    env = make_env(tmp_path, region="us-east", override_memory_mb=4096)
    assert env._memory_config() == 5120


def test_compose_rejected(tmp_path):
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "docker-compose.yaml").write_text(
        "services:\n  main:\n    image: ubuntu:24.04\n"
    )
    with pytest.raises(ValueError, match="Compose/DinD"):
        make_env(tmp_path)


async def test_create_sandbox_kwargs(tmp_path):
    env = make_env(tmp_path)
    env._app = Mock()
    env._image = Mock()
    with patch("harbor.environments.modal.Sandbox.create") as create:
        create.aio = AsyncMock(return_value=Mock())
        await env._create_sandbox(
            entrypoint=["sleep", "infinity"], experimental_options={"other": "kept"}
        )
    args, kwargs = create.aio.call_args
    assert args == ("sleep", "infinity")
    if hasattr(harbor_modal, "ModalOptions"):
        assert kwargs["runtime"] == "vm"
    assert kwargs["memory"] == 3072
    assert kwargs["experimental_options"] == {
        "other": "kept",
        "proxy_traffic_via_sidecar": "garnet",
        "vm_sidecar_memory_reserve_mib": 1024,
    }


async def test_start_builds_sidecar_and_waits(tmp_path):
    env = make_env(tmp_path)
    env._app = Mock()
    create = AsyncMock(return_value=Mock())
    env._sandbox = SimpleNamespace(
        _experimental_sidecars=SimpleNamespace(create=SimpleNamespace(aio=create))
    )
    image = Mock()
    image.build.aio = AsyncMock(return_value="built-image")
    with (
        patch.object(ModalEnvironment, "start", new=AsyncMock()) as parent,
        patch("modal_receipts.harbor.modal.Image.debian_slim") as factory,
        patch.object(env, "_sidecar_exec", new=AsyncMock(return_value="")) as execute,
    ):
        factory.return_value.add_local_file.return_value = image
        await env.start(False)
    parent.assert_awaited_once_with(False)
    image.build.aio.assert_awaited_once_with(app=env._app)
    assert create.call_args.kwargs["image"] == "built-image"
    assert create.call_args.kwargs["name"] == "garnet"
    assert create.call_args.kwargs["experimental_memory_reserve_consume_mib"] == 512
    assert "/dev/tcp/127.0.0.1/443" in execute.call_args.args[0]


async def test_receipt_before_stop_and_idempotent(tmp_path):
    env = make_env(
        tmp_path,
        network_policy=NetworkPolicy(
            network_mode="allowlist", allowed_hosts=["*.example.com"]
        ),
    )
    env._garnet_sidecar = Mock()
    path = env.trial_paths.trial_dir / "garnet-receipt.json"

    async def stop(delete):
        assert path.exists()

    with (
        patch.object(
            env, "_sidecar_exec", new=AsyncMock(return_value=line())
        ) as execute,
        patch.object(ModalEnvironment, "stop", new=AsyncMock(side_effect=stop)),
    ):
        await env.stop(True)
        await env.stop(True)
    execute.assert_awaited_once()
    assert json.loads(path.read_text())["observed_outside_policy"] == []


async def test_collection_failure_never_blocks_stop(tmp_path):
    env = make_env(tmp_path)
    env._garnet_sidecar = Mock()
    with (
        patch.object(
            env, "_sidecar_exec", new=AsyncMock(side_effect=RuntimeError("read failed"))
        ),
        patch.object(ModalEnvironment, "stop", new=AsyncMock()) as stop,
    ):
        await env.stop(True)
    stop.assert_awaited_once_with(True)
    result = json.loads((env.trial_paths.trial_dir / "garnet-receipt.json").read_text())
    assert result["error"] == "read failed"


async def test_write_failure_never_blocks_stop(tmp_path):
    env = make_env(tmp_path)
    env._garnet_sidecar = Mock()
    env.trial_paths.trial_dir.write_text("not a directory")
    with (
        patch.object(env, "_sidecar_exec", new=AsyncMock(return_value="")),
        patch.object(ModalEnvironment, "stop", new=AsyncMock()) as stop,
    ):
        await env.stop(True)
    stop.assert_awaited_once_with(True)


async def test_non_deleting_stop_does_not_collect(tmp_path):
    env = make_env(tmp_path)
    with patch.object(ModalEnvironment, "stop", new=AsyncMock()) as stop:
        await env.stop(False)
    stop.assert_awaited_once_with(False)
    assert not env._garnet_collected
