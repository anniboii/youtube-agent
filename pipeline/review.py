"""review.py - contact sheets of every unlabelled b-roll window, so each one gets looked at.

    python pipeline/review.py sheets          # writes footage/review/sheet_NNN.jpg + sheet_NNN.json
    python pipeline/review.py apply labels.json

Each tile shows the middle frame of one window with its number. labels.json maps a window key
("file.mp4@12.5") to either {"ok": false} or {"ok": true, "scene": ["hostel","night"]}. make.py
only uses windows marked ok, and prefers scene tags over the video-level tags.

Scene vocabulary: campus-outdoor, building, hostel, room, mess, food, lecture, library, lab,
lake, greenery, road, night, fest-stage, crowd, music, dance, sports, laptop, desk, city, travel,
office, sea, sky, celebration, graduation.
"""
import glob, json, os, sys
from PIL import Image, ImageDraw, ImageFont
from common import CFG, FFMPEG, FOOTAGE_INDEX, FOOTAGE_RAW, ROOT, load_json, save_json
import subprocess

REVIEW = os.path.join(ROOT, "footage", "review")
LABELS = os.path.join(ROOT, "footage", "labels.json")
TILE_W, TILE_H, COLS, PER = 320, 180, 6, 30


def key(name, s):
    return f"{name}@{s}"


def frame(name, t):
    p = subprocess.run([FFMPEG, "-v", "error", "-ss", str(t), "-i", os.path.join(FOOTAGE_RAW, name),
                        "-frames:v", "1", "-vf", f"scale={TILE_W}:{TILE_H}:force_original_aspect_ratio=decrease,pad={TILE_W}:{TILE_H}:(ow-iw)/2:(oh-ih)/2",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    import io
    return Image.open(io.BytesIO(p.stdout)).convert("RGB") if p.stdout else Image.new("RGB", (TILE_W, TILE_H))


def sheets():
    os.makedirs(REVIEW, exist_ok=True)
    index, labels = load_json(FOOTAGE_INDEX, {}), load_json(LABELS, {})
    todo = [(n, s) for n, v in index.items() for s in v.get("starts", []) if key(n, s) not in labels]
    f = ImageFont.truetype(CFG["caption_font"], 30)
    seg = CFG["clip_seconds"]
    for i in range(0, len(todo), PER):
        batch = todo[i:i + PER]
        rows = -(-len(batch) // COLS)
        sheet = Image.new("RGB", (COLS * TILE_W, rows * TILE_H), "black")
        d = ImageDraw.Draw(sheet)
        for j, (n, s) in enumerate(batch):
            x, y = (j % COLS) * TILE_W, (j // COLS) * TILE_H
            sheet.paste(frame(n, s + seg / 2), (x, y))
            d.text((x + 6, y + 2), str(j), font=f, fill="yellow", stroke_width=3, stroke_fill="black")
        num = i // PER
        sheet.save(os.path.join(REVIEW, f"sheet_{num:03d}.jpg"), quality=80)
        save_json(os.path.join(REVIEW, f"sheet_{num:03d}.json"), [key(n, s) for n, s in batch])
    print(f"{len(todo)} windows on {-(-len(todo) // PER)} sheets in {REVIEW}")


def apply(path):
    labels = load_json(LABELS, {})
    new = load_json(path)
    labels.update(new)
    save_json(LABELS, labels)
    ok = sum(1 for v in labels.values() if v.get("ok"))
    print(f"{len(new)} labelled now, {len(labels)} total, {ok} approved")


def label(num, spec):
    """label 000 "16-21=fest-stage,music; 3,5=hostel" - every tile not named is rejected."""
    keys = load_json(os.path.join(REVIEW, f"sheet_{int(num):03d}.json"))
    out = {k: {"ok": False} for k in keys}
    for part in filter(None, (p.strip() for p in spec.split(";"))):
        ids, tags = part.split("=")
        for r in ids.split(","):
            a, _, b = r.partition("-")
            for j in range(int(a), int(b or a) + 1):
                out[keys[j]] = {"ok": True, "scene": [t.strip() for t in tags.split(",")]}
    labels = load_json(LABELS, {})
    labels.update(out)
    save_json(LABELS, labels)
    print(f"sheet {num}: {sum(v['ok'] for v in out.values())}/{len(out)} approved")


if __name__ == "__main__":
    {"sheets": sheets, "apply": lambda: apply(sys.argv[2]),
     "label": lambda: label(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")}[sys.argv[1]]()
