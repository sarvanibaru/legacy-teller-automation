from src.safety.redaction import redact_text, redact_value


def test_ssn_pattern_is_redacted():
    result = redact_text("Member SSN is 123-45-6789 on file.")
    assert "123-45-6789" not in result
    assert "[REDACTED]" in result


def test_anthropic_api_key_is_redacted():
    result = redact_text("Using key sk-ant-abc123XYZ for this call.")
    assert "sk-ant-abc123XYZ" not in result


def test_bearer_token_is_redacted():
    result = redact_text("Authorization: Bearer abcDEF123.xyz")
    assert "abcDEF123.xyz" not in result


def test_non_sensitive_text_passes_through_unchanged():
    result = redact_text("Member 12345 has a savings balance.")
    assert result == "Member 12345 has a savings balance."


def test_sensitive_key_name_redacted_regardless_of_value():
    data = {"username": "teller1", "password": "password123"}
    result = redact_value(data)
    assert result["username"] == "teller1"
    assert result["password"] == "[REDACTED]"


def test_sensitive_pattern_caught_even_under_innocent_key_name():
    data = {"notes": "customer mentioned SSN 123-45-6789 for verification"}
    result = redact_value(data)
    assert "123-45-6789" not in result["notes"]


def test_nested_structures_are_redacted_recursively():
    data = {
        "step": "login",
        "form_data": {"username": "teller1", "password": "hunter2"},
        "history": [{"action": "type", "api_key": "sk-ant-shouldnotleak"}],
    }
    result = redact_value(data)
    assert result["form_data"]["password"] == "[REDACTED]"
    assert result["history"][0]["api_key"] == "[REDACTED]"
