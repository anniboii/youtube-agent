"""story.py - calm illustrated story explainers: props drawn in code, a camera that follows the story.

    python pipeline/story.py episodes/<slug>

Format (studied from a reference Short): a story told through everyday props - phone screens, a QR
stand, a ledger, sticky notes - on a warm palette. The camera pushes into and pans between props as
the narration moves; few hard cuts. Captions are Roman Hinglish in a dark box with **highlighted**
words; narration is Hindi (Devanagari "say"), one line at a time with real pauses.

episode.json ("style": "story"):
{
  "slug": "...", "voice": "hi-IN-SwaraNeural", "voice_rate": "+12%", "brand": "DAILY CURIO",
  "scenes": [
    {"bg": "desk" | "cream" | "teal",
     "props": [{"id": "phone", "type": "phone", "x": 800, "y": 1500, "screen": {"kind": "pay", ...},
                "show": 0, "states": {"2": {"screen": {"kind": "success", ...}}}}, ...],
     "lines": [{"say": "...", "cap": "Priya ne **₹20** ka UPI kiya.", "focus": "phone", "zoom": 1.8}, ...]}
  ]
}
"show" = line index (in that scene) where the prop appears; "states" = line index -> overrides.
Prop types: phone, notif, qr, speaker, hub, bank, card, ledger, bars, chip, sticky, avatar, book, title, arrow.
Canvas per scene is 1600 x 2844 (zoom 1 = the whole canvas on screen).
"""
import asyncio, hashlib, json, math, os, random, shutil, subprocess, sys
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from common import CFG, FFMPEG, ROOT, ff, duration, load_json, save_json
from make import pronounce
from anim import icon, Ass, ts

W, H, FPS = 1080, 1920, 30
CW, CH = 1600, 2844
PAUSE, SCENE_PAUSE = 0.38, 0.35

C = {"cream": (243, 238, 228), "paper": (251, 248, 241), "teal": (21, 66, 72), "teal2": (35, 92, 98),
     "orange": (222, 96, 52), "mustard": (232, 178, 62), "ink": (32, 34, 38), "grey": (205, 196, 184),
     "grey2": (160, 152, 142), "wall": (229, 221, 207), "desk": (78, 56, 43), "desk2": (62, 44, 34),
     "green": (46, 160, 112), "white": (255, 255, 255), "phone": (30, 36, 40), "skin": (196, 134, 92),
     "hair": (34, 28, 26), "red": (210, 70, 60), "blue": (60, 110, 200)}
F = {}
FONT_DIR = os.path.join(ROOT, "assets", "fonts")  # open Noto fonts (OFL) - used wherever Windows fonts are absent
WIN = os.path.exists("C:/Windows/Fonts/seguisb.ttf")
WIN_FONTS = {"r": "segoeui.ttf", "sb": "seguisb.ttf", "b": "segoeuib.ttf", "serif": "georgia.ttf",
             "serifb": "georgiab.ttf", "serifi": "georgiai.ttf", "mono": "consola.ttf", "monob": "consolab.ttf"}
NOTO_FONTS = {"r": "NotoSans-Regular.ttf", "sb": "NotoSans-SemiBold.ttf", "b": "NotoSans-Bold.ttf",
              "serif": "NotoSerif-Regular.ttf", "serifb": "NotoSerif-Bold.ttf", "serifi": "NotoSerif-Regular.ttf",
              "mono": "NotoSansMono-Regular.ttf", "monob": "NotoSansMono-Bold.ttf"}
CAP_FONT, HOOK_FONT = ("Segoe UI Semibold", "Segoe UI Black") if WIN else ("Noto Sans SemiBold", "Noto Sans Black")


def font(name, size):
    key = (name, size)
    if key not in F:
        path = os.path.join("C:/Windows/Fonts", WIN_FONTS[name]) if WIN else os.path.join(FONT_DIR, NOTO_FONTS[name])
        F[key] = ImageFont.truetype(path, size)
    return F[key]


# ---------- motion ----------
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease(x): x = clamp(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def spring(t, w=11.0, z=0.7):
    if t <= 0: return 0.0
    wd = w * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * w * t) * (math.cos(wd * t) + (z * w / wd) * math.sin(wd * t))


