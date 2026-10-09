"""PyPI publication wait before a requested release install (design C4), offline.

fetch, sleep and clock are injected, so no test touches the network or sleeps.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_pypi_wait", ROOT / "scripts/release_smoke.py"
)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

URL = "https://pypi.org/pypi/pycubrid/1.10.0/json"


def release(name="pycubrid", version="1.10.0", types=("bdist_wheel", "sdist")) -> bytes:
    urls = [{"packagetype": kind, "filename": f"{name}-{version}.{kind}"} for kind in types]
    return json.dumps({"info": {"name": name, "version": version}, "urls": urls}).encode()


def not_found(url: str) -> bytes:
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]


class FakeTime:
    """A clock that only advances when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Responses:
    """Return (or raise) the given responses in order, repeating the last one."""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        response = self.responses[min(len(self.urls), len(self.responses)) - 1]
        return response(url) if callable(response) else response


class WaitForPyPITests(unittest.TestCase):
    def wait(self, fetch: Responses, timeout: float = 600) -> FakeTime:
        fake = FakeTime()
        with contextlib.redirect_stderr(io.StringIO()):
            smoke.wait_for_pypi(
                "pycubrid", "1.10.0", timeout, sleep=fake.sleep, fetch=fetch, clock=fake.clock
            )
        return fake

    def test_available_immediately_returns_without_sleeping(self) -> None:
        fetch = Responses(release())
        fake = self.wait(fetch)
        self.assertEqual(fetch.urls, [URL])
        self.assertEqual(fake.sleeps, [])

    def test_wheel_or_sdist_alone_is_enough(self) -> None:
        for types in (("bdist_wheel",), ("sdist",)):
            with self.subTest(types=types):
                self.assertEqual(self.wait(Responses(release(types=types))).sleeps, [])

    def test_available_after_n_polls_with_backoff(self) -> None:
        fetch = Responses(not_found, not_found, not_found, not_found, not_found, release())
        fake = self.wait(fetch)
        self.assertEqual(len(fetch.urls), 6)
        self.assertEqual(fake.sleeps, [5, 10, 20, 30, 30])

    def test_never_available_times_out_with_a_clear_message(self) -> None:
        fetch = Responses(not_found)
        with self.assertRaisesRegex(
            ValueError, r"^PyPI does not serve pycubrid==1\.10\.0 after 600 s \(HTTPError"
        ):
            self.wait(fetch)
        # Bounded: 5+10+20, eighteen 30 s waits, then the last 25 s fit the budget exactly.
        self.assertEqual(len(fetch.urls), 23)

    def test_timeout_is_a_total_wall_clock_budget(self) -> None:
        fake = FakeTime()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError):
            smoke.wait_for_pypi(
                "pycubrid",
                "1.10.0",
                42,
                sleep=fake.sleep,
                fetch=Responses(not_found),
                clock=fake.clock,
            )
        self.assertEqual(fake.now, 42)
        self.assertEqual(fake.sleeps, [5, 10, 20, 7])

    def test_malformed_json_and_http_errors_are_retried_then_time_out(self) -> None:
        def unreachable(url: str) -> bytes:
            raise urllib.error.URLError("temporary failure in name resolution")

        def server_error(url: str) -> bytes:
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)  # type: ignore[arg-type]

        broken = [
            b"<html>not json</html>",
            b"",
            b"[]",
            b'{"info": null, "urls": []}',
            b'{"info": {"name": "pycubrid", "version": "1.10.0"}}',
            b'{"info": {"name": "pycubrid", "version": "1.10.0"}, "urls": {"a": 1}}',
            unreachable,
            server_error,
            not_found,
        ]
        for response in broken:
            with self.subTest(response=response):
                fetch = Responses(response)
                with self.assertRaisesRegex(ValueError, "does not serve pycubrid==1.10.0 after"):
                    self.wait(fetch, timeout=60)
                self.assertGreater(len(fetch.urls), 1)  # Retried, not failed on first error.
        # An error followed by a good document still succeeds.
        self.assertEqual(self.wait(Responses(b"garbage", server_error, release())).sleeps, [5, 10])

    def test_the_wrong_version_is_never_accepted(self) -> None:
        # The timeout reason names what PyPI served instead, to diagnose stale CDN nodes.
        wrong = [
            (release(version="1.9.0"), "served pycubrid 1.9.0 with 2 wheel/sdist files"),
            (release(version="1.10.0rc1"), "served pycubrid 1.10.0rc1 with 2 wheel/sdist files"),
            (release(version="1.10"), "served pycubrid 1.10 with 2 wheel/sdist files"),
            (
                release(name="sqlalchemy-cubrid"),
                "served sqlalchemy-cubrid 1.10.0 with 2 wheel/sdist files",
            ),
            (release(types=()), "served pycubrid 1.10.0 with 0 wheel/sdist files"),
            (release(types=("bdist_egg",)), "served pycubrid 1.10.0 with 0 wheel/sdist files"),
        ]
        for document, reason in wrong:
            with self.subTest(document=document):
                with self.assertRaises(ValueError) as raised:
                    self.wait(Responses(document), timeout=60)
                self.assertEqual(
                    str(raised.exception),
                    f"PyPI does not serve pycubrid==1.10.0 after 60 s ({reason})",
                )

    def test_default_budget_is_600_seconds(self) -> None:
        self.assertEqual(smoke.PUBLICATION_TIMEOUT, 600)
        fake = FakeTime()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(ValueError) as raised:
            smoke.wait_for_pypi(
                "pycubrid", "1.10.0", sleep=fake.sleep, fetch=Responses(not_found), clock=fake.clock
            )
        self.assertEqual(fake.now, 600)
        self.assertIn("after 600 s", str(raised.exception))

    def test_name_normalization_follows_pypi(self) -> None:
        fake = FakeTime()
        document = release(name="SQLAlchemy_Cubrid", version="1.10.0")
        smoke.wait_for_pypi(
            "sqlalchemy-cubrid",
            "1.10.0",
            sleep=fake.sleep,
            fetch=Responses(document),
            clock=fake.clock,
        )
        self.assertEqual(fake.sleeps, [])

    def test_default_fetch_is_an_anonymous_https_get(self) -> None:
        response = SimpleNamespace(read=lambda: b"{}")
        opened = []

        @contextlib.contextmanager
        def urlopen(request, timeout):
            opened.append((request, timeout))
            yield response

        with patch.object(smoke.urllib.request, "urlopen", urlopen):
            self.assertEqual(smoke.fetch_pypi(URL), b"{}")
        request, timeout = opened[0]
        self.assertEqual(request.full_url, URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertNotIn("Authorization", request.headers)
        self.assertGreater(timeout, 0)


class SelectWaitsForPyPITests(unittest.TestCase):
    """select_releases polls PyPI only for a release request, before installing."""

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.event = self.root / "event.json"
        self.constraints = self.root / "constraints.txt"
        distribution = patch.object(
            smoke.metadata,
            "distribution",
            lambda name: SimpleNamespace(version="1.10.0", read_text=lambda _: None),
        )
        distribution.start()
        self.addCleanup(distribution.stop)

    def test_release_request_waits_before_the_no_cache_install(self) -> None:
        self.event.write_text(
            json.dumps({"client_payload": {"package": "pycubrid", "ref": "v1.10.0"}})
        )
        calls = []
        with (
            patch.object(smoke, "wait_for_pypi", lambda *a: calls.append(("wait", a))),
            patch.object(smoke.subprocess, "run", lambda c, **_: calls.append(("pip", c))),
            patch.object(smoke.subprocess, "check_call"),
        ):
            smoke.select_releases("repository_dispatch", self.event, self.constraints)
        self.assertEqual(calls[0], ("wait", ("pycubrid", "1.10.0")))
        self.assertEqual(calls[1][0], "pip")
        self.assertIn("--no-cache-dir", calls[1][1])
        self.assertIn("pycubrid==1.10.0", calls[1][1])

    def test_timeout_fails_before_any_install_or_fallback(self) -> None:
        self.event.write_text(json.dumps({"inputs": {"package": "pycubrid", "version": "1.10.0"}}))
        timeout = ValueError("PyPI does not serve pycubrid==1.10.0 after 600 s")
        with (
            patch.object(smoke, "wait_for_pypi", side_effect=timeout),
            patch.object(smoke.subprocess, "run") as install,
            patch.object(smoke.subprocess, "check_call") as bootstrap,
            self.assertRaisesRegex(ValueError, "does not serve pycubrid==1.10.0 after 600 s"),
        ):
            smoke.select_releases("workflow_dispatch", self.event, self.constraints)
        install.assert_not_called()
        bootstrap.assert_not_called()

    def test_non_release_runs_never_poll(self) -> None:
        self.event.write_text(json.dumps({"inputs": {"package": "latest", "version": ""}}))
        for event_name, path in (
            ("push", None),
            ("schedule", None),
            ("pull_request", None),
            ("workflow_dispatch", self.event),
        ):
            with self.subTest(event=event_name):
                with (
                    patch.object(smoke, "wait_for_pypi") as wait,
                    patch.object(smoke.urllib.request, "urlopen") as urlopen,
                    patch.object(smoke.subprocess, "run") as install,
                    patch.object(smoke.subprocess, "check_call") as bootstrap,
                ):
                    smoke.select_releases(event_name, path, self.constraints)
                wait.assert_not_called()
                urlopen.assert_not_called()
                install.assert_not_called()
                bootstrap.assert_called_once()

    def test_invalid_release_request_never_polls(self) -> None:
        self.event.write_text(
            json.dumps({"client_payload": {"package": "pycubrid", "ref": "main"}})
        )
        with (
            patch.object(smoke, "wait_for_pypi") as wait,
            patch.object(smoke.subprocess, "run"),
            patch.object(smoke.subprocess, "check_call"),
            self.assertRaises(ValueError),
        ):
            smoke.select_releases("repository_dispatch", self.event, self.constraints)
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
