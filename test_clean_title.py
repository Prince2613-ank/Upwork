import re

def clean_title(title_tag_text, header_text, slug_text, cur_title):
    # 1. Test header_text first if it is specific and not generic
    for cand in [header_text, title_tag_text]:
        if cand:
            c = cand.strip()
            # Remove Upwork title tag suffixes
            c = re.sub(r'\s*\|\s*Upwork.*$', '', c, flags=re.I)
            # Remove category suffix if separated by " - "
            parts = re.split(r'\s+-\s+(?:Marketing|Design|Development|Writing|Admin|Customer|Sales|Accounting|Legal|Engineering|IT|Web|Mobile|Software|Data|AI|Translation|Upwork)', c, flags=re.I)
            if parts and len(parts[0].strip()) > 3:
                clean_cand = parts[0].strip()
                if not any(bad in clean_cand.lower() for bad in [
                    "featured job posts", "search freelance jobs", "just a moment", 
                    "access denied", "page not found", "404", "attention required",
                    "security check", "cloudflare"
                ]):
                    return clean_cand

    # 2. Slug fallback
    if slug_text and len(slug_text) > 3:
        clean_slug = slug_text.replace('-', ' ').replace('_', ' ').strip()
        if not any(bad in clean_slug.lower() for bad in ["featured job posts", "search freelance jobs"]):
            return clean_slug

    return cur_title

# Test samples
test_cases = [
    ("impact.com Affiliate & Creator Manager – Mobile App Paid Subscriber Growth - Marketing, PR & Brand Strategy", 
     "impact.com Affiliate & Creator Manager – Mobile App Paid Subscriber Growth", 
     "impact-com-Affiliate-Creator-Manager-Mobile-App-Paid-Subscriber-Growth", 
     "Exceptional Impact Expert As An Affiliate & Crea"),
    ("Direct Response Creative Strategist - DTC Skincare USA - Upwork", 
     "Direct Response Creative Strategist - DTC Skincare USA", 
     "Direct-Response-Creative-Strategist-DTC-Skincare-USA", 
     "Highly Skilled Performance Creative Strategist"),
    ("Search Freelance Jobs on Upwork",
     "",
     "Full-Stack-Developer-Needed-to-Build-Partner-Admin-Dashboard-Using-Claude",
     "Full-Stack Developer Needed to Build Partner & Admin Dashboard Using Claude"),
    ("Featured job posts",
     "",
     "Taboola-Paid-Media-Expert-Needed",
     "Taboola Paid Media Expert Needed")
]

for tt, ht, st, ct in test_cases:
    res = clean_title(tt, ht, st, ct)
    print(f"Input Title Tag: {tt[:40]}... -> Result: {res}")
