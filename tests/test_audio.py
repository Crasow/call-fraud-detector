import base64
from pathlib import Path

import pytest

from call_fraud_detector.audio import (
    encode_bytes_base64,
    get_audio_format,
    get_mime_type,
)


def test_get_audio_format():
    assert get_audio_format("call.wav") == "wav"
    assert get_audio_format("recording.mp3") == "mp3"
    assert get_audio_format("audio.OGG") == "ogg"


def test_get_mime_type():
    assert get_mime_type("test.wav") == "audio/wav"
    assert get_mime_type("test.mp3") == "audio/mp3"
    assert get_mime_type("test.ogg") == "audio/ogg"


def test_get_mime_type_unsupported():
    with pytest.raises(ValueError, match="Unsupported"):
        get_mime_type("test.txt")


def test_encode_bytes_base64():
    data = b"hello audio"
    result = encode_bytes_base64(data)
    assert base64.b64decode(result) == data
