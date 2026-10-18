"""kinetic.py - fast, high-energy animated explainers: kinetic type, colour floods, HUD, real SFX.

    python pipeline/kinetic.py episodes/<slug>

Design rules adapted from Barty-Bart/motion-graphics (MIT): explainer-high-energy (spring overshoot,
kinetic slams on hard background swaps, transitions as objects, HUD viewfinder, grain + vignette,
3 colours max per shot, no glows, no emoji) and sound-effects (real CC0 sounds, one per cue,
whoosh 2 frames early, voice > SFX > music, measured loudness). Sound-pass method credited to Vox.

episode.json ("style": "kinetic") - each beat has "say" (Devanagari narration, English words in
Latin; pronounce.json fixes how they are spoken) and "shots", each starting on a spoken word:

  {"at": 0, "type": "question", "lines": ["UPI 2 सेकंड में", "पैसा कैसे भेजता है?"], "bg": "ink"}
  {"at": "पैसा", "type": "slam", "text": "पैसा गया ही नहीं", "bg": "accent", "hit": true}
  {"at": 0, "type": "flow", "from": 0, "to": 1, "nodes": [...], "badge": {...}}
  {"at": 0, "type": "icon", "icon": "lock", "text": "GPay को भी नहीं दिखता", "bg": "blue"}
  {"at": 0, "type": "bars", "a": {...}, "b": {...}, "unit": "करोड़", "result": "..."}
  {"at": 3, "type": "pattern", "text": "PROMISE", "bg": "cream"}       # word repeated as outline pattern

"at" is a word index in the beat or the first caption word containing that string. Optional per
shot: "sfx": "impact"|"pop"|"ding"|"riser"|"none". A shot with "riser": true gets a riser that
ENDS on its start.
"""
import asyncio, glob, hashlib, json, math, os, random, shutil, subprocess, sys
import edge_tts
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from common import CFG, FFMPEG, ROOT, ff, duration, load_json, save_json
from make import pronounce
from anim import icon, coin, Ass, ts, HINDI_FONT

W, H, FPS = 1080, 1920, 30
PAL = {"ink": (11, 11, 16), "accent": (255, 79, 26), "cream": (237, 235, 228), "blue": (47, 71, 255), "white": (255, 255, 255)}
TEXT_ON = {"ink": "white", "accent": "ink", "cream": "ink", "blue": "white", "white": "ink"}
HI = {"ink": "accent", "accent": "white", "cream": "accent", "blue": "white", "white": "accent"}  # highlight colour per bg
SFX_DIR = os.path.join(ROOT, "assets", "sfx")  # CC0 kit from Barty-Bart/motion-graphics (see assets/sfx/LICENSES.md)
MONO = ImageFont.truetype("C:/Windows/Fonts/consola.ttf" if os.path.exists("C:/Windows/Fonts/consola.ttf")
                          else os.path.join(ROOT, "assets", "fonts", "NotoSansMono-Regular.ttf"), 26)
TAIL = 0.15  # breath after each beat


def ass_col(rgb):
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}&"


# ---------- motion ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def spring(t, w=14.0, z=0.62):
    """Damped spring 0 -> 1 with overshoot (z < 1). Ported from explainer-high-energy."""
    if t <= 0: return 0.0
    if z >= 1: return 1 - math.exp(-w * t) * (1 + w * t)
    wd = w * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * w * t) * (math.cos(wd * t) + (z * w / wd) * math.sin(wd * t))
