#!/usr/bin/env python3
"""Agent-review evidence gate: decide from GitHub review records whether a PR
has the review that AGENTS.md requires before merging (#351).

ADVISORY ONLY. The verdict is published as a GitHub Actions check, and any PR
can publish a check with the same name from a workflow of its own, so this check
must not be made a required status check until it is posted from an identity a
PR cannot impersonate, such as a GitHub App (tracked separately).

``.github/workflows/agent-review.yml`` runs this file from the **base branch**
(never the PR's copy, except for the bootstrap run described below) with a
read-only token. It only reads the GitHub REST and GraphQL APIs; it never checks
out or runs PR code. Exit status 0 passes the ``agent-review`` check and 1 fails
it; any API error, missing field or truncated listing fails closed.

Evidence is only what GitHub records for the PR. The PR body, its checkboxes,
review requests and CI results are never evidence. The rule (maintainer
decision, 2026-10-15) is a substantive Copilot review or a maintainer's review.
A review counts only when:

* it is submitted (not ``PENDING``) and not ``DISMISSED``, and its account
  still exists (a deleted account's review is reported and never counts);
* its reviewer is not the PR author and authored or committed no commit in the
  PR (self-review), other than a merge commit that only brings in the base
  branch (an "Update branch" sync);
* it is current: its ``commit_id`` is the PR head, or the PR's change against
  the base branch is identical at both commits (file names, statuses and exact
  patches, hunk line numbers included; the blob SHA for a file without a
  patch). A base sync or a rebase that changes nothing of the PR carries the
  review forward without spending an AI round;
* it comes from GitHub Copilot code review or from a maintainer
  (``MAINTAINERS``, the code owners). Other people, other bots and other AI
  agents are reported but never count.

``APPROVED`` and ``COMMENTED`` are different evidence:

* A maintainer's ``APPROVED`` review is formal approval. It satisfies every PR,
  and it is the only evidence that authorizes a change to a protected path
  (``PROTECTED_PATHS``, the no-bypass list).
* A ``COMMENTED`` review is an assessment, not approval. A maintainer's
  ``COMMENTED`` review counts only when it opens at least one inline thread;
  review-body text alone does not. A Copilot review counts only when it is
  substantive: it has inline comments, or its overview states a verdict, an
  assessment sentence and an open-findings count. A summary of what changed,
  or an error or quota notice, is not an assessment. A Copilot review
  satisfies only a PR that changes no protected path, and only within the AI
  review budget (``AI_REVIEW_BUDGET`` published Copilot rounds); past it the
  final head needs a maintainer's review.

A maintainer whose latest decision is ``CHANGES_REQUESTED`` blocks the gate,
even when that maintainer also committed to the PR. Among threads opened by
Copilot or a maintainer, an unresolved critical, high-severity or security
finding blocks (even when outdated), and so does one the PR author resolved.

Exempt PRs pass with a notice: release-please candidates (author
``github-actions[bot]``, branch ``release-please--``, same repository) that
change only the files release-please writes (``RELEASE_FILES``) and no
protected path, governed by RELEASING.md; and Dependabot PRs (author
``dependabot[bot]``, branch ``dependabot/``, same repository) whose commits
Dependabot created through GitHub (committer ``web-flow``, verified signature)
or are base syncs. Every other PR, human or agent, is evaluated the same way.

``--bootstrap`` is used only while the base branch does not contain this file
yet (the PR that adds it): the verdict is printed but the step always exits 0,
because the PR's own copy is not trusted to enforce.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.client import HTTPException
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

# Repository policy. Mirrors of this gate in sibling repositories change only
# these constants.
PROTECTED_PATHS = (
    # Every workflow and composite action: any of them can gain write permissions
    # or impersonate a check; smoke-test.yml verifies sibling repositories' releases.
    ".github/workflows/*",
    ".github/actions/*",
    ".github/dependabot.yml",
    # The release smoke scripts that smoke-test.yml runs for other repositories.
    "scripts/release_smoke.py",
    "scripts/mcp_smoke.py",
    # Lane selection: ci_scope.py decides which CI lanes run (ci.yml, the pr-smoke
    # action, smoke-test.yml) and driver_floors.py which goldens the floor lane runs.
    "scripts/ci_scope.py",
    "scripts/driver_floors.py",
    # The gate itself and the tests that pin its behaviour.
    "scripts/agent_review_gate.py",
    "tests/test_agent_review_gate.py",
)
# The code owners in .github/CODEOWNERS (a test keeps the two equal).
MAINTAINERS = frozenset({"yeongseon", "paikend"})
AI_REVIEW_BUDGET = 2
COPILOT_LOGINS = frozenset({"copilot-pull-request-reviewer[bot]"})
# GraphQL and REST spell Copilot's comment author differently.
COPILOT_THREAD_AUTHORS = frozenset(
    {"copilot-pull-request-reviewer", "copilot-pull-request-reviewer[bot]", "Copilot"}
)
RELEASE_AUTHOR = "github-actions[bot]"
RELEASE_BRANCH_PREFIX = "release-please--"
DEPENDABOT = "dependabot[bot]"
DEPENDABOT_BRANCH_PREFIX = "dependabot/"
# Every file release-please writes here. This repository has no release-please
# configuration, so no pull request is exempt as a release candidate.
RELEASE_FILES: frozenset[str] = frozenset()

API = "https://api.github.com"
PAGE = 100
MAX_LISTED_FILES = 3000  # GitHub lists at most 3000 files of a PR.
MAX_LISTED_COMMITS = 250  # ... and 250 commits.
COMPARE_FILE_LIMIT = 300  # A compare lists at most 300 files.

COPILOT_VERDICT = re.compile(r"^###\s+\S+\s+(?P<verdict>[A-Za-z][^\n]*?)\s*$", re.M)
COPILOT_FINDINGS = re.compile(r"\b(?P<count>\d+)\s+open\s+findings?\b", re.I)
COPILOT_NOTICE = re.compile(
    r"wasn't able to review|was unable to review|unable to review|could not review"
    r"|encountered an error|quota|rate limit|usage limit",
    re.I,
)
COPILOT_SEVERITY = re.compile(
    r'alt="(?P<severity>[A-Za-z]+) severity".*?#discussion_r(?P<comment>\d+)', re.I
)
BLOCKING_SEVERITIES = frozenset({"critical", "high"})
SECURITY_WORDS = re.compile(
    r"\b(?:critical|security|vulnerab\w*|exploit\w*|injection|cve-\d+|credentials?"
    r"|secrets?|privileges?|bypass\w*)\b",
    re.I,
)
ROUTE_LINE = re.compile(r"^[-*\s]*Development route:\s*(?P<route>.+)$", re.I | re.M)

THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          isResolved
          isOutdated
          resolvedBy { login }
          comments(first: 1) {
            nodes { databaseId body url path author { login } }
          }
        }
      }
    }
  }
}
"""


