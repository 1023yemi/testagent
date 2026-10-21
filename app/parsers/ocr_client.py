from __future__ import annotations

import os
from typing import Any

import requests


class OCRClient:
    """Client for the provided OCR endpoint.

    The service accepts a URL, not a local file. This guard prevents accidentally
    transmitting an unusable local path or a private file without user intent.
    """

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = endpoint or os.getenv("OCR_API_URL", "http://36.103.199.11:5002/process")

    def extract(self, file_url: str) -> dict[str, Any]:
        if not file_url.startswith(("http://", "https://")):
            raise ValueError("OCR file_url must be an HTTP(S) URL accessible to the OCR service")
        payload = {"file": file_url, "task": "orderChange", "callBack": "", "taskType": ""}
        response = requests.post(self.endpoint, json=payload, timeout=(10, 300))
        response.raise_for_status()
        return response.json()

    @staticmethod
    def to_text(result: dict[str, Any]) -> str:
        """Tolerate common OCR response envelopes without assuming a vendor schema."""
        for key in ("text", "content", "result", "data"):
            value = result.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in value)
            if isinstance(value, dict):
                return "\n".join(str(v) for v in value.values() if isinstance(v, (str, int, float)))
        return str(result)
