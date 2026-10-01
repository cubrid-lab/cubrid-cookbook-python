"""Keep smoke tests on the published driver versions selected at job start."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

DRIVERS = ("pycubrid", "sqlalchemy-cubrid")
PACKAGES = (*DRIVERS, "cubrid-mcp-server")
MANUAL_LATEST = "latest"  # workflow_dispatch default: no pinned release.
RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)")
# Upstream correlation id; also used verbatim in the run name and artifact name.
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,80}")
REPORT_SCHEMA = 1
REPORT_PART = "release-verification-part.json"
# Another repository's release workflow calls smoke-test.yml (on: workflow_call).
# GITHUB_EVENT_NAME/GITHUB_EVENT_PATH then describe the CALLER's event, so the
# workflow flags the call and passes its inputs through the environment instead.
WORKFLOW_CALL = "workflow_call"
CALL_FLAG = "RELEASE_WORKFLOW_CALL"
CALL_INPUTS = {
    "package": "RELEASE_INPUT_PACKAGE",
    "version": "RELEASE_INPUT_VERSION",
    "request_id": "RELEASE_INPUT_REQUEST_ID",
}


def read_request_id(value: object) -> str | None:
    """Validate the optional upstream request id; absent or empty means none."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or REQUEST_ID.fullmatch(value) is None:
        raise ValueError("Release request_id must match [A-Za-z0-9._-]{8,80}")
    return value


def read_request(
    event_name: str, event_path: Path | None, environ: Mapping[str, str] | None = None
) -> dict[str, str] | None:
    """Validate an upstream release request: dispatch, pinned manual run or workflow call.

    Dispatch and manual fields are read from the event JSON. Under ``workflow_call`` the
    event JSON is the caller's, so the call inputs come from ``RELEASE_INPUT_*``
    environment variables instead. Request fields never enter shell code.
    A manual run without a package keeps the ordinary latest-release smoke behavior.
    """
    if event_name == WORKFLOW_CALL:
        environ = os.environ if environ is None else environ
        inputs = {key: environ.get(name, "") for key, name in CALL_INPUTS.items()}
        if inputs["package"] in ("", MANUAL_LATEST):
            raise ValueError("Release workflow call requires a package: " + ", ".join(PACKAGES))
        return read_inputs(inputs, "Release workflow call")
    if event_name not in ("repository_dispatch", "workflow_dispatch"):
        return None
    if event_path is None or not event_path.is_file():
        raise ValueError("Release request requires an event JSON file")
    event = json.loads(event_path.read_text(encoding="utf-8"))
    if not isinstance(event, dict):
        raise ValueError("Release request event JSON must be an object")
    if event_name == "repository_dispatch":
        payload = event.get("client_payload")
        if not isinstance(payload, dict) or payload.get("package") not in PACKAGES:
            raise ValueError("Release dispatch package is not in the upstream allowlist")
        ref = payload.get("ref")
        if not isinstance(ref, str) or RELEASE_TAG.fullmatch(ref) is None:
            raise ValueError("Release dispatch ref must be canonical vMAJOR.MINOR.PATCH")
        request_id = read_request_id(payload.get("request_id"))
        return {
            "package": payload["package"],
            "ref": ref,
            "version": ref[1:],
            "request_id": request_id,
        }
    inputs = event.get("inputs")
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError("Manual release inputs must be an object")
    return read_inputs(inputs, "Manual release")


def read_inputs(inputs: Mapping[str, object], source: str) -> dict[str, str] | None:
    """Validate package/version/request_id inputs of a manual run or workflow call."""
    package = inputs.get("package")
    version = inputs.get("version")
    request_id = inputs.get("request_id")
    if package in (None, "", MANUAL_LATEST):
        if version in (None, "") and request_id in (None, ""):
            return None
        raise ValueError(f"{source} version or request_id requires a non-latest package")
    if package not in PACKAGES:
        raise ValueError(f"{source} package must be one of " + ", ".join(PACKAGES))
    if not isinstance(version, str) or not version:
        raise ValueError(f"{source} run requires a version such as 1.8.0 or v1.8.0")
    ref = version if version.startswith("v") else "v" + version
    if RELEASE_TAG.fullmatch(ref) is None:
        raise ValueError(f"{source} version must be MAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH")
    return {
        "package": package,
        "ref": ref,
        "version": ref[1:],
        "request_id": read_request_id(request_id),
    }


