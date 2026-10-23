from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('output/raw_html/022089338363935389527.html', 'r', encoding='utf-8', errors='ignore') as f:
    html_text = f.read()

soup = BeautifulSoup(html_text, 'html.parser')

print("--- TITLE TAG ---")
for t in soup.find_all('title'):
    print(t.get_text())

print("\n--- H1 TAGS ---")
for h in soup.find_all('h1'):
    print(h.get_text(strip=True))

print("\n--- H2/H3/H4 TAGS ---")
for h in soup.find_all(['h2', 'h3', 'h4'])[:10]:
    print(h.name, ':', h.get_text(strip=True))

print("\n--- ABOUT CLIENT ---")
from collector.extraction.client_parser import parse_about_client
client = parse_about_client(soup)
print("Client Location:", client.location)
print("Client Rating:", client.rating)
print("Client Total Spent:", client.total_spent)
print("Client Total Hires:", client.total_hires)
print("Client Active Hires:", client.active_hires)
print("Client Hours Billed:", client.hours_billed)
print("Client Jobs Posted:", client.jobs_posted)
print("Client Hire Rate:", client.hire_rate)
print("Client Member Since:", client.member_since)

print("\n--- CLIENT HISTORY ---")
from collector.extraction.review_parser import parse_client_history
hist = parse_client_history(soup)
print(f"Total Client History items extracted by review_parser: {len(hist)}")
for idx, item in enumerate(hist[:10]):
    print(f"[{idx+1}] {item.job_title} | {item.date} | {item.amount} | {item.rating} | {item.freelancer_name} | {repr(item.feedback[:60] if item.feedback else '')}")
