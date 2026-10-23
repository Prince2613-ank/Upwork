from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('output/search_page_diag.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

cards = soup.select('article, [data-test="job-tile"], li[data-test]')
print(f'Found {len(cards)} cards in search_page_diag.html')

for idx, card in enumerate(cards[:5]):
    links = card.select('a[href*="/jobs/"]')
    print(f'Card #{idx+1}: {len(links)} links with /jobs/')
    for l in links:
        print('   href:', l.get('href'))
        print('   text:', repr(l.get_text(strip=True)[:100]))
    h_tags = card.find_all(['h1', 'h2', 'h3', 'h4'])
    for h in h_tags:
        print(f'   {h.name}:', repr(h.get_text(strip=True)[:100]))
    print('-'*50)
