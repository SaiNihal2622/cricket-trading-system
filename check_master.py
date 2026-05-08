import urllib.request, json, os

token = os.environ.get('GH_TOKEN', '')
repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# Check what files are on master
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/git/trees/master?recursive=1',
    headers=headers
)
resp = json.loads(urllib.request.urlopen(req).read())
for item in resp.get('tree', []):
    if '.github' in item['path'] or 'frontend' in item['path']:
        print(f"  {item['path']}")

# Check latest commits
print('\nLatest commits:')
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/commits?per_page=5',
    headers=headers
)
resp = json.loads(urllib.request.urlopen(req).read())
for c in resp:
    print(f"  {c['sha'][:8]}: {c['commit']['message'][:80]}")