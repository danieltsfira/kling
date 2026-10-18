"""Client for Kling AI text-to-video generation."""

import os
import time
from typing import Any, Optional

import requests

from .auth import TOKEN_TTL_SECONDS, generate_jwt_token

DEFAULT_BASE_URL = "https://api-singapore.klingai.com"
TEXT2VIDEO_PATH = "/v1/videos/text2video"

# Refresh the token this many seconds before it actually expires.
TOKEN_REFRESH_MARGIN = 60


class KlingAPIError(RuntimeError):
    """Raised when the Kling API returns an error or a task fails."""


class KlingClient:
    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30,
    ):
        self.access_key = access_key or os.getenv("KLING_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("KLING_SECRET_KEY")
        if not self.access_key or not self.secret_key:
            raise ValueError("Set KLING_ACCESS_KEY and KLING_SECRET_KEY (e.g. in .env)")
        self.base_url = (base_url or os.getenv("KLING_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self._token: Optional[str] = None
        self._token_expires_at = 0.0

    def _get_token(self) -> str:
        """Return a cached JWT, regenerating it shortly before it expires."""
        if self._token is None or time.time() >= self._token_expires_at - TOKEN_REFRESH_MARGIN:
            self._token = generate_jwt_token(self.access_key, self.secret_key)
            self._token_expires_at = time.time() + TOKEN_TTL_SECONDS
        return self._token

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }
        resp = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=self.timeout, **kwargs
        )
        try:
            body = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise KlingAPIError(f"Non-JSON response ({resp.status_code}): {resp.text[:200]}")

        # Kling returns {"code": 0, "message": ..., "data": {...}} on success.
        if not resp.ok or body.get("code") != 0:
            raise KlingAPIError(
                f"HTTP {resp.status_code}, code={body.get('code')}: {body.get('message')} "
                f"(request_id={body.get('request_id')})"
            )
        return body["data"]

    def submit_text_to_video(
        self,
        prompt: str,
        model_name: str = "kling-v1-6",
        negative_prompt: Optional[str] = None,
        mode: str = "std",
        aspect_ratio: str = "16:9",
        duration: str = "5",
        cfg_scale: Optional[float] = None,
        callback_url: Optional[str] = None,
        external_task_id: Optional[str] = None,
    ) -> str:
        """Submit a text-to-video task and return its task_id.

        mode: "std" (faster/cheaper) or "pro" (higher quality).
        aspect_ratio: "16:9", "9:16" or "1:1". duration: "5" or "10" seconds.
        """
        payload: dict[str, Any] = {
            "model_name": model_name,
            "prompt": prompt,
            "mode": mode,
            "aspect_ratio": aspect_ratio,
            "duration": str(duration),
        }
        optional = {
            "negative_prompt": negative_prompt,
            "cfg_scale": cfg_scale,
            "callback_url": callback_url,
            "external_task_id": external_task_id,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})

        data = self._request("POST", TEXT2VIDEO_PATH, json=payload)
        return data["task_id"]

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Fetch the current state of a text-to-video task."""
        return self._request("GET", f"{TEXT2VIDEO_PATH}/{task_id}")

    def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 10,
        timeout: float = 15 * 60,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Poll a task until it succeeds, fails, or `timeout` seconds pass.

        Returns the task data on success; its videos are in
        data["task_result"]["videos"], each with a "url" and "duration".
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                data = self.get_task(task_id)
            except requests.RequestException as exc:
                # Transient network errors shouldn't abort a long-running wait.
                if verbose:
                    print(f"[{task_id}] network error while polling, retrying: {exc}")
            else:
                status = data.get("task_status")
                if verbose:
                    print(f"[{task_id}] status: {status}")
                if status == "succeed":
                    return data
                if status == "failed":
                    raise KlingAPIError(f"Task {task_id} failed: {data.get('task_status_msg')}")

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Task {task_id} not finished after {timeout:.0f}s")
            time.sleep(poll_interval)

    def download_video(self, url: str, dest_path: str) -> str:
        """Download a generated video to `dest_path` and return the path."""
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with requests.get(url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        return dest_path
