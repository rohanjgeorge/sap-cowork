import json
from contextlib import nullcontext

from fastapi.testclient import TestClient
from typer.testing import CliRunner
from backend.app.api import create_app
from backend.app.settings import MemorySecretStore
from cli import main


def test_cli_commands_share_api_state(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORK_CLI_HOME", str(tmp_path / "cli"))
    app = create_app(tmp_path / "data", MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        monkeypatch.setattr(main, "client_factory", lambda: nullcontext(client))
        runner = CliRunner()

        def invoke(args, **kwargs):
            result = runner.invoke(main.app, args, **kwargs)
            assert result.exit_code == 0, (result.output, result.exception)
            return result.output

        created = json.loads(invoke(["projects", "create", "--name", "CLI STO"]))
        p = created["project_id"]
        assert "CLI STO" in invoke(["projects", "list"])
        assert "Planning" in invoke(["projects", "open", p])
        assert "Planning" in invoke(["status"])
        invoke(["chat", "-m", "Automate STO deliveries"])
        invoke(["chat", "-m", "Generate BRD"])
        assert "BRD" in invoke(["artifacts", "list"])
        assert "pending_approval" in invoke(["artifacts", "show", "BRD", "--version", "1"])
        invoke(["artifacts", "approve", "BRD", "--version", "1"])
        assert client.get(f"/api/projects/{p}/status").json()["stages"][0]["color"] == "green"
        assert "usage_percent" in invoke(["context", "status"])
        assert "compactions" in invoke(["context", "compact"])
        source = tmp_path / "sap.md"
        source.write_text("Curated SAP fact")
        invoke(["files", "upload", str(source), "--domain", "SAP"])
        assert "sap.md" in invoke(["files", "list"])
        invoke(["provider", "configure", "--provider", "fake"])
        assert "connected" in invoke(["provider", "test"])
        assert "CoWork >" in invoke(["chat"], input="status\n/exit\n")


def test_cli_login_hides_token(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORK_CLI_HOME", str(tmp_path))
    with TestClient(create_app(tmp_path / "data", MemorySecretStore(), access_code="secret")) as client:
        monkeypatch.setattr(main, "client_factory", lambda: nullcontext(client))
        saved = {}
        monkeypatch.setattr(
            main.keyring, "set_password", lambda service, key, value: saved.update(token=value)
        )
        result = CliRunner().invoke(main.app, ["login"], input="secret\n")
        assert result.exit_code == 0, result.output
        assert "signed_in" in result.output
        assert saved["token"] not in result.output and "secret" not in result.output
