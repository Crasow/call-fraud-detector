import asyncio
import json
import logging
import time

import httpx

from call_analyzer.config import settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _build_request() -> tuple[str, dict[str, str]]:
    """Build URL and headers based on gemini_mode config."""
    if settings.gemini_mode == "direct":
        url = (
            f"https://generativelanguage.googleapis.com/v1beta"
            f"/models/{settings.gemini_model}:generateContent"
            f"?key={settings.gemini_api_key}"
        )
        return url, {"Content-Type": "application/json"}
    else:
        # proxy mode: Vertex AI format through proxy
        url = (
            f"{settings.gemini_proxy_url}/v1/projects/{settings.gemini_project_id}"
            f"/locations/{settings.gemini_location}/publishers/google/models/{settings.gemini_model}"
            ":generateContent"
        )
        return url, {"Content-Type": "application/json"}


async def generate_content(
    inline_data_base64: str,
    mime_type: str,
    text_prompt: str,
) -> dict:
    url, headers = _build_request()

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
    logger.info("Gemini request [%s]: mime=%s, audio=%.2fMB, prompt=%d chars",
                settings.gemini_mode, mime_type, data_size_mb, len(text_prompt))

    body_bytes = json.dumps(body).encode()
    timeout = httpx.Timeout(connect=30, write=600, read=settings.gemini_read_timeout, pool=30)

    last_error: Exception | None = None

    for attempt in range(settings.gemini_max_retries):
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)
                elapsed = time.monotonic() - t0
                logger.info("Gemini response: status=%s, elapsed=%.1fs", resp.status_code, elapsed)

                if resp.status_code in RETRYABLE_STATUS_CODES:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                    backoff = 2 ** attempt
                    logger.warning("Retryable status %s, retrying in %ds (attempt %d/%d)",
                                   resp.status_code, backoff, attempt + 1, settings.gemini_max_retries)
                    await asyncio.sleep(backoff)
                    continue

                resp.raise_for_status()
                return resp.json()

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            elapsed = time.monotonic() - t0
            last_error = e
            backoff = 2 ** attempt
            logger.warning("Gemini %s after %.1fs, retrying in %ds (attempt %d/%d)",
                           type(e).__name__, elapsed, backoff, attempt + 1, settings.gemini_max_retries)
            await asyncio.sleep(backoff)
            continue

        except httpx.HTTPStatusError as e:
            # Non-retryable HTTP error
            logger.error("Gemini HTTP error %s: %s", e.response.status_code, e.response.text[:500])
            raise RuntimeError(f"Gemini proxy returned {e.response.status_code}: {e.response.text[:500]}")

    # All retries exhausted
    if isinstance(last_error, httpx.ConnectError):
        raise RuntimeError(f"Cannot connect to Gemini proxy at {settings.gemini_proxy_url} after {settings.gemini_max_retries} attempts")
    elif isinstance(last_error, httpx.TimeoutException):
        raise RuntimeError(f"Gemini proxy request timed out after {settings.gemini_max_retries} attempts")
    elif isinstance(last_error, httpx.HTTPStatusError):
        raise RuntimeError(f"Gemini proxy returned {last_error.response.status_code} after {settings.gemini_max_retries} attempts")
    else:
        raise RuntimeError(f"Gemini request failed after {settings.gemini_max_retries} attempts: {last_error}")
