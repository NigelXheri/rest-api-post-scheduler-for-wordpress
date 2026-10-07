#!/usr/bin/env python3
"""Produce the featured image for a scheduled YouTube video's post.

YouTube's thumbnail CDN refuses to serve real images for private videos,
and the Data API only returns URLs (which point at that same CDN). The
only reliable pre-publish path is to extract a real frame from the video:
yt-dlp authenticates as the channel owner via browser cookies and
downloads only a few seconds around the target timestamp; ffmpeg then
pulls a single full-resolution frame from that clip, and cwebp re-encodes
it as WebP.

System deps (install with apt): ffmpeg, webp
"""
import os
import subprocess
import tempfile
import time
from pathlib import Path

from wp_slug import wp_slug

THUMB_DIR = Path("thumbnails")
COOKIES = os.getenv("YT_COOKIES", "cookies.txt")
DEFAULT_AT_SECONDS = 3
DEFAULT_WEBP_QUALITY = 70
DEFAULT_WEBP_METHOD = 6
DEFAULT_WIDTH = 800  # <-- New default width for WordPress cards

_MIN_VALID_BYTES = 10_000
_TRANSIENT = "the page needs to be reloaded"


def fetch_thumbnail(video_id: str, video_title: str | None = None,
                    at_seconds: int = DEFAULT_AT_SECONDS,
                    cookies: str = COOKIES,
                    quality: int = DEFAULT_WEBP_QUALITY,
                    width: int = DEFAULT_WIDTH) -> Path:  # <-- Added width
    """Return a local WebP holding a frame from `video_id` at `at_seconds`.

    Cached by slug: subsequent calls return the existing file without
    touching the network.
    """
    THUMB_DIR.mkdir(exist_ok=True)
    stem = wp_slug(video_title) if video_title else video_id
    final = THUMB_DIR / f"{stem}.webp"

    if final.exists() and final.stat().st_size >= _MIN_VALID_BYTES:
        return final

    if not Path(cookies).exists():
        raise FileNotFoundError(
            f"Cookie file {cookies!r} not found. Export youtube.com cookies "
            f"from the channel owner's browser session."
        )

    # Intermediate JPEG — written into THUMB_DIR so it survives the temp
    # directory cleanup and can be inspected if cwebp fails.
    jpg = THUMB_DIR / f"{stem}.jpg"

    with tempfile.TemporaryDirectory() as tmp:
        clip_template = str(Path(tmp) / "clip.%(ext)s")

        _run_ytdlp([
            "yt-dlp",
            "--cookies", cookies,
            "--download-sections", f"*{at_seconds}-{at_seconds + 2}",
            "-f", "bv*[height<=1080]/bv*/b",
            "-o", clip_template,
            f"https://www.youtube.com/watch?v={video_id}",
        ], video_id)

        downloads = list(Path(tmp).glob("clip.*"))
        if not downloads:
            raise RuntimeError(
                f"yt-dlp reported success but wrote no clip for {video_id}"
            )
        clip = downloads[0]

        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(clip),
            "-frames:v", "1",
            "-q:v", "2",
            str(jpg),
        ], check=True)

    if not jpg.exists() or jpg.stat().st_size < _MIN_VALID_BYTES:
        raise RuntimeError(
            f"ffmpeg ran but {jpg} is missing or suspiciously small "
            f"({jpg.stat().st_size if jpg.exists() else 0} bytes)"
        )

    # Pass the width to the WebP conversion step
    _to_webp(jpg, final, quality=quality, width=width)
    jpg.unlink(missing_ok=True)      # WebP is the artefact; drop the JPEG

    if not final.exists() or final.stat().st_size < _MIN_VALID_BYTES:
        raise RuntimeError(
            f"cwebp ran but {final} is missing or suspiciously small"
        )
    return final


def _to_webp(jpg_path: Path, webp_path: Path,
             quality: int = DEFAULT_WEBP_QUALITY,
             method: int = DEFAULT_WEBP_METHOD,
             width: int = DEFAULT_WIDTH) -> None:  # <-- Added width
    """Re-encode a JPEG frame as WebP using cwebp, resized to target width."""
    
    cmd = [
        "cwebp",
        "-q", str(quality),
        "-m", str(method),
        "-mt",
        "-metadata", "none",
    ]
    
    # Add the resize flag if width is specified. 
    # Setting height to 0 tells cwebp to maintain the aspect ratio.
    if width:
        cmd.extend(["-resize", str(width), "0"])
        
    cmd.extend([
        str(jpg_path),
        "-o", str(webp_path),
    ])
    
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _run_ytdlp(cmd: list[str], video_id: str, attempts: int = 3) -> None:
    """Run yt-dlp, retrying YouTube's transient session-rotation error."""
    last_err: subprocess.CalledProcessError | None = None
    for i in range(attempts):
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return
        except subprocess.CalledProcessError as e:
            last_err = e
            stderr = (e.stderr or "").lower()
            if _TRANSIENT in stderr and i < attempts - 1:
                time.sleep(2 ** i)
                continue
            break

    assert last_err is not None
    raise RuntimeError(
        f"yt-dlp failed for {video_id}:\n{last_err.stderr.strip()}"
    ) from last_err


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <video_id> [video_title] [at_seconds] [width]",
              file=sys.stderr)
        sys.exit(1)

    vid = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else None
    at = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_AT_SECONDS
    w = int(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_WIDTH  # <-- CLI override

    try:
        path = fetch_thumbnail(vid, video_title=title, at_seconds=at, width=w)
    except (FileNotFoundError, RuntimeError) as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print(f"Saved: {path}  ({path.stat().st_size} bytes)")