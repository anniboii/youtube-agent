"""make.py - turn an episode.json into a finished, captioned, voiced MP4 plus a thumbnail.

    python pipeline/make.py episodes/<slug>            # build everything
    python pipeline/make.py episodes/<slug> --only thumb

episode.json:
{
  "slug": "iitb-first-year", "format": "long" | "short",
  "title": "...", "description": "...", "tags": ["..."], "thumb_text": "FIRST YEAR\\nSACH",
  "thumb_tags": ["campus"],
  "beats": [
    {"say": "TTS text (Devanagari Hinglish reads best)", "caption": "Roman text shown on screen",
     "visual": {"type": "footage", "tags": ["hostel"]}
             | {"type": "text", "text": "BIG LINE", "sub": "smaller line"}
             | {"type": "stock", "query": "students laptop night"}
             | {"type": "image", "path": "relative/or/absolute.png"}}
  ]
}
Nothing here uploads. upload.py does that, as Private.
"""
import asyncio, hashlib, json, os, random, sys, urllib.parse, urllib.request
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from common import CFG, FOOTAGE_RAW, FOOTAGE_INDEX, ROOT, ff, duration, load_json, save_json, secret

FPS = 30
PAD = 0.25  # breath after each beat


# ---------- voice ----------
async def _tts(text, voice, rate, out):
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


_LEX = None


def pronounce(text):
    """Swap English words/acronyms for Devanagari spellings the Hindi voice says correctly."""
    global _LEX
    if _LEX is None:
        lex = load_json(os.path.join(ROOT, "pronounce.json"), {})
        _LEX = sorted(((k, v) for k, v in lex.items() if not k.startswith("_")), key=lambda kv: -len(kv[0]))
    import re
    for k, v in _LEX:
        text = re.sub(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])", v, text, flags=re.I)
    return text


def voice(beat, ep, out):
    v = ep.get("voice", CFG["voice"]); r = ep.get("voice_rate", CFG["voice_rate"])
    text = beat.get("say_override") or pronounce(beat["say"])  # say_override: hand-written TTS text
    beat["_say_tts"] = text
    key = hashlib.md5(f"{v}|{r}|{text}".encode()).hexdigest()
    stamp = out + ".key"
    if os.path.exists(out) and os.path.exists(stamp) and open(stamp).read() == key:
        return
    asyncio.run(_tts(text, v, r, out))
    open(stamp, "w").write(key)


# ---------- drawing ----------
def font(path, size):
    return ImageFont.truetype(path, size)


