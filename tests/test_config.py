from call_fraud_detector.config import Settings


def test_default_settings():
    s = Settings(gemini_project_id="test")
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.gemini_location == "us-central1"
    assert "localhost:8000" in s.gemini_proxy_url
