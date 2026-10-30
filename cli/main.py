"""Thin HTTP client; contains no orchestration, model or storage-provider logic."""

import json
import os
from contextlib import contextmanager
from pathlib import Path

import httpx
import keyring
import typer

app = typer.Typer(help="SAP CoWork project workspace", no_args_is_help=True)
projects = typer.Typer(no_args_is_help=True)
artifacts = typer.Typer(no_args_is_help=True)
files = typer.Typer(no_args_is_help=True)
context = typer.Typer(no_args_is_help=True)
provider = typer.Typer(no_args_is_help=True)
for name, group in [
    ("projects", projects),
    ("artifacts", artifacts),
    ("files", files),
    ("context", context),
    ("provider", provider),
    ("project", projects),
    ("artifact", artifacts),
]:
    app.add_typer(group, name=name)


def config_path():
    return Path(os.getenv("COWORK_CLI_HOME", str(Path.home() / ".sap-cowork"))) / "session.json"


def load_config():
    path = config_path()
    return json.loads(path.read_text()) if path.exists() else {}


def save_config(value):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@contextmanager
def client_factory():
    base = os.getenv("COWORK_API_URL", "http://127.0.0.1:8000")
    token = os.getenv("COWORK_TOKEN") or keyring.get_password("SAP-CoWork-CLI", base)
    with httpx.Client(
        base_url=base, headers={"Authorization": f"Bearer {token}"} if token else {}, timeout=180
    ) as client:
        yield client


def call(method, path, **kwargs):
    try:
        with client_factory() as client:
            response = client.request(method, "/api" + path, **kwargs)
        if response.status_code >= 400:
            message = response.json().get("detail", "Request failed")
            typer.echo(f"Error: {message}", err=True)
            raise typer.Exit(1)
        return response.json()
    except httpx.HTTPError:
        typer.echo("Cannot reach the CoWork backend. Start the server or check COWORK_API_URL.", err=True)
        raise typer.Exit(1) from None


def display(value):
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False))


def project_id(value=None):
    selected = value or load_config().get("project_id")
    if not selected:
        raise typer.BadParameter("Open a project first, or provide a project ID")
    return selected


@app.command()
def login():
    """Sign in. Credentials are prompted privately and tokens use the OS keyring."""
    access_code = typer.prompt(
        "Local access code (empty if not configured)", default="", hide_input=True, show_default=False
    )
    result = call("POST", "/session", json={"access_code": access_code})
    keyring.set_password(
        "SAP-CoWork-CLI", os.getenv("COWORK_API_URL", "http://127.0.0.1:8000"), result["token"]
    )
    display({"user_id": result["user_id"], "signed_in": True})


@projects.command("create")
def create(name: str = typer.Option(..., "--name"), stage: str = "Planning", requirement: str = ""):
    result = call(
        "POST", "/projects", json={"project_name": name, "stage": stage, "requirement": requirement}
    )
    save_config({"project_id": result["project"]["project_id"]})
    display(result["project"])


@projects.command("list")
def list_projects():
    display(call("GET", "/projects"))


@projects.command("open")
def open_project(project: str):
    result = call("GET", f"/projects/{project}")
    save_config({"project_id": project})
    display({"project": result["project"], "status": result["status"]})


@app.command()
def status(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/status"))


@app.command()
def chat(
    project: str | None = None,
    message: str | None = typer.Option(None, "--message", "-m"),
    model_policy: str | None = typer.Option(None, "--model-policy"),
):
    selected = project_id(project)
    if message is not None:
        display(
            call(
                "POST", f"/projects/{selected}/chat", json={"message": message, "model_policy": model_policy}
            )
        )
        return
    typer.echo(f"Project {selected}. Type /exit to leave chat.")
    while True:
        try:
            text = typer.prompt("You")
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip() == "/exit":
            break
        result = call(
            "POST", f"/projects/{selected}/chat", json={"message": text, "model_policy": model_policy}
        )
        typer.echo("CoWork > " + result["message"])


@artifacts.command("list")
def list_artifacts(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/artifacts"))


@artifacts.command("show")
def show_artifact(artifact_id: str, project: str | None = typer.Option(None), version: str | None = None):
    display(
        call(
            "GET",
            f"/projects/{project_id(project)}/artifacts/{artifact_id}",
            params={"version": version} if version else {},
        )
    )


@artifacts.command("approve")
def approve(artifact_id: str, project: str | None = typer.Option(None), version: str | None = None):
    display(
        call(
            "POST",
            f"/projects/{project_id(project)}/artifacts/{artifact_id}/review",
            json={"action": "approve", "version": version},
        )
    )


@artifacts.command("reject")
def reject(
    artifact_id: str,
    reason: str = typer.Option(...),
    project: str | None = typer.Option(None),
    version: str | None = None,
):
    display(
        call(
            "POST",
            f"/projects/{project_id(project)}/artifacts/{artifact_id}/review",
            json={"action": "reject", "version": version, "feedback": reason},
        )
    )


@context.command("status")
def context_status(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/context"))


@context.command("compact")
def compact(project: str | None = None):
    display(call("POST", f"/projects/{project_id(project)}/context/compact"))


@files.command("list")
def list_files(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/files"))


@files.command("upload")
def upload(
    path: Path,
    project: str | None = typer.Option(None),
    artifact_type: str | None = None,
    domain: str = "BUSINESS",
):
    with path.open("rb") as stream:
        display(
            call(
                "POST",
                f"/projects/{project_id(project)}/files",
                files={"file": (path.name, stream)},
                data={"domain": domain, **({"artifact_type": artifact_type} if artifact_type else {})},
            )
        )


@provider.command("configure")
def configure(
    provider_name: str = typer.Option("fake", "--provider"),
    model: str = "deterministic-v1",
    base_url: str | None = None,
    context_window: int = 32000,
):
    credential = (
        typer.prompt(
            "Provider API key (empty to retain existing)", default="", hide_input=True, show_default=False
        )
        if provider_name != "fake"
        else None
    )
    display(
        call(
            "PUT",
            "/settings/provider",
            json={
                "provider": provider_name,
                "default_model": model,
                "credential": credential or None,
                "base_url": base_url,
                "capabilities": {"context_window": context_window},
            },
        )
    )


@provider.command("test")
def test_provider():
    display(call("POST", "/settings/provider/test"))


if __name__ == "__main__":
    app()
