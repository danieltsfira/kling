"""Generate a video from a text prompt with Kling AI.

Usage:
    python main.py "A corgi running on a beach at sunset, cinematic"
    python main.py "..." --mode pro --duration 10 --aspect-ratio 9:16
"""

import argparse
import os

from dotenv import load_dotenv

from kling_client import KlingClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Kling AI text-to-video")
    parser.add_argument("prompt", help="Text description of the video")
    parser.add_argument("--negative-prompt")
    parser.add_argument("--model", default="kling-v1-6")
    parser.add_argument("--mode", choices=["std", "pro"], default="std")
    parser.add_argument("--aspect-ratio", choices=["16:9", "9:16", "1:1"], default="16:9")
    parser.add_argument("--duration", choices=["5", "10"], default="5")
    parser.add_argument("--poll-interval", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=15 * 60)
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()

    load_dotenv()
    client = KlingClient()

    task_id = client.submit_text_to_video(
        prompt=args.prompt,
        model_name=args.model,
        negative_prompt=args.negative_prompt,
        mode=args.mode,
        aspect_ratio=args.aspect_ratio,
        duration=args.duration,
    )
    print(f"Submitted task {task_id}")

    result = client.wait_for_task(task_id, poll_interval=args.poll_interval, timeout=args.timeout)
    for i, video in enumerate(result["task_result"]["videos"]):
        print(f"Video ready: {video['url']}")
        path = client.download_video(video["url"], os.path.join(args.output_dir, f"{task_id}_{i}.mp4"))
        print(f"Saved to {path}")


if __name__ == "__main__":
    main()
