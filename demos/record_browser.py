#!/usr/bin/env python3
"""Record the browser demos with Playwright against apps that are already running.

Usage::

    python demos/record_browser.py dashboard  # Streamlit at DEMO_DASHBOARD_URL
    python demos/record_browser.py fastapi    # FastAPI at DEMO_FASTAPI_URL

Defaults: http://localhost:8501 (``templates/dashboard`` via ``docker compose up -d``)
and http://localhost:8000 (``quickstart/5min-fastapi`` via ``uvicorn app:app``).
Set DEMO_CHROME to a Chrome/Chromium binary to use it instead of Playwright's own
browser. The raw WebM is written to ``.demo-artifacts/raw/<name>.webm``; the
script fails, and writes nothing, if an expected element or response is missing.
See demos/README.md for converting the raw video into the committed GIF/MP4.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / ".demo-artifacts" / "raw"
VIEWPORT = {"width": 1280, "height": 720}


def record_dashboard(page: Page) -> None:
    base = os.environ.get("DEMO_DASHBOARD_URL", "http://localhost:8501")
    page.goto(base)
    grid = page.get_by_test_id("stDataFrame")
    expect(grid).to_be_visible(timeout=60_000)
    expect(page.get_by_text("Rows shown: 15")).to_be_visible()
    # The grid is a canvas; give it time to paint before the first frames that matter.
    page.wait_for_timeout(4_000)
    box = grid.bounding_box()
    if box is None:
        raise RuntimeError("dataframe has no bounding box")
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    for _ in range(4):
        page.mouse.wheel(0, 120)
        page.wait_for_timeout(500)
    page.wait_for_timeout(1_000)
    for _ in range(4):
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(300)
    page.wait_for_timeout(1_000)
    page.get_by_role("button", name="Reset Demo Data").click()
    # Only the rerun triggered by the click renders this message.
    reset_done = page.get_by_text("Demo tables recreated and reseeded.")
    expect(reset_done).to_be_visible(timeout=30_000)
    expect(page.get_by_text("Rows shown: 15")).to_be_visible()
    page.wait_for_timeout(2_000)
    page.get_by_role("button", name="Refresh").click()
    # st.rerun() starts a run without the Reset click, which drops the message.
    expect(reset_done).to_have_count(0, timeout=30_000)
    expect(page.get_by_text("Rows shown: 15")).to_be_visible()
    page.wait_for_timeout(3_000)


def _open_operation(page: Page, method: str, path: str) -> None:
    block = page.locator(f"#operations-default-{method}_{path}")
    block.locator(".opblock-summary").click()
    page.wait_for_timeout(600)
    block.get_by_role("button", name="Try it out").click()
    page.wait_for_timeout(600)


def record_fastapi(page: Page) -> None:
    base = os.environ.get("DEMO_FASTAPI_URL", "http://localhost:8000")
    page.goto(base + "/docs")
    expect(page.get_by_text("CUBRID Quickstart API")).to_be_visible(timeout=30_000)
    page.wait_for_timeout(1_500)

    post = page.locator("#operations-default-create_item_items_post")
    _open_operation(page, "create_item", "items_post")
    body = post.locator("textarea.body-param__text")
    body.fill("")
    body.type('{"val": "hello from Swagger UI"}', delay=35)
    page.wait_for_timeout(400)
    post.get_by_role("button", name="Execute").click()
    created = post.locator(".live-responses-table tbody .response-col_status").first
    expect(created).to_have_text("200", timeout=15_000)
    post.locator(".live-responses-table").scroll_into_view_if_needed()
    page.wait_for_timeout(2_500)

    listing = page.locator("#operations-default-list_items_items_get")
    listing.scroll_into_view_if_needed()
    _open_operation(page, "list_items", "items_get")
    listing.get_by_role("button", name="Execute").click()
    listed = listing.locator(".live-responses-table tbody .response-col_status").first
    expect(listed).to_have_text("200", timeout=15_000)
    expect(listing.locator(".live-responses-table")).to_contain_text("hello from Swagger UI")
    listing.locator(".live-responses-table").scroll_into_view_if_needed()
    page.wait_for_timeout(3_000)


SCENARIOS = {"dashboard": record_dashboard, "fastapi": record_fastapi}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"{args.name}.webm"
    # A failed run must not leave an older recording for build_media.sh to reuse.
    target.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as playwright:
        launch = (
            {"executable_path": os.environ["DEMO_CHROME"]} if "DEMO_CHROME" in os.environ else {}
        )
        browser = playwright.chromium.launch(**launch)
        context = browser.new_context(
            viewport=VIEWPORT, record_video_dir=tmp, record_video_size=VIEWPORT
        )
        page = context.new_page()
        try:
            SCENARIOS[args.name](page)
        finally:
            video = page.video
            context.close()
            browser.close()
        if video is None:
            raise RuntimeError("Playwright recorded no video")
        shutil.move(video.path(), target)
    print(f"Recorded {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
