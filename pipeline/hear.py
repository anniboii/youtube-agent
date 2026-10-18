"""hear.py - transcribe narration back with Whisper, to catch mispronounced words before upload.

    python pipeline/hear.py episodes/<slug>          # every beat's voice clip vs its script
    python pipeline/hear.py some.mp3

A word the transcript renders very differently from the script (an acronym read as a word, an
English word mangled) is listed per beat. It is a check you read, not a verdict: Whisper also
makes mistakes, so a flagged word means listen to that beat.
"""
import glob, os, subprocess, sys
import numpy as np
from common import FFMPEG, load_json

_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel("small", device="cpu", compute_type="int8")
    return _MODEL


def pcm(path):
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def transcribe(path):
    segs, _ = model().transcribe(pcm(path), language="hi", beam_size=5, vad_filter=False)
    return " ".join(s.text.strip() for s in segs)


def main():
    target = os.path.abspath(sys.argv[1])
    if os.path.isdir(target):
        ep = load_json(os.path.join(target, "episode.json"))
        clips = sorted(glob.glob(os.path.join(target, "build", "s[0-9][0-9].mp3")) or glob.glob(os.path.join(target, "build", "k[0-9][0-9].mp3")) or glob.glob(os.path.join(target, "build", "v[0-9][0-9].mp3")) or
                       glob.glob(os.path.join(target, "build", "b[0-9][0-9].mp3")))
        lines = ep.get("beats") or [ln for sc in ep.get("scenes", []) for ln in sc["lines"]]
        for i, c in enumerate(clips):
            print(f"\n[{i:02d}] SCRIPT  {lines[i].get('_say_tts') or lines[i]['say']}")
            print(f"     HEARD   {transcribe(c)}")
    else:
        print(transcribe(target))


if __name__ == "__main__":
    main()
