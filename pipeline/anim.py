"""anim.py - animated explainer videos (no footage): motion graphics + AI voice + Hindi text.

    python pipeline/anim.py episodes/<slug>

episode.json uses "style": "anim". Each beat has "say" (Devanagari narration) and "scene":

  {"type": "title", "lines": ["headline", "second line"], "icon": "phone", "check": true}
  {"type": "flow",  "nodes": [{"label": "...", "icon": "phone"}, ...],
                    "from": 0, "to": 2, "badge": {"node": 1, "icon": "lock", "text": "PIN"}}
  {"type": "bars",  "a": {"label": "A to B", "value": 500}, "b": {"label": "B to A", "value": 480},
                    "unit": "crore", "result": "net line"}
  {"type": "card",  "text": "big line", "sub": "..."}

Graphics are drawn per frame with Pillow. Every piece of text - captions, labels, headlines - is
written into one .ass subtitle file and burned in by libass, because Pillow on this machine has
no complex-script shaping and would break Devanagari matras.
"""
import math, os, shutil, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
from common import CFG, FFMPEG, ROOT, ff, duration, load_json, save_json
from make import voice, chunks

W, H, FPS = 1080, 1920, 30
PAD = 0.2
BG_TOP, BG_BOT = (12, 18, 34), (28, 38, 66)
ACCENT, GREEN, WHITE, DIM = (255, 210, 63), (60, 199, 154), (240, 244, 250), (90, 104, 140)
_WIN = os.path.exists("C:/Windows/Fonts/Nirmala.ttc")
_NOTO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
HINDI_FONT = "Nirmala UI" if _WIN else "Noto Sans Devanagari"
RUPEE = (ImageFont.truetype("C:/Windows/Fonts/Nirmala.ttc", 64, index=1) if _WIN
         else ImageFont.truetype(os.path.join(_NOTO, "NotoSans-Bold.ttf"), 64))


# ---------- easing ----------
def clamp(x): return max(0.0, min(1.0, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def pop(x):
    x = clamp(x); s = 1.70158
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


# ---------- background ----------
_BG = None
GLOWS = [(255, 210, 63), (60, 199, 154), (110, 170, 255), (255, 120, 120)]
_GLOW = {}


def glow(color):
    """A big soft colour blob, blurred once and cached."""
    if color not in _GLOW:
        from PIL import ImageFilter
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse((W * .1, H * .25, W * .9, H * .65), fill=color + (60,))
        _GLOW[color] = g.filter(ImageFilter.GaussianBlur(120))
    return _GLOW[color]


def background(t, beat_index=0):
    global _BG
    if _BG is None:
        col = Image.new("RGB", (1, 256))
        for y in range(256):
            col.putpixel((0, y), tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * y / 255) for i in range(3)))
        _BG = col.resize((W, H), Image.BILINEAR)
    img = _BG.copy()
    img.paste(glow(GLOWS[beat_index % len(GLOWS)]), (0, int(20 * math.sin(t * .8))), glow(GLOWS[beat_index % len(GLOWS)]))
    d = ImageDraw.Draw(img, "RGBA")
    for k in range(7):  # slow drifting dots so a still scene never looks frozen
        x = (k * 173 + t * 18 * (1 + k % 3)) % (W + 200) - 100
        y = 260 + k * 230 + 30 * math.sin(t * 0.6 + k)
        r = 70 + 25 * (k % 3)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 10))
    return img


