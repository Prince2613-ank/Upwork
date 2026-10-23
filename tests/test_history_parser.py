import pytest
from parsers.history_parser import parse_client_history

HISTORY_HTML = """
<div data-test="client-history">
    <li data-test="client-history-item">
        <h4 data-test="contract-title">Financial Analytics Pipeline</h4>
        <span class="date">May 2024 - Jun 2024</span>
        <span data-test="rating">5.0</span>
        <span class="amount">$750.00</span>
        <div class="freelancer">Freelancer: Alice Dev</div>
        <div class="feedback" data-test="freelancer-feedback">
            <p data-test="review-full">Fantastic data modeling, will definitely rehire.</p>
        </div>
    </li>
    <li data-test="client-history-item">
        <h4 data-test="contract-title">Snowflake ETL & Python Script</h4>
        <span class="date">Jan 2024 - Mar 2024</span>
        <span data-test="rating">4.9</span>
        <span class="amount">$45.00/hr (30 hrs)</span>
        <div class="freelancer">Freelancer: Bob Engineer</div>
        <div class="feedback" data-test="freelancer-feedback">
            <p data-test="review-full">Very thorough documentation and proactive updates throughout.</p>
        </div>
    </li>
</div>
"""

def test_parse_client_history():
    items = parse_client_history(HISTORY_HTML)
    assert len(items) == 2

    assert items[0].job_title == "Financial Analytics Pipeline"
    assert items[0].date == "May 2024 - Jun 2024"
    assert items[0].rating == 5.0
    assert items[0].amount == "$750.00"
    assert items[0].freelancer == "Alice Dev"
    assert items[0].full_review == "Fantastic data modeling, will definitely rehire."

    assert items[1].job_title == "Snowflake ETL & Python Script"
    assert items[1].payment_type == "Hourly"
    assert items[1].rating == 4.9
    assert items[1].amount == "$45.00/hr (30 hrs)"
    assert items[1].freelancer == "Bob Engineer"
    assert items[1].full_review == "Very thorough documentation and proactive updates throughout."