def request_source(event_name: str) -> str:
    if event_name == WORKFLOW_CALL:
        return "release workflow call"
    return "manual release run" if event_name == "workflow_dispatch" else "release dispatch"


def indexed_package(name: str) -> dict[str, str | None]:
    dist = metadata.distribution(name)
    direct_url = dist.read_text("direct_url.json")
    if direct_url is not None:
        raise ValueError(f"{name} must be installed from the package index, not a direct URL")
    return {"version": dist.version, "direct_url": direct_url}


def verify_request(request: dict[str, str]) -> None:
    installed = indexed_package(request["package"])
    if installed["version"] != request["version"]:
        raise ValueError(
            f"Installed {request['package']} {installed['version']} differs from requested "
            f"release {request['version']}"
        )


def select_releases(
    event_name: str,
    event_path: Path | None,
    constraints: Path,
    attempts: int = 6,
    delay: int = 10,
    timeout: int = 60,
) -> None:
    request = read_request(event_name, event_path)
    bootstrap = [sys.executable, "-m", "pip", "install", *DRIVERS, "sqlalchemy"]
    if request is not None:
        requirement = f"{request['package']}=={request['version']}"
        constraints.write_text(requirement + "\n", encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--index-url",
            "https://pypi.org/simple",
            "--constraint",
            str(constraints.resolve()),
            requirement,
        ]
        for attempt in range(1, attempts + 1):
            try:
                subprocess.run(command, check=True, timeout=timeout)
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                if attempt == attempts:
                    raise ValueError(
                        f"Requested release {requirement} unavailable after {attempts} attempts"
                    ) from error
                print(
                    f"Waiting for {requirement} publication ({attempt}/{attempts})", file=sys.stderr
                )
                time.sleep(delay)
        verify_request(request)
        bootstrap.extend(["--constraint", str(constraints.resolve())])
    subprocess.check_call(bootstrap)


def installed_drivers() -> dict[str, dict[str, str | None]]:
    result = {}
    for name in DRIVERS:
        result[name] = indexed_package(name)
    return result


def freeze(state: Path, constraints: Path, request: dict[str, str] | None = None) -> None:
    selected = installed_drivers()
    if request is not None:
        verify_request(request)
    state.write_text(
        json.dumps({"drivers": selected, "requested": request}, indent=2) + "\n", encoding="utf-8"
    )
    pins = {name: selected[name]["version"] for name in DRIVERS}
    if request is not None:
        pins[request["package"]] = request["version"]
    constraints.write_text(
        "".join(f"{name}=={version}\n" for name, version in pins.items()),
        encoding="utf-8",
    )


def verify(state: Path) -> None:
    selected = json.loads(state.read_text(encoding="utf-8"))
    installed = installed_drivers()
    drivers = selected.get("drivers", selected)  # Read older ephemeral snapshots as well.
    if installed != drivers:
        raise ValueError(
            f"Smoke driver versions changed: selected {drivers}, installed {installed}"
        )
    if selected.get("requested") is not None:
        verify_request(selected["requested"])


def install_examples(root: Path, constraints: Path) -> None:
    if not constraints.is_file():
        raise ValueError(f"Missing release constraints: {constraints}")
    roots = sorted({p.parent for p in root.glob("**/expected") if p.is_dir()})
    for example in roots:
        if any(part.startswith(".") for part in example.relative_to(root).parts):
            continue
        requirements = example / "requirements.txt"
        if requirements.is_file():
            print(f"Installing example requirements: {requirements}", file=sys.stderr)
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--constraint",
                    str(constraints.resolve()),
                    "-r",
                    str(requirements),
                ]
            )


def install_mcp(state: Path) -> None:
    selected = json.loads(state.read_text(encoding="utf-8"))
    request = selected.get("requested")
    if request is not None and request["package"] == "cubrid-mcp-server":
        # Already installed exactly from PyPI; never substitute a git artifact.
        verify_request(request)
        return
    command = [sys.executable, "-m", "pip", "install"]
    try:
        subprocess.check_call([*command, "cubrid-mcp-server"])
    except subprocess.CalledProcessError:
        # Preserve the existing fallback when MCP is not the requested release.
        subprocess.check_call(
            [*command, "git+https://github.com/cubrid-lab/cubrid-mcp-server.git@v0.4.0"]
        )


def report() -> None:
    print("### Tested upstream versions\n")
    print("| Package | Version |")
    print("| --- | --- |")
    for name in (*DRIVERS, "cubrid-mcp-server"):
        print(f"| {name} | {metadata.version(name)} |")


