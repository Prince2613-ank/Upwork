"""Qualification rule shared by the dashboard, live feed, analytics and final HTML generation."""
import copy
import re


EMPTY_REVIEWS = {"no feedback given", "no feedback", "n/a", "none", "no review", "no review given"}
REASON_LABELS = {"missing_description":"No description", "incomplete_description":"Incomplete description",
    "no_freelancer_reviews":"No written freelancer reviews", "unverified_review_direction":"Unverified review direction",
    "incomplete_reviews":"Incomplete review text", "incomplete_history":"Incomplete contract history"}


def release_candidate(data):
    """A job qualifies when its description has words and at least one freelancer wrote a review about the client."""
    data = copy.deepcopy(data or {})
    description = str((data.get("job") or {}).get("description") or data.get("description") or "").strip()
    if not re.search(r"\w", description):
        return None, "missing_description"
    written = [r for r in data.get("client_recent_history", [])
               if str(r.get("feedback") or "").strip() and str(r.get("feedback") or "").strip().lower().rstrip(".") not in EMPTY_REVIEWS]
    if not written:
        return None, "no_freelancer_reviews"
    data.setdefault("job", {})["description"] = description
    data["client_recent_history"] = written
    return data, "ready"