def wrap(draw, text, f, maxw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if draw.textlength(t, font=f) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
    return lines


def draw_block(img, lines, f, cx, cy, fill, stroke=8, gap=1.12):
    d = ImageDraw.Draw(img)
    lh = int(f.size * gap)
    y = cy - lh * len(lines) // 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text((cx - w / 2, y), ln, font=f, fill=fill, stroke_width=stroke, stroke_fill="black")
        y += lh


def caption_png(text, W, H, path, short):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = font(CFG["caption_font"], 84 if short else 62)
    d = ImageDraw.Draw(img)
    lines = wrap(d, text, f, W * (0.84 if short else 0.78))
    draw_block(img, lines, f, W // 2, int(H * (0.66 if short else 0.83)), "white", stroke=7)
    img.save(path)


def text_slide(vis, W, H, path):
    top, bot = (16, 20, 26), (34, 44, 62)
    col = Image.new("RGB", (1, 256))
    for y in range(256):
        col.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * y / 255) for i in range(3)))
    img = col.resize((W, H), Image.BILINEAR)
    d = ImageDraw.Draw(img)
    short = H > W
    big = font(CFG["title_font"], 120 if short else 108)
    lines = wrap(d, vis.get("text", ""), big, W * 0.84)
    draw_block(img, lines, big, W // 2, int(H * 0.42), CFG["accent"], stroke=0)
    if vis.get("sub"):
        sf = font(CFG["caption_font"], 56 if short else 50)
        draw_block(img, wrap(d, vis["sub"], sf, W * 0.8), sf, W // 2,
                   int(H * 0.42) + len(lines) * big.size // 2 + 110, (230, 230, 230), stroke=0)
    img.save(path)


def chunks(caption, words=6):
    w = caption.split()
    out, cur = [], []
    for x in w:
        cur.append(x)
        if len(cur) >= words or x.endswith((".", "?", "!", ",")) and len(cur) >= 3:
            out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return out


# ---------- footage ----------
class Picker:
    def __init__(self, ep, short):
        self.index = load_json(FOOTAGE_INDEX, {})
        self.labels = load_json(os.path.join(ROOT, "footage", "labels.json"), {})
        self.used = set(ep.get("_avoid", []))
        self.short = short
        self.rng = random.Random(ep.get("slug", "x"))

    def windows(self, tags):
        """Only windows a human-eye review approved. Scene tags (what is in the shot) count double."""
        pool = []
        for name, v in self.index.items():
            orient = 1 if v.get("vertical") == self.short else 0
            for s in v.get("starts", []):
                lab = self.labels.get(f"{name}@{s}")
                if not lab or not lab.get("ok") or (name, s) in self.used:
                    continue
                if "other-iit" in lab.get("scene", []) and "other-iit" not in (tags or []):
                    continue  # never pass another campus off as IIT Bombay
                match = 2 * len(set(tags or []) & set(lab.get("scene", []))) + len(set(tags or []) & set(v["tags"]))
                pool.append((match, orient, self.rng.random(), name, s))
        pool.sort(reverse=True)
        return pool

    def take(self, tags, n):
        got = []
        for m, o, _, name, s in self.windows(tags):
            if len(got) == n:
                break
            if any(g[0] == name and abs(g[1] - s) < 10 for g in got):
                continue  # spread across each video
            got.append((name, s)); self.used.add((name, s))
        return got


def stock_clip(query, short, cache):
    key = secret("pexels_key.txt")
    if not key:
        return None
    q = urllib.parse.urlencode({"query": query, "per_page": 6,
                                "orientation": "portrait" if short else "landscape"})
    req = urllib.request.Request(f"https://api.pexels.com/videos/search?{q}", headers={"Authorization": key})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:
        print("  pexels failed:", e); return None
    for v in data.get("videos", []):
        files = sorted((f for f in v["video_files"] if f.get("width")), key=lambda f: abs((f["height"] if short else f["width"]) - 1920))
        if not files:
            continue
        out = os.path.join(cache, f"pexels_{v['id']}.mp4")
        if not os.path.exists(out):
            urllib.request.urlretrieve(files[0]["link"], out)
        return out
    return None


def scale_crop(W, H):
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"


# ---------- beat ----------
def build_beat(i, beat, ep, picker, build, W, H, short):
    audio = os.path.join(build, f"b{i:02d}.mp3")
    voice(beat, ep, audio)
    d = duration(audio) + PAD
    vis = beat.get("visual") or {"type": "footage", "tags": []}
    inputs, pre = [], []
    seg = CFG["clip_seconds"]

    if vis["type"] == "stock":
        p = stock_clip(vis.get("query", ""), short, os.path.join(ROOT, "footage", "stock"))
        if p:
            inputs += ["-stream_loop", "-1", "-i", p]; pre.append(f"[0:v]{scale_crop(W, H)}[bg]")
        else:
            vis = {"type": "footage", "tags": vis.get("tags", [])}
    if vis["type"] == "image":
        p = vis["path"] if os.path.isabs(vis["path"]) else os.path.join(ROOT, vis["path"])
        inputs += ["-loop", "1", "-i", p]; pre.append(f"[0:v]{scale_crop(W, H)}[bg]")
    if vis["type"] == "text":
        png = os.path.join(build, f"b{i:02d}_slide.png"); text_slide(vis, W, H, png)
        inputs += ["-loop", "1", "-i", png]; pre.append(f"[0:v]{scale_crop(W, H)}[bg]")
    if vis["type"] == "footage":
        n = max(1, int(-(-d // seg)))
        picks = picker.take(vis.get("tags", []), n)
        if not picks:  # no footage indexed yet: fall back to a text slide
            png = os.path.join(build, f"b{i:02d}_slide.png")
            text_slide({"text": beat.get("caption", "")[:60]}, W, H, png)
            inputs += ["-loop", "1", "-i", png]; pre.append(f"[0:v]{scale_crop(W, H)}[bg]")
        else:
            for k, (name, s) in enumerate(picks):
                inputs += ["-ss", s, "-t", seg, "-i", os.path.join(FOOTAGE_RAW, name)]
                pre.append(f"[{k}:v]{scale_crop(W, H)}[v{k}]")
            pre.append("".join(f"[v{k}]" for k in range(len(picks))) + f"concat=n={len(picks)}:v=1:a=0[bg]")
            beat["_footage"] = picks

    # captions
    cap = beat.get("caption") or beat["say"]
    parts = [] if vis["type"] == "text" else chunks(cap)  # a text slide already says it
    total_chars = sum(len(p) for p in parts) or 1
    t, last = 0.0, "bg"
    base = len([x for x in inputs if x == "-i"])
    for k, part in enumerate(parts):
        png = os.path.join(build, f"b{i:02d}_c{k}.png"); caption_png(part, W, H, png, short)
        inputs += ["-i", png]
        dt = (d - PAD) * len(part) / total_chars
        pre.append(f"[{last}][{base + k}:v]overlay=0:0:enable='between(t,{t:.2f},{t + dt:.2f})'[o{k}]")
        last, t = f"o{k}", t + dt
    inputs += ["-i", audio]
    ai = base + len(parts)
    out = os.path.join(build, f"b{i:02d}.mp4")
    ff(*inputs, "-filter_complex", ";".join(pre), "-map", f"[{last}]", "-map", f"{ai}:a",
       "-af", f"apad=pad_dur={PAD}", "-t", f"{d:.2f}", "-r", FPS,
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out)
    return out, d


# ---------- thumbnail ----------
def thumbnail(ep, epdir, picker):
    out = os.path.join(epdir, "thumbnail.jpg")
    W, H = 1280, 720
    frame = os.path.join(epdir, "build", "thumb_frame.jpg")
    picks = picker.take(ep.get("thumb_tags", ["campus"]), 1)
    if picks:
        name, s = picks[0]
        ff("-ss", s + 1, "-i", os.path.join(FOOTAGE_RAW, name), "-frames:v", 1,
           "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", frame)
        img = Image.open(frame).convert("RGB").filter(ImageFilter.GaussianBlur(1.2))
        img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
    else:
        img = Image.new("RGB", (W, H), (20, 24, 32))
    f = font(CFG["title_font"], 118)
    d = ImageDraw.Draw(img)
    lines = wrap(d, ep.get("thumb_text", ep["title"]).upper(), f, W * 0.9)
    draw_block(img, lines, f, W // 2, H // 2, CFG["accent"], stroke=10)
    img.save(out, quality=92)
    return out


# ---------- main ----------
def main():
    epdir = os.path.abspath(sys.argv[1])
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    ep = load_json(os.path.join(epdir, "episode.json"))
    short = ep.get("format") == "short"
    W, H = (CFG["short"] if short else CFG["long"]).values()
    build = os.path.join(epdir, "build"); os.makedirs(build, exist_ok=True)
    picker = Picker(ep, short)

    if only != "thumb":
        parts, total = [], 0.0
        for i, beat in enumerate(ep["beats"]):
            p, d = build_beat(i, beat, ep, picker, build, W, H, short)
            parts.append(p); total += d
            print(f"  beat {i:02d}  {d:5.1f}s  {beat.get('visual', {}).get('type', 'footage')}", flush=True)
        lst = os.path.join(build, "concat.txt")
        open(lst, "w", encoding="utf-8").write("".join(f"file '{p}'\n" for p in parts))
        final = os.path.join(epdir, f"{ep['slug']}.mp4")
        music = sorted(glob_music())
        loud = "loudnorm=I=-14:TP=-1.5:LRA=11"  # YouTube plays back near -14 LUFS
        if music:
            ff("-f", "concat", "-safe", 0, "-i", lst, "-stream_loop", "-1", "-i", music[0],
               "-filter_complex", f"[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,{loud}[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", final)
        else:
            ff("-f", "concat", "-safe", 0, "-i", lst, "-map", "0:v", "-map", "0:a", "-c:v", "copy",
               "-af", loud, "-c:a", "aac", "-b:a", "160k", "-ar", "44100", final)
        ep["_render"] = {"file": os.path.basename(final), "seconds": round(total, 1)}
        print(f"\n  video     {final}  ({total / 60:.1f} min)")
        if short and total > 60:
            print("  WARNING   over 60s - YouTube will not treat this as a Short")
    print(f"  thumbnail {thumbnail(ep, epdir, picker)}")
    save_json(os.path.join(epdir, "episode.json"), ep)


def glob_music():
    import glob
    return glob.glob(os.path.join(ROOT, "assets", "music", "*.mp3"))


if __name__ == "__main__":
    main()
