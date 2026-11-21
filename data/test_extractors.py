import os
import re
import requests
from bs4 import BeautifulSoup

def test_ssstik(url):
    s = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
    }
    r = s.get('https://ssstik.io/en', headers=headers)
    m = re.search(r's_code\s*=\s*["\']([^"\']+)["\']', r.text) or re.search(r'tt\s*=\s*["\']([^"\']+)["\']', r.text)
    tt = m.group(1) if m else 'dHl6Ylg4'
    print(f"[SSSTik] TT token: {tt}")
    
    post_data = {'id': url, 'locale': 'en', 'tt': tt}
    r2 = s.post('https://ssstik.io/abc?url=dl', data=post_data, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'HX-Request': 'true',
        'HX-Target': 'target',
        'HX-Current-URL': 'https://ssstik.io/en'
    })
    print(f"[SSSTik] POST status: {r2.status_code}")
    soup = BeautifulSoup(r2.text, 'html.parser')
    links = []
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if href.startswith('http'):
            links.append((a.text.strip(), href))
    return links

if __name__ == '__main__':
    res = test_ssstik('https://www.tiktok.com/@tiktok/video/7106594312292453678')
    print("Links found:", len(res))
    for text, href in res:
        print(f" -> {text}: {href[:60]}...")
