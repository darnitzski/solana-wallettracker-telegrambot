from curl_cffi import requests as cf_requests
import json, re

# Find the leaderboard/rank endpoint from JS
r0 = cf_requests.get('https://gmgn.ai/sol/degens',
    impersonate='chrome120', headers={'Referer':'https://gmgn.ai/'}, timeout=15)
scripts = re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', r0.text)
print(f"Found {len(scripts)} scripts")

for s in scripts:
    r = cf_requests.get(f'https://gmgn.ai{s}', impersonate='chrome120', timeout=10)
    if 'winrate' in r.text and ('rank' in r.text or 'leaderboard' in r.text):
        url_hits = re.findall(r'(?:url|URL)[^"\'`]{0,10}["`\']([^"`\']{10,80})["`\']', r.text)
        rank_urls = [u for u in url_hits if any(k in u for k in ['rank','wallet','stat'])]
        if rank_urls:
            print(f"\n=== {s}")
            for u in list(set(rank_urls))[:15]:
                print("  URL:", u)
            break
