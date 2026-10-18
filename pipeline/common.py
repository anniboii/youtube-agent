"""Shared paths and helpers for the YouTube agent pipeline."""
import json, os, re, subprocess
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FOOTAGE_RAW = os.path.join(ROOT, "footage", "raw")
FOOTAGE_INDEX = os.path.join(ROOT, "footage", "index.json")
SECRETS = os.path.join(ROOT, "secrets")


def ff(*args, quiet=True):
    """Run ffmpeg; raise with the tail of stderr on failure."""
    cmd = [FFMPEG, "-hide_banner", "-y", *map(str, args)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + p.stderr[-2000:])
    return p.stderr


def duration(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    if not m:
        raise RuntimeError(f"no duration for {path}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    return json.load(open(path, encoding="utf-8"))


def save_json(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def secret(name):
    p = os.path.join(SECRETS, name)
    return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else None
