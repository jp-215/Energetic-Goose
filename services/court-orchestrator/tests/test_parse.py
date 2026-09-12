from app.core.canopy import parse_structured_response


def test_plain_json():
    parsed = parse_structured_response(
        '{"verdict": "plaintiff", "confidence": 0.9, "rationale": "clear breach"}'
    )
    assert parsed["verdict"] == "PLAINTIFF"
    assert parsed["confidence"] == 0.9
    assert parsed["rationale"] == "clear breach"


def test_fenced_json():
    text = '```json\n{"verdict": "MIXED", "confidence": 0.7, "rationale": "both at fault"}\n```'
    parsed = parse_structured_response(text)
    assert parsed["verdict"] == "MIXED"
    assert parsed["confidence"] == 0.7


def test_json_with_reasoning_preamble_and_trailer():
    text = (
        "Let me think about this case step by step. The contract was breached...\n"
        'Here is my ruling: {"verdict": "DEFENDANT", "confidence": 0.65, '
        '"rationale": "excusable delay"} — end of opinion.'
    )
    parsed = parse_structured_response(text)
    assert parsed["verdict"] == "DEFENDANT"
    assert parsed["confidence"] == 0.65
    assert parsed["rationale"] == "excusable delay"


def test_truncated_json_falls_back_to_keywords():
    text = '```json\n{"verdict": "MIXED", "confidence": 0.78, "rationale": "the defendant is subst'
    parsed = parse_structured_response(text)
    # Truncated JSON never parses; keyword fallback sees "defendant".
    assert parsed["verdict"] == "DEFENDANT"
    assert parsed["confidence"] is None


def test_keyword_fallback_prefers_plaintiff():
    parsed = parse_structured_response("I rule for the plaintiff over the defendant.")
    assert parsed["verdict"] == "PLAINTIFF"


def test_empty_response():
    parsed = parse_structured_response("")
    assert parsed == {"answer": "", "verdict": "UNKNOWN", "confidence": None, "rationale": ""}


def test_non_numeric_confidence_is_dropped():
    parsed = parse_structured_response('{"verdict": "MIXED", "confidence": "high", "rationale": "r"}')
    assert parsed["verdict"] == "MIXED"
    assert parsed["confidence"] is None
