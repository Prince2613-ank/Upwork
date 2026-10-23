import pytest
from parsers.review_extractor import extract_review_from_html, clean_review_text

def test_clean_review_text():
    raw1 = "  'Great freelancer, helped us finish on time.' Less  "
    assert clean_review_text(raw1) == "Great freelancer, helped us finish on time."

    raw2 = '  "Flodata Analytics exceeded expectations." More '
    assert clean_review_text(raw2) == "Flodata Analytics exceeded expectations."

def test_extract_review_from_expanded_container():
    html_expanded = """
    <div class="feedback" data-test="freelancer-feedback" data-full-text="Complete feedback text that was previously truncated. It contains full vendor names and enterprise scope.">
        <p class="comment">Complete feedback text that was previously truncated... <button>More</button></p>
    </div>
    """
    review, is_trunc, reason = extract_review_from_html(html_expanded)
    assert review == "Complete feedback text that was previously truncated. It contains full vendor names and enterprise scope."
    assert is_trunc is False
    assert reason == "Complete un-truncated review"

def test_extract_review_with_button_decomposition():
    html_with_btn = """
    <div class="feedback" data-test="freelancer-feedback">
        <p data-test="review-comment">We had an excellent engagement. He built our automated scrapers cleanly. <button class="air3-btn-link">Less</button></p>
    </div>
    """
    review, is_trunc, reason = extract_review_from_html(html_with_btn)
    assert review == "We had an excellent engagement. He built our automated scrapers cleanly."
    assert is_trunc is False
