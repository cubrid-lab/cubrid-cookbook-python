#!/usr/bin/env bash
# Convert the staged recordings in .demo-artifacts/ into the published GIF/MP4 files.
# Run from the repository root after the VHS tapes and demos/record_browser.py
# (see demos/README.md). Writes only .demo-artifacts/out/; promoting the files
# into docs/ is a separate, reviewed step.
set -euo pipefail

A=.demo-artifacts
OUT="$A/out"
mkdir -p "$OUT"
for f in "$A/demo-agent-state.gif" "$A/agent-state.mp4" "$A/mcp-toolchain.mp4" \
    "$A/dashboard-terminal.mp4" "$A/raw/dashboard.webm" "$A/raw/fastapi.webm"; do
    test -s "$f" || { echo "missing recording: $f" >&2; exit 1; }
done

# Browser excerpt -> README GIF: 10 fps, 960 px wide, one palette per GIF.
gif() {
    local src=$1 start=$2 length=$3 dst=$4
    ffmpeg -loglevel error -y -ss "$start" -t "$length" -i "$src" -filter_complex \
        "fps=10,scale=960:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" \
        "$dst"
}
gif "$A/raw/dashboard.webm" 9.5 12 "$OUT/demo-dashboard.gif"
gif "$A/raw/fastapi.webm" 0.5 12 "$OUT/demo-fastapi.gif"

# Terminal half + browser half -> docs-site dashboard MP4 (H.264, 25 fps, yuv420p).
ffmpeg -loglevel error -y -i "$A/dashboard-terminal.mp4" -i "$A/raw/dashboard.webm" \
    -filter_complex \
    "[0:v]fps=25,scale=1280:720,setsar=1,format=yuv420p[t];[1:v]fps=25,scale=1280:720,setsar=1,format=yuv420p[b];[t][b]concat=n=2:v=1:a=0[v]" \
    -map "[v]" -c:v libx264 -preset slow -crf 30 -movflags +faststart "$OUT/dashboard.mp4"

# VHS output is already H.264; copy it with the moov atom first for streaming.
for name in agent-state mcp-toolchain; do
    ffmpeg -loglevel error -y -i "$A/$name.mp4" -c copy -movflags +faststart "$OUT/$name.mp4"
done
cp "$A/demo-agent-state.gif" "$OUT/demo-agent-state.gif"

ls -l "$OUT"
