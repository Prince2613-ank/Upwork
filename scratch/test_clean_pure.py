import sqlite3, json, sys, re

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT job_id, job_json FROM jobs")

def clean_pure_freelancer_review(raw_fb, fl_name=""):
    if not raw_fb:
        return ""
    text = str(raw_fb).strip()
    
    # If the text contains the explicit Upwork "To freelancer:" marker, cut everything from it!
    to_fl_idx = text.lower().find("to freelancer:")
    if to_fl_idx != -1:
        text = text[:to_fl_idx].strip()
        
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        return ""
        
    # In Upwork, when both parties review, Block 0 is Freelancer-to-Client,
    # and Block 1 is Client-to-Freelancer. We strictly take Block 0!
    fl_text = paras[0]
    
    # Strip UI artifacts
    fl_text = re.sub(r'\s+(less|more)$', '', fl_text, flags=re.I).strip()
    
    lower_t = fl_text.lower().rstrip(".:;!").strip()
    
    # Standard invalid strings
    if not lower_t or lower_t in [
        "true", "false", "no feedback given", "no feedback", "none", "none given",
        "no comment provided by client", "no comment provided by freelancer",
        "no review given", "no feedback provided", "n/a", "na",
        "job in progress", "contract in progress", "in progress", "still in progress",
        "work in progress", "rating is 5.0 out of 5", "rating is 5 out of 5", "completed project"
    ]:
        return ""
        
    if lower_t.startswith("no feedback") or lower_t.startswith("no comment") or lower_t.startswith("no review"):
        return ""

    # Synthetic milestone / proposal leaks
    if "the freelancer did an extraordinary job on milestone" in lower_t:
        return ""
    if any(leak in lower_t for leak in [
        "this range includes relevant proposals", "you’ll need connects to bid",
        "you will be asked to answer the following questions", "this is when the client last reviewed"
    ]):
        return ""

    # Check for Client reviewing Freelancer phrases
    fl_first = (fl_name or "").split()[0].lower() if fl_name else ""
    if fl_first and len(fl_first) >= 3:
        if lower_t.startswith(fl_first) or lower_t.startswith(f"thanks {fl_first}") or lower_t.startswith(f"thank you {fl_first}") or lower_t.startswith(f"thank you, {fl_first}") or lower_t.startswith(f"thanks, {fl_first}"):
            return ""
            
    client_reviewing_fl_patterns = [
        "the freelancer", "this freelancer", "great freelancer", "good freelancer",
        "awesome freelancer", "excellent freelancer", "talented freelancer", "skilled freelancer",
        "a great freelancer", "freelancer did", "freelancer was", "freelancer is", "freelancer failed",
        "did a good job", "did a great job", "did great job", "did an amazing job", "did an excellent job",
        "did wonderful job", "did a wonderful job", "did a fantastic job", "did an outstanding job",
        "great job", "good job", "amazing job", "fantastic job", "nice job",
        "he delivered", "she delivered", "they delivered", "he failed", "she failed",
        "his work", "her work", "their work", "his code", "her code", "his designs", "her designs",
        "thank you for your work", "thanks for your work", "thank you for your diligence",
        "fast and professional, he", "fast and professional, she",
        "would hire again", "will hire again", "will hire him again", "will hire her again",
        "would hire him again", "would hire her again", "i will hire", "i would hire",
        "we will be hiring", "we will hire",
        "he was very skilled", "she was very skilled", "he is very skilled", "she is very skilled",
        "quality of her work", "quality of his work", "quality of their work",
        "recommend his services", "recommend her services", "recommend their services",
        "he went above and beyond", "she went above and beyond",
        "with this freelancer", "with the freelancer", "from the freelancer"
    ]
    
    # Exceptions where freelancer says "client" in a positive/descriptive way
    # e.g., "The client has no respect for the freelancer's time" -> this IS a freelancer reviewing a client!
    is_freelancer_reviewing_client = any(kw in lower_t for kw in [
        "client", "buyer", "employer", "company", "team", "to other freelancers", "for other freelancers"
    ])
    
    for pat in client_reviewing_fl_patterns:
        if pat in lower_t:
            if not is_freelancer_reviewing_client:
                return ""
            # Even if it contains "client", if it explicitly evaluates the freelancer's delivery, drop it:
            if any(fl_eval in lower_t for eval_word in ["the freelancer was", "the freelancer did", "the freelancer delivered", "this freelancer was", "this freelancer did", "did a great job", "did an excellent job", "did a good job"] for fl_eval in [eval_word]):
                return ""

    words = fl_text.split()
    if len(fl_text) < 15 or len(words) < 3:
        return ""
        
    return fl_text

total = 0
valid_fl = 0
leaks_remaining = 0

for jid, raw_j in cur.fetchall():
    d = json.loads(raw_j)
    for h in (d.get("client_recent_history") or []):
        fb = h.get("feedback") or ""
        fl = h.get("freelancer_name") or ""
        if fb:
            total += 1
            cleaned = clean_pure_freelancer_review(fb, fl)
            if cleaned:
                valid_fl += 1
                c_low = cleaned.lower()
                if any(x in c_low for x in ["did a great job", "the freelancer was", "he was a great"]):
                    leaks_remaining += 1

print(f"Total reviews in DB: {total}")
print(f"Verified Pure Freelancer-to-Client reviews: {valid_fl}")
print(f"Leaks remaining: {leaks_remaining}")
