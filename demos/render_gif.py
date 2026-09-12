#!/usr/bin/env python3
"""Render a fast, crisp terminal demo GIF from a JSON script.

Optimized for GitHub README: 8fps, 800x450, 6-10 seconds.
Usage: python render_gif.py script.json output.gif
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont

BG = (13, 17, 23)
FG = (230, 237, 243)
GREEN = (63, 185, 80)
CYAN = (121, 192, 255)
YELLOW = (227, 179, 81)
DIM = (139, 148, 158)
RED = (248, 113, 113)
TITLE_BG = (22, 27, 34)
BORDER = (48, 54, 61)

FPS = 8
WIDTH = 800
HEIGHT = 450
FONT_SIZE = 14
LINE_H = 22
PAD = 16
TITLE_H = 32

_font = None

def _get_font():
    global _font
    if _font is None:
        for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"]:
            if Path(p).exists():
                _font = ImageFont.truetype(p, FONT_SIZE)
                break
        else:
            _font = ImageFont.load_default()
    return _font

def _draw(lines, cursor=-1):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    f = _get_font()

    d.rectangle([0, 0, WIDTH, TITLE_H], fill=TITLE_BG)
    d.line([0, TITLE_H, WIDTH, TITLE_H], fill=BORDER, width=1)
    for i, c in enumerate([(255,95,86),(255,189,46),(39,201,63)]):
        x = 12 + i*20
        d.ellipse([x, TITLE_H//2-5, x+10, TITLE_H//2+5], fill=c)
    d.text((WIDTH//2-30, TITLE_H//2-7), "bash", font=f, fill=DIM)

    y = TITLE_H + PAD
    max_lines = (HEIGHT - TITLE_H - PAD*2) // LINE_H
    vis = lines[-max_lines:]
    adj = len(lines) - len(vis)

    for i, line in enumerate(vis):
        x = PAD
        if line.startswith("$ "):
            d.text((x, y), "$ ", font=f, fill=GREEN)
            x += 18
            d.text((x, y), line[2:], font=f, fill=FG)
        elif line.startswith(">>> ") or line.startswith("... "):
            d.text((x, y), line[:4], font=f, fill=GREEN)
            x += 36
            rest = line[4:]
            # split on quotes for string highlighting
            segs = re_split(rest)
            for text, color in segs:
                if text:
                    d.text((x, y), text, font=f, fill=color)
                    bb = f.getbbox(text)
                    x += bb[2] - bb[0] + 2
        elif line.startswith("# ") or line.startswith("-- "):
            d.text((x, y), line, font=f, fill=DIM)
        elif any(w in line for w in ["✓", "Success", "working", "OK"]):
            d.text((x, y), line, font=f, fill=GREEN)
        elif any(w in line for w in ["Error", "FAIL", "rejected"]):
            d.text((x, y), line, font=f, fill=RED)
        else:
            d.text((x, y), line, font=f, fill=FG)

        if cursor == i + adj:
            bb = f.getbbox(line) if line else (0,0,8,0)
            cx = PAD + (bb[2] if bb else 8) + 4
            d.rectangle([cx, y+2, cx+7, y+FONT_SIZE], fill=FG)
        y += LINE_H

    return img

def re_split(s):
    """Split string into (text, color) segments with basic syntax highlighting."""
    segs = []
    for kw in ("import ", "from ", "print(", "def ", "class ", "return "):
        if kw in s:
            idx = s.index(kw)
            if idx > 0:
                segs.append((s[:idx], FG))
            segs.append((kw, YELLOW))
            rest = s[idx+len(kw):]
            # highlight strings in rest
            parts = rest.split('"')
            for j, p in enumerate(parts):
                if j % 2 == 1:
                    segs.append(('"'+p+'"', CYAN))
                elif p:
                    segs.append((p, FG))
            return segs
    # no keyword, check for strings
    parts = s.split('"')
    for j, p in enumerate(parts):
        if j % 2 == 1:
            segs.append(('"'+p+'"', CYAN))
        elif p:
            segs.append((p, FG))
    return segs

def render(script_path, output_path):
    _get_font()
    with open(script_path) as fh:
        script = json.load(fh)

    frames = []
    lines = []
    ms = 0
    step_ms = 1000 // FPS

    for step in script["steps"]:
        st = step.get("type", "")

        if st == "type":
            text = step["text"]
            # batch: 4 chars per frame
            for i in range(4, len(text)+4, 4):
                partial = text[:min(i, len(text))]
                curlines = lines + ["$ " + partial]
                frames.append(_draw(curlines, cursor=len(curlines)-1))
                ms += step_ms

        elif st == "enter":
            lines = lines + ["$ " + step.get("_last", "")]
            # just add empty prompt
            lines = lines + ["$ "]
            frames.append(_draw(lines, cursor=len(lines)-1))
            ms += step_ms

        elif st == "output":
            text = step["text"]
            # replace the "$ " prompt line with output
            if lines and lines[-1].startswith("$ "):
                lines[-1] = text
            else:
                lines = lines + [text]
            frames.append(_draw(lines))
            ms += step_ms * 2

        elif st == "python":
            code = step["code"]
            result = step.get("result", "")
            lines = lines + [">>> " + code]
            frames.append(_draw(lines, cursor=len(lines)-1))
            ms += step_ms
            if result:
                lines = lines + [result]
                frames.append(_draw(lines))
                ms += step_ms * 2

        elif st == "sleep":
            n = max(1, (step.get("ms", 500) * FPS) // 1000)
            for _ in range(n):
                frames.append(_draw(lines))
                ms += step_ms

        elif st == "pause":
            for _ in range(FPS):
                frames.append(_draw(lines))
                ms += 1000

    if not frames:
        frames = [_draw(["$ echo 'demo'"])]

    imageio.mimsave(output_path, frames, fps=FPS, loop=0)
    dur = ms / 1000
    kb = Path(output_path).stat().st_size // 1024
    print(f"  {output_path}: {len(frames)}f {dur:.1f}s {kb}KB {WIDTH}x{HEIGHT}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <script.json> <output.gif>")
        sys.exit(1)
    render(sys.argv[1], sys.argv[2])
