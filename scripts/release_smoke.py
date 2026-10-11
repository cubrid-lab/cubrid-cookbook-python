"""Keep smoke tests on the published driver versions selected at job start."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from email.parser import HeaderParser
from importlib import metadata
from pathlib import Path

# Tests load this file by path, so make its sibling helper importable either way.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from example_requirements import requirement_files  # noqa: E402

DRIVERS = ("pycubrid", "sqlalchemy-cubrid")
PACKAGES = (*DRIVERS, "cubrid-mcp-server")
MANUAL_LATEST = "latest"  # workflow_dispatch default: no pinned release.
RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)")
# Upstream correlation id; also used verbatim in the run name and artifact name.
REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,80}")
REPORT_SCHEMA = 1
# The cells a release verification must report, mirroring the smoke-test.yml
# matrix (cubrid x python, plus the Python 3.11 include); a test keeps them in sync.
DEFAULT_PYTHON = "3.12"
RELEASE_CELLS = frozenset({("11.2", "3.12"), ("11.4", "3.12"), ("11.4", "3.11")})
REPORT_PART = "release-verification-part.json"
# Before installing a requested release, wait until PyPI's JSON API lists exactly
# that version with a file (design C4): on 2026-10-09 stale PyPI CDN nodes hid a
# fresh upload from one cell for ~95-106 s. Anonymous requests only, no tokens.
PYPI_RELEASE_URL = "https://pypi.org/pypi/{package}/{version}/json"
PUBLICATION_TIMEOUT = 600  # seconds; total wall-clock budget of wait_for_pypi
PUBLICATION_DELAYS = (5, 10, 20, 30)  # backoff between polls; the last value repeats
PYPI_FILE_TYPES = frozenset({"bdist_wheel", "sdist"})
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
# Candidate artifact mode (#240): a release workflow passes the distribution its
# own build job uploaded earlier in the SAME run, plus the build job's
# {"<file>": "<sha256>"} output. Only workflow calls can select it; the default
# `published` mode is the exact-PyPI behavior above, unchanged. Neither mode
# ever falls back to the other source.
MODE_INPUTS = {
    "mode": "RELEASE_INPUT_MODE",
    "candidate_artifact": "RELEASE_INPUT_CANDIDATE_ARTIFACT",
    "candidate_hashes": "RELEASE_INPUT_CANDIDATE_HASHES",
    "candidate_source_sha": "RELEASE_INPUT_CANDIDATE_SOURCE_SHA",
}
PUBLISHED, CANDIDATE = "published", "candidate"
# The evidence type a report proves; driver-main.yml labels its own summary
# "representative main" (advisory, never release evidence).
EVIDENCE = {PUBLISHED: "published package", CANDIDATE: "candidate artifact"}
ORIGIN_INDEX, ORIGIN_CANDIDATE = "package index", "candidate artifact"
ARTIFACT_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
DIST_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,199}")
SHA256 = re.compile(r"[0-9a-f]{64}")
SOURCE_SHA = re.compile(r"[0-9a-f]{40}")
# Candidate part artifacts are release-candidate-part-<request_id>--<cell>; a
# candidate request_id may not contain "--", so one id is never a prefix of another
# in the report's download pattern.
CANDIDATE_PART_DELIMITER = "--"
MAX_CANDIDATE_FILES = 20
# Where the workflow downloads the candidate artifact ($RUNNER_TEMP/candidate).
CANDIDATE_DIR_ENV = "RELEASE_CANDIDATE_DIR"


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
        request = read_inputs(inputs, "Release workflow call")
        assert request is not None
        return read_mode(request, {key: environ.get(name, "") for key, name in MODE_INPUTS.items()})
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


def read_mode(request: dict, inputs: Mapping[str, str]) -> dict:
    """Validate the call mode and its inputs; incompatible combinations fail.

    ``published`` (the default, also for an empty value) must not carry candidate
    inputs and returns the request unchanged. ``candidate`` requires a request_id
    (it namespaces the candidate artifacts, so it must stay the same across run
    attempts and must not contain "--"), the artifact name, the build job's digest
    map, which must name exactly one wheel of package==version, and the 40-hex
    source commit the caller built the candidate from.
    """
    mode = inputs.get("mode") or PUBLISHED
    artifact = inputs.get("candidate_artifact", "")
    hashes = inputs.get("candidate_hashes", "")
    source_sha = inputs.get("candidate_source_sha", "")
    if mode not in EVIDENCE:
        raise ValueError(f"Release workflow call mode must be {PUBLISHED} or {CANDIDATE}")
    if mode == PUBLISHED:
        if artifact or hashes or source_sha:
            raise ValueError(
                "candidate_artifact, candidate_hashes and candidate_source_sha require mode "
                "candidate; published mode installs only the exact PyPI release"
            )
        return request
    if request["request_id"] is None:
        raise ValueError("Candidate mode requires a request_id")
    if CANDIDATE_PART_DELIMITER in request["request_id"]:
        raise ValueError(f"Candidate request_id must not contain {CANDIDATE_PART_DELIMITER!r}")
    if SOURCE_SHA.fullmatch(source_sha) is None:
        raise ValueError("Candidate mode requires candidate_source_sha: 40 lowercase hex")
    if ARTIFACT_NAME.fullmatch(artifact) is None:
        raise ValueError(
            "Candidate mode requires candidate_artifact matching [A-Za-z0-9._-]{1,100}"
        )
    files = read_hashes(hashes)
    wheel = candidate_wheel(files, request["package"], request["version"])
    return {
        **request,
        "mode": CANDIDATE,
        "candidate": {
            "artifact": artifact,
            "files": files,
            "wheel": wheel,
            "sha256": files[wheel],
            "source_sha": source_sha,
        },
    }


def read_hashes(value: str) -> dict[str, str]:
    """Parse the caller build job's {"<file>": "<sha256 hex>"} JSON object."""
    try:
        files = json.loads(value) if value else None
    except json.JSONDecodeError as error:
        raise ValueError(f"candidate_hashes is not JSON: {error}") from error
    if not isinstance(files, dict) or not files or len(files) > MAX_CANDIDATE_FILES:
        raise ValueError(
            f"candidate_hashes must be a JSON object of 1-{MAX_CANDIDATE_FILES} file digests"
        )
    for name, digest in files.items():
        if DIST_FILE.fullmatch(name) is None or ".." in name:
            raise ValueError(f"candidate_hashes has an invalid file name: {name!r}")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise ValueError(f"candidate_hashes digest for {name} is not 64 lowercase hex")
    return files