def summary(
    event_name: str,
    event_path: Path | None,
    state: Path,
    commit: str,
    server: str,
    result: str,
    part: Path | None = None,
    cubrid: str = "",
) -> None:
    """Report facts even if selection, publication or validation failed.

    For a release request (valid or not) also write this job's machine-readable
    result to ``part`` so the report job can combine the matrix.
    """
    request = None
    valid_request = True
    validation = "none (latest releases; not a release verification)"
    try:
        request = read_request(event_name, event_path)
        if request is not None:
            validation = f"{request_source(event_name)}: {request['package']} {request['ref']}"
    except (ValueError, OSError) as error:
        validation = f"invalid release request: {error}"
        valid_request = False
    verification = "unavailable"
    if state.is_file():
        try:
            verify(state)
            if request is not None:
                verify_request(request)
            verification = "passed"
        except (ValueError, OSError, metadata.PackageNotFoundError):
            verification = "failed"
    if not valid_request:
        verification = "failed"
    invalid_success = result == "success" and verification != "passed"
    if invalid_success:
        result = "failure"
    print("### Release smoke result\n")
    print("| Field | Actual |\n| --- | --- |")
    for name, value in (
        ("Request", validation),
        ("Request id", (request or {}).get("request_id") or "none"),
        ("Verification commit", commit),
        ("CUBRID server", server),
        ("Verification", verification),
        ("Result", result),
    ):
        print(f"| {name} | {value or 'unavailable'} |")
    print("\n| Package | Requested | Installed | Origin |\n| --- | --- | --- | --- |")
    installed: dict[str, tuple[str, str]] = {}
    for name in PACKAGES:
        version = origin = "unavailable"
        try:
            dist = metadata.distribution(name)
            version = dist.version
            origin = (
                "package index" if dist.read_text("direct_url.json") is None else "direct URL / VCS"
            )
        except metadata.PackageNotFoundError:
            pass
        installed[name] = (version, origin)
        expected = (
            request["version"]
            if request is not None and request["package"] == name
            else "not requested"
        )
        print(f"| {name} | {expected} | {version} | {origin} |")
    if part is not None and (request is not None or not valid_request):
        version, origin = installed[request["package"]] if request else (None, None)
        part.write_text(
            json.dumps(
                {
                    "cubrid": cubrid,
                    "request_valid": valid_request,
                    "installed_version": None if version == "unavailable" else version,
                    "origin": origin,
                    "server": server or None,
                    "verification": verification,
                    "result": result,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if invalid_success:
        raise ValueError("A successful smoke result requires final version and origin verification")


def build_report(
    request: dict[str, str | None] | None,
    error: str | None,
    parts: list[dict[str, object]],
    verify_result: str,
    run: dict[str, str],
) -> dict[str, object]:
    """Combine the matrix results into one release verification report."""
    requested = request["version"] if request else None
    installed = {p.get("installed_version") for p in parts}
    reasons = []
    if error is not None:
        reasons.append(f"invalid release request: {error}")
    if not parts:
        reasons.append("no smoke job reported a result")
    if verify_result != "success":
        reasons.append(f"smoke jobs finished with {verify_result or 'unknown'}")
    for p in parts:
        if p.get("installed_version") != requested:
            reasons.append(
                f"CUBRID {p.get('cubrid')}: installed {p.get('installed_version')} "
                f"differs from requested {requested}"
            )
        elif p.get("verification") != "passed" or p.get("result") != "success":
            reasons.append(
                f"CUBRID {p.get('cubrid')}: verification {p.get('verification')}, "
                f"result {p.get('result')}"
            )
    return {
        "schema_version": REPORT_SCHEMA,
        "request_id": request.get("request_id") if request else None,
        "package": request["package"] if request else None,
        "requested_version": requested,
        # One agreed version across the matrix, else null (see "matrix").
        "installed_version": next(iter(installed)) if len(installed) == 1 else None,
        "status": "failure" if reasons else "success",
        "reasons": reasons,
        "run": run,
        "matrix": sorted(parts, key=lambda p: str(p.get("cubrid"))),
    }


def report_markdown(report: dict[str, object]) -> str:
    lines = ["### Release verification\n", "| Field | Value |", "| --- | --- |"]
    for key in ("request_id", "package", "requested_version", "installed_version", "status"):
        lines.append(f"| {key} | {report[key] if report[key] is not None else 'none'} |")
    for reason in report["reasons"]:  # type: ignore[union-attr]
        lines.append(f"\n- {reason}")
    return "\n".join(lines) + "\n"


def report_releases(
    event_name: str,
    event_path: Path | None,
    parts_dir: Path,
    verify_result: str,
    output: Path,
    run: dict[str, str],
    github_output: Path | None,
) -> bool:
    """Write the combined report for a release request; return whether it passed."""
    request, error = None, None
    try:
        request = read_request(event_name, event_path)
    except (ValueError, OSError) as exc:
        error = str(exc)
    if request is None and error is None:
        print("### Release verification\n\nnot a release verification (latest releases)")
        outputs = {"release": "false"}
        passed = True
    else:
        parts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(parts_dir.glob(f"**/{REPORT_PART}"))
        ]
        report = build_report(request, error, parts, verify_result, run)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report_markdown(report))
        suffix = report["request_id"] or f"run-{run.get('id') or 'unknown'}"
        outputs = {
            "release": "true",
            "artifact": f"release-verification-{suffix}",
            "status": str(report["status"]),
            "request_id": str(report["request_id"] or ""),
            "package": str(report["package"] or ""),
            "requested_version": str(report["requested_version"] or ""),
            "installed_version": str(report["installed_version"] or ""),
        }
        passed = report["status"] == "success"
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in outputs.items())
    return passed


