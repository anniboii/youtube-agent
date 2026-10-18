# Daily run - one Daily Curio story video, ready to post

You are running unattended. Never upload or post anything - the creator posts by hand. Never invent a number,
statistic or claim.

**Where you are running:**
- **Cloud (Linux, Claude Code routine):** you are in a checkout of github.com/anniboii/youtube-agent. Run
  `bash setup.sh` first. Python is `python3`. Commands below written as `python pipeline/...` work as `python3 ...`.
  Fonts come from `assets/fonts` (Noto, OFL) automatically.
- **Laptop (Windows):** work in `C:\Users\Aniruddh Goyal\YouTube-Agent`. Use PowerShell (Git Bash is blocked by the
  laptop's application-control policy). Python is `python`; set `$env:PYTHONIOENCODING="utf-8"` before python calls.
If a program, package or site is blocked, do not try to work around it - stop that step and report it.

**State lives in the repo:** `state/used_topics.json` and `episodes/NNN-*/episode.json` + `POST.md`. In the cloud,
commit and push them at the end of the run (message "daily: NNN-slug") so tomorrow's run sees them. Videos are not
committed (.gitignore); see step 5 for delivery.

## 1. Pick today's topic
- The library is the Daily Curio artifact https://claude.ai/artifact/ThSSCgGNcTKWY1vav47aVz, collection `topics`
  (read it with the ArtifactData tool, `list`, saving to `state/curio/` with out_dir).
- `state/used_topics.json` lists topic ids already made into videos. Pick the first unused topic that tells well
  as a story (a person, an everyday moment, a twist). Prefer variety: not the same category as yesterday.
- If every topic is used: write ONE new Daily Curio explainer first (how an everyday thing in India really works),
  researched with WebSearch, in the library's exact document shape (title, category, hook, minutes, sections[{h,body}],
  facts[], aura, sources[{t,u}], origin "daily", date today, createdAt ms, read false, readAt null) and add it with
  ArtifactData `set` (new doc id = slug of the title). Then use it.

## 2. Fact-check
Every claim the video makes must be backed today by a source (the topic's own sources, or WebSearch). Drop or
soften ("typically", "maan lo" for examples) anything you cannot confirm. Record what you checked in
`facts_checked` in episode.json.

## 3. Write the episode
- Copy the structure of `episodes/004-upi-story/episode.json` (read it first - it is the approved style).
- `episodes/NNN-<slug>/episode.json`, NNN = next number. "style": "story", with a "cast" (see 3b).
- Story: one named person (vary names, gender, city), an everyday moment, the hidden mechanism step by step,
  a twist, the payoff line, then the Curio "aura" line as "Agli baar koi pooche, toh bolna: ...", then follow.
- Hook: line 1 starts mid-action with tension inside 2 seconds (no intro, no "aaj hum"). Score 5 hook options with
  `python ~/.claude/skills/yt-script/hookscore.py hooks.txt`, keep the best.
- 14-18 lines, 55-80 s (see 3b). Each line: "say" in Devanagari (English words may stay Latin), "cap" in Roman Hinglish
  with 1-2 **highlighted** words, a "focus" prop and "zoom" (1.0 wide - 2.0 close).
- Props only from story.py's list (phone screens pay/success/pin/bank, notif, qr, speaker, hub, bank, card, ledger,
  bars, chip, sticky, avatar, book, title, arrow). Text on props is Latin script only (Pillow cannot shape Devanagari).
  Keep important props above the bottom 30% of the frame - captions live there.
- Avoid the spoken word "app" (heard as "aap"); write acronyms in pronounce.json with spaced letters.

## 3b. Make it catchy (creator's standing feedback - apply every time)
- **Voices (cast):** narrator = `hi-IN-MadhurNeural` rate "+12%" (male, matches the reference Short the creator
  loves); characters = `hi-IN-SwaraNeural` "+10%" for women, a second male voice only if needed. In episode.json:
  `"cast": {"narrator": {...}, "priya": {"voice": ..., "rate": ..., "name": "Priya"}}`, and `"who": "priya"` on her
  lines. Give the avatar prop the same `"who"` - its mouth then moves with her voice.
- **Dialogue, not a lecture:** at least 3-4 lines spoken by characters ("Bhaiya, paisa aaya?", "Yeh kaise hua?").
  A small conflict or confusion between two people is the engine of the story.
- **Frame 0 = the question.** Set `"hook_title"`: the curiosity question in 6-9 words, Roman, with one
  **highlighted** word ("₹20 gaye… par **pahunche** kahan?"). It shows from the first frame. Line 1 is spoken
  mid-action. Keep the top 15% of the first two shots free so the card does not cover a face.
- **Open loop by 40%:** one line that promises the twist is coming ("Par asli khel abhi baaki hai").
- **Length 55-80 s**, 14-18 lines, no line longer than ~12 words. Cut anything that is not story, mechanism, twist
  or payoff.
- **Something changes every 3-4 s:** a new prop, a state change, a camera move or a character reaction (expr).
- **Ending loops:** the last story line should echo line 1, so a rewatch feels continuous.
- **Music:** if `assets/music/` has an approved track, set `"music": "assets/music/<file>.mp3"`, `"music_db": -20`.
  It ducks automatically under speech. Never download music on your own - only tracks the creator approved.

## 4. Render and check (mandatory - you cannot hear, so measure)
1. `python pipeline/story.py episodes/NNN-slug`
2. `python pipeline/hear.py episodes/NNN-slug` - for any line where an English word or acronym comes back wrong,
   add a spelling to `pronounce.json` or reword the line, re-render, re-check. Whisper itself misreads बैंक as
   "बांक" - that alone is fine.
3. Contact sheet: one frame from the middle of every line (see how 004 was checked) and READ the image. Fix
   cropped faces, captions covering props, empty frames, wrong framing. Re-render until clean.
4. Loudness: `ffmpeg -i video.mp4 -af ebur128=peak=true -f null -` -> about -14 LUFS, peak below -1 dBFS.

## 5. Ready-to-post pack
In the episode folder write `POST.md`:
- YouTube Shorts: title (under 70 chars, the question/curiosity), description (2 lines + hashtags), tags.
- Instagram Reel: caption (hook line, 1-line payoff, a "save/share" ask, 6-10 hashtags).
- Best time to post: 7-9 PM IST unless analytics in `reports/` say otherwise.
- The facts checked and their sources.
Append the topic id to `state/used_topics.json`.

**Delivery (cloud runs):** upload the MP4 and POST.md to the creator's Google Drive folder **"Daily Curio Videos"**
(create it if missing) with the Google Drive connector, so they can watch and post from their phone. If the
connector is unavailable or refuses a file that size, say so in the report and leave the video in the run's
workspace - do not commit video files to git.

## 6. Report
Send a push notification (PushNotification tool, if available) or end with a short summary: the topic, the video
path, length, hook score, anything you could not verify or fix. If any step failed, say exactly which and why.
