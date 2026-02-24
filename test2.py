import requests
import re
import base64
import json

url = "https://news.google.com/rss/articles/CBMiZkFVX3lxTE9qaDZqb1Z3NVRqUWtrZmtJSjJRN3JVSGx4bm90S0JmZ2VrV2xsRTFrNjUwZkVIQTBpOFZCNmtiQldVUVRPdkQwVXZIT2tKeVZ1bGRaTTk2YmhxT3RacFFNTGtPcUFTQQ?oc=5"
r = requests.get(url)

# 方法1: base64デコード（CBMi...の部分はProtobufエンコードされたURLを含む場合がある）
# 方法2: HTML内の特定のJavaScript変数から抽出
match = re.search(r'data-n-v="([^"]+)"', r.text)
if match:
    print("data-n-v:", match.group(1))

match2 = re.search(r'<a[^>]+href="([^"]+)"', r.text)
if match2:
    print("a href:", match2.group(1))
    
# fetch article URL from google news RSS redirect
# 実際には https://news.google.com/rss/articles/... は js でリダイレクトする仕組み
# 多くのスクレイパーでは、GoogleNewsのURLのベース64(CBMi...)をデコードしている
import urllib.parse
prefix_len = len("https://news.google.com/rss/articles/")
encoded = url[prefix_len:].split('?')[0]
print("encoded:", encoded)
try:
    decoded = base64.urlsafe_b64decode(encoded + "==").decode('utf-8', errors='ignore')
    print("decoded:", decoded)
    # デコードされた文字列の中から http... を探す
    m = re.search(r'(https?://[^\x00-\x1f"\']+)', decoded)
    if m:
        print("FOUND URL IN B64:", m.group(1))
except Exception as e:
    print("B64 Error:", e)
