"""Call Gemini directly, outside the app, and time it. Never prints the key."""

import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
base = "https://generativelanguage.googleapis.com/v1beta"

for model in ["gemini-3.5-flash-lite", "gemini-3.8-flash"]:
    t = time.perf_counter()
    try:
        r = httpx.post(
            f"{base}/models/{model}:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [{"text": "Say hi in 3 words."}]}]},
            timeout=40,
        )
        print(
            model,
            r.status_code,
            f"{time.perf_counter() - t:.2f} s",
            r.text[:120].replace("\n", " "),
        )
    except Exception as exc:
        print(model, type(exc).__name__, f"{time.perf_counter() - t:.2f} s")

MODEL = "gemini-2.5-flash-lite"
t = time.perf_counter()
try:
    r = httpx.post(
        f"{base}/models/{MODEL}:generateContent",
        params={"key": key},
        json={"contents": [{"parts": [{"text": "Say hi in 3 words."}]}]},
        timeout=60,
    )
    print(MODEL, r.status_code, f"{time.perf_counter() - t:.2f} s")
    print(r.text[:300])
except Exception as exc:
    print(MODEL, type(exc).__name__, f"{time.perf_counter() - t:.2f} s")