# ---------- sprite drawing: each returns an RGBA image; (x, y) in the episode is its centre ----------
def rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadowed(img, pad=24, alpha=60):
    """Soft drop shadow under a sprite - the flat-illustration look, not a glow."""
    from PIL import ImageFilter
    w, h = img.size
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    a = img.split()[3].point(lambda v: min(alpha, v))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 255)); sh.putalpha(a)
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)), (pad + 6, pad + 14))
    out.alpha_composite(img, (pad, pad))
    return out


def text_c(d, xy, s, f, fill, anchor="mm"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def wrap(d, s, f, maxw):
    out, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw or not cur: cur = t
        else: out.append(cur); cur = w
    if cur: out.append(cur)
    return out


def sp_phone(p):
    w, h = p.get("w", 400), p.get("h", 800)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 54, fill=C["phone"])
    sx0, sy0, sx1, sy1 = 18, 18, w - 18, h - 18
    rr(d, (sx0, sy0, sx1, sy1), 40, fill=C["paper"])
    d.rounded_rectangle((w / 2 - 50, 30, w / 2 + 50, 46), radius=8, fill=C["phone"])
    sc = p.get("screen", {}); k = sc.get("kind", "blank"); cx = w / 2
    if k == "pay":
        text_c(d, (cx, 140), sc.get("app", "UPI"), font("sb", 30), C["grey2"])
        d.ellipse((cx - 60, 200, cx + 60, 320), fill=C["teal"]); text_c(d, (cx, 260), sc.get("initial", "R"), font("b", 56), C["white"])
        text_c(d, (cx, 365), sc.get("to", "Ramesh Tea Stall"), font("sb", 32), C["ink"])
        text_c(d, (cx, 470), sc.get("amount", "₹20"), font("b", 110), C["ink"])
        rr(d, (60, h - 170, w - 60, h - 90), 40, fill=C["teal"]); text_c(d, (cx, h - 130), sc.get("button", "Pay"), font("b", 38), C["white"])
    elif k == "success":
        d.ellipse((cx - 95, 190, cx + 95, 380), fill=C["green"])
        d.line((cx - 45, 288, cx - 12, 322, cx + 50, 250), fill=C["white"], width=18, joint="curve")
        text_c(d, (cx, 440), sc.get("title", "Payment Successful"), font("b", 34), C["ink"])
        text_c(d, (cx, 520), sc.get("amount", "₹20"), font("b", 90), C["ink"])
        text_c(d, (cx, 600), sc.get("to", "to Ramesh Tea Stall"), font("r", 28), C["grey2"])
    elif k == "pin":
        text_c(d, (cx, 130), "ENTER UPI PIN", font("monob", 26), C["grey2"])
        for i in range(4):
            x = cx - 105 + i * 70; d.ellipse((x - 16, 190, x + 16, 222), fill=C["ink"])
        for r in range(4):
            for c in range(3):
                x, y = cx - 110 + c * 110, 320 + r * 105
                rr(d, (x - 44, y - 38, x + 44, y + 38), 18, fill=(232, 226, 214))
        icon(d, "lock", cx, h - 120, 70, C["teal"])
    elif k == "bank":
        rr(d, (40, 110, w - 40, 300), 26, fill=C["teal"])
        text_c(d, (70, 150), "BALANCE", font("monob", 22), (180, 210, 210), "lm")
        text_c(d, (70, 225), sc.get("balance", "• • • • •"), font("b", 54), C["white"], "lm")
        for i, (lab, val, col) in enumerate(sc.get("rows", [])):
            y = 360 + i * 90
            text_c(d, (60, y), lab, font("sb", 30), C["ink"], "lm"); text_c(d, (w - 60, y), val, font("b", 30), C[col], "rm")
            d.line((60, y + 40, w - 60, y + 40), fill=C["grey"], width=2)
    return img


def sp_notif(p):
    w, h = p.get("w", 520), 150
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 28, fill=(246, 242, 234), outline=C["grey"], width=3)
    d.ellipse((24, 30, 84, 90), fill=C[p.get("color", "teal")])
    text_c(d, (54, 60), p.get("glyph", "₹"), font("b", 34), C["white"])
    text_c(d, (104, 46), p.get("app", "BANK · now").upper(), font("monob", 20), C["grey2"], "lm")
    text_c(d, (104, 84), p.get("title", ""), font("b", 32), C["ink"], "lm")
    text_c(d, (104, 120), p.get("body", ""), font("r", 24), C["grey2"], "lm")
    return img


