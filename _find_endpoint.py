from curl_cffi import requests as cf_requests
import json, re

wallet = 'GZQErjcSVmJBiWZaHiQknvKq6vrJEWhSHobvTezJaBT'
r0 = cf_requests.get(f'https://gmgn.ai/sol/address/{wallet}',
    impersonate='chrome120', headers={'Referer':'https://gmgn.ai/'}, timeout=15)
scripts = re.findall(r'src="(/_next/static/chunks/[^"]+\.js)"', r0.text)
print(f"Found {len(scripts)} scripts")

for s in scripts:
    r = cf_requests.get(f'https://gmgn.ai{s}', impersonate='chrome120', timeout=10)
    if 'winrate' in r.text and 'wallet' in r.text:
        hits = re.findall(r'.{0,60}winrate.{0,60}', r.text)
        url_hits = re.findall(r'/api/v\d[^\s"\'`]{5,80}', r.text)
        wallet_urls = [u for u in url_hits if 'wallet' in u.lower()]
        if wallet_urls:
            print(f"\n=== {s}")
            for h in hits[:3]:
                print("  WIN:", h)
            for u in list(set(wallet_urls))[:10]:
                print("  URL:", u)
            break