# ---------- icons (centred at cx, cy, size s) ----------
def icon(d, kind, cx, cy, s, color=WHITE, alpha=255):
    c = color + (alpha,)
    w = max(4, int(s * 0.07))
    if kind == "phone":
        d.rounded_rectangle((cx - s * .32, cy - s * .55, cx + s * .32, cy + s * .55), radius=s * .1, outline=c, width=w)
        d.line((cx - s * .08, cy + s * .44, cx + s * .08, cy + s * .44), fill=c, width=w)
    elif kind == "bank":
        d.polygon([(cx - s * .55, cy - s * .15), (cx, cy - s * .5), (cx + s * .55, cy - s * .15)], outline=c, width=w)
        for k in range(4):
            x = cx - s * .38 + k * s * .253
            d.line((x, cy - s * .08, x, cy + s * .35), fill=c, width=w)
        d.line((cx - s * .55, cy + s * .42, cx + s * .55, cy + s * .42), fill=c, width=w)
    elif kind == "switch":
        d.ellipse((cx - s * .22, cy - s * .22, cx + s * .22, cy + s * .22), outline=c, width=w)
        for a in range(0, 360, 60):
            r = math.radians(a)
            d.line((cx + math.cos(r) * s * .22, cy + math.sin(r) * s * .22,
                    cx + math.cos(r) * s * .5, cy + math.sin(r) * s * .5), fill=c, width=w)
            d.ellipse((cx + math.cos(r) * s * .5 - s * .07, cy + math.sin(r) * s * .5 - s * .07,
                       cx + math.cos(r) * s * .5 + s * .07, cy + math.sin(r) * s * .5 + s * .07), fill=c)
    elif kind == "shop":
        d.rectangle((cx - s * .5, cy - s * .1, cx + s * .5, cy + s * .45), outline=c, width=w)
        for k in range(5):
            x0 = cx - s * .55 + k * s * .22
            d.pieslice((x0, cy - s * .32, x0 + s * .22, cy - s * .05), 0, 180, fill=c)
        d.rectangle((cx - s * .12, cy + s * .12, cx + s * .12, cy + s * .45), outline=c, width=w)
    elif kind == "lock":
        d.rounded_rectangle((cx - s * .35, cy - s * .05, cx + s * .35, cy + s * .45), radius=s * .06, fill=c)
        d.arc((cx - s * .25, cy - s * .45, cx + s * .25, cy + s * .1), 180, 360, fill=c, width=w)
    elif kind == "check":
        d.ellipse((cx - s * .5, cy - s * .5, cx + s * .5, cy + s * .5), fill=GREEN + (alpha,))
        d.line((cx - s * .22, cy, cx - s * .05, cy + s * .18, cx + s * .25, cy - s * .18), fill=(255, 255, 255, alpha), width=w * 2)
    elif kind == "speaker":
        d.polygon([(cx - s * .4, cy - s * .15), (cx - s * .15, cy - s * .15), (cx + s * .1, cy - s * .4),
                   (cx + s * .1, cy + s * .4), (cx - s * .15, cy + s * .15), (cx - s * .4, cy + s * .15)], fill=c)
        for r in (.25, .42):
            d.arc((cx - s * r + s * .1, cy - s * r, cx + s * r + s * .1, cy + s * r), -45, 45, fill=c, width=w)
    elif kind == "rbi":
        d.ellipse((cx - s * .5, cy - s * .5, cx + s * .5, cy + s * .5), outline=c, width=w)
        icon(d, "bank", cx, cy + s * .03, s * .6, color, alpha)


def coin(img, cx, cy, s=70):
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse((cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2), fill=ACCENT + (255,), outline=(180, 140, 20, 255), width=5)
    d.text((cx, cy + 2), "₹", font=RUPEE, fill=(60, 40, 0, 255), anchor="mm")