def sp_qr(p):
    w, h = 420, 620
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 80), 30, fill=C["white"], outline=C["grey"], width=4)
    d.polygon([(w / 2 - 70, h - 82), (w / 2 + 70, h - 82), (w / 2 + 120, h - 1), (w / 2 - 120, h - 1)], fill=C["grey"])
    text_c(d, (w / 2, 60), p.get("label", "SCAN & PAY"), font("monob", 28), C["teal"])
    rnd = random.Random(p.get("seed", 3)); x0, y0, cell = 70, 110, 14
    for i in range(20):
        for j in range(20):
            corner = (i < 6 and j < 6) or (i > 13 and j < 6) or (i < 6 and j > 13)
            if corner or rnd.random() < .45:
                d.rectangle((x0 + i * cell, y0 + j * cell, x0 + i * cell + cell - 1, y0 + j * cell + cell - 1), fill=C["ink"])
    for (ci, cj) in ((0, 0), (14, 0), (0, 14)):
        d.rectangle((x0 + ci * cell + 14, y0 + cj * cell + 14, x0 + ci * cell + 69, y0 + cj * cell + 69), fill=C["white"])
        d.rectangle((x0 + ci * cell + 28, y0 + cj * cell + 28, x0 + ci * cell + 55, y0 + cj * cell + 55), fill=C["ink"])
    text_c(d, (w / 2, h - 125), p.get("name", "Ramesh Tea Stall"), font("sb", 28), C["ink"])
    return img


def sp_speaker(p):
    w, h = 360, 300
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 44, fill=C["teal"])
    for r in range(4):
        for c in range(9):
            d.ellipse((40 + c * 32, 40 + r * 30, 52 + c * 32, 52 + r * 30), fill=C["teal2"])
    rr(d, (34, 180, w - 34, 262), 16, fill=(16, 30, 30))
    text_c(d, (w / 2, 221), p.get("led", "₹20 RECEIVED"), font("monob", 34), (120, 240, 170))
    return img


def sp_hub(p):
    w = h = 460
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.ellipse((30, 30, w - 30, h - 30), fill=C[p.get("color", "teal")])
    icon(d, "switch", w / 2, h / 2 - 40, 230, C["white"])
    text_c(d, (w / 2, h - 120), p.get("label", "NPCI"), font("b", 64), C["white"])
    return img


def sp_bank(p):
    w, h = 400, 400
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 36, fill=C["paper"], outline=C["grey"], width=4)
    icon(d, "bank", w / 2, 160, 210, C[p.get("color", "teal")])
    text_c(d, (w / 2, 320), p.get("label", "Bank"), font("b", 40), C["ink"])
    return img


def sp_card(p):
    w = p.get("w", 760); items = p.get("items", []); checks = p.get("checks", 0)
    h = p.get("h", 170 + 90 * len(items))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 18, fill=C["paper"], outline=C["grey"], width=3)
    text_c(d, (50, 80), p.get("title", ""), font("b", 50), C["ink"], "lm")
    d.line((50, 120, 150, 120), fill=C["orange"], width=6)
    for i, it in enumerate(items):
        y = 190 + i * 90
        if p.get("checkbox", True):
            rr(d, (50, y - 26, 102, y + 26), 8, outline=C["ink"], width=4)
            if i < checks:
                d.line((60, y, 74, y + 14, 96, y - 16), fill=C["green"], width=8)
            text_c(d, (130, y), it, font("sb", 38), C["ink"], "lm")
        else:
            text_c(d, (50, y), it, font("sb", 38), C["ink"], "lm")
    return img


def sp_ledger(p):
    rows = p.get("rows", []); reveal = p.get("reveal", len(rows)); w = 900; h = 180 + 110 * len(rows)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 18, fill=C["paper"], outline=C["grey"], width=3)
    text_c(d, (50, 80), p.get("title", "LEDGER"), font("monob", 40), C["teal"], "lm")
    for i, (lab, val, col) in enumerate(rows):
        if i >= reveal: break
        y = 180 + i * 110
        if col == "total":
            d.line((50, y - 50, w - 50, y - 50), fill=C["ink"], width=4); col = "orange"
        text_c(d, (50, y), lab, font("sb", 40), C["ink"], "lm"); text_c(d, (w - 50, y), val, font("b", 44), C[col], "rm")
    return img


