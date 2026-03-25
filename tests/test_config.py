from call_analyzer.config import Settings


def test_default_settings():
    s = Settings(gemini_project_id="test", _env_file=None)
    assert s.gemini_model == "gemini-2.5-flash"
    assert s.gemini_location == "us-central1"
    assert ":8000" in s.gemini_proxy_url