def ease(x): x = clamp(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


# ---------- texture (built once) ----------
_VIG, _GRAIN = None, []
def texture(img, f):
    global _VIG
    if _VIG is None:
        m = Image.new("L", (W // 4, H // 4), 0)
        px = m.load()  # radial: dark corners
        for y in range(H // 4):
            for x in range(W // 4):
                dx, dy = (x - W / 8) / (W / 8), (y - H / 8) / (H / 8)
                px[x, y] = int(130 * clamp((dx * dx + dy * dy) ** .5 - 0.55, 0, 1))
        _VIG = m.resize((W, H), Image.BILINEAR)
        rng = random.Random(7)
        for _ in range(4):
            g = Image.effect_noise((W // 2, H // 2), 40).resize((W, H))
            _GRAIN.append(g)
    img.paste((0, 0, 0), (0, 0, W, H), _VIG)
    return Image.blend(img, Image.merge("RGB", [_GRAIN[f % 4]] * 3), 0.035)


def hud(img, k, n, label, t, total):
    d = ImageDraw.Draw(img, "RGBA")
    c = (255, 255, 255, 120); m, L = 46, 54
    for (x, y, sx, sy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
        d.line((x, y, x + sx * L, y), fill=c, width=4); d.line((x, y, x, y + sy * L), fill=c, width=4)
    d.text((W - m - 8, m + 22), f"{k:02d} / {n:02d}", font=MONO, fill=c, anchor="ra")
    d.text((m + 8, H - m - 22), label.upper(), font=MONO, fill=c, anchor="ld")
    tc = f"{int(t // 60):02d}:{int(t % 60):02d}:{int((t % 1) * FPS):02d}"
    d.text((W - m - 8, H - m - 22), tc, font=MONO, fill=c, anchor="rd")
    if int(t * 2) % 2 == 0:
        d.ellipse((W - m - 200, H - m - 50, W - m - 184, H - m - 34), fill=(255, 50, 50, 220))
    d.rectangle((0, 0, int(W * t / total), 10), fill=PAL["accent"] + (255,))


# ---------- shot drawers: (img, shot, local_t, shot_dur) ----------
def bg_fill(img, name):
    img.paste(PAL[name], (0, 0, W, H))


def flood(img, prev_bg, bg, lt, origin):
    """Transition object: the new colour grows from a point until it is the background."""
    if lt >= 0.32 or prev_bg == bg:
        bg_fill(img, bg); return
    bg_fill(img, prev_bg)
    r = (math.hypot(W, H)) * ease(lt / 0.32)
    x, y = origin
    ImageDraw.Draw(img).ellipse((x - r, y - r, x + r, y + r), fill=PAL[bg])


def draw_question(img, sh, lt, dur):
    d = ImageDraw.Draw(img, "RGBA")
    for k in range(5):  # coins arc phone -> phone, never stop
        f = ((lt * 1.4) + k * .2) % 1
        coin(img, 230 + (W - 460) * f, 520 - 190 * math.sin(math.pi * f), 84)
    s = 250 * (0.85 + 0.15 * spring(lt + 0.15))
    icon(d, "phone", 150, 560, s); icon(d, "phone", W - 150, 560, s)


def draw_slam(img, sh, lt, dur):
    if sh.get("bar"):  # a bar slides under the text
        L = W * 0.78 * spring(lt - 0.08, 16, 0.75)
        ImageDraw.Draw(img).rectangle((W / 2 - L / 2, 1130, W / 2 + L / 2, 1152), fill=PAL[HI[sh["bg"]]])


def draw_pattern(img, sh, lt, dur):
    pass  # the outline pattern is text, drawn in ASS


def draw_icon(img, sh, lt, dur):
    d = ImageDraw.Draw(img, "RGBA")
    col = PAL[TEXT_ON[sh["bg"]]]
    s = 380 * spring(lt, 13, 0.55)
    icon(d, sh["icon"], W / 2, 720, s, col)
    if sh.get("ring"):
        ph = (lt * 1.6) % 1
        r = 260 + 160 * ph
        d.ellipse((W / 2 - r, 720 - r, W / 2 + r, 720 + r), outline=col + (int(200 * (1 - ph)),), width=6)


def flow_pos(n):
    top, bot = 360, 1380
    return [(W * (0.3 if i % 2 == 0 else 0.7), top + (bot - top) * i / max(1, n - 1)) for i in range(n)]


def draw_flow(img, sh, lt, dur):
    d = ImageDraw.Draw(img, "RGBA")
    nodes = sh["nodes"]; pos = flow_pos(len(nodes))
    a, b = sh.get("from", 0), sh.get("to", len(nodes) - 1)
    prog = a + (b - a) * ease(clamp(lt / max(0.4, dur * 0.8)))
    line = PAL["accent"]; fg = PAL[TEXT_ON[sh.get("bg", "ink")]]
    for i in range(len(nodes) - 1):
        if i >= prog: break
        (x0, y0), (x1, y1) = pos[i], pos[i + 1]; f = clamp(prog - i)
        d.line((x0, y0, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), fill=line, width=12)
    for i, (x, y) in enumerate(pos):
        if i > max(a, math.floor(prog + 1e-3)):
            d.ellipse((x - 70, y - 70, x + 70, y + 70), outline=fg + (50,), width=3); continue
        arrive = clamp(prog - (i - 1)) if i > a else 1.0
        r = 96 * (0.4 + 0.6 * spring(arrive * 0.6, 14, 0.5)) if i > a else 96
        active = abs(prog - i) < 0.5
        d.ellipse((x - r, y - r, x + r, y + r), fill=(PAL["accent"] if active else (40, 40, 52)) + (255,))
        icon(d, nodes[i].get("icon", "bank"), x, y, r * .95, PAL["ink"] if active else PAL["white"])
    if prog < b:
        i = int(prog); f = prog - i
        (x0, y0), (x1, y1) = pos[i], pos[min(i + 1, len(pos) - 1)]
        coin(img, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, 76)
    bd = sh.get("badge")
    if bd and lt > 0.3:
        x, y = pos[bd["node"]]
        icon(d, bd.get("icon", "lock"), x + 130, y - 100, 80 * spring(lt - 0.3, 14, 0.5), PAL["accent"])


def draw_bars(img, sh, lt, dur):
    d = ImageDraw.Draw(img, "RGBA")
    va, vb = sh["a"]["value"], sh["b"]["value"]; m = max(va, vb)
    grow = spring(lt, 9, 0.8); merge = ease((lt - dur * 0.5) / (dur * 0.25))
    for k, (v, col) in enumerate(((va, PAL["accent"]), (vb, PAL["blue"]))):
        y = 640 + k * 240
        L = 800 * v / m * grow * (1 - merge * (min(va, vb) / v))
        d.rectangle((140, y, 140 + max(10, L), y + 130), fill=col)


DRAW = {"question": draw_question, "slam": draw_slam, "pattern": draw_pattern, "icon": draw_icon,
        "flow": draw_flow, "bars": draw_bars}


# ---------- shot text (ASS) ----------
SLAM_FX = "\\fscx160\\fscy160\\blur8\\t(0,90,\\fscx92\\fscy92\\blur0)\\t(90,200,\\fscx104\\fscy104)\\t(200,300,\\fscx100\\fscy100)"
IN_FX = "\\blur6\\t(0,140,\\blur0)"


def shot_text(ass, sh, t0, t1):
    bg = sh.get("bg", "ink"); fg = ass_col(PAL[TEXT_ON[bg]]); hi = ass_col(PAL[HI[bg]])
    ty = sh["type"]
    if ty == "question":
        for k, line in enumerate(sh["lines"]):
            ass.add(t0, t1, "Big", line, W / 2, 900 + k * 150, f"\\c{hi if k == 0 else fg}\\fscx118\\fscy118\\t(0,220,\\fscx100\\fscy100)")
    elif ty == "slam":
        lines = sh["text"].split("\n")
        for k, line in enumerate(lines):
            st = t0 + 0.06 * k
            ass.add(st, t1, "Slam", line, W / 2 + (60 if k % 2 else -60) * 0, 920 + (k - (len(lines) - 1) / 2) * 175,
                    f"\\c{hi if k == len(lines) - 1 else fg}{SLAM_FX}")
        if sh.get("sub"):
            ass.add(t0 + .25, t1, "Mid", sh["sub"], W / 2, 1180, f"\\c{fg}{IN_FX}")
    elif ty == "pattern":
        for row in range(9):
            y = 240 + row * 175
            off = (row % 2) * 220
            ass.add(t0 + row * 0.03, t1, "Out", (sh["text"] + "  ") * 3, W / 2 - 120 + off, y,
                    f"\\3c{ass_col(PAL[HI[bg]])}\\alpha&HB0&\\fad(120,0)")
        ass.add(t0 + .15, t1, "Slam", sh["text"], W / 2, 900, f"\\c{fg}{SLAM_FX}")
        if sh.get("sub"):
            ass.add(t0 + .35, t1, "Mid", sh["sub"], W / 2, 1100, f"\\c{fg}\\3c{ass_col(PAL[bg])}\\bord8{IN_FX}")
    elif ty == "icon":
        ass.add(t0 + .12, t1, "Mid", sh.get("text", ""), W / 2, 1140, f"\\c{fg}{IN_FX}")
    elif ty == "flow":
        pos = flow_pos(len(sh["nodes"]))
        a, b = sh.get("from", 0), sh.get("to", len(sh["nodes"]) - 1)
        span = max(1, b - a); dur = max(0.4, (t1 - t0) * 0.8)
        for i, n in enumerate(sh["nodes"]):
            if i > b: continue
            st = t0 if i <= a else t0 + dur * ((i - a) / span)
            x, y = pos[i]
            ass.add(st, t1, "Label", n["label"], x, y + 150, f"{IN_FX}")
        if sh.get("badge", {}).get("text"):
            x, y = pos[sh["badge"]["node"]]
            ass.add(t0 + .3, t1, "Label", sh["badge"]["text"], x + 130, y - 20, f"\\c{ass_col(PAL['accent'])}")
    elif ty == "bars":
        u = sh.get("unit", ""); half = t0 + (t1 - t0) * 0.5
        for k, side in enumerate((sh["a"], sh["b"])):
            ass.add(t0 + .1 * k, half, "Label", f"{side['label']}  ₹{side['value']} {u}", W / 2, 640 + k * 240 - 50, "\\fad(80,120)")
        ass.add(t0 + (t1 - t0) * 0.78, t1, "Slam", sh.get("result", ""), W / 2, 1300, f"\\c{ass_col(PAL['accent'])}{SLAM_FX}")


ASS_STYLES = f"""Style: Big,{HINDI_FONT},124,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1
Style: Slam,{HINDI_FONT},170,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,-2,0,1,0,0,5,30,30,0,1
Style: Mid,{HINDI_FONT},70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,60,60,0,1
Style: Out,{HINDI_FONT},150,&HFF000000,&HFF000000,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1
Style: Label,{HINDI_FONT},48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,20,20,0,1
Style: Cap,{HINDI_FONT},68,&H0000D9FF,&H00FFFFFF,&H50000000,&H50000000,-1,0,0,0,100,100,0,0,3,14,0,2,80,80,250,1
"""


# ---------- voice with word timings ----------
async def _tts(text, voice, rate, out_mp3):
    c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    with open(out_mp3, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio": f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
    return words


def speak(beat, ep, out):
    v = ep.get("voice", CFG["voice"]); r = ep.get("voice_rate", CFG["voice_rate"])
    text = beat.get("say_override") or pronounce(beat["say"]); beat["_say_tts"] = text
    key = hashlib.md5(f"{v}|{r}|{text}".encode()).hexdigest()
    meta = out + ".json"
    m = load_json(meta)
    if not (m and m.get("key") == key and os.path.exists(out)):
        words = asyncio.run(_tts(text, v, r, out))
        save_json(meta, {"key": key, "words": words}); m = {"words": words}
    return m["words"]


def align(caption_words, tts_words, dur):
    """Times for each caption word: 1:1 when counts match, else by character share of the TTS clock."""
    if len(caption_words) == len(tts_words):
        return [(a, b) for a, b, _ in tts_words]
    if not tts_words:
        n = len(caption_words); return [(dur * i / n, dur * (i + 1) / n) for i in range(n)]
    t_start, t_end = tts_words[0][0], tts_words[-1][1]
    total = sum(len(w) for w in caption_words) or 1; out, c = [], t_start
    for w in caption_words:
        d = (t_end - t_start) * len(w) / total; out.append((c, c + d)); c += d
    return out


# ---------- sfx ----------
KIT = {"whoosh": "kit/whoosh.ogg", "pop": "kit/pop.ogg", "impact": "kit/impact.ogg", "riser": "kit/riser.ogg",
       "tick": "kit/tick.ogg", "ding": "ding/kenney-interface-confirmation-001.ogg", "click": "kit/click.ogg"}
GAIN = {"whoosh": -9, "pop": -10, "impact": -5, "riser": -11, "tick": -14, "ding": -8, "click": -12}


def sfx_mix(cues, total, build):
    """One real sound per cue, mixed under the voice. Returns a wav path or None."""
    if not cues or not os.path.isdir(SFX_DIR):
        return None
    inputs, parts = [], []
    for k, (t, kind) in enumerate(cues):
        p = os.path.join(SFX_DIR, KIT[kind])
        delay = max(0, int(t * 1000))
        inputs += ["-i", p]
        parts.append(f"[{k}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={GAIN[kind]}dB,adelay={delay}|{delay}[s{k}]")
    mix = "".join(f"[s{k}]" for k in range(len(cues))) + f"amix=inputs={len(cues)}:normalize=0:duration=longest,apad=whole_dur={total:.3f}[out]"
    out = os.path.join(build, "sfx.wav")
    ff(*inputs, "-filter_complex", ";".join(parts) + ";" + mix, "-map", "[out]", "-t", f"{total:.3f}", out)
    return out


# ---------- build ----------
def main():
    epdir = os.path.abspath(sys.argv[1])
    ep = load_json(os.path.join(epdir, "episode.json"))
    build = os.path.join(epdir, "build"); os.makedirs(build, exist_ok=True)
    fonts = os.path.join(build, "fonts"); os.makedirs(fonts, exist_ok=True)
    if not os.path.exists(os.path.join(fonts, "Nirmala.ttc")):
        shutil.copy("C:/Windows/Fonts/Nirmala.ttc", fonts)

    # voice + word clock
    beats, t = [], 0.0
    clips = []
    for i, beat in enumerate(ep["beats"]):
        mp3 = os.path.join(build, f"k{i:02d}.mp3")
        words = speak(beat, ep, mp3)
        d = duration(mp3) + TAIL
        cap = (beat.get("caption") or beat["say"]).split()
        times = [(t + a, t + b) for a, b in align(cap, words, d - TAIL)]
        beats.append({"t0": t, "t1": t + d, "beat": beat, "cap": cap, "times": times})
        clips.append((mp3, d)); t += d
    total = t

    # shots on the word clock
    shots = []
    for B in beats:
        for sh in B["beat"]["shots"]:
            at = sh.get("at", 0)
            if isinstance(at, str):
                at = next((i for i, w in enumerate(B["cap"]) if at in w), 0)
            st = B["t0"] if at == 0 else B["times"][min(at, len(B["times"]) - 1)][0] - 0.05
            shots.append({**sh, "_t0": st})
    shots.sort(key=lambda s: s["_t0"])
    for i, sh in enumerate(shots):
        sh["_t1"] = shots[i + 1]["_t0"] if i + 1 < len(shots) else total
        sh.setdefault("bg", "ink")
        sh["_prev_bg"] = shots[i - 1]["bg"] if i else sh["bg"]

    # audio: voice track
    parts = []
    for i, (mp3, d) in enumerate(clips):
        w = os.path.join(build, f"k{i:02d}.wav")
        ff("-i", mp3, "-af", f"apad=whole_dur={d:.3f}", "-t", f"{d:.3f}", "-ar", "44100", "-ac", "2", w); parts.append(w)
    lst = os.path.join(build, "kvoice.txt")
    open(lst, "w", encoding="utf-8").write("".join(f"file '{p}'\n" for p in parts))
    voice_wav = os.path.join(build, "kvoice.wav")
    ff("-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", voice_wav)

    # sfx cues from the composition itself (skill: take cues from the timeline when you can)
    cues = []
    for i, sh in enumerate(shots):
        if i: cues.append((max(0, sh["_t0"] - 2 / FPS), "whoosh"))
        kind = sh.get("sfx") or {"slam": "impact" if sh.get("hit") else "pop", "pattern": "impact",
                                 "icon": "pop", "question": "pop", "bars": "pop", "flow": "tick"}.get(sh["type"])
        if kind and kind != "none": cues.append((sh["_t0"] + 0.03, kind))
        if sh.get("riser"):
            cues.append((max(0, sh["_t0"] - 1.1), "riser"))
        if sh["type"] == "flow":  # a tick each time the coin reaches a node
            a, b = sh.get("from", 0), sh.get("to", 1); span = max(1, b - a)
            dd = max(0.4, (sh["_t1"] - sh["_t0"]) * 0.8)
            for k in range(1, span + 1):
                cues.append((sh["_t0"] + dd * k / span, "pop"))
        if sh.get("ding_at_end"):
            cues.append((sh["_t1"] - 0.35, "ding"))
    sfx = sfx_mix(sorted(cues), total, build)

    # text track
    ass = Ass()
    for sh in shots:
        shot_text(ass, sh, sh["_t0"] + (0.12 if sh["bg"] != sh["_prev_bg"] else 0), sh["_t1"])
    for B in beats:  # karaoke captions on the real word clock, 3-4 words a line
        cap, times = B["cap"], B["times"]
        i = 0
        while i < len(cap):
            j = min(len(cap), i + 4)
            for k in range(i + 1, j):
                if cap[k - 1].endswith((",", ".", "?", "!")): j = k; break
            st, en = times[i][0], times[j - 1][1] + 0.05
            kara = "".join(f"{{\\kf{max(1, round((times[k][1] - times[k][0]) * 100))}}}{cap[k]} " for k in range(i, j))
            ass.ev.append(f"Dialogue: 1,{ts(st)},{ts(en)},Cap,,0,0,0,,{kara.strip()}")
            i = j
    path = os.path.join(build, "ktext.ass")
    ass.save(path)
    txt = open(path, encoding="utf-8-sig").read()
    head, rest = txt.split("[Events]")
    head = head.split("Style: Cap")[0].rsplit("Format: Name", 1)
    style_hdr = "Format: Name" + head[1].split("\n")[0]
    open(path, "w", encoding="utf-8-sig").write(head[0] + style_hdr + "\n" + ASS_STYLES + "\n[Events]" + rest)

    # frames
    final = os.path.join(epdir, f"{ep['slug']}.mp4")
    cmd = [FFMPEG, "-hide_banner", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", voice_wav]
    if sfx:
        cmd += ["-i", sfx]
        afilt = "[1:a]volume=0dB[vo];[2:a]volume=-2dB[s];[vo][s]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    else:
        afilt = "[1:a]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    cmd += ["-filter_complex", f"[0:v]ass=ktext.ass:fontsdir=fonts:shaping=complex[v];{afilt}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", final]
    log = open(os.path.join(build, "kffmpeg.log"), "w", encoding="utf-8")
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log, cwd=build)
    label = ep.get("hud_label", "kaise kaam karta hai")
    si = 0
    for f in range(int(total * FPS)):
        tt = f / FPS
        while si < len(shots) - 1 and tt >= shots[si + 1]["_t0"]:
            si += 1
        sh = shots[si]; lt = tt - sh["_t0"]
        img = Image.new("RGB", (W, H))
        flood(img, sh["_prev_bg"], sh["bg"], lt, sh.get("origin", (W / 2, H * .45)))
        DRAW[sh["type"]](img, sh, lt, sh["_t1"] - sh["_t0"])
        if si and lt < 0.18:  # camera punch on every cut
            z = 1 + 0.06 * (1 - ease(lt / 0.18)); zw, zh = int(W * z), int(H * z)
            img = img.resize((zw, zh), Image.BILINEAR).crop(((zw - W) // 2, (zh - H) // 2, (zw - W) // 2 + W, (zh - H) // 2 + H))
        img = texture(img, f)
        hud(img, si + 1, len(shots), label, tt, total)
        p.stdin.write(img.tobytes())
    p.stdin.close(); p.wait(); log.close()
    if p.returncode:
        raise RuntimeError(open(os.path.join(build, "kffmpeg.log"), encoding="utf-8", errors="replace").read()[-2000:])
    ep["_render"] = {"file": os.path.basename(final), "seconds": round(total, 1), "shots": len(shots),
                     "avg_shot_s": round(total / len(shots), 2)}
    save_json(os.path.join(epdir, "episode.json"), ep)
    used = sorted({k for _, k in cues})
    open(os.path.join(epdir, "CREDITS.txt"), "w", encoding="utf-8").write(
        "Sound effects: CC0 1.0 (Freesound / Kenney) via Barty-Bart/motion-graphics sound-effects kit: " + ", ".join(used) +
        "\nSound-pass method: Vox (@Voxyz_ai). Motion design rules: Barty-Bart/motion-graphics (MIT).\n")
    print(f"  video {final}  ({total:.1f}s, {len(shots)} shots, avg {total / len(shots):.1f}s/shot)")
    if ep.get("format") == "short" and total > 60:
        print("  WARNING over 60s - not a Short")


if __name__ == "__main__":
    main()
