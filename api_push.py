import urllib.request, json, base64, os

token = os.environ.get('GH_TOKEN', '')
repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json',
    'Content-Type': 'application/json'
}

def api_update_file(filepath, message):
    """Update a file via GitHub Contents API"""
    # Get current SHA
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/contents/{filepath}?ref=master',
            headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        sha = resp['sha']
    except Exception:
        sha = None
    
    # Read local file
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    body = {
        'message': message,
        'content': base64.b64encode(content.encode()).decode(),
        'branch': 'master',
    }
    if sha:
        body['sha'] = sha
    
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/contents/{filepath}',
        data=data, method='PUT', headers=headers
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    commit_url = resp.get('commit', {}).get('html_url', 'OK')
    print(f'  Updated {filepath}: {commit_url}')
    return True

# Update the workflow file
print('Updating workflow file...')
api_update_file('.github/workflows/deploy.yml', 'ci: Remove Railway/VPS, add GitHub Pages deployment')

# Enable GitHub Pages
print('\nEnabling GitHub Pages...')
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
    print(f'  GitHub Pages enabled: {resp.get("html_url", "OK")}')
except Exception as e:
    print(f'  Pages POST failed: {e}')
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
        print(f'  GitHub Pages updated: {resp.get("html_url", "OK")}')
    except Exception as e2:
        print(f'  Pages PATCH: {e2}')

# Enable GitHub Pages via repository settings
print('\nUpdating repo settings for Pages...')
try:
    settings_body = json.dumps({
        'default_branch': 'master'
    }).encode()
    req = urllib.request.Request(
        f'https://api.github.com/repos/{repo}',
        data=settings_body, method='PATCH', headers=headers
    )
    resp = json.loads(urllib.request.urlopen(req).read())
    print(f'  Repo default branch: {resp.get("default_branch", "OK")}')
except Exception as e:
    print(f'  Repo settings: {e}')

print('\nDone!')