def event_arguments(parser: argparse.ArgumentParser) -> None:
    called = os.environ.get(CALL_FLAG) == "true"
    event_name = WORKFLOW_CALL if called else os.environ.get("GITHUB_EVENT_NAME", "")
    parser.add_argument("--event-name", default=event_name)
    parser.add_argument("--event-path", type=Path, default=os.environ.get("GITHUB_EVENT_PATH"))


def cookbook_commit() -> str:
    """The cookbook commit under test; GITHUB_SHA is the caller's under workflow_call."""
    return os.environ.get("COOKBOOK_COMMIT") or os.environ.get("GITHUB_SHA", "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select")
    event_arguments(select)
    select.add_argument("--constraints", type=Path, required=True)
    snapshot = commands.add_parser("freeze")
    event_arguments(snapshot)
    snapshot.add_argument("--state", type=Path, required=True)
    snapshot.add_argument("--constraints", type=Path, required=True)
    install = commands.add_parser("install-examples")
    install.add_argument("--root", type=Path, default=Path("."))
    install.add_argument("--constraints", type=Path, required=True)
    mcp = commands.add_parser("install-mcp")
    mcp.add_argument("--state", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--state", type=Path, required=True)
    check.add_argument("--report", action="store_true")
    final = commands.add_parser("summary")
    event_arguments(final)
    final.add_argument("--state", type=Path, required=True)
    final.add_argument("--commit", default=cookbook_commit())
    final.add_argument("--server", default=os.environ.get("CUBRID_SERVER_VERSION", "unavailable"))
    final.add_argument("--result", required=True)
    final.add_argument("--part", type=Path)
    final.add_argument("--cubrid", default="")
    combine = commands.add_parser("report")
    event_arguments(combine)
    combine.add_argument("--parts", type=Path, required=True)
    combine.add_argument("--verify-result", required=True)
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("--github-output", type=Path, default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    try:
        if args.command == "select":
            select_releases(args.event_name, args.event_path, args.constraints)
        elif args.command == "freeze":
            freeze(args.state, args.constraints, read_request(args.event_name, args.event_path))
        elif args.command == "install-examples":
            install_examples(args.root, args.constraints)
        elif args.command == "install-mcp":
            install_mcp(args.state)
        elif args.command == "verify":
            verify(args.state)
            if args.report:
                report()
        elif args.command == "report":
            server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
            repository = os.environ.get("GITHUB_REPOSITORY", "")
            run_id = os.environ.get("GITHUB_RUN_ID", "")
            run = {
                "id": run_id,
                "attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
                "url": f"{server_url}/{repository}/actions/runs/{run_id}",
                "commit": cookbook_commit(),
                "event": args.event_name,
            }
            if not report_releases(
                args.event_name,
                args.event_path,
                args.parts,
                args.verify_result,
                args.output,
                run,
                args.github_output,
            ):
                raise ValueError("Release verification failed; see the report")
        else:
            summary(
                args.event_name,
                args.event_path,
                args.state,
                args.commit,
                args.server,
                args.result,
                args.part,
                args.cubrid,
            )
    except (ValueError, OSError, metadata.PackageNotFoundError) as error:
        parser.exit(1, f"Release smoke check failed: {error}\n")


if __name__ == "__main__":
    main()
