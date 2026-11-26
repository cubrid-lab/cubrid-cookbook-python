#!/usr/bin/env bash
# Convert the staged recordings in .demo-artifacts/ into the published GIF/MP4 files.
# Run from the repository root after the VHS tapes and demos/record_browser.py
# (see demos/README.md). Stages a complete set before replacing .demo-artifacts/out/.
# Promoting the files into docs/ is a separate, reviewed step.
set -euo pipefail

A=.demo-artifacts
DEST="$A/out"
for f in "$A/demo-agent-state.gif" "$A/agent-state.mp4" "$A/mcp-toolchain.mp4" \
    "$A/dashboard-terminal.mp4" "$A/raw/dashboard.webm" "$A/raw/fastapi.webm"; do
    test -s "$f" || { echo "missing recording: $f" >&2; exit 1; }
done

# Never follow an output symlink or replace an unrelated non-directory.
if [[ -L "$DEST" || ( -e "$DEST" && ! -d "$DEST" ) ]]; then
    echo "output must be a directory, not a symlink or file: $DEST" >&2
    exit 1
fi

# Both renames stay on the same filesystem. Keep the previous set until the
# final rename succeeds; an error or handled signal restores it before cleanup.
WORK=$(mktemp -d "$A/.build-media.XXXXXX")
OUT="$WORK/out"
publishing=0
cleanup() {
    local status=$?
    trap - EXIT HUP INT TERM
    if (( status != 0 && publishing )); then
        if [[ ! -d "$OUT" && -d "$DEST" ]]; then
            if ! mv -- "$DEST" "$OUT"; then
                echo "cannot undo publication; recovery files retained in $WORK" >&2
                exit 1
            fi
        fi
        if [[ -d "$WORK/previous" ]]; then
            if ! mv -- "$WORK/previous" "$DEST"; then
                echo "cannot restore previous output; recovery files retained in $WORK" >&2
                exit 1
            fi
        fi
    fi
    rm -rf -- "$WORK"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$OUT"

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

# README still posters: the last frame of each GIF, linked to the GIF, so no
# motion starts without the reader selecting it (WCAG 2.2 SC 2.2.2).
for name in agent-state fastapi dashboard; do
    # -update 1 overwrites one PNG with every decoded frame, so the final frame remains.
    ffmpeg -loglevel error -y -i "$OUT/demo-$name.gif" -update 1 "$OUT/demo-$name.png"
done

# A converter may return success without producing usable output.
for f in demo-dashboard.gif demo-fastapi.gif demo-agent-state.gif \
    dashboard.mp4 agent-state.mp4 mcp-toolchain.mp4 \
    demo-agent-state.png demo-fastapi.png demo-dashboard.png; do
    test -s "$OUT/$f" || { echo "missing or empty output: $f" >&2; exit 1; }
done
ls -l "$OUT"

publishing=1
if [[ -d "$DEST" ]]; then
    mv -- "$DEST" "$WORK/previous"
fi
mv -- "$OUT" "$DEST"