class GateError(Exception):
    """Missing or unreadable API data: the gate fails closed."""


# --------------------------------------------------------------------------- fetch


class Client:
    """Minimal read-only GitHub API client (stdlib only)."""

    def __init__(self, token: str) -> None:
        if not token:
            raise GateError("no API token (GH_TOKEN) is set")
        self.token = token

    def _request(self, url: str, data: bytes | None = None) -> tuple[Any, str]:
        request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response), response.headers.get("Link", "")
        except urllib.error.HTTPError as exc:
            raise GateError(f"HTTP {exc.code} for {url}") from exc
        except (OSError, HTTPException, ValueError) as exc:
            raise GateError(f"request failed for {url}: {exc}") from exc

    def get(self, path: str) -> Any:
        return self._request(f"{API}/{path}")[0]

    def get_optional(self, path: str) -> Any:
        """Like get(), but None for a 404 or 422 (for example a commit that a
        force push removed)."""
        try:
            return self.get(path)
        except GateError as exc:
            if re.match(r"HTTP (?:404|422) ", str(exc)):
                return None
            raise

    def paginate(self, path: str) -> list[Any]:
        sep = "&" if "?" in path else "?"
        url: str | None = f"{API}/{path}{sep}per_page={PAGE}"
        items: list[Any] = []
        while url:
            page, link = self._request(url)
            if not isinstance(page, list):
                raise GateError(f"expected a list from {url}")
            items.extend(page)
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = match.group(1) if match else None
        return items

    def graphql(self, query: str, variables: dict[str, Any]) -> Any:
        body = json.dumps({"query": query, "variables": variables}).encode()
        result, _ = self._request(f"{API}/graphql", body)
        if not isinstance(result, dict) or result.get("errors") or "data" not in result:
            raise GateError(
                f"GraphQL error: {result.get('errors') if isinstance(result, dict) else result}"
            )
        return result["data"]