def sp_chip(p):
    f = font("b", p.get("size", 46)); tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = tmp.textlength(p["text"], font=f); w, h = int(tw + 70), int(f.size * 1.7)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), fill=C[p.get("color", "orange")])
    text_c(d, (w / 2, h / 2), p["text"], f, C[p.get("fg", "white")])
    return img


def sp_sticky(p):
    w = p.get("w", 620); f = font("b", p.get("size", 56))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1))); lines = wrap(tmp, p["text"], f, w - 90)
    h = int(110 + len(lines) * f.size * 1.2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), fill=C[p.get("color", "mustard")])
    for i, ln in enumerate(lines):
        text_c(d, (45, 60 + i * f.size * 1.2), ln, f, C["ink"], "lm")
    return img.rotate(p.get("tilt", -3), expand=True, resample=Image.BICUBIC)


def sp_avatar(p):
    s = p.get("size", 520); img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    cx = s / 2; skin = C[p.get("skin", "skin")]; ex = p.get("expr", "neutral")
    d.pieslice((cx - s * .42, s * .62, cx + s * .42, s * 1.3), 180, 360, fill=C[p.get("shirt", "teal")])
    d.rectangle((cx - s * .09, s * .52, cx + s * .09, s * .68), fill=skin)
    d.ellipse((cx - s * .23, s * .14, cx + s * .23, s * .62), fill=skin)
    if p.get("hair", "short") == "long":
        d.ellipse((cx - s * .27, s * .08, cx + s * .27, s * .4), fill=C["hair"])
        d.rectangle((cx - s * .27, s * .24, cx - s * .17, s * .66), fill=C["hair"])
        d.rectangle((cx + s * .17, s * .24, cx + s * .27, s * .66), fill=C["hair"])
    else:
        d.pieslice((cx - s * .245, s * .1, cx + s * .245, s * .42), 180, 360, fill=C["hair"])
        d.rectangle((cx - s * .245, s * .26, cx - s * .2, s * .36), fill=C["hair"])
    ey = s * .37
    for sx in (-1, 1):
        x = cx + sx * s * .085
        if p.get("blink"):
            d.line((x - s * .022, ey, x + s * .022, ey), fill=C["ink"], width=max(3, int(s * .01)))
        else:
            d.ellipse((x - s * .018, ey - s * .02, x + s * .018, ey + s * .02), fill=C["ink"])
        by = ey - s * .055
        tilt = {"angry": .02 * sx, "worried": -.02 * sx, "surprised": -.02}.get(ex, 0) * s
        d.line((x - s * .04, by - tilt, x + s * .04, by + tilt), fill=C["hair"], width=max(3, int(s * .012)))
    my = s * .5
    mouth = p.get("mouth", 0)  # 0 closed .. 2 wide: driven by the speaker's own audio level
    if mouth:
        h_ = s * (.018 if mouth == 1 else .038)
        d.ellipse((cx - s * .045, my - h_, cx + s * .045, my + h_), fill=(70, 30, 30))
    elif ex == "happy":
        d.arc((cx - s * .07, my - s * .05, cx + s * .07, my + s * .03), 20, 160, fill=C["ink"], width=max(3, int(s * .012)))
    elif ex == "surprised":
        d.ellipse((cx - s * .025, my - s * .025, cx + s * .025, my + s * .03), fill=C["ink"])
    else:
        d.line((cx - s * .05, my, cx + s * .05, my), fill=C["ink"], width=max(3, int(s * .012)))
    return img


def sp_bars(p):
    w, h = 1000, 620
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    va, vb = p["a"]["value"], p["b"]["value"]; m = max(va, vb); net = p.get("net", False)
    for k, (side, col) in enumerate(((p["a"], "orange"), (p["b"], "teal"))):
        y = 90 + k * 230; L = 900 * side["value"] / m
        if net: L = 900 * (abs(va - vb) / m) if k == 0 else 6
        text_c(d, (40, y - 10), f"{side['label']}   ₹{side['value']} cr", font("sb", 40), C["ink"], "lm")
        rr(d, (40, y + 30, 40 + max(12, L), y + 140), 14, fill=C[col])
    if net:
        text_c(d, (w / 2, 560), p.get("result", ""), font("b", 64), C["orange"])
    return img


