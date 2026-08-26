"""Tests for Presidio PII/PHI scrubbing."""
import pytest

from app.security.pii import PIIScrubber


@pytest.fixture(scope="module")
def scrubber():
    return PIIScrubber(["en"])


def test_email_and_phone_redacted(scrubber):
    text = "Contact jane.doe@example.com or 555-123-4567 for the report."
    redacted, counts = scrubber.scrub(text)
    assert "jane.doe@example.com" not in redacted
    assert "555-123-4567" not in redacted
    assert "EMAIL_ADDRESS" in counts and "PHONE_NUMBER" in counts
    assert redacted.count("<EMAIL_ADDRESS>") == 1


def test_mrn_redacted(scrubber):
    text = "The patient MRN: 88410293 was discharged."
    redacted, counts = scrubber.scrub(text)
    assert "88410293" not in redacted
    assert counts.get("MEDICAL_RECORD_NUMBER", 0) == 1


def test_clean_text_unchanged(scrubber):
    text = "Summarize the quarterly revenue report."
    redacted, counts = scrubber.scrub(text)
    assert redacted == text
    assert counts == {}