def fetch(client: Client, repo: str, number: int) -> dict[str, Any]:
    """Collect every record the decision needs. Raises GateError when any is
    missing or truncated."""
    owner, name = repo.split("/", 1)
    pr = client.get(f"repos/{repo}/pulls/{number}")
    reviews = client.paginate(f"repos/{repo}/pulls/{number}/reviews")
    comments = client.paginate(f"repos/{repo}/pulls/{number}/comments")
    commits = client.paginate(f"repos/{repo}/pulls/{number}/commits")
    files = client.paginate(f"repos/{repo}/pulls/{number}/files")
    threads: list[Any] = []
    after: str | None = None
    while True:
        data = client.graphql(
            THREADS_QUERY, {"owner": owner, "name": name, "number": number, "after": after}
        )
        try:
            block = data["repository"]["pullRequest"]["reviewThreads"]
            threads.extend(block["nodes"])
            if not block["pageInfo"]["hasNextPage"]:
                break
            after = block["pageInfo"]["endCursor"]
        except (KeyError, TypeError) as exc:
            raise GateError(f"unexpected review-thread data: {exc}") from exc
    head = _require(pr, "head", "sha")
    # The PR's change (its diff against the base branch) as of the head, each
    # reviewed commit, and each merge commit and its first parent.
    base = urllib.parse.quote(_require(pr, "base", "ref"), safe="")
    wanted = [head, *(r.get("commit_id") for r in reviews)]
    for item in commits:
        parents = item.get("parents") or []
        if len(parents) >= 2:
            wanted += [_require(item, "sha"), _require(parents[0], "sha")]
    diffs: dict[str, Any] = {}
    for sha in wanted:
        if sha and sha not in diffs:
            diffs[sha] = diff_fingerprint(
                client.get_optional(f"repos/{repo}/compare/{base}...{sha}")
            )
    return {
        "repo": repo,
        "pr": pr,
        "reviews": reviews,
        "comments": comments,
        "commits": commits,
        "files": files,
        "threads": threads,
        "diffs": diffs,
    }


# ------------------------------------------------------------------------ evaluate


@dataclass
class Verdict:
    passed: bool = False
    exempt: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def _require(record: Any, *keys: str) -> Any:
    value = record
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise GateError(f"API data lacks {'.'.join(keys)}")
        value = value[key]
    return value


def _login(user: Any) -> str:
    return user.get("login", "") if isinstance(user, dict) else ""


def _identity(record: dict[str, Any], key: str, what: str) -> str:
    """The login in ``record[key]``: "" for an explicit null (a deleted account);
    a missing field or an account without a login fails closed."""
    if key not in record:
        raise GateError(f"API data lacks {what}")
    user = record[key]
    if user is None:
        return ""
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or not login:
        raise GateError(f"API data has {what} without a login")
    return login


def _paths(files: Iterable[dict[str, Any]]) -> set[str]:
    paths = set()
    for item in files:
        paths.add(_require(item, "filename"))
        if item.get("previous_filename"):
            paths.add(item["previous_filename"])
    return paths


