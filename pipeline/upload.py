"""upload.py - upload a rendered episode to YouTube as PRIVATE, with its thumbnail.

    python pipeline/upload.py --auth                 # one-time Google sign-in (opens your browser)
    python pipeline/upload.py episodes/<slug>        # upload as private

Privacy is forced to the config value ("private"). Going public is a click you make in Studio.
Needs secrets/client_secret.json (an OAuth "Desktop app" client from Google Cloud with the
YouTube Data API v3 enabled). The token lands in secrets/token.json after --auth.
"""
import os, sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from common import CFG, SECRETS, load_json, save_json

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
CLIENT = os.path.join(SECRETS, "client_secret.json")
TOKEN = os.path.join(SECRETS, "token.json")


def creds(interactive=False):
    c = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if c and c.expired and c.refresh_token:
        c.refresh(Request())
    if not c or not c.valid:
        if not interactive:
            sys.exit("Not signed in. Run: python pipeline/upload.py --auth")
        if not os.path.exists(CLIENT):
            sys.exit(f"Missing {CLIENT} - see SETUP.md step 3.")
        c = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES).run_local_server(port=0)
    open(TOKEN, "w").write(c.to_json())
    return c


def main():
    if "--auth" in sys.argv:
        yt = build("youtube", "v3", credentials=creds(True))
        ch = yt.channels().list(part="snippet", mine=True).execute()["items"][0]["snippet"]["title"]
        print("Signed in. Uploads will go to:", ch)
        return
    epdir = os.path.abspath(sys.argv[1])
    ep = load_json(os.path.join(epdir, "episode.json"))
    if ep.get("_upload", {}).get("id"):
        sys.exit(f"Already uploaded: https://youtu.be/{ep['_upload']['id']}")
    video = os.path.join(epdir, ep["_render"]["file"])
    tags = ep.get("tags", [])
    title = ep["title"] + (" #shorts" if ep.get("format") == "short" and "#short" not in ep["title"].lower() else "")
    body = {
        "snippet": {"title": title[:100], "description": ep.get("description", ""), "tags": tags,
                    "categoryId": CFG["category_id"], "defaultLanguage": CFG["default_language"],
                    "defaultAudioLanguage": CFG["default_language"]},
        "status": {"privacyStatus": CFG["upload_privacy"], "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": CFG["contains_synthetic_media"]},
    }
    yt = build("youtube", "v3", credentials=creds())
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%", flush=True)
    vid = resp["id"]
    thumb = os.path.join(epdir, "thumbnail.jpg")
    if os.path.exists(thumb) and ep.get("format") != "short":
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb)).execute()
        except Exception as e:
            print("  thumbnail not set (channel may need phone verification):", str(e)[:200])
    ep["_upload"] = {"id": vid, "privacy": CFG["upload_privacy"]}
    save_json(os.path.join(epdir, "episode.json"), ep)
    print(f"Uploaded as {CFG['upload_privacy'].upper()}: https://youtu.be/{vid}")
    print(f"Review and publish: https://studio.youtube.com/video/{vid}/edit")


if __name__ == "__main__":
    main()
