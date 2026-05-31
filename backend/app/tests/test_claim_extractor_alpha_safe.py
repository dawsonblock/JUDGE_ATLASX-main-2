from app.ai.claim_extractor import extract_claims_from_text


def test_extract_claims_from_text_empty_returns_no_claims():
    assert extract_claims_from_text("") == []
    assert extract_claims_from_text("   \n   ") == []


def test_extract_claims_from_text_is_conservative_and_derivative_only():
    text = (
        "Judge Smith wrote a memo. The report alleges misconduct by the sheriff. "
        "No other conclusion should be inferred."
    )

    claims = extract_claims_from_text(text)

    assert [claim["text"] for claim in claims] == [
        "Judge Smith wrote a memo",
        "The report alleges misconduct by the sheriff",
        "No other conclusion should be inferred",
    ]
    assert all(claim["claim_type"] == "explicit_text_span" for claim in claims)
    assert all(claim["confidence"] == 0.25 for claim in claims)
    assert all(claim["evidence_required"] is True for claim in claims)
    assert all(claim["authority"] == "derivative_only" for claim in claims)
    assert not any("guilty" in claim["text"].lower() for claim in claims)
    assert not any("corrupt" in claim["text"].lower() for claim in claims)
    assert not any("bias" in claim["text"].lower() for claim in claims)
