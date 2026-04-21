"""
core/ollama_client.py — Async Ollama vision API client.

Calls the locally-running Ollama server to generate an AI caption for an
image. Gracefully degrades — if Ollama is offline, a fallback string is
returned so the rest of the pipeline keeps working.

Usage:
    from core.ollama_client import get_caption, check_ollama_health

    description = await get_caption(image_bytes)   # str
    is_up       = await check_ollama_health()       # bool
"""

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL  = "http://localhost:11434"
OLLAMA_MODEL     = "moondream"          # swap to "llava" for richer captions
REQUEST_TIMEOUT  = 45.0                 # seconds


async def get_caption(image_bytes: bytes) -> str:
    """Call Ollama vision model and return a one-sentence image caption.

    Args:
        image_bytes: Raw bytes of the image (any common format).

    Returns:
        Caption string, or a human-readable fallback on failure.
    """
    try:
        image_b64 = base64.b64encode(image_bytes).decode()

        payload = {
            "model":  OLLAMA_MODEL,
            "prompt": "Describe this image in one clear, detailed sentence.",
            "images": [image_b64],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
            response.raise_for_status()

        caption = response.json().get("response", "").strip()
        logger.info("Ollama caption: %s…", caption[:80])
        return caption or "No description generated."

    except httpx.ConnectError:
        logger.warning("Ollama not reachable — returning fallback caption.")
        return "Vision model unavailable (Ollama is not running)."
    except httpx.TimeoutException:
        logger.warning("Ollama request timed out.")
        return "Vision model timed out. Try again or start Ollama."
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return f"Vision model error: {exc}"


async def check_ollama_health() -> bool:
    """Return True if the local Ollama server is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False
