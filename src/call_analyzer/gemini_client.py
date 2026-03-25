import json
import logging
import time

import httpx

from call_analyzer.config import settings

logger = logging.getLogger(__name__)


async def generate_content(
    inline_data_base64: str,
    mime_type: str,
    text_prompt: str,
) -> dict:
    url = (
        f"{settings.gemini_proxy_url}/v1/projects/{settings.gemini_project_id}"
        f"/locations/{settings.gemini_location}/publishers/google/models/{settings.gemini_model}"
        ":generateContent"
    )

    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": inline_data_base64,
                        }
                    },
                    {"text": text_prompt},
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }

    data_size_mb = len(inline_data_base64) / 1024 / 1024
    logger.warning("=== GEMINI REQUEST ===")
    logger.warning("URL: %s", url)
    logger.warning("MIME type: %s", mime_type)
    logger.warning("Audio data size (base64): %.2f MB", data_size_mb)
    logger.warning("Prompt length: %d chars", len(text_prompt))

    logger.warning("Serializing JSON body...")
    body_bytes = json.dumps(body).encode()
    logger.warning("JSON body size: %.2f MB", len(body_bytes) / 1024 / 1024)

    timeout = httpx.Timeout(connect=30, write=600, read=600, pool=30)
    t0 = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            logger.warning("Sending POST request...")
            resp = await client.post(url, content=body_bytes, headers={"Content-Type": "application/json"})
            elapsed = time.monotonic() - t0
            logger.warning("=== GEMINI RESPONSE ===")
            logger.warning("Status: %s", resp.status_code)
            logger.warning("Elapsed: %.1fs", elapsed)
            logger.warning("Response size: %d bytes", len(resp.content))
            logger.warning("Response body (first 1000 chars): %s", resp.text[:1000])
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError as e:
        elapsed = time.monotonic() - t0
        logger.error("=== CONNECT ERROR (%.1fs) ===", elapsed)
        logger.error("Error: %s", e)
        raise RuntimeError(f"Cannot connect to Gemini proxy at {settings.gemini_proxy_url}. Is it running?")
    except httpx.TimeoutException as e:
        elapsed = time.monotonic() - t0
        logger.error("=== TIMEOUT (%.1fs) ===", elapsed)
        logger.error("Error type: %s, details: %s", type(e).__name__, e)
        raise RuntimeError(f"Gemini proxy request timed out after {elapsed:.0f}s ({type(e).__name__})")
    except httpx.HTTPStatusError as e:
        elapsed = time.monotonic() - t0
        logger.error("=== HTTP ERROR (%.1fs) ===", elapsed)
        logger.error("Status: %s", e.response.status_code)
        logger.error("Body: %s", e.response.text[:2000])
        raise RuntimeError(f"Gemini proxy returned {e.response.status_code}: {e.response.text[:500]}")
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error("=== UNEXPECTED ERROR (%.1fs) ===", elapsed)
        logger.error("Type: %s, Error: %s", type(e).__name__, e, exc_info=True)
        raise
