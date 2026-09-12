#!/usr/bin/env python3
"""Render a terminal demo GIF from a scripted sequence.

Pure Python terminal GIF renderer — works in headless environments.
Produces professional-looking terminal screenshots that show commands
being typed and output appearing, with syntax highlighting.

Usage:
    python render_gif.py script.json output.gif
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import imageio

# ── Theme ─────────────────────────────────────────────────────────
BG = (30, 30, 46)  # Catppuccin Mocha base
FG = (205, 214, 244)  # Catppuccin Mocha text
GREEN = (166, 227, 161)  # prompt green
CYAN = (137, 220, 235)  # strings
YELLOW = (249, 226, 175)  # keywords
BLUE = (137, 180, 250)  # function names
COMMENT = (108, 112, 134)  # comments
RED = (243, 139, 168)  # errors
TITLEBAR = (49, 50, 68)  # window titlebar

FONT_MONO = None
FONT_TITLE = None


def _load_fonts(size: int = 18):
    global FONT_MONO, FONT_TITLE
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
    ]:
        if Path(path).exists():
            FONT_MONO = ImageFont.truetype(path, size)
            title_path = path.replace("Mono", "").replace("-Regular", "-Bold")
            if not Path(title_path).exists():
                title_path = path
            FONT_TITLE = ImageFont.truetype(title_path, size - 4)
            return
    FONT_MONO = ImageFont.load_default()
    FONT_TITLE = ImageFont.load_default()


def colorize_line(line: str) -> list[tuple[str, tuple[int, int, int]]]:
    """Split a line into colored segments based on simple syntax rules."""
    if line.startswith("$ "):
        return [("$ ", GREEN), (line[2:], FG)]
    if line.startswith(">>> ") or line.startswith("... "):
        prefix = line[:4]
        rest = line[4:]
        segments = [(prefix, GREEN)]
        # Color Python-like syntax
        for kw in [
            "import ",
            "from ",
            "print(",
            "def ",
            "class ",
            "async ",
            "await ",
            "with ",
            "return ",
        ]:
            if kw in rest:
                idx = rest.index(kw)
                if idx > 0:
                    segments.append((rest[:idx], FG))
                segments.append((kw, YELLOW))
                rest = rest[idx + len(kw) :]
                break
        if rest:
            # Color strings
            if '"' in rest or "'" in rest:
                parts = rest.replace('"', '\x00"\x00').split("\x00")
                for p in parts:
                    if p.startswith('"') or p.startswith("'"):
                        segments.append((p, CYAN))
                    elif p:
                        segments.append((p, FG))
            else:
                segments.append((rest, FG))
        return segments
    if line.startswith("# ") or line.startswith("-- "):
        return [(line, COMMENT)]
    if "✓" in line or "OK" in line or "Success" in line:
        return [(line, GREEN)]
    if "✗" in line or "Error" in line or "FAIL" in line:
        return [(line, RED)]
    return [(line, FG)]


def render_frame(
    lines: list[str],
    width: int = 1200,
    height: int = 600,
    cursor_line: int = -1,
    show_cursor: bool = True,
) -> Image.Image:
    """Render a single terminal frame."""
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Title bar
    bar_h = 36
    draw.rectangle([0, 0, width, bar_h], fill=TITLEBAR)
    # Traffic light dots
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        x = 20 + i * 28
        draw.ellipse([x, bar_h // 2 - 7, x + 14, bar_h // 2 + 7], fill=color)
    # Title text
    if FONT_TITLE:
        draw.text((width // 2 - 60, 8), "Terminal", font=FONT_TITLE, fill=FG)

    # Terminal content
    line_h = 28
    y = bar_h + 12
    for i, line in enumerate(lines):
        segments = colorize_line(line)
        x = 24
        for text, color in segments:
            if FONT_MONO:
                draw.text((x, y), text, font=FONT_MONO, fill=color)
                bbox = FONT_MONO.getbbox(text)
                x += bbox[2] - bbox[0] + 2 if bbox else len(text) * 10
            else:
                draw.text((x, y), text, fill=color)
                x += len(text) * 10

        # Cursor on current line
        if show_cursor and i == cursor_line:
            cursor_x = x + 4
            draw.rectangle([cursor_x, y + 2, cursor_x + 10, y + 22], fill=FG)

        y += line_h
        if y > height - 20:
            break

    return img


def render_gif(script_path: str, output_path: str, fps: int = 2):
    """Render a GIF from a JSON script.

    Script format:
    {
        "title": "pycubrid demo",
        "steps": [
            {"type": "type", "text": "pip install pycubrid", "speed": 50},
            {"type": "enter"},
            {"type": "sleep", "ms": 2000},
            {"type": "output", "text": "Successfully installed pycubrid-1.7.0"},
            {"type": "python", "code": "import pycubrid", "result": "..."}
        ]
    }
    """
    _load_fonts()

    with open(script_path) as f:
        script = json.load(f)

    frames: list[Image.Image] = []
    visible_lines: list[str] = []
    width = script.get("width", 1200)
    height = script.get("height", 600)

    for step in script["steps"]:
        stype = step["type"]

        if stype == "type":
            text = step["text"]
            # speed handled per-character above
            # Show typing character by character
            for i in range(1, len(text) + 1):
                lines = visible_lines + ["$ " + text[:i]]
                frames.append(render_frame(lines, width, height, cursor_line=len(lines) - 1))

        elif stype == "python":
            code = step["code"]
            result = step.get("result", "")
            lines = visible_lines + [">>> " + code]
            frames.append(render_frame(lines, width, height, cursor_line=len(lines) - 1))
            if result:
                visible_lines = lines + [result]
                frames.append(render_frame(visible_lines, width, height, cursor_line=-1))

        elif stype == "enter":
            if visible_lines:
                visible_lines[-1] = visible_lines[-1]  # keep as-is
            frames.append(render_frame(visible_lines, width, height, cursor_line=-1))

        elif stype == "output":
            text = step["text"]
            visible_lines = visible_lines + [text]
            frames.append(render_frame(visible_lines, width, height, cursor_line=-1))

        elif stype == "sleep":
            ms = step.get("ms", 1000)
            n_pause = max(1, ms // (1000 // fps))
            for _ in range(n_pause):
                frames.append(render_frame(visible_lines, width, height, cursor_line=-1))

        elif stype == "clear":
            visible_lines = []

    if not frames:
        frames = [render_frame(["$ echo 'empty'"], width, height)]

    # Save GIF
    imageio.mimsave(output_path, frames, fps=fps, loop=0)
    print(f"✓ {output_path} — {len(frames)} frames, {width}x{height}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <script.json> <output.gif>")
        sys.exit(1)
    render_gif(sys.argv[1], sys.argv[2])