def sp_book(p):
    w, h = 900, 760
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    rr(d, (0, 0, w - 1, h - 1), 20, fill=C["teal"])
    text_c(d, (w / 2, 110), p.get("kicker", "").upper(), font("monob", 30), C["mustard"])
    for i, ln in enumerate(wrap(d, p.get("title", ""), font("serif", 72), w - 140)):
        text_c(d, (w / 2, 230 + i * 86), ln, font("serif", 72), C["paper"])
    text_c(d, (w / 2, h - 210), p.get("big", ""), font("serifb", 110), C["paper"])
    for i, ln in enumerate(wrap(d, p.get("sub", ""), font("b", 40), w - 140)):
        text_c(d, (w / 2, h - 100 + i * 48), ln, font("b", 40), C["mustard"])
    return img


def sp_title(p):
    f = font(p.get("font", "b"), p.get("size", 110)); tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines = p["text"].split("\n"); w = int(max(tmp.textlength(l, font=f) for l in lines) + 40); h = int(len(lines) * f.size * 1.15 + 30)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        text_c(d, (w / 2, 15 + f.size * .6 + i * f.size * 1.15), ln, f, C[p.get("color", "ink")])
    return img


def sp_arrow(p):
    L = p.get("len", 300); img = Image.new("RGBA", (L + 40, 80), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.line((10, 40, L - 20, 40), fill=C[p.get("color", "orange")], width=14)
    d.polygon([(L - 30, 12), (L + 30, 40), (L - 30, 68)], fill=C[p.get("color", "orange")])
    return img.rotate(-p.get("angle", 0), expand=True, resample=Image.BICUBIC)


SPRITES = {"phone": sp_phone, "notif": sp_notif, "qr": sp_qr, "speaker": sp_speaker, "hub": sp_hub, "bank": sp_bank,
           "card": sp_card, "ledger": sp_ledger, "chip": sp_chip, "sticky": sp_sticky, "avatar": sp_avatar,
           "bars": sp_bars, "book": sp_book, "title": sp_title, "arrow": sp_arrow}
NO_SHADOW = {"chip", "title", "arrow"}
_CACHE = {}


def sprite(p):
    key = json.dumps({k: v for k, v in p.items() if k not in ("x", "y", "show", "states", "id")}, sort_keys=True, ensure_ascii=False)
    if key not in _CACHE:
        img = SPRITES[p["type"]](p)
        _CACHE[key] = img if p["type"] in NO_SHADOW else shadowed(img)
    return _CACHE[key]


# ---------- backgrounds ----------
_BG = {}
def background(kind):
    if kind not in _BG:
        img = Image.new("RGB", (CW, CH), C["cream"]); d = ImageDraw.Draw(img)
        if kind == "desk":
            d.rectangle((0, 0, CW, int(CH * .5)), fill=C["wall"])
            d.rectangle((0, int(CH * .5), CW, CH), fill=C["desk"])
            d.rectangle((0, int(CH * .5), CW, int(CH * .5) + 26), fill=C["desk2"])
            d.rectangle((CW - 330, 160, CW - 120, 560), fill=(54, 80, 84))  # a window shape, like a real room
        elif kind == "teal":
            img.paste(C["teal"], (0, 0, CW, CH))
        rnd = random.Random(1)
        for _ in range(9000):  # paper grain, baked once
            x, y = rnd.randrange(CW), rnd.randrange(CH); v = rnd.choice((-6, 6))
            px = img.getpixel((x, y)); img.putpixel((x, y), tuple(max(0, min(255, c + v)) for c in px))
        _BG[kind] = img
    return _BG[kind]


# ---------- voice ----------
async def _tts(text, voice, rate, out):
    await edge_tts.Communicate(text, voice, rate=rate).save(out)


def voice_for(ln, ep):
    """Line voice: "who" names a character in ep["cast"] (voice, rate); default is the narrator."""
    cast = ep.get("cast", {})
    who = ln.get("who", "narrator")
    c = cast.get(who) or cast.get("narrator") or {"voice": ep.get("voice", CFG["voice"]), "rate": ep.get("voice_rate", "+12%")}
    return who, c["voice"], c.get("rate", ep.get("voice_rate", "+12%"))


def speak(text, voice, rate, out):
    key = hashlib.md5(f"{voice}|{rate}|{text}".encode()).hexdigest()
    if not (os.path.exists(out) and os.path.exists(out + ".key") and open(out + ".key").read() == key):
        asyncio.run(_tts(text, voice, rate, out)); open(out + ".key", "w").write(key)


def envelope(path):
    """Loudness per video frame (0..1), to drive the speaking character's mouth."""
    import numpy as np
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32); hop = 16000 // FPS
    n = len(x) // hop
    if n == 0: return []
    rms = np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1))
    return list(np.clip(rms / (np.percentile(rms, 90) + 1e-6), 0, 1.5))