def protected_paths(paths: Iterable[str]) -> list[str]:
    return sorted(p for p in paths if any(fnmatch.fnmatchcase(p, g) for g in PROTECTED_PATHS))


def copilot_assessment(body: str, inline_comments: int) -> tuple[str, str]:
    """Classify a Copilot review as "substantive", "summary" or "notice", and why."""
    verdict = COPILOT_VERDICT.search(body)
    findings = COPILOT_FINDINGS.search(body)
    if verdict and findings and verdict.end() < findings.start():
        between = re.sub(r"<[^>]*>|[*_`]", " ", body[verdict.end() : findings.start()])
        if re.search(r"[A-Za-z]{3,}.*[A-Za-z]{3,}", between):
            return "substantive", (
                f"verdict '{verdict['verdict']}' with an assessment and "
                f"{findings['count']} open finding(s)"
            )
    if inline_comments:
        return "substantive", f"{inline_comments} inline comment(s)"
    if COPILOT_NOTICE.search(body):
        return "notice", "an error or quota notice, not a review"
    return "summary", "a change summary without an assessment"


def diff_fingerprint(compare: Any) -> list[list[str]] | None:
    """The PR's change as of one commit, from a ``base...commit`` compare: per
    file its name, status, previous name and exact patch, hunk line numbers
    included, so an edit moved to another place never matches. None when the
    compare is missing or cannot show the whole change."""
    if not isinstance(compare, dict):
        return None
    files = compare.get("files")
    if not isinstance(files, list) or len(files) >= COMPARE_FILE_LIMIT:
        return None
    result = []
    for item in files:
        patch = item.get("patch")
        if not isinstance(item.get("filename"), str):
            return None
        if patch is None:
            # Binary, too large to show, or a pure rename: compare the blob.
            blob = item.get("sha")
            if not isinstance(blob, str) or not blob:
                return None
            content = f"blob {blob}"
        else:
            content = patch
        result.append(
            [
                item["filename"],
                str(item.get("status")),
                item.get("previous_filename") or "",
                content,
            ]
        )
    return sorted(result)


def _same_change(data: dict[str, Any], one: str, other: str) -> bool:
    """Whether two commits carry exactly the same PR change."""
    first = data["diffs"].get(one)
    return first is not None and first == data["diffs"].get(other)


def _neutral_merge(commit: dict[str, Any], data: dict[str, Any]) -> bool:
    """A merge commit that only brings in the base branch: the PR's change is the
    same before (its first parent) and after it."""
    parents = commit.get("parents") or []
    if len(parents) < 2:
        return False
    return _same_change(data, commit.get("sha", ""), parents[0].get("sha", ""))


def _dependabot_made(commit: dict[str, Any]) -> bool:
    """A commit Dependabot created through GitHub: authored by Dependabot,
    committed by GitHub (``web-flow``) and carrying a verified signature. An
    amended or re-signed commit keeps the author but not this provenance."""
    verification = (commit.get("commit") or {}).get("verification") or {}
    return (
        _login(commit.get("author")) == DEPENDABOT
        and _login(commit.get("committer")) == "web-flow"
        and verification.get("verified") is True
    )


def _exemption(data: dict[str, Any]) -> str:
    pr = data["pr"]
    author = _login(pr.get("user"))
    head_repo = (pr.get("head") or {}).get("repo") or {}
    same_repo = head_repo.get("full_name") == data["repo"]
    branch = _require(pr, "head", "ref")
    if author == RELEASE_AUTHOR and branch.startswith(RELEASE_BRANCH_PREFIX) and same_repo:
        paths = _paths(data["files"])
        if paths <= RELEASE_FILES and not protected_paths(paths):
            return "release-please candidate: review and CI follow RELEASING.md"
    if author == DEPENDABOT and branch.startswith(DEPENDABOT_BRANCH_PREFIX) and same_repo:
        if all(_dependabot_made(c) or _neutral_merge(c, data) for c in data["commits"]):
            return "Dependabot update: dependency-only, merged by its required checks"
    return ""