def wheel_identity(filename: str) -> tuple[str, str]:
    """Return the (normalized name, version) a wheel filename declares."""
    parts = filename[: -len(".whl")].split("-")
    if not filename.endswith(".whl") or len(parts) not in (5, 6):
        raise ValueError(f"{filename} is not a wheel filename")
    return normalize_name(parts[0]), parts[1]


def candidate_wheel(files: Mapping[str, str], package: str, version: str) -> str:
    """The one wheel in the digest map; it must be package==version."""
    wheels = [name for name in files if name.endswith(".whl")]
    if len(wheels) != 1:
        raise ValueError(f"candidate_hashes must name exactly one wheel, found {len(wheels)}")
    name, declared = wheel_identity(wheels[0])
    if name != normalize_name(package) or declared != version:
        raise ValueError(f"Candidate wheel {wheels[0]} is not {package} {version}")
    return wheels[0]


def candidate_dir() -> Path:
    """Directory the workflow downloads the candidate artifact into."""
    configured = os.environ.get(CANDIDATE_DIR_ENV)
    if configured:
        return Path(configured)
    return Path(os.environ.get("RUNNER_TEMP") or ".") / "candidate"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_candidate_files(request: dict, directory: Path) -> Path:
    """Check the downloaded artifact against the digest map; return the wheel path.

    The directory must hold exactly the mapped files (regular files, no
    subdirectory or symlink), every SHA-256 must match, and the wheel must be an
    intact archive whose own metadata names package==version. Nothing is
    installed unless every check passes.
    """
    candidate = request["candidate"]
    if not directory.is_dir():
        raise ValueError(f"Candidate artifact {candidate['artifact']} was not downloaded")
    found = {}
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Candidate artifact holds a non-regular file: {path.name}")
        found[path.name] = path
    expected = candidate["files"]
    if set(found) != set(expected):
        missing = sorted(set(expected) - set(found))
        extra = sorted(set(found) - set(expected))
        raise ValueError(f"Candidate artifact files differ: missing {missing}, unexpected {extra}")
    for name, path in sorted(found.items()):
        actual = sha256_file(path)
        if actual != expected[name]:
            raise ValueError(f"SHA-256 of {name} is {actual}, expected {expected[name]}")
    wheel = found[candidate["wheel"]]
    wheel_metadata(wheel, request["package"], request["version"])
    return wheel


