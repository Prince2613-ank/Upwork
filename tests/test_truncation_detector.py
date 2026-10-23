import pytest
from parsers.truncation_detector import detect_truncation

def test_truncation_detection_trailing_dots():
    bad1 = "I enjoyed working with Patrick... He's collaborative, provides p..."
    is_trunc, reason = detect_truncation(bad1)
    assert is_trunc is True
    assert "trailing ellipsis" in reason.lower()

    bad2 = "Great work by the engineer…"
    is_trunc, reason = detect_truncation(bad2)
    assert is_trunc is True

    bad3 = "He was very quick and helped us with.."
    is_trunc, reason = detect_truncation(bad3)
    assert is_trunc is True

def test_truncation_detection_trailing_more():
    bad_more1 = "Solid delivery on time. He is reliable and... More"
    is_trunc, reason = detect_truncation(bad_more1)
    assert is_trunc is True
    assert "more" in reason.lower()

    bad_more2 = "Communication was prompt and clear. Read more"
    is_trunc, reason = detect_truncation(bad_more2)
    assert is_trunc is True

def test_truncation_detection_midword_cutoff():
    bad_cutoff = "Exceptional performance, will hire agai..."
    is_trunc, reason = detect_truncation(bad_cutoff)
    assert is_trunc is True

def test_valid_complete_reviews():
    good1 = "I enjoyed working with Patrick. He is collaborative, provides proactive updates, and finished the project ahead of schedule."
    is_trunc, reason = detect_truncation(good1)
    assert is_trunc is False
    assert reason == "Complete un-truncated review"

    good2 = "5/5 stars! Excellent Python developer who wrote clean unit tests."
    is_trunc, reason = detect_truncation(good2)
    assert is_trunc is False