# ---------- ASS text ----------
def ts(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


ASS_HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{HINDI_FONT},74,&H003FD2FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,230,1
Style: Big,{HINDI_FONT},118,&H003FD2FF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,5,60,60,0,1
Style: Mid,{HINDI_FONT},74,&H00FAF4F0,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,5,60,60,0,1
Style: Label,{HINDI_FONT},50,&H00FAF4F0,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,20,20,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


class Ass:
    def __init__(self): self.ev = []
    def add(self, t0, t1, style, text, x=None, y=None, fx=""):
        pos = f"\\pos({x:.0f},{y:.0f})" if x is not None else ""
        text = text.replace("\n", "\\N")
        self.ev.append(f"Dialogue: 0,{ts(t0)},{ts(t1)},{style},,0,0,0,,{{{pos}{fx}}}{text}")
    def save(self, path):
        open(path, "w", encoding="utf-8-sig").write(ASS_HEAD + "\n".join(self.ev) + "\n")


POP = "\\fad(120,120)\\fscx70\\fscy70\\t(0,220,\\fscx100\\fscy100)"


# ---------- scenes ----------
def flow_layout(n):
    top, bot = 330, 1420
    ys = [top + (bot - top) * i / max(1, n - 1) for i in range(n)]
    xs = [W * (0.3 if i % 2 == 0 else 0.7) for i in range(n)]
    return list(zip(xs, ys))


def draw_flow(img, sc, p):
    d = ImageDraw.Draw(img, "RGBA")
    nodes = sc["nodes"]; pos = flow_layout(len(nodes))
    a, b = sc.get("from", 0), sc.get("to", len(nodes) - 1)
    span = max(1, b - a)
    prog = a + span * ease(p / 0.85)  # edges from a to b animate over the beat
    for i in range(len(nodes) - 1):
        if i >= prog:
            break
        (x0, y0), (x1, y1) = pos[i], pos[i + 1]
        f = clamp(prog - i)
        d.line((x0, y0, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), fill=ACCENT + (230,), width=10)
    for i, (x, y) in enumerate(pos):
        visible = i <= max(a, math.floor(prog + 0.001))
        if not visible:
            d.ellipse((x - 90, y - 90, x + 90, y + 90), outline=DIM + (90,), width=4)
            continue
        appear = 1.0 if i <= a else ease((prog - (i - 1)) * 2)
        r = 95 * (0.6 + 0.4 * pop(appear))
        active = abs(prog - i) < 0.5
        if active:  # pulse ring on the node the money is at
            ph = (p * 4) % 1
            rr = r + 60 * ph
            d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=ACCENT + (int(200 * (1 - ph)),), width=5)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 26), outline=(ACCENT if active else WHITE) + (255,), width=6)
        icon(d, nodes[i].get("icon", "bank"), x, y, r * 0.95, ACCENT if active else WHITE)
    if prog < b:  # the coin rides the edge being drawn
        i = int(prog); f = prog - i
        (x0, y0), (x1, y1) = pos[i], pos[min(i + 1, len(pos) - 1)]
        dd = ImageDraw.Draw(img, "RGBA")
        for k in range(1, 6):  # trail
            g = max(0.0, f - k * 0.05)
            r_ = 30 - k * 4
            cx_, cy_ = x0 + (x1 - x0) * g, y0 + (y1 - y0) * g
            dd.ellipse((cx_ - r_, cy_ - r_, cx_ + r_, cy_ + r_), fill=ACCENT + (150 - k * 25,))
        coin(img, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
    bd = sc.get("badge")
    if bd and p > 0.25:
        x, y = pos[bd["node"]]
        icon(ImageDraw.Draw(img, "RGBA"), bd.get("icon", "lock"), x + 120, y - 90, 70, ACCENT, int(255 * ease((p - .25) * 4)))


def flow_text(ass, sc, t0, t1):
    pos = flow_layout(len(sc["nodes"]))
    a, b = sc.get("from", 0), sc.get("to", len(sc["nodes"]) - 1)
    span = max(1, b - a); dur = t1 - t0
    for i, n in enumerate(sc["nodes"]):
        if i > b:
            continue
        start = t0 if i <= a else t0 + dur * 0.85 * (1 - (1 - (i - a) / span) ** (1 / 3)) if span else t0
        x, y = pos[i]
        ass.add(start, t1, "Label", n["label"], x, y + 140, "\\fad(150,0)")
    bd = sc.get("badge")
    if bd and bd.get("text"):
        x, y = pos[bd["node"]]
        ass.add(t0 + dur * .3, t1, "Label", bd["text"], x + 120, y - 10, "\\c&H3FD2FF&\\fad(150,0)")


def draw_title(img, sc, p):
    d = ImageDraw.Draw(img, "RGBA")
    instant = sc.get("instant")  # frame 0 must already be full: no grow-from-nothing
    grow = (1.12 - 0.12 * ease(p * 5)) if instant else pop(p * 3)
    if sc.get("icon"):
        s = 300 * grow
        icon(d, sc["icon"], W / 2, 560, s, WHITE)
        if sc.get("check"):
            a = clamp(p * 3 - .6)
            icon(d, "check", W / 2 + s * .32, 560 + s * .3, s * .38, alpha=int(255 * a))
            if 0 < a < 1:  # sparkle burst as the tick lands
                cx, cy = W / 2 + s * .32, 560 + s * .3
                for k in range(10):
                    ang = math.radians(k * 36)
                    r0, r1 = s * .25 + 120 * a, s * .25 + 170 * a
                    d.line((cx + math.cos(ang) * r0, cy + math.sin(ang) * r0, cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                           fill=ACCENT + (int(255 * (1 - a)),), width=7)
    if sc.get("coin"):
        coin(img, W / 2, 560, 200 * grow)
    if sc.get("coins"):  # money flying phone to phone, for the opening question
        for k in range(4):
            f = ((p * 2.2) + k * .25) % 1
            x = 250 + (W - 500) * f
            y = 560 - 160 * math.sin(math.pi * f)
            coin(img, x, y, 90)
        icon(d, "phone", 170, 600, 260 * grow, WHITE)
        icon(d, "phone", W - 170, 600, 260 * grow, WHITE)


def title_text(ass, sc, t0, t1):
    y = 950 if (sc.get("icon") or sc.get("coin") or sc.get("coins")) else 760
    fx0 = "\\fscx115\\fscy115\\t(0,250,\\fscx100\\fscy100)" if sc.get("instant") else POP
    for k, line in enumerate(sc.get("lines", [])):
        start = t0 if sc.get("instant") else t0 + 0.25 * k
        ass.add(start, t1, "Big" if k == 0 else "Mid", line, W / 2, y + k * 150, fx0)


def draw_bars(img, sc, p):
    d = ImageDraw.Draw(img, "RGBA")
    va, vb = sc["a"]["value"], sc["b"]["value"]
    m = max(va, vb); full = 760; x0 = 160
    grow = ease(p / 0.4); merge = ease((p - 0.55) / 0.3)
    for k, (v, col) in enumerate(((va, ACCENT), (vb, (110, 170, 255)))):
        y = 620 + k * 230
        L = full * v / m * grow * (1 - merge * (min(va, vb) / v))
        d.rounded_rectangle((x0, y, x0 + max(8, L), y + 120), radius=24, fill=col + (255,))
    if merge > 0.98:
        coin(img, W / 2, 1250, int(150 * pop((p - .85) * 6)))


def bars_text(ass, sc, t0, t1):
    dur = t1 - t0; u = sc.get("unit", "")
    for k, side in enumerate((sc["a"], sc["b"])):
        y = 620 + k * 230
        ass.add(t0, t0 + dur * .55, "Label", f"{side['label']}  ₹{side['value']} {u}", W / 2, y - 45, "\\fad(150,150)")
    ass.add(t0 + dur * .85, t1, "Mid", sc.get("result", ""), W / 2, 1460, POP)


def draw_card(img, sc, p):
    d = ImageDraw.Draw(img, "RGBA")
    k = pop(p * 3)
    d.rounded_rectangle((90, 620 - 40 * k, W - 90, 1240 + 40 * k), radius=50, fill=(255, 255, 255, 18), outline=ACCENT + (200,), width=6)


def card_text(ass, sc, t0, t1):
    ass.add(t0 + .1, t1, "Big", sc["text"], W / 2, 900, POP)
    if sc.get("sub"):
        ass.add(t0 + .5, t1, "Mid", sc["sub"], W / 2, 1120, "\\fad(200,0)")


SCENES = {"flow": (draw_flow, flow_text), "title": (draw_title, title_text),
          "bars": (draw_bars, bars_text), "card": (draw_card, card_text)}


# ---------- build ----------
def main():
    epdir = os.path.abspath(sys.argv[1])
    ep = load_json(os.path.join(epdir, "episode.json"))
    build = os.path.join(epdir, "build"); os.makedirs(build, exist_ok=True)
    fonts = os.path.join(build, "fonts"); os.makedirs(fonts, exist_ok=True)
    for f in ("Nirmala.ttc",):
        if not os.path.exists(os.path.join(fonts, f)):
            shutil.copy(os.path.join("C:/Windows/Fonts", f), fonts)

    # voice, timeline
    timeline, t, audio_list = [], 0.0, []
    for i, beat in enumerate(ep["beats"]):
        a = os.path.join(build, f"v{i:02d}.mp3"); voice(beat, ep, a)
        d = duration(a) + PAD
        timeline.append((t, t + d, beat)); audio_list.append((a, d)); t += d
    total = t
    # audio: each clip padded to its slot, then joined
    parts = []
    for i, (a, d) in enumerate(audio_list):
        out = os.path.join(build, f"v{i:02d}.wav")
        ff("-i", a, "-af", f"apad=whole_dur={d:.3f}", "-t", f"{d:.3f}", "-ar", "44100", "-ac", "2", out)
        parts.append(out)
    lst = os.path.join(build, "audio.txt")
    open(lst, "w", encoding="utf-8").write("".join(f"file '{p}'\n" for p in parts))
    audio = os.path.join(build, "voice.wav")
    ff("-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", audio)

    # text track: scene text + karaoke captions (each word lights up as it is spoken)
    ass = Ass()
    for t0, t1, beat in timeline:
        sc = beat["scene"]; SCENES[sc["type"]][1](ass, sc, t0, t1)
        parts_ = chunks(beat.get("caption") or beat["say"], words=4)
        tot = sum(len(x) for x in parts_) or 1; c = t0
        for x in parts_:
            dt = (t1 - t0 - PAD) * len(x) / tot
            words = x.split(); wl = sum(len(w) for w in words) or 1
            kara = "".join(f"{{\\kf{max(1, round(dt * 100 * len(w) / wl))}}}{w} " for w in words)
            ass.ev.append(f"Dialogue: 0,{ts(c)},{ts(c + dt)},Cap,,0,0,0,,{kara.strip()}")
            c += dt
    ass.save(os.path.join(build, "text.ass"))

    # frames -> ffmpeg (graphics) + libass (text) + voice
    final = os.path.join(epdir, f"{ep['slug']}.mp4")
    music = sorted(__import__("glob").glob(os.path.join(ROOT, "assets", "music", "*.mp3")))
    cmd = [FFMPEG, "-hide_banner", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio]
    afilt = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    if music:
        cmd += ["-stream_loop", "-1", "-i", music[0]]
        afilt = "[2:a]volume=0.07[m];[1:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    cmd += ["-filter_complex", f"[0:v]ass=text.ass:fontsdir=fonts:shaping=complex[v];{afilt}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", final]
    log = open(os.path.join(build, "ffmpeg.log"), "w", encoding="utf-8")  # a stderr pipe would fill and deadlock
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log, cwd=build)
    n = int(total * FPS); bi = 0
    for f in range(n):
        tt = f / FPS
        while bi < len(timeline) - 1 and tt >= timeline[bi][1]:
            bi += 1
        t0, t1, beat = timeline[bi]
        img = background(tt, bi)
        SCENES[beat["scene"]["type"]][0](img, beat["scene"], (tt - t0) / (t1 - t0))
        into = tt - t0
        if bi > 0 and into < 0.25:  # beat change: punch-in + flash, a pattern interrupt every beat
            z = 1 + 0.07 * (1 - ease(into / 0.25))
            zw, zh = int(W * z), int(H * z)
            img = img.resize((zw, zh), Image.BILINEAR).crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))
            if into < 0.12:
                img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), 0.35 * (1 - into / 0.12))
        d = ImageDraw.Draw(img)  # progress bar: viewers see how little is left
        d.rectangle((0, 0, int(W * tt / total), 12), fill=ACCENT)
        p.stdin.write(img.tobytes())
    p.stdin.close(); p.wait(); log.close()
    if p.returncode:
        raise RuntimeError(open(os.path.join(build, "ffmpeg.log"), encoding="utf-8", errors="replace").read()[-2000:])
    ep["_render"] = {"file": os.path.basename(final), "seconds": round(total, 1)}
    save_json(os.path.join(epdir, "episode.json"), ep)
    print(f"  video {final}  ({total:.1f}s)")
    if ep.get("format") == "short" and total > 60:
        print("  WARNING over 60s - not a Short")


if __name__ == "__main__":
    main()

