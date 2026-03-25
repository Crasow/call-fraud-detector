import base64
from pathlib import Path

MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
}

SUPPORTED_EXTENSIONS = set(MIME_TYPES.keys())


def get_audio_format(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def get_mime_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    mime = MIME_TYPES.get(ext)
    if not mime:
        raise ValueError(f"Unsupported audio format: {ext}")
    return mime


def encode_audio_base64(file_path: Path) -> str:
    return base64.b64encode(file_path.read_bytes()).decode()


def encode_bytes_base64(data: bytes) -> str:
    return base64.b64encode(data).decode()
