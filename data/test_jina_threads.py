import requests
import re
import html
import json

url = 'https://r.jina.ai/https://www.threads.net/@kfury/post/DaGcWDwj8tW'
headers = {'x-respond-with': 'html'}
r = requests.get(url, headers=headers, timeout=20)
content = r.text

print(f"Status: {r.status_code}, Length: {len(content)}")

# Tìm thẻ title
m_title = re.search(r'<title>([^<]+)</title>', content)
title = m_title.group(1).strip() if m_title else "Threads Video"
print(f"Title: {title}")

# Tìm link MP4 trong toàn bộ HTML / JSON nhúng
matches = re.findall(r'https://[^"\'\s<>]+\.mp4[^"\'\s<>]*', content)
valid_urls = []
for m in matches:
    clean_url = html.unescape(m.replace('\\u0026', '&'))
    if clean_url not in valid_urls:
        valid_urls.append(clean_url)

print(f"Found {len(valid_urls)} unique direct MP4 URLs!")
for idx, v in enumerate(valid_urls[:3]):
    print(f" [{idx + 1}] {v[:100]}...")

# Test tải 1 chunk từ video đầu tiên để xác thực
if valid_urls:
    first_vid = valid_urls[0]
    head_resp = requests.head(first_vid, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    print("Direct Video CDN status:", head_resp.status_code, "Content-Type:", head_resp.headers.get('content-type'), "Size:", head_resp.headers.get('content-length'))
