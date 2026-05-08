import urllib.request, json, base64, os

token = os.environ.get('GH_TOKEN', '')
repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json',
    'Content-Type': 'application/json'
}

# 1. Get current SHA of deploy.yml on master
path = '.github/workflows/deploy.yml'
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/contents/{path}?ref=master',
    headers=headers
)
resp = json.loads(urllib.request.urlopen(req).read())
sha = resp['sha']
print(f'Current SHA: {sha}')

# 2. Read and push updated workflow
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

body = {
    'message': 'ci: Remove Railway/VPS, add GitHub Pages deployment',
    'content': base64.b64encode(content.encode()).decode(),
    'sha': sha,
    'branch': 'master',
}

data = json.dumps(body).encode()
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/contents/{path}',
    data=data, method='PUT', headers=headers
)
resp = json.loads(urllib.request.urlopen(req).read())
print(f'Workflow updated: {resp.get("commit", {}).get("html_url", "OK")}')

# 3. Enable GitHub Pages via API (using gh-actions source)
try:
    pages_body = json.dumps({
        'build_type': 'workflow',
        'source': {
            'branch': 'master',
            'path': '/'
        }
    }).encode()
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/pages',
        data=pages_body, method='POST', headers=headers
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    print(f'GitHub Pages enabled: {resp.get("html_url", "OK")}')
except Exception as e:
    print(f'Pages setup (may already exist): {e}')
    # Try PATCH to update
    try:
        pages_body = json.dumps({
            'build_type': 'workflow',
            'source': {
                'branch': 'master',
                'path': '/'
            }
        }).encode()
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/pages',
            data=pages_body, method='PATCH', headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        print(f'GitHub Pages updated: {resp.get("html_url", "OK")}')
    except Exception as e2:
        print(f'Pages update: {e2}')

# 4. Set GitHub secrets (NVIDIA_API_KEY, GEMINI_API_KEY, GROK_API_KEY)
# First get the repo public key for secret encryption
try:
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/actions/secrets/public-key',
        headers=headers
    )
    key_resp = json.loads(urllib.request.urlopen(req).read())
    print(f'Got public key for secrets encryption')
    
    # Read .env for API keys
    env_path = os.path.join(os.path.dirname(path) if os.path.dirname(path) else '.', '.env')
    env_keys = {}
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_keys[k.strip()] = v.strip().strip('"').strip("'")
    
    print(f'Found {len(env_keys)} keys in .env')
    print(f'Keys: {list(env_keys.keys())}')
    
except Exception as e:
    print(f'Secrets setup: {e}')

print('\nDone! Check https://github.com/SaiNihal2622/cricket-trading-system/actions')