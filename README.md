# youtube-agent

Private production pipeline for youtube.com/@AniruddhGoyalIITB: faceless, Hindi-narrated animated Shorts made from
the Daily Curio library. It makes videos and post packs; it never posts.

- `DAILY.md` - the daily runbook (one Daily Curio story video + POST.md), for the laptop task or a cloud routine.
- `pipeline/story.py` - story style (props, camera, cast of voices, boxed Roman Hinglish captions). Current default.
- `pipeline/kinetic.py`, `pipeline/anim.py` - fast kinetic-type style and the earlier animated style.
- `pipeline/hear.py` - Whisper transcription of the narration, to catch mispronounced words.
- `pronounce.json` - spellings that make the Hindi voice say English words and acronyms correctly.
- `episodes/NNN-slug/episode.json` - one per video. `004-upi-story` is the approved reference.
- `state/used_topics.json` - Daily Curio topics already made.
- `profile/voice.md`, `skills/yt-*` - creator voice profile and the yt skills (hookscore etc.) the runbooks call.
- `assets/sfx` - CC0 sound kit (Kenney / Freesound via Barty-Bart/motion-graphics, see LICENSES.md).
- `assets/fonts` - Noto fonts, SIL Open Font License (OFL.txt).

Cloud setup: `bash setup.sh`. Never commit `secrets/`.
