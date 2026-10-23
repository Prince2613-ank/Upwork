import sqlite3, json, sys, re

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT job_id, job_json FROM jobs")

client_pfxs = [
    "the freelancer", "this freelancer", "great freelancer", "good freelancer",
    "awesome freelancer", "excellent freelancer", "talented freelancer", "skilled freelancer",
    "a great freelancer", "he was", "she was", "they were", "he is", "she is", "they are",
    "he did", "she did", "they did", "he delivered", "she delivered", "they delivered", "he failed",
    "she failed", "his work", "her work", "their work", "his communication", "her communication",
    "his skills", "her skills", "great work", "fast and professional", "very professional and delivered",
    "good communication, delivered", "excellent work", "pleasure to work with him",
    "pleasure to work with her", "pleasure working with him", "pleasure working with her",
    "we hired", "i hired", "we worked with him", "we worked with her", "i worked with him",
    "i worked with her", "clear communicator, fast", "will hire again", "would hire again",
    "will hire him again", "will hire her again", "would hire him again", "would hire her again",
    "highly recommend him", "highly recommend her", "i can strongly recommend working with",
    "i strongly recommend him", "i strongly recommend her", "i strongly recommend",
    "i recommend him", "i recommend her", "freelancer did", "freelancer was",
    "freelancer is", "freelancer failed", "did a good job", "did a great job", "did great job",
    "great job", "good job", "amazing job", "fantastic job", "nice job",
    "thank you for your work", "thanks for your work", "thank you for the screenshots",
    "thanks for the great designs", "thank you, john", "thank you john", "thanks max"
]

def extract_pure_freelancer_review(raw_fb, fl_name=""):
    if not raw_fb:
        return ""
    text = str(raw_fb).strip()
    
    # 1. If multi-paragraph: Paragraph 0 is the Freelancer reviewing the client!
    # (Paragraph 1 was the client reviewing the freelancer)
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        return ""
    
    fl_text = paras[0]
    
    # Strip trailing "less" / "more" UI artifacts
    fl_text = fl_text.rstrip()
    if fl_text.endswith(" less"):
        fl_text = fl_text[:-5].strip()
    elif fl_text.endswith(" more"):
        fl_text = fl_text[:-5].strip()
        
    lower_t = fl_text.lower()
    
    # Basic invalid checks
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
        
    # Check if this text is a client reviewing the freelancer
    # Check if it starts with freelancer name
    fl_first = (fl_name or "").split()[0].lower() if fl_name else ""
    if fl_first and len(fl_first) >= 3 and (lower_t.startswith(fl_first) or f"{fl_first} was" in lower_t or f"{fl_first} did" in lower_t or f"{fl_first} is" in lower_t):
        return ""
        
    if any(lower_t.startswith(pfx) for pfx in client_pfxs):
        return ""
        
    if any(pfx in lower_t for pfx in [
        "with this freelancer", "with the freelancer", "collaborating with this freelancer",
        "working with this freelancer", "pleasure working with him", "pleasure working with her",
        "would hire him again", "would hire her again", "will hire him again", "will hire her again",
        "hire him again", "hire her again", "the freelancer did", "this freelancer is"
    ]):
        return ""
        
    words = fl_text.split()
    if len(fl_text) < 15 or len(words) < 3:
        return ""
        
    return fl_text

total_checked = 0
pure_fl_count = 0
dropped_client_count = 0
sample_pure = []
sample_dropped = []

for jid, raw_j in cur.fetchall():
    d = json.loads(raw_j)
    for h in (d.get("client_recent_history") or []):
        fb = h.get("feedback") or ""
        fl = h.get("freelancer_name") or ""
        if fb:
            total_checked += 1
            pure = extract_pure_freelancer_review(fb, fl)
            if pure:
                pure_fl_count += 1
                if len(sample_pure) < 10:
                    sample_pure.append((fl, pure))
            else:
                dropped_client_count += 1
                if len(sample_dropped) < 10:
                    sample_dropped.append((fl, fb))

print(f"Total reviews audited: {total_checked}")
print(f"Pure Freelancer-to-Client reviews preserved: {pure_fl_count} ({(pure_fl_count/total_checked)*100:.1f}%)")
print(f"Client reviews / stubs eliminated: {dropped_client_count} ({(dropped_client_count/total_checked)*100:.1f}%)")

print("\n--- SAMPLE 5 PURE FREELANCER-TO-CLIENT REVIEWS ---")
for fl, p in sample_pure[:5]:
    print(f"• FL: '{fl}' -> Client Review:\n  \"{p}\"\n")

print("\n--- SAMPLE 5 DROPPED CLIENT-TO-FREELANCER / STUB REVIEWS ---")
for fl, d in sample_dropped[:5]:
    print(f"• FL: '{fl}' -> Dropped Review:\n  \"{d}\"\n")
