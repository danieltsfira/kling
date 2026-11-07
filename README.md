# Kling AI text-to-video client

A small Python client for the [Kling AI](https://klingai.com) text-to-video API.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your keys in .env
```

## Usage

```bash
python main.py "A corgi running on a beach at sunset, cinematic"
python main.py "Neon city in the rain" --mode pro --duration 10 --aspect-ratio 9:16
```

The script submits a task, polls it until it finishes, and downloads the video(s) to `output/`.

Print a JWT on its own (handy for testing with curl):

```bash
python -m kling_client.auth
```

## Library usage

```python
from dotenv import load_dotenv
from kling_client import KlingClient

load_dotenv()
client = KlingClient()
task_id = client.submit_text_to_video("A paper boat sailing down a rainy street")
result = client.wait_for_task(task_id)
print(result["task_result"]["videos"][0]["url"])
```

## Files

- `kling_client/auth.py` – builds the HS256 JWT (`iss` = access key, valid 20 minutes).
- `kling_client/client.py` – `KlingClient`: submit task, get status, poll until done, download.
- `main.py` – command-line entry point.
- `.env.example` – template for `KLING_ACCESS_KEY` / `KLING_SECRET_KEY`.

Note: Kling serves its global API at `https://api-singapore.klingai.com`. If your account
uses a different endpoint, set `KLING_API_BASE_URL` in `.env`.

## Audio clips from YouTube (`clip_audio.py`)

Cuts a short audio clip (10 seconds by default) out of a YouTube video. Only the needed
section is downloaded, and the clip is saved to `audio_clips/`.

Requires `ffmpeg` (`brew install ffmpeg` / `winget install ffmpeg` / `apt install ffmpeg`)
and `yt-dlp` (`pip install -r requirements.txt`).

```bash
# Start time taken from the link's ?t= (YouTube "Share > Start at")
python clip_audio.py "https://youtu.be/VIDEO_ID?t=83"

# Explicit start time (83, 1:23 or 1m23s all work)
python clip_audio.py "https://www.youtube.com/watch?v=VIDEO_ID" 1:23

# Different length / explicit end / custom name / other format
python clip_audio.py URL 1:23 -d 7
python clip_audio.py URL 1:23 --end 1:31.5
python clip_audio.py URL 1:23 -n "laugh" -f wav     # mp3 (default), wav, m4a, ogg, flac

# Many clips at once
python clip_audio.py --batch clips.txt
```

`clips.txt` holds one clip per line: `URL START [DURATION] [NAME]` (use `-` to keep a default,
`#` for comments):

```
https://www.youtube.com/watch?v=VIDEO_ID 1:23
https://youtu.be/VIDEO_ID?t=95 - 8 funny laugh
```

If a section download fails, add `--full-download` to grab the whole audio track and cut it locally.
If YouTube starts refusing downloads, update yt-dlp: `pip install -U yt-dlp`.
