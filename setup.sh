#!/usr/bin/env bash
# One-shot setup for a cloud (Linux) run. Safe to re-run; takes ~1-2 min on a fresh machine.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install --quiet -r requirements.txt
# the yt-* skills the runbooks call (hookscore.py etc.) are vendored in skills/
mkdir -p ~/.claude/skills ~/.claude/youtube
cp -r --update=none skills/yt-* ~/.claude/skills/ 2>/dev/null || true
cp --update=none profile/voice.md ~/.claude/youtube/voice.md 2>/dev/null || true
python3 - <<'EOF'
import imageio_ffmpeg, edge_tts, PIL
print("ffmpeg:", imageio_ffmpeg.get_ffmpeg_exe())
print("setup ok")
EOF
