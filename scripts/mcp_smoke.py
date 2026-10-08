#!/usr/bin/env python3
"""Real-usage smoke of the installed cubrid-mcp-server tool surface.

Builds the FastMCP server object and enumerates its registered tools rather
than only importing the package. This exercises the @mcp.tool registration
path and catches a broken server surface (e.g. a tool that fails to register)
that a bare ``import`` would silently pass. Tool handlers connect to CUBRID
lazily (only on first call via _db()), so listing the tool surface needs no
live database and no CUBRID_* environment variables.

Shared by smoke-test.yml (main, schedule, release verification) and the ci.yml
pull-request smoke lanes so the public tool contract is defined once.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import version as _pkg_version

# The public tool contract documented in the server's README. Every
# supported release must expose these; a rename or drop fails loudly.
EXPECTED = {
    "all_table_names",
    "filter_table_names",
    "schema_definitions",
    "describe_table",
    "list_indexes",
    "explain_query",
    "table_row_counts",
    "list_serials",
    "list_class_hierarchy",
    "execute_query",
}
# Tools added after v0.2.1 (e.g. health_check on main). Optional ONLY for
# the pinned v0.2.1 tag; the version gate below promotes health_check to
# required once a newer ref (see install step) is installed, so a newer
# dispatched release that drops it fails loudly.
OPTIONAL = {
    "health_check",
}


def _numeric_release(raw: str) -> tuple[int, ...]:
    # Parse the numeric (major, minor, patch) prefix without depending on
    # `packaging`, so a dispatched newer release must actually expose it.
    parts = []
    for chunk in raw.split(".")[:3]:
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def main() -> None:
    from cubrid_mcp_server.server import mcp

    expected = set(EXPECTED)
    optional = set(OPTIONAL)

    # Promote health_check from optional to required once the installed
    # cubrid-mcp-server is newer than v0.2.1 (the release that predates it).
    installed = _numeric_release(_pkg_version("cubrid-mcp-server"))
    if installed > (0, 2, 1):
        expected.add("health_check")
        optional.discard("health_check")
        print(f"cubrid-mcp-server {installed} > (0, 2, 1): requiring health_check tool")

    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    print(f"cubrid-mcp-server exposes {len(names)} tools: {sorted(names)}")

    missing = expected - names
    if missing:
        raise SystemExit(f"cubrid-mcp-server missing expected tools: {sorted(missing)}")

    # Fail on genuinely unknown tools so an upstream addition can't slip in
    # untracked; known-optional additions are tolerated on purpose.
    unknown = names - expected - optional
    if unknown:
        raise SystemExit(
            "cubrid-mcp-server exposes undocumented tools "
            f"(update the smoke-test contract): {sorted(unknown)}"
        )
    print("cubrid-mcp-server real-usage smoke OK")


if __name__ == "__main__":
    main()