def evaluate(data: dict[str, Any], event_head: str = "") -> Verdict:
    verdict = Verdict()
    pr = data["pr"]
    head = _require(pr, "head", "sha")
    author = _login(_require(pr, "user"))
    if not author:
        raise GateError("API data lacks the PR author")
    if event_head and event_head != head:
        verdict.errors.append(
            f"the event head {event_head[:12]} is no longer the PR head {head[:12]}; "
            "the run for the current head decides"
        )
        return verdict
    if int(_require(pr, "commits")) > len(data["commits"]) or len(data["commits"]) >= (
        MAX_LISTED_COMMITS
    ):
        raise GateError("the commit listing is incomplete (GitHub lists at most 250)")
    if int(_require(pr, "changed_files")) > len(data["files"]) or len(data["files"]) >= (
        MAX_LISTED_FILES
    ):
        raise GateError("the changed-file listing is incomplete (GitHub lists at most 3000)")

    exempt = _exemption(data)
    if exempt:
        verdict.passed, verdict.exempt = True, exempt
        verdict.notes.append(f"Exempt: {exempt}.")
        return verdict

    route = ROUTE_LINE.search(pr.get("body") or "")
    verdict.notes.append(
        "Declared development route (reported only, never evidence): "
        + (route["route"].strip() if route else "not stated")
    )
    for login in sorted(_login(u) for u in pr.get("requested_reviewers") or []):
        verdict.notes.append(f"Pending review request for {login}: not evidence.")
    for team in pr.get("requested_teams") or []:
        verdict.notes.append(f"Pending review request for team {team.get('slug')}: not evidence.")

    pr_paths = _paths(data["files"])
    protected = protected_paths(pr_paths)
    if protected:
        verdict.notes.append(
            "Protected (no-bypass) paths changed; a maintainer's APPROVED review "
            "of the head is required: " + ", ".join(protected)
        )

    committers = set()
    for commit in data["commits"]:
        if not _neutral_merge(commit, data):
            # null: the commit's email maps to no GitHub account.
            committers.add(_identity(commit, "author", "a commit's author"))
            committers.add(_identity(commit, "committer", "a commit's committer"))
    committers -= {"", "web-flow"}

    # Inline comments that open a thread; a reply to an existing thread is not an
    # assessment of the change (GitHub records each reply as a COMMENTED review).
    inline: dict[int, int] = {}
    for comment in data["comments"]:
        review_id = comment.get("pull_request_review_id")
        if review_id is not None and comment.get("in_reply_to_id") is None:
            inline[review_id] = inline.get(review_id, 0) + 1

    severities: dict[int, str] = {}
    approved: list[str] = []
    commented: list[str] = []
    ai_current: list[tuple[int, str]] = []
    decisions: dict[str, str] = {}
    rounds = self_reviews = 0
    reviews = []
    for item in data["reviews"]:
        state = _require(item, "state")
        if _require(item, "user") is None:
            verdict.notes.append(f"Ignored a {state} review by a deleted account.")
            continue
        if not _login(item["user"]):
            raise GateError("a review has no reviewer login")
        if state == "PENDING":
            continue
        if not item.get("submitted_at"):
            raise GateError(f"a {state} review has no submission time")
        reviews.append(item)
    for review in sorted(reviews, key=lambda r: (r["submitted_at"], r.get("id", 0))):
        state = _require(review, "state")
        user = _require(review, "user")
        login = _login(user)
        sha = review.get("commit_id") or ""
        body = review.get("body") or ""
        comments = inline.get(review.get("id", -1), 0)
        current = sha == head or _same_change(data, sha, head)
        where = "the head" if sha == head else sha[:12]
        if sha != head and current:
            where += " (same change as the head, carried forward)"
        label = f"{state} review by {login} at {where}"

        if login in COPILOT_LOGINS:
            for match in COPILOT_SEVERITY.finditer(body):
                severities[int(match["comment"])] = match["severity"].lower()
            kind, why = copilot_assessment(body, comments)
            if kind == "notice":
                verdict.notes.append(f"Ignored {label}: {why}; not a review round.")
                continue
            rounds += 1
            if kind != "substantive":
                verdict.warnings.append(f"Rejected {label} (AI round {rounds}): {why}.")
            elif not current:
                verdict.notes.append(
                    f"Stale {label} (AI round {rounds}): the code changed after it."
                )
            else:
                ai_current.append((rounds, f"{label} (AI round {rounds}): {why}"))
            continue
        maintainer = user.get("type") == "User" and login in MAINTAINERS
        # A maintainer's decision is recorded before the self-review filters, so a
        # maintainer who also committed can still block with CHANGES_REQUESTED.
        if maintainer and state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            decisions[login] = state
        if login == author:
            self_reviews += 1
            continue
        if login in committers:
            verdict.warnings.append(f"Rejected {label}: the reviewer authored commits in this PR.")
            continue
        if user.get("type") != "User":
            verdict.warnings.append(f"Rejected {label}: a bot other than Copilot code review.")
            continue
        if not maintainer:
            verdict.warnings.append(
                f"Rejected {label}: {login} is not a maintainer (a code owner); only "
                "Copilot or a maintainer can satisfy the review route."
            )
            continue
        if state == "APPROVED" and current:
            approved.append(login)
            verdict.evidence.append(f"{label}: formal approval.")
        elif state == "COMMENTED" and current:
            if comments:
                commented.append(login)
                verdict.evidence.append(f"{label}: assessment (COMMENTED is not approval).")
            else:
                verdict.warnings.append(
                    f"Rejected {label}: a COMMENTED review counts only when it opens an "
                    "inline thread; approve instead to accept the change."
                )
        elif state in {"APPROVED", "COMMENTED"}:
            verdict.notes.append(f"Stale {label}: the code changed after it.")

    if self_reviews:
        verdict.warnings.append(
            f"Rejected {self_reviews} review(s) by the PR author {author}: self-review "
            "(replies to review threads are recorded as reviews too)."
        )
    approvers = [login for login in approved if decisions.get(login) == "APPROVED"]
    for login, state in sorted(decisions.items()):
        if state == "CHANGES_REQUESTED":
            verdict.errors.append(f"{login} requested changes; their latest decision blocks.")

    # Past the budget, no Copilot review counts alone, not even an earlier round.
    over = rounds > AI_REVIEW_BUDGET
    within = [] if over else [text for _, text in ai_current]
    beyond = [text for _, text in ai_current] if over else []
    verdict.evidence.extend(within)
    for text in beyond:
        verdict.warnings.append(
            f"Not counted alone: {text}; this PR has {rounds} Copilot rounds, past the "
            f"{AI_REVIEW_BUDGET}-round AI review budget, so the head needs a "
            "maintainer's review."
        )

    replies: dict[int, list[str]] = {}
    for comment in data["comments"]:
        if comment.get("in_reply_to_id") is not None:
            replies.setdefault(comment["in_reply_to_id"], []).append(comment.get("body") or "")
    for thread in data["threads"]:
        first = ((thread.get("comments") or {}).get("nodes") or [None])[0]
        if not isinstance(first, dict):
            raise GateError("a review thread has no first comment")
        root = first.get("databaseId")
        body = first.get("body")
        if not isinstance(root, int) or isinstance(root, bool) or root <= 0:
            raise GateError("a review thread's first comment has no comment ID")
        if not isinstance(body, str):
            raise GateError("a review thread's first comment has no body")
        resolved = thread.get("isResolved")
        if not isinstance(resolved, bool):
            raise GateError("a review thread has no resolution state")
        opener = _identity(first, "author", "a review thread's author")
        place = f"{first.get('path')} ({first.get('url')})"
        if opener not in COPILOT_THREAD_AUTHORS and opener not in MAINTAINERS:
            if not resolved:
                verdict.notes.append(
                    f"Unresolved thread at {place} by {opener or 'a deleted account'}: not "
                    "opened by Copilot or a maintainer, so it does not block."
                )
            continue
        severity = severities.get(root, "")
        texts = [body, *replies.get(root, [])]
        serious = severity in BLOCKING_SEVERITIES or any(SECURITY_WORDS.search(t) for t in texts)
        if not resolved:
            if serious:
                verdict.errors.append(
                    f"Unresolved {severity + '-severity ' if severity else ''}"
                    + ("" if severity in BLOCKING_SEVERITIES else "security-relevant ")
                    + f"finding by "
                    f"{opener} at {place}"
                    + (" (outdated, still unresolved)" if thread.get("isOutdated") else "")
                )
            else:
                verdict.notes.append(f"Unresolved thread at {place}.")
        elif serious and _identity(thread, "resolvedBy", "a resolved thread's resolver") == author:
            verdict.errors.append(
                f"The {severity or 'security-relevant'} finding at {place} was resolved by "
                "the PR author; a maintainer must unresolve and resolve it after checking."
            )

    if protected:
        satisfied = bool(approvers)
        if not satisfied:
            verdict.errors.append(
                "Protected paths changed without a maintainer's APPROVED review of the "
                "head. COMMENTED and Copilot reviews do not authorize them."
            )
    else:
        satisfied = bool(approvers or commented or within)
        if not satisfied:
            verdict.errors.append(
                "No qualifying review of the head: needs a substantive submitted Copilot review "
                f"(within {AI_REVIEW_BUDGET} rounds) or a maintainer's APPROVED review, or "
                "COMMENTED review that opens an inline thread."
            )
    verdict.passed = satisfied and not verdict.errors
    return verdict


