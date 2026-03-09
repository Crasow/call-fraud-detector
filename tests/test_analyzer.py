from call_fraud_detector.analyzer import _parse_gemini_response


def test_parse_gemini_response():
    raw = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"transcript": "Hello", "is_fraud": true, "fraud_score": 0.9, "fraud_categories": ["Vishing"], "reasons": ["Suspicious"]}'
                        }
                    ]
                }
            }
        ]
    }
    parsed = _parse_gemini_response(raw)
    assert parsed["is_fraud"] is True
    assert parsed["fraud_score"] == 0.9
    assert parsed["transcript"] == "Hello"
    assert "Vishing" in parsed["fraud_categories"]
    assert "Suspicious" in parsed["reasons"]


def test_parse_gemini_response_clean():
    raw = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": '{"transcript": "Normal call", "is_fraud": false, "fraud_score": 0.1, "fraud_categories": [], "reasons": []}'
                        }
                    ]
                }
            }
        ]
    }
    parsed = _parse_gemini_response(raw)
    assert parsed["is_fraud"] is False
    assert parsed["fraud_score"] == 0.1