def wheel_metadata(wheel: Path, package: str, version: str) -> None:
    """Read Name/Version from the wheel's own METADATA (not its filename)."""
    try:
        with zipfile.ZipFile(wheel) as archive:
            broken = archive.testzip()
            if broken is not None:
                raise ValueError(f"Candidate wheel member {broken} is corrupt")
            entries = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
            ]
            if len(entries) != 1:
                raise ValueError(f"Candidate wheel has {len(entries)} METADATA files")
            text = archive.read(entries[0]).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise ValueError(f"Candidate wheel {wheel.name} is not a valid wheel: {error}") from error
    headers = HeaderParser().parsestr(text)
    name, declared = headers.get("Name", ""), headers.get("Version", "")
    if normalize_name(name) != normalize_name(package) or declared != version:
        raise ValueError(f"Candidate wheel metadata is {name} {declared}, not {package} {version}")


def candidate_package(name: str, request: dict) -> dict[str, str | None]:
    """The requested package must be the verified candidate wheel, installed directly.

    pip writes direct_url.json only for a direct archive install; a missing file,
    another URL or another digest means a later install replaced the candidate
    (for example with a PyPI or VCS copy of the same version).
    """
    candidate = request["candidate"]
    dist = metadata.distribution(name)
    text = dist.read_text("direct_url.json")
    if text is None:
        raise ValueError(f"{name} is not the candidate artifact (installed from a package index)")
    try:
        direct_url = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} has an unreadable direct_url.json") from error
    wheel = candidate_dir().resolve() / candidate["wheel"]
    if not isinstance(direct_url, dict) or direct_url.get("url") != wheel.as_uri():
        raise ValueError(f"{name} was not installed from the verified candidate {wheel}")
    archive = direct_url.get("archive_info")
    archive = archive if isinstance(archive, dict) else {}
    hashes = archive.get("hashes") if isinstance(archive.get("hashes"), dict) else {}
    recorded = hashes.get("sha256")
    legacy = archive.get("hash")
    if recorded is None and isinstance(legacy, str) and legacy.startswith("sha256="):
        recorded = legacy[len("sha256=") :]  # The older single-hash form.
    # The recorded digest binds the installed copy to the verified bytes.
    if recorded != candidate["sha256"]:
        raise ValueError(f"{name} was installed from a wheel with SHA-256 {recorded}")
    if not wheel.is_file() or sha256_file(wheel) != candidate["sha256"]:
        raise ValueError(f"Candidate wheel {wheel} changed after verification")
    return {"version": dist.version, "direct_url": wheel.as_uri()}


def installed_package(name: str, request: dict | None) -> dict[str, str | None]:
    """Mode-aware provenance: only the requested candidate may be a direct install."""
    if request is not None and request.get("mode") == CANDIDATE and request["package"] == name:
        return candidate_package(name, request)
    return indexed_package(name)


def environment_versions() -> dict[str, str]:
    """Every installed distribution (normalized name -> version), like pip freeze."""
    versions = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") if dist.metadata is not None else None
        if name:
            versions[normalize_name(name)] = dist.version
    return dict(sorted(versions.items()))