# ---------------------------------------------------------------------------- main


def one_line(text: str) -> str:
    """Report text as a single line: messages quote PR-controlled strings (file
    paths, thread paths and URLs, logins), and a line break inside one could
    start a workflow command such as ``::error::`` in the log."""
    return re.sub(r"[\r\n\u0085\u2028\u2029]", " ", text)


def command_data(text: str) -> str:
    """Escape a workflow-command message as GitHub's runner expects."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def render(verdict: Verdict, number: int, bootstrap: bool) -> str:
    status = "exempt" if verdict.exempt else ("passed" if verdict.passed else "failed")
    lines = [f"### agent-review: {status} (PR #{number})", ""]
    if bootstrap:
        lines += [
            "> Bootstrap run: the base branch has no gate yet, so this verdict is advisory.",
            "",
        ]
    for title, items in (
        ("Blocking", verdict.errors),
        ("Counted evidence", verdict.evidence),
        ("Rejected or attention", verdict.warnings),
        ("Notes", verdict.notes),
    ):
        if items:
            lines.append(f"**{title}**")
            lines += [f"- {one_line(item)}" for item in items]
            lines.append("")
    lines.append(
        (
            "Re-run this check after Copilot reviews (its review run waits for approval) "
            "or after resolving a thread (resolution sends no event)."
        )
    )
    return "\n".join(lines) + "\n"


def main(
    argv: list[str] | None = None,
    client_factory: Callable[[str], Client] = Client,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--event-head-sha", default="")
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args(argv)

    try:
        data = fetch(client_factory(os.environ.get("GH_TOKEN", "")), args.repo, args.pr)
        verdict = evaluate(data, args.event_head_sha)
    except GateError as exc:
        verdict = Verdict(errors=[f"Failing closed on missing API data: {exc}"])

    report = render(verdict, args.pr, args.bootstrap)
    sys.stdout.write(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report)
    for message in verdict.errors:
        print(f"::error title=agent-review::{command_data(message)}")
    for message in verdict.warnings:
        print(f"::warning title=agent-review::{command_data(message)}")
    if args.bootstrap:
        print("::warning title=agent-review::Bootstrap run: advisory only.")
        return 0
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
