"""JWT authentication for the Kling AI API."""

import time

import jwt

TOKEN_TTL_SECONDS = 20 * 60  # 20 minutes


def generate_jwt_token(access_key: str, secret_key: str, ttl_seconds: int = TOKEN_TTL_SECONDS) -> str:
    """Return an HS256-signed JWT for the Kling API.

    The token's issuer is the access key; it is valid from 5 seconds ago
    (to tolerate small clock skew) until `ttl_seconds` from now.
    """
    if not access_key or not secret_key:
        raise ValueError("Both access_key and secret_key are required")

    now = int(time.time())
    payload = {
        "iss": access_key,
        "exp": now + ttl_seconds,
        "nbf": now - 5,
    }
    headers = {"alg": "HS256", "typ": "JWT"}
    return jwt.encode(payload, secret_key, algorithm="HS256", headers=headers)


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    print(generate_jwt_token(os.environ["KLING_ACCESS_KEY"], os.environ["KLING_SECRET_KEY"]))
