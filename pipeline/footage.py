"""footage.py - index the channel's own uploads into faceless b-roll windows.

    python pipeline/footage.py            # index new files in footage/raw
    python pipeline/footage.py --rebuild  # re-index everything

Each video is cut into fixed windows. A window is kept only if no face is detected in any of three
sampled frames and the frame is not near-black or flat. Windows are tagged from the video's title
and description so a script can ask for "mess" or "hostel" or "night".
"""
import glob, json, os, subprocess, sys
import cv2
import numpy as np
from common import CFG, FFMPEG, FOOTAGE_RAW, FOOTAGE_INDEX, load_json, save_json

# Personal footage never used as b-roll, matched against the title.
EXCLUDE = ["shaadi", "wedding", "didi", "sister", "b'day", "bday", "birthday", "my channel", "trailer", "intro"]

TAGS = {
    "campus": ["iit", "campus", "insti", "powai", "first day", "areal", "aerial"],
    "hostel": ["hostel", "room", "h16", "hostel16"],
    "mess": ["mess", "khana", "food", "dal", "bati", "zomato", "swiggy"],
    "lecture": ["lecture", "class", "lh", "library", "exam", "quiz", "acads"],
    "fest": ["mood indigo", "techfest", "insync", "concert", "fest", "nite", "goonj", "show"],
    "music": ["music", "band", "guitar", "drums", "song", "jamming", "raabta"],
    "dance": ["dance", "insync"],
    "holi": ["holi"],
    "graduation": ["graduation", "convocation", "degree", "alumni", "reunion", "valedictory"],
    "city": ["mumbai", "marine", "bangalore", "bengaluru", "city", "beach", "night"],
    "work": ["office", "intern", "internship", "corporate", "google", "shadowfax", "job"],
    "travel": ["train", "airport", "air india", "home", "travel", "cycling", "lake"],
    "jee": ["jee", "result", "josaa", "advanced", "books", "strategy", "tips", "motivation"],
    "tech": ["robotics", "project", "unboxing", "tech", "mechanical", "club", "chemistry"],
}

FRONT = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
PROFILE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
YUNET_PATH = os.path.join(os.path.dirname(FOOTAGE_INDEX), "..", "assets", "models", "yunet.onnx")
YUNET = None
MAX_FACE = 0.07  # a face taller than 7% of the frame is a recognisable face; crowds far away pass


def tags_for(info):
    text = " ".join([info.get("title", ""), info.get("description", "")[:400]]).lower()
    tags = [t for t, kws in TAGS.items() if any(k in text for k in kws)]
    return tags or ["campus"]


def has_face(gray):
    """YuNet when the model is present (far better on close-ups and angles); Haar as a fallback."""
    global YUNET
    h, w = gray.shape
    if os.path.exists(YUNET_PATH):
        if YUNET is None or tuple(YUNET.getInputSize()) != (w, h):
            YUNET = cv2.FaceDetectorYN.create(YUNET_PATH, "", (w, h), 0.6, 0.3, 50)
        _, faces = YUNET.detect(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
        return faces is not None and any(f[3] > MAX_FACE * h for f in faces)
    for c in (FRONT, PROFILE):
        if len(c.detectMultiScale(gray, 1.15, 6, minSize=(36, 36))):
            return True
    return False


def probe(path):
    cap = cv2.VideoCapture(path)
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return w, h


def scan(path, seg):
    """Decode at 2 fps, 480 px wide, through ffmpeg; a window passes if every sampled frame does."""
    w, h = probe(path)
    sw = 480; sh = int(sw * h / w) // 2 * 2
    p = subprocess.Popen([FFMPEG, "-v", "error", "-i", path, "-vf", f"fps=2,scale={sw}:{sh}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    good, size = [], sw * sh
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        g = np.frombuffer(buf, np.uint8).reshape(sh, sw)
        good.append(not (g.mean() < 35 or g.std() < 18 or has_face(g)))
    p.wait()
    total = len(good) / 2
    keep, t = [], 6.0 if total > 30 else 0.5
    while t + seg < total - 3:
        a, b = int(t * 2), int((t + seg) * 2) + 1
        if all(good[a:b]):
            keep.append(round(t, 2)); t += seg + 0.5
        else:
            t += 0.5
    return {"duration": round(total, 2), "w": w, "h": h, "starts": keep}


def main():
    rebuild = "--rebuild" in sys.argv
    seg = CFG["clip_seconds"]
    index = {} if rebuild else load_json(FOOTAGE_INDEX, {})
    for path in sorted(glob.glob(os.path.join(FOOTAGE_RAW, "*.mp4"))):
        name = os.path.basename(path)
        if name in index:
            continue
        info = load_json(path[:-4] + ".info.json", {}) or {}
        if any(x in info.get("title", "").lower() for x in EXCLUDE):
            index[name] = {"excluded": True, "title": info.get("title"), "starts": [], "tags": []}
            save_json(FOOTAGE_INDEX, index); continue
        r = scan(path, seg)
        r.update(title=info.get("title", name), tags=tags_for(info),
                 vertical=r["h"] > r["w"], views=info.get("view_count"))
        index[name] = r
        save_json(FOOTAGE_INDEX, index)
        print(f"{len(r['starts']):4d} faceless windows  {r['tags']}  {r['title'][:60]}", flush=True)
    total = sum(len(v["starts"]) for v in index.values())
    print(f"\n{len(index)} videos, {total} faceless windows (~{total * seg / 60:.0f} min of b-roll)")


if __name__ == "__main__":
    main()