# ---------- captions ----------
def cap_ass(cap):
    """**word** -> mustard highlight."""
    out, on = "", False
    for part in cap.split("**"):
        if part:
            out += ("{\\c&H3EB2E8&}" + part + "{\\c&HFFFFFF&}") if on else part
        on = not on
    return out


ASS_HEAD = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{CAP_FONT},62,&H00FFFFFF,&H00FFFFFF,&H28282220,&H28282220,-1,0,0,0,100,100,0,0,3,16,0,2,110,110,330,1
Style: Hook,{HOOK_FONT},86,&H00FFFFFF,&H00FFFFFF,&H003460DE,&H003460DE,-1,0,0,0,100,100,0,0,3,22,0,8,90,90,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


ENV = {}  # (scene, line) -> (who, t0, per-frame loudness)


# ---------- build ----------
def main():
    epdir = os.path.abspath(sys.argv[1])
    ep = load_json(os.path.join(epdir, "episode.json"))
    build = os.path.join(epdir, "build"); os.makedirs(build, exist_ok=True)

    # 1. voice: one clip per line, real pauses between lines
    timeline, t, n = [], 0.0, 0   # (scene_idx, line_idx, t0, t1)
    clips = []
    for si, sc in enumerate(ep["scenes"]):
        for li, ln in enumerate(sc["lines"]):
            text = ln.get("say_override") or pronounce(ln["say"]); ln["_say_tts"] = text
            who, vo, rate = voice_for(ln, ep)
            mp3 = os.path.join(build, f"s{n:02d}.mp3"); speak(text, vo, rate, mp3)
            d = duration(mp3)
            gap = PAUSE + (SCENE_PAUSE if li == len(sc["lines"]) - 1 else 0)
            gap = ln.get("pause", gap)
            timeline.append((si, li, t, t + d)); clips.append((mp3, d + gap))
            ENV[(si, li)] = (who, t, envelope(mp3)); t += d + gap; n += 1
    total = t
    scene_t = {}
    for si, li, t0, t1 in timeline:
        a, b = scene_t.get(si, (t0, t1)); scene_t[si] = (min(a, t0), max(b, t1))
    starts = [scene_t[s][0] for s in range(len(ep["scenes"]))]
    ends = starts[1:] + [total]

    parts = []
    for i, (mp3, d) in enumerate(clips):
        w = os.path.join(build, f"s{i:02d}.wav")
        ff("-i", mp3, "-af", f"apad=whole_dur={d:.3f}", "-t", f"{d:.3f}", "-ar", "44100", "-ac", "2", w); parts.append(w)
    lst = os.path.join(build, "svoice.txt")
    open(lst, "w", encoding="utf-8").write("".join(f"file '{p}'\n" for p in parts))
    voice_wav = os.path.join(build, "svoice.wav")
    ff("-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", voice_wav)

    # 2. per-scene: prop appear times, camera keyframes, sfx cues
    line_t = {(si, li): (t0, t1) for si, li, t0, t1 in timeline}
    cues = []
    for si, sc in enumerate(ep["scenes"]):
        s0 = starts[si]
        if si: cues.append((max(0, s0 - 2 / FPS), "whoosh"))
        for p in sc["props"]:
            show = p.get("show", 0)
            p["_t"] = s0 if show == 0 else line_t[(si, show)][0] - 0.1
            if si == 0 and show == 0:
                p["_t"] = -1.0  # frame 0 must already be full - no fade-in on the opening shot
            if p["type"] in ("notif",): cues.append((p["_t"] + .05, "ding"))
            elif p["_t"] > s0 + 0.05: cues.append((p["_t"] + .04, "pop"))
            for k in p.get("states", {}):
                tk = line_t[(si, int(k))][0] - 0.1
                st = p["states"][k]
                cues.append((tk + .04, "ding" if st.get("screen", {}).get("kind") == "success" else "tick"))
        keys = []  # camera: (t, cx, cy, zoom)
        props = {p["id"]: p for p in sc["props"] if "id" in p}
        for li, ln in enumerate(sc["lines"]):
            t0 = line_t[(si, li)][0]
            f = ln.get("focus"); z = ln.get("zoom", 1.0)
            if f in props:
                cx, cy = props[f]["x"] + ln.get("dx", 0), props[f]["y"] + ln.get("dy", 0)
            else:
                cx, cy = CW / 2, CH / 2
            keys.append((t0 - 0.15 if li else starts[si], cx, cy, z))
        sc["_cam"] = keys

    # 3. sfx mix (CC0 kit from Barty-Bart/motion-graphics), quieter than the kinetic style
    from kinetic import SFX_DIR, KIT
    gains = {"whoosh": -16, "pop": -17, "ding": -12, "tick": -18}
    sfx = None
    cues = [c for c in sorted(cues) if c[0] < total]
    if cues and os.path.isdir(SFX_DIR):
        ins, fl = [], []
        for k, (tc, kind) in enumerate(cues):
            ins += ["-i", os.path.join(SFX_DIR, KIT[kind])]; dl = int(tc * 1000)
            fl.append(f"[{k}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={gains[kind]}dB,adelay={dl}|{dl}[s{k}]")
        fl.append("".join(f"[s{k}]" for k in range(len(cues))) + f"amix=inputs={len(cues)}:normalize=0:duration=longest,apad=whole_dur={total:.3f}[o]")
        sfx = os.path.join(build, "ssfx.wav")
        ff(*ins, "-filter_complex", ";".join(fl), "-map", "[o]", "-t", f"{total:.3f}", sfx)

    # 4. captions
    ass_ev = []
    for si, li, t0, t1 in timeline:
        ln = ep["scenes"][si]["lines"][li]; cap = cap_ass(ln["cap"])
        who = ln.get("who", "narrator")
        if who != "narrator":  # a character speaking: name tag, like a chat line
            cap = "{\\c&H3460DE&}" + ep.get("cast", {}).get(who, {}).get("name", who).upper() + ":{\\c&HFFFFFF&} " + cap
        ass_ev.append(f"Dialogue: 0,{ts(t0)},{ts(t1 + PAUSE * .8)},Cap,,0,0,0,,{{\\fad(90,60)}}{cap}")
    if ep.get("hook_title"):  # the question, readable in frame 0, gone once the story takes over
        h_end = timeline[min(1, len(timeline) - 1)][3] if len(timeline) > 1 else timeline[0][3]
        ass_ev.append(f"Dialogue: 1,{ts(0)},{ts(h_end)},Hook,,0,0,0,,{{\\fad(0,200)\\fscx108\\fscy108\\t(0,220,\\fscx100\\fscy100)}}{cap_ass(ep['hook_title'])}")
    open(os.path.join(build, "stext.ass"), "w", encoding="utf-8-sig").write(ASS_HEAD + "\n".join(ass_ev) + "\n")

    # 5. frames
    final = os.path.join(epdir, f"{ep['slug']}.mp4")
    cmd = [FFMPEG, "-hide_banner", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", voice_wav]
    # music bed (optional): ep["music"] = path under assets/music; sits ~20 dB under the voice and ducks while
    # anyone speaks (sidechain), so the voice always wins (voice > SFX > music)
    music = ep.get("music"); mpath = os.path.join(ROOT, music) if music else None
    k = 2
    mix_in = "[1:a]"
    pre = ""
    if sfx:
        cmd += ["-i", sfx]; mix_in += f"[{k}:a]"; k += 1
    if mpath and os.path.exists(mpath):
        cmd += ["-stream_loop", "-1", "-i", mpath]
        pre = (f"[1:a]asplit=2[vx][sc];[{k}:a]volume={ep.get('music_db', -20)}dB,afade=t=in:d=1,"
               f"afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[mu];[mu][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];")
        mix_in = mix_in.replace("[1:a]", "[vx]") + "[md]"
    n_in = mix_in.count("[")
    af = pre + f"{mix_in}amix=inputs={n_in}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=9[a]" if n_in > 1 else \
        "[1:a]loudnorm=I=-14:TP=-1.5:LRA=9[a]"
    cmd += ["-filter_complex", f"[0:v]ass=stext.ass:shaping=complex:fontsdir={os.path.relpath(FONT_DIR, build).replace(os.sep, "/")}[v];{af}", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", final]
    log = open(os.path.join(build, "sffmpeg.log"), "w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log, cwd=build)
    brand = ep.get("brand", "DAILY CURIO"); bfont = font("monob", 30)
    prev_last = None; si = 0
    for fr in range(int(total * FPS)):
        tt = fr / FPS
        while si < len(ep["scenes"]) - 1 and tt >= starts[si + 1]:
            si += 1
        sc = ep["scenes"][si]; s0, s1 = starts[si], ends[si]
        canvas = background(sc.get("bg", "cream")).copy()
        line_idx = max([li for (a, li, t0, t1) in timeline if a == si and t0 - 0.1 <= tt] or [0])
        for p in sc["props"]:
            if tt < p["_t"]: continue
            q = dict(p)
            for k in sorted(p.get("states", {}), key=int):
                if int(k) <= line_idx: q.update(p["states"][k])
            if p["type"] == "avatar":  # alive: blink every few seconds, mouth follows its own voice
                q["blink"] = ((tt + hash(p.get("id", "")) % 7) % 3.7) < 0.12
                cur = ENV.get((si, line_idx))
                if cur and cur[0] == p.get("who"):
                    fi = int((tt - cur[1]) * FPS)
                    lvl = cur[2][fi] if 0 <= fi < len(cur[2]) else 0
                    q["mouth"] = 0 if lvl < .25 else (1 if lvl < .7 else 2)
            spr = sprite(q); a = tt - p["_t"]
            s = spring(a, 10, .72); alpha = clamp(a / 0.22)
            if p["type"] == "notif":  # drops in from above
                dy = -90 * (1 - ease(a / .35)); scale = 1.0
            else:
                dy = 40 * (1 - s); scale = 0.9 + 0.1 * s
            img = spr if abs(scale - 1) < 1e-3 else spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BILINEAR)
            if alpha < 1:
                img = img.copy(); img.putalpha(img.split()[3].point(lambda v: int(v * alpha)))
            canvas.paste(img, (int(p["x"] - img.width / 2), int(p["y"] - img.height / 2 + dy)), img)
        # camera: ease between line targets, plus a slow continuous push so nothing is ever still
        keys = sc["_cam"]; k = max([i for i, kk in enumerate(keys) if kk[0] <= tt] or [0])
        tk, cx, cy, z = keys[k]
        if k:
            _, px, py, pz = keys[k - 1]; e = ease((tt - tk) / 1.1)
            cx, cy, z = px + (cx - px) * e, py + (cy - py) * e, pz + (z - pz) * e
        z *= 1 + 0.035 * ((tt - s0) / max(1, s1 - s0))
        lt0 = max([t0 for (a, li, t0, t1) in timeline if a == si and t0 <= tt] or [s0])
        z *= 1 + 0.03 * max(0.0, 1 - (tt - lt0) / 0.3) ** 2  # small punch-in on every new line
        vw, vh = CW / z, CH / z
        x0 = clamp(cx - vw / 2, 0, CW - vw); y0 = clamp(cy - vh / 2, 0, CH - vh)
        frame = canvas.crop((int(x0), int(y0), int(x0 + vw), int(y0 + vh))).resize((W, H), Image.BILINEAR)
        if si and tt - s0 < 0.25 and prev_last is not None:  # soft crossfade between scenes
            frame = Image.blend(prev_last, frame, ease((tt - s0) / 0.25))
        if tt < s1 - 1 / FPS:
            last_of_scene = frame
        else:
            prev_last = frame
        dd = ImageDraw.Draw(frame)
        dd.text((60, 70), brand, font=bfont, fill=C["ink"] if sc.get("bg") != "teal" else C["paper"])
        proc.stdin.write(frame.tobytes())
        if tt + 1 / FPS >= s1:
            prev_last = frame
    proc.stdin.close(); proc.wait(); log.close()
    if proc.returncode:
        raise RuntimeError(open(os.path.join(build, "sffmpeg.log"), encoding="utf-8", errors="replace").read()[-2000:])
    ep["_render"] = {"file": os.path.basename(final), "seconds": round(total, 1), "lines": len(timeline), "scenes": len(ep["scenes"])}
    save_json(os.path.join(epdir, "episode.json"), ep)
    open(os.path.join(epdir, "CREDITS.txt"), "w", encoding="utf-8").write(
        "Sound effects: CC0 1.0 (Freesound / Kenney) via Barty-Bart/motion-graphics sound-effects kit.\n")
    print(f"  video {final}  ({total:.1f}s, {len(timeline)} lines, {len(ep['scenes'])} scenes)")


if __name__ == "__main__":
    main()
