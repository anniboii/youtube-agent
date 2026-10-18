# One-time setup (about 10 minutes, only you can do these)

Everything else is automated. These steps need your Google account, so they are yours.

## 1. Let the agent upload to your channel (as Private)

1. Open https://console.cloud.google.com/ with the Google account that owns @AniruddhGoyalIITB.
2. Create a project (any name, e.g. "yt-agent").
3. APIs & Services -> Library -> search **YouTube Data API v3** -> Enable.
4. APIs & Services -> OAuth consent screen -> External -> fill app name + your email ->
   add yourself under **Test users**.
5. APIs & Services -> Credentials -> Create credentials -> **OAuth client ID** -> type
   **Desktop app** -> Create -> **Download JSON**.
6. Save that file as `C:\Users\Aniruddh Goyal\YouTube-Agent\secrets\client_secret.json`.
7. In a terminal:

   ```
   cd "C:\Users\Aniruddh Goyal\YouTube-Agent"
   python pipeline\upload.py --auth
   ```

   A browser opens; sign in and allow. It prints the channel name it will upload to.

## 2. Optional - stock footage

Free key from https://www.pexels.com/api/ -> paste it alone into `secrets\pexels_key.txt`.

## 3. Optional - background music

Drop one or more royalty-free `.mp3` files into `assets\music\` (YouTube Audio Library is safe).
The first one plays quietly under every video.

## 4. Optional - pick a different voice

Listen to `assets\voice-samples\`. To change, edit `"voice"` in `config.json`
(`hi-IN-MadhurNeural`, `en-IN-PrabhatNeural`, `hi-IN-SwaraNeural`).

## 5. Retention data (makes the agent smarter each week)

Studio -> a video -> Analytics -> Engagement -> audience retention -> download ->
put the CSV in `inbox\`. The weekly run reads it.
