#!/usr/bin/env python3
from googleapiclient.discovery import build
from yt_auth import get_creds


def list_scheduled_videos():
    """Return every scheduled (private + future publishAt) video on the
    authenticated user's channel."""
    yt = build("youtube", "v3", credentials=get_creds())

    # 1. Uploads playlist contains ALL videos (public, unlisted, private, scheduled)
    ch = yt.channels().list(part="contentDetails", mine=True).execute()
    if not ch.get("items"):
        raise RuntimeError("No channel found for the authenticated account.")
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    scheduled = []
    page_token = None
    while True:
        pl = yt.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=uploads,
            maxResults=50,
            pageToken=page_token,
        ).execute()

        ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        if ids:  # guard: videos.list errors on an empty id= argument
            vids = yt.videos().list(
                part="status,snippet",
                id=",".join(ids),
            ).execute()

            for v in vids.get("items", []):
                st = v["status"]
                # Scheduled = private + has a publishAt timestamp
                if st.get("privacyStatus") == "private" and st.get("publishAt"):
                    scheduled.append({
                        "id": v["id"],
                        "title": v["snippet"]["title"],
                        "publish_at": st["publishAt"],   # ISO 8601, UTC
                        "url": f"https://www.youtube.com/watch?v={v['id']}",
                    })

        page_token = pl.get("nextPageToken")
        if not page_token:
            break

    return scheduled