def request_mode(request: dict | None) -> str:
    return (request or {}).get("mode", PUBLISHED)


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


def verify_request(request: dict) -> None:
    installed = installed_package(request["package"], request)
    if installed["version"] != request["version"]:
        raise ValueError(
            f"Installed {request['package']} {installed['version']} differs from requested "
            f"release {request['version']}"
        )


def fetch_pypi(url: str) -> bytes:
    """GET one PyPI JSON document; HTTP errors (such as 404) raise."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "cubrid-cookbook-release-smoke"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read()


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pypi_mismatch(document: bytes, package: str, version: str) -> str | None:
    """None if a PyPI release JSON document lists exactly package==version with a
    wheel or sdist; otherwise what PyPI served instead (for stale-CDN diagnosis)."""
    data = json.loads(document)
    info = data["info"]
    files = sum(
        isinstance(item, dict) and item.get("packagetype") in PYPI_FILE_TYPES
        for item in data["urls"]
    )
    name, served = info["name"], info["version"]
    if normalize_name(name) == normalize_name(package) and served == version and files:
        return None
    return f"served {name} {served} with {files} wheel/sdist files"


def wait_for_pypi(
    package: str,
    version: str,
    timeout: float = PUBLICATION_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
    fetch: Callable[[str], bytes] = fetch_pypi,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Poll PyPI until it serves package==version, or fail after ``timeout`` seconds.

    Any HTTP, network or JSON error, and any other version or a release without a
    wheel or sdist, counts as "not yet served"; there is no fallback version.
    """
    url = PYPI_RELEASE_URL.format(package=package, version=version)
    start = clock()
    for attempt in itertools.count(1):
        try:
            reason = pypi_mismatch(fetch(url), package, version)
            if reason is None:
                return
        except Exception as error:  # Every failure means "not served yet".
            reason = f"{type(error).__name__}: {error}"
        remaining = timeout - (clock() - start)
        if remaining <= 0:
            break
        delay = min(PUBLICATION_DELAYS[min(attempt, len(PUBLICATION_DELAYS)) - 1], remaining)
        print(
            f"PyPI does not serve {package}=={version} yet ({reason}); poll {attempt}, "
            f"retrying in {delay:.0f} s",
            file=sys.stderr,
        )
        sleep(delay)
    raise ValueError(
        f"PyPI does not serve {package}=={version} after {clock() - start:.0f} s ({reason})"
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
        target = requirement
        if request_mode(request) == CANDIDATE:
            # Verify the downloaded bytes before anything is installed; there is
            # no publication to wait for and no index copy of the candidate.
            target = str(verify_candidate_files(request, candidate_dir()).resolve())
        else:
            wait_for_pypi(request["package"], request["version"])
        constraints.write_text(requirement + "\n", encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "--index-url",
            "https://pypi.org/simple",
            "--constraint",
            str(constraints.resolve()),
            target,
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


def installed_drivers(request: dict | None = None) -> dict[str, dict[str, str | None]]:
    result = {}
    for name in DRIVERS:
        result[name] = installed_package(name, request)
    return result


def freeze(state: Path, constraints: Path, request: dict | None = None) -> None:
    selected = installed_drivers(request)
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
    installed = installed_drivers(selected.get("requested"))
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
    for requirements in requirement_files(root):
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
        # Already installed exactly (from PyPI, or the verified candidate wheel);
        # never substitute a git artifact or an index copy.
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
    python: str = "",
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
    mode = request_mode(request)
    print("### Release smoke result\n")
    print("| Field | Actual |\n| --- | --- |")
    for name, value in (
        ("Request", validation),
        (
            "Evidence",
            "unavailable"
            if not valid_request
            else EVIDENCE[mode]
            if request is not None
            else "none (not release evidence)",
        ),
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
                ORIGIN_INDEX if dist.read_text("direct_url.json") is None else "direct URL / VCS"
            )
            if mode == CANDIDATE and request["package"] == name:
                # Only the verified wheel, still in place, counts as the candidate;
                # otherwise the ValueError keeps the index/direct-URL origin above.
                installed_package(name, request)
                origin = ORIGIN_CANDIDATE
        except (metadata.PackageNotFoundError, ValueError, OSError):
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
        record = {
            "cubrid": cubrid,
            "python": python or None,
            "request_valid": valid_request,
            "installed_version": None if version == "unavailable" else version,
            "origin": origin,
            "server": server or None,
            "verification": verification,
            "result": result,
            # Additive (#240): the evidence type and every installed package version.
            "evidence": EVIDENCE[mode] if valid_request else None,
            # The tracked packages (None when missing) plus every other installed
            # distribution, such as SQLAlchemy and the framework packages.
            "packages": {
                **environment_versions(),
                **{
                    name: None if found == "unavailable" else found
                    for name, (found, _) in installed.items()
                },
            },
        }
        if mode == CANDIDATE:
            passed = verification == "passed" and origin == ORIGIN_CANDIDATE
            record["request_id"] = request["request_id"]
            record["candidate_sha256"] = request["candidate"]["sha256"] if passed else None
        part.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if invalid_success:
        raise ValueError("A successful smoke result requires final version and origin verification")


def cell(part: dict[str, object]) -> str:
    """Name a smoke matrix cell: the CUBRID version plus a non-default Python."""
    python = part.get("python")
    show = python and python != DEFAULT_PYTHON
    return f"CUBRID {part.get('cubrid')}" + (f", Python {python}" if show else "")


def build_report(
    request: dict[str, str | None] | None,
    error: str | None,
    parts: list[dict[str, object]],
    verify_result: str,
    download_result: str,
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
    if download_result != "success":
        # download-artifact v8 can fail its digest check after extracting the files.
        reasons.append(f"smoke result download did not succeed: {download_result or 'unknown'}")
    if request is not None:
        seen = [(p.get("cubrid"), p.get("python")) for p in parts]
        for key in sorted(RELEASE_CELLS):
            name = cell({"cubrid": key[0], "python": key[1]})
            if key not in seen:
                reasons.append(f"{name}: no result reported")
            elif seen.count(key) > 1:
                reasons.append(f"{name}: reported {seen.count(key)} times")
        for key in sorted(set(seen) - RELEASE_CELLS, key=str):
            reasons.append(f"unexpected smoke cell: CUBRID {key[0]}, Python {key[1]}")
    mode = request_mode(request)
    evidence = EVIDENCE[mode] if error is None else None
    for p in parts:
        if p.get("installed_version") != requested:
            reasons.append(
                f"{cell(p)}: installed {p.get('installed_version')} "
                f"differs from requested {requested}"
            )
        elif p.get("verification") != "passed" or p.get("result") != "success":
            reasons.append(
                f"{cell(p)}: verification {p.get('verification')}, result {p.get('result')}"
            )
        # A part of the other mode never counts (older published parts lack the key).
        elif request is not None and p.get("evidence", EVIDENCE[PUBLISHED]) != evidence:
            reasons.append(f"{cell(p)}: evidence {p.get('evidence')}, expected {evidence}")
        elif mode == CANDIDATE and p.get("request_id") != request["request_id"]:
            reasons.append(f"{cell(p)}: request_id {p.get('request_id')} is another request")
        elif mode == CANDIDATE and (
            p.get("origin") != ORIGIN_CANDIDATE
            or p.get("candidate_sha256") != request["candidate"]["sha256"]
        ):
            reasons.append(
                f"{cell(p)}: origin {p.get('origin')}, SHA-256 {p.get('candidate_sha256')} "
                f"is not the verified candidate {request['candidate']['sha256']}"
            )
    report = {
        "schema_version": REPORT_SCHEMA,
        "request_id": request.get("request_id") if request else None,
        "package": request["package"] if request else None,
        "requested_version": requested,
        # One agreed version across the matrix, else null (see "matrix").
        "installed_version": next(iter(installed)) if len(installed) == 1 else None,
        "status": "failure" if reasons else "success",
        "reasons": reasons,
        "run": run,
        "matrix": sorted(parts, key=lambda p: (str(p.get("cubrid")), str(p.get("python")))),
        "evidence": evidence,
    }
    if mode == CANDIDATE:
        candidate = request["candidate"]
        report["candidate"] = {
            "artifact": candidate["artifact"],
            "wheel": candidate["wheel"],
            "source_sha": candidate["source_sha"],
            "files": candidate["files"],
            # What the caller claimed; candidate_sha256 is set only once verified.
            "expected_sha256": candidate["sha256"],
            "candidate_sha256": candidate["sha256"] if not reasons else None,
        }
    return report


def report_markdown(report: dict[str, object]) -> str:
    lines = ["### Release verification\n", "| Field | Value |", "| --- | --- |"]
    keys = ("evidence", "request_id", "package", "requested_version", "installed_version")
    for key in (*keys, "status"):
        lines.append(f"| {key} | {report[key] if report[key] is not None else 'none'} |")
    if "candidate" in report:
        candidate = report["candidate"]
        for key in ("wheel", "source_sha", "expected_sha256", "candidate_sha256"):
            value = candidate[key]  # type: ignore[index]
            lines.append(f"| candidate {key} | {value if value is not None else 'none'} |")
    for reason in report["reasons"]:  # type: ignore[union-attr]
        lines.append(f"\n- {reason}")
    return "\n".join(lines) + "\n"


def report_releases(
    event_name: str,
    event_path: Path | None,
    parts_dir: Path,
    verify_result: str,
    download_result: str,
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
        report = build_report(request, error, parts, verify_result, download_result, run)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report_markdown(report))
        suffix = report["request_id"] or f"run-{run.get('id') or 'unknown'}"
        prefix = (
            "release-candidate-verification" if "candidate" in report else "release-verification"
        )
        outputs = {
            "release": "true",
            "artifact": f"{prefix}-{suffix}",
            "status": str(report["status"]),
            "request_id": str(report["request_id"] or ""),
            "package": str(report["package"] or ""),
            "requested_version": str(report["requested_version"] or ""),
            "installed_version": str(report["installed_version"] or ""),
            "evidence": str(report["evidence"] or ""),
            "candidate_sha256": (
                str(report["candidate"]["candidate_sha256"] or "")  # type: ignore[index]
                if "candidate" in report
                else ""
            ),
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
    validate = commands.add_parser("validate")
    event_arguments(validate)
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
    final.add_argument("--python", default="")
    combine = commands.add_parser("report")
    event_arguments(combine)
    combine.add_argument("--parts", type=Path, required=True)
    combine.add_argument("--verify-result", required=True)
    combine.add_argument("--download-result", required=True)
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
        elif args.command == "validate":
            # Request and mode inputs only; runs before any download or install.
            request = read_request(args.event_name, args.event_path)
            if os.environ.get(MODE_INPUTS["mode"]) == CANDIDATE and request_mode(request) != (
                CANDIDATE
            ):
                raise ValueError("mode candidate was requested but this is not a candidate call")
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
            if os.environ.get(MODE_INPUTS["mode"]) == CANDIDATE:
                # Under a call GITHUB_REPOSITORY/GITHUB_SHA are the caller's run; the
                # candidate's own build source is candidate.source_sha (an input),
                # which differs on a resume that builds from another commit.
                run["caller_repository"] = repository
                run["caller_run_sha"] = os.environ.get("GITHUB_SHA", "")
                run["caller_workflow_ref"] = os.environ.get("GITHUB_WORKFLOW_REF", "")
            if not report_releases(
                args.event_name,
                args.event_path,
                args.parts,
                args.verify_result,
                args.download_result,
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
                args.python,
            )
    except (ValueError, OSError, metadata.PackageNotFoundError) as error:
        parser.exit(1, f"Release smoke check failed: {error}\n")


if __name__ == "__main__":
    main()
