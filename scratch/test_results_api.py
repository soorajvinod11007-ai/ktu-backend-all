import urllib.request, json, urllib.error

login_req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'ChangeMe123!'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)
token = json.loads(urllib.request.urlopen(login_req).read().decode())['access_token']

# Test with no sort param (empty string -> undefined)
urls = [
    'http://127.0.0.1:8000/api/v1/admin/results?page=1&page_size=2',
    'http://127.0.0.1:8000/api/v1/admin/results?page=1&page_size=2&sort=-created_at',
    'http://127.0.0.1:8000/api/v1/admin/results?page=1&page_size=2&sort=id',
]
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        data = urllib.request.urlopen(req).read().decode()
        parsed = json.loads(data)
        print(f"OK  {url.split('?')[1]}: {len(parsed.get('items',[]))} items, total={parsed.get('total')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERR {url.split('?')[1]}: HTTP {e.code} - {body[:150]}")
