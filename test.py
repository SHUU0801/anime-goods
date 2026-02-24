import requests
import re

url = "https://news.google.com/rss/articles/CBMiZkFVX3lxTE9qaDZqb1Z3NVRqUWtrZmtJSjJRN3JVSGx4bm90S0JmZ2VrV2xsRTFrNjUwZkVIQTBpOFZCNmtiQldVUVRPdkQwVXZIT2tKeVZ1bGRaTTk2YmhxT3RacFFNTGtPcUFTQQ?oc=5"
r = requests.get(url)
print("STATUS:", r.status_code)
html = r.text
match = re.search(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
if match:
    real_url = match.group(1)
    print("REAL URL:", real_url)
    
    r2 = requests.get(real_url)
    print("REAL STATUS:", r2.status_code)
    m2 = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']', r2.text, re.IGNORECASE)
    print("OGP:", m2.group(1) if m2 else "Not found")
else:
    print("NO LINK FOUND")
