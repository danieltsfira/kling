"""Cut short audio clips (default 10 seconds) out of YouTube videos.

Only the requested section is downloaded, not the whole video.

Usage:
    python clip_audio.py URL START [--duration 10] [--name NAME] [--format mp3]
    python clip_audio.py "https://youtu.be/VIDEO_ID?t=83"          # start taken from ?t=
    python clip_audio.py "https://www.youtube.com/watch?v=VIDEO_ID" 1:23
    python clip_audio.py URL 1:23 --end 1:31                      # explicit end time
    python clip_audio.py --batch clips.txt                         # many clips at once

Batch file: one clip per line -> URL START [DURATION] [NAME]. Use - to keep a default
(e.g. take START from the link's ?t=). Lines starting with # are ignored.

Clips are saved to audio_clips/ by default.
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

DEFAULT_DURATION = 10.0
CODECS = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "6"],
    "flac": ["-c:a", "flac"],
}


def parse_time(value: str) -> float:
    """Accept 83, 83.5, 1:23, 01:02:03, or YouTube style 1m23s / 1h2m3s."""
    value = value.strip()
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?", value)
    if m and any(m.groups()) and not re.fullmatch(r"\d+(?:\.\d+)?", value):
        h, mi, s = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)
    total = 0.0
    for part in value.split(":"):
        total = total * 60 + float(part)
    return total


def start_from_url(url: str) -> float | None:
    query = parse_qs(urlparse(url).query)
    for key in ("t", "start"):
        if key in query:
            return parse_time(query[key][0])
    return None


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", text).strip()
    return re.sub(r"\s+", "_", text)[:80] or "clip"


def yt_dlp_base() -> list[str]:
    """yt-dlp needs a JS runtime for YouTube; it only looks for deno by default."""
    cmd = ["yt-dlp", "--no-playlist"]
    if not shutil.which("deno") and shutil.which("node"):
        cmd += ["--js-runtimes", "node"]
    return cmd


def video_title(url: str) -> str:
    out = subprocess.run(
        [*yt_dlp_base(), "--skip-download", "--print", "%(title)s", url],
        capture_output=True, text=True,
    )
    return out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else "clip"


def unique_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path


def make_clip(url: str, start: float, duration: float, name: str | None,
              fmt: str, out_dir: str, full_download: bool = False) -> str:
    os.makedirs(out_dir, exist_ok=True)
    name = safe_name(name or video_title(url))
    out_path = unique_path(os.path.join(out_dir, f"{name}_{fmt_time(start)}.{fmt}"))

    with tempfile.TemporaryDirectory() as tmp:
        cmd = [*yt_dlp_base(), "-f", "bestaudio/best", "-o", os.path.join(tmp, "src.%(ext)s")]
        if full_download:
            seek = start
        else:
            # Grab a small margin either side, then trim precisely with ffmpeg.
            pre = min(start, 2.0)
            cmd += ["--download-sections", f"*{start - pre:.3f}-{start + duration + 2:.3f}"]
            seek = pre
        subprocess.run(cmd + [url], check=True)

        files = os.listdir(tmp)
        if not files:
            raise RuntimeError("yt-dlp did not produce a file")
        src = os.path.join(tmp, files[0])

        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{seek:.3f}", "-i", src, "-t", f"{duration:.3f}", "-vn",
             *CODECS[fmt], out_path],
            check=True,
        )
    return out_path


def read_batch(path: str):
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = shlex.split(line)
            url = parts[0]
            given = lambda i: len(parts) > i and parts[i] != "-"
            start = parse_time(parts[1]) if given(1) else start_from_url(url)
            if start is None:
                print(f"line {lineno}: no start time, skipping", file=sys.stderr)
                continue
            duration = parse_time(parts[2]) if given(2) else None
            name = " ".join(parts[3:]) if len(parts) > 3 else None
            yield url, start, duration, name


def main() -> None:
    p = argparse.ArgumentParser(description="Cut a short audio clip out of a YouTube video")
    p.add_argument("url", nargs="?", help="YouTube link (a ?t= in the link is used as the start)")
    p.add_argument("start", nargs="?", help="Start time: 83, 1:23, 1m23s")
    p.add_argument("--end", help="End time (instead of --duration)")
    p.add_argument("-d", "--duration", type=parse_time, default=None,
                   help=f"Clip length in seconds (default {DEFAULT_DURATION:g})")
    p.add_argument("-n", "--name", help="File name (default: video title)")
    p.add_argument("-f", "--format", choices=sorted(CODECS), default="mp3")
    p.add_argument("-o", "--output-dir", default="audio_clips")
    p.add_argument("--batch", help="Text file with one clip per line: URL START [DURATION] [NAME]")
    p.add_argument("--full-download", action="store_true",
                   help="Download the whole audio track first (fallback if section download fails)")
    args = p.parse_args()

    for tool in ("yt-dlp", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit(f"'{tool}' not found. Install it first (see README).")

    jobs = []
    if args.batch:
        jobs = list(read_batch(args.batch))
    elif args.url:
        start = parse_time(args.start) if args.start else start_from_url(args.url)
        if start is None:
            p.error("give a START time or a link with ?t=")
        duration = args.duration
        if args.end:
            duration = parse_time(args.end) - start
            if duration <= 0:
                p.error("--end must be after the start time")
        jobs = [(args.url, start, duration, args.name)]
    else:
        p.error("give a URL or --batch FILE")

    failed = 0
    for url, start, duration, name in jobs:
        duration = duration or args.duration or DEFAULT_DURATION
        print(f"\n>>> {url}  from {fmt_time(start)} for {duration:g}s")
        try:
            path = make_clip(url, start, duration, name, args.format, args.output_dir, args.full_download)
            print(f"Saved: {path}")
        except (subprocess.CalledProcessError, RuntimeError) as e:
            failed += 1
            print(f"Failed: {e}", file=sys.stderr)
    if failed:
        sys.exit(f"{failed} of {len(jobs)} clip(s) failed")


if __name__ == "__main__":
    main()
