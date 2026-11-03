"""Thin HTTP client; contains no orchestration, model or storage-provider logic."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

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
def create(
    name: str = typer.Option(..., "--name"),
    stage: str = "Planning",
    requirement: str = "",
    organization_id: str | None = None,
    program_id: str | None = None,
    sap_product: str | None = None,
    deployment: str | None = None,
    release: str | None = None,
    system: str | None = None,
    client: str | None = None,
):
    result = call(
        "POST",
        "/projects",
        json={
            "project_name": name,
            "stage": stage,
            "requirement": requirement,
            "organization_id": organization_id,
            "program_id": program_id,
            "sap_applicability": {
                k: v
                for k, v in {
                    "product": sap_product,
                    "deployment": deployment,
                    "release": release,
                    "system": system,
                    "client": client,
                }.items()
                if v
            },
        },
    )
    save_config({"project_id": result["project"]["project_id"]})
    display(result["project"])


@projects.command("metadata")
def update_metadata(
    project: str | None = typer.Option(None),
    organization_id: str | None = None,
    program_id: str | None = None,
    sap_product: str | None = None,
    deployment: str | None = None,
    release: str | None = None,
    system: str | None = None,
    client: str | None = None,
):
    selected = project_id(project)
    current = call("GET", f"/projects/{selected}")
    sap = {
        **current["project"].get("sap_applicability", {}),
        **{
            k: v
            for k, v in {
                "product": sap_product,
                "deployment": deployment,
                "release": release,
                "system": system,
                "client": client,
            }.items()
            if v is not None
        },
    }
    payload = {
        "sap_applicability": sap,
        "expected_revision": current["state"]["state_revision"],
        "request_id": uuid4().hex,
    }
    if organization_id is not None:
        payload["organization_id"] = organization_id or None
    if program_id is not None:
        payload["program_id"] = program_id or None
    display(call("PUT", f"/projects/{selected}/metadata", json=payload))


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


def state_operation(project, operation, payload=None):
    selected = project_id(project)
    state = call("GET", f"/projects/{selected}/state")
    return call(
        "POST",
        f"/projects/{selected}/state/operations",
        json={
            "operation": operation,
            "payload": payload or {},
            "expected_revision": state["state_revision"],
            "request_id": uuid4().hex,
        },
    )


@projects.command("stage")
def change_stage(stage: str, project: str | None = typer.Option(None)):
    display(state_operation(project, "change_draft_stage", {"stage": stage}))


@projects.command("close")
def close_project(project: str | None = typer.Option(None)):
    display(state_operation(project, "close_project"))


@projects.command("reopen")
def reopen(project: str | None = typer.Option(None)):
    display(state_operation(project, "reopen_project"))


@projects.command("confirm-code")
def confirm_code(project: str | None = typer.Option(None), remarks: str = ""):
    display(state_operation(project, "confirm_code", {"remarks": remarks}))


@projects.command("confirm-testing")
def confirm_testing(project: str | None = typer.Option(None), remarks: str = ""):
    display(state_operation(project, "confirm_testing", {"remarks": remarks}))


@projects.command("withdraw")
def withdraw(kind: str, project: str | None = typer.Option(None)):
    display(state_operation(project, "withdraw_confirmation", {"kind": kind}))


@projects.command("retry-follow-up")
def retry_follow_up(kind: str, project: str | None = typer.Option(None)):
    display(call("POST", f"/projects/{project_id(project)}/follow-ups/{kind}/retry"))


@artifacts.command("generate")
def generate_artifact(
    artifact_id: str,
    project: str | None = typer.Option(None),
    new_version: bool = False,
    authors: str = "",
    remarks: str = "",
):
    display(
        call(
            "POST",
            f"/projects/{project_id(project)}/chat",
            json={
                "action": "generate",
                "artifact_type": artifact_id,
                "new_version": new_version,
                "authors": authors,
                "remarks": remarks,
            },
        )
    )


@artifacts.command("submit")
def submit_artifact(artifact_id: str, version: str, project: str | None = typer.Option(None)):
    display(state_operation(project, "submit_artifact", {"artifact_id": artifact_id, "version": version}))


@artifacts.command("reconcile")
def reconcile_artifacts(project: str | None = typer.Option(None)):
    display(state_operation(project, "reconcile_artifacts"))


@artifacts.command("edit")
def edit_artifact(
    artifact_id: str,
    path: Path,
    project: str | None = typer.Option(None),
    new_version: bool = False,
    authors: str = "",
    remarks: str = "",
):
    selected = project_id(project)
    state = call("GET", f"/projects/{selected}/state")
    display(
        call(
            "PUT",
            f"/projects/{selected}/artifacts/{artifact_id}",
            json={
                "content": path.read_text(encoding="utf-8"),
                "expected_revision": state["state_revision"],
                "new_version": new_version,
                "authors": authors,
                "remarks": remarks,
            },
        )
    )


@artifacts.command("download")
def download_artifact(
    artifact_id: str, output: Path, project: str | None = typer.Option(None), version: str | None = None
):
    selected = project_id(project)
    with client_factory() as client:
        response = client.get(
            f"/api/projects/{selected}/artifacts/{artifact_id}/download",
            params={"version": version} if version else {},
        )
    if response.status_code >= 400:
        typer.echo("Artifact download failed", err=True)
        raise typer.Exit(1)
    output.write_bytes(response.content)
    typer.echo(str(output.resolve()))


@artifacts.command("delete-draft")
def delete_draft(artifact_id: str, version: str, project: str | None = typer.Option(None)):
    display(
        call(
            "DELETE", f"/projects/{project_id(project)}/artifacts/{artifact_id}", params={"version": version}
        )
    )


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


@context.command("plans")
def context_plans(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/context/plans"))


@context.command("plan")
def context_plan(plan_ref: str, project: str | None = typer.Option(None)):
    display(call("GET", f"/projects/{project_id(project)}/context/plans/{plan_ref}"))


@context.command("sources")
def context_sources(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/context/sources"))


@context.command("updates")
def context_updates(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/context/updates"))


@context.command("review-update")
def review_context_update(
    record_id: str,
    approved: bool = typer.Option(..., "--approve/--reject"),
    project: str | None = typer.Option(None),
):
    comparison = call("GET", f"/projects/{project_id(project)}/context/updates/{record_id}")
    display(comparison)
    display(
        call(
            "POST",
            f"/projects/{project_id(project)}/context/updates/{record_id}/review",
            json={"approved": approved, "expected_fingerprint": comparison["current_fingerprint"]},
        )
    )


@context.command("compare-update")
def compare_context_update(record_id: str, project: str | None = typer.Option(None)):
    display(call("GET", f"/projects/{project_id(project)}/context/updates/{record_id}"))


@files.command("list")
def list_files(project: str | None = None):
    display(call("GET", f"/projects/{project_id(project)}/files"))


@files.command("upload")
def upload(
    path: Path,
    project: str | None = typer.Option(None),
    artifact_type: str | None = None,
    domain: str = "BUSINESS",
    confirmed: bool = False,
):
    with path.open("rb") as stream:
        display(
            call(
                "POST",
                f"/projects/{project_id(project)}/files",
                files={"file": (path.name, stream)},
                data={
                    "domain": domain,
                    "confirmed": str(confirmed).lower(),
                    **({"artifact_type": artifact_type} if artifact_type else {}),
                },
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
