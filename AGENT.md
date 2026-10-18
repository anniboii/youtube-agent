# Weekly run - YouTube agent for @AniruddhGoyalIITB

You are running unattended. Work in `C:\Users\Aniruddh Goyal\YouTube-Agent`. Read
`~/.claude/youtube/voice.md` first and follow it on every line you write. Faceless channel: voice
is the AI narrator (config.json), the visuals are the creator's own approved footage, text slides
and stock. Never put his face on screen.

Output this week: **1 long video (4-8 min) + 3 Shorts (30-55 s)**, all uploaded as PRIVATE.

## Steps

1. **Research** - run the /yt-viral method: re-collect the channels in `research/channels.txt`
   (yt-dlp --flat-playlist, last 30 videos + 30 Shorts each), run swipe.py at --min 2.0, save the
   output to `research/YYYY-MM-DD.md`. Note any new channel worth adding.
2. **Pick** - choose 1 long idea and 3 Short ideas that (a) match an outlier format from this week
   or the standing winners in `research/winners.md`, (b) can be made from approved footage
   (`footage/labels.json` scene tags) plus text slides, (c) are not already in `episodes/`.
3. **Script** - /yt-script method for each: write FIVE hooks, score them with
   `python ~/.claude/skills/yt-script/hookscore.py`, keep the best (store it in `hook_score`).
   No channel intro, no "is video mein". One idea per beat. Every beat names its visual.
   `say` is Devanagari Hinglish (English words stay in Latin script); `caption` is the same
   line in Roman Hinglish. Shorts: under 55 s at the rendered pace. Long: 600-1100 words.
4. **Package** - /yt-package: lint title + thumb_text as a pair with
   `python ~/.claude/skills/yt-package/title.py --title "..." --thumb "..."`. Fix every `x`.
5. **SEO** - /yt-seo: description (first 2 lines carry the search query), 8-15 tags.
6. **Build** - write `episodes/NNN-slug/episode.json`, then `python pipeline/make.py episodes/NNN-slug`.
7. **QC - mandatory, look at it**:
   - contact sheet: `ffmpeg -i video.mp4 -vf "fps=1/2.5,scale=270:-2,tile=7x4" -frames:v 1 sheet.jpg`
     and READ the image. Reject on: any recognisable face, burned-in old captions/text, footage that
     contradicts the line, unreadable captions. Fix the beat (swap tags, add `_avoid`) and rebuild.
   - read the thumbnail image the same way.
   - Shorts must be under 60 s (make.py warns).
8. **Upload** - `python pipeline/upload.py episodes/NNN-slug` (forced Private). If not signed in,
   skip upload and say so in the report - do not try to sign in.
9. **Report** - write `reports/YYYY-MM-DD.md`: what was made and why (which outlier it follows),
   hook scores, Studio links, anything rejected in QC, and the one thing to change next week.
   If retention CSVs appear in `inbox/`, run /yt-retention on them and include the finding.

## Hard rules

- Never publish. Upload is Private; making it Public is the creator's click in Studio.
- Never invent a number, rank, salary, statistic or quote. If a line needs a figure you do not
  have, rewrite the line without it.
- Never use footage that is not labelled `ok` in `footage/labels.json`.
- New footage in `footage/raw`: run `python pipeline/footage.py`, then `python pipeline/review.py
  sheets`, look at every sheet, write labels, `python pipeline/review.py apply <file>`.
- Do not reply to comments or post anything. Comment replies (/yt-comment) are drafts in the report.
- If anything fails, stop that item, keep going with the others, and put the error in the report.
