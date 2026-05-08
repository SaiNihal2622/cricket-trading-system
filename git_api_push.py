import urllib.request, json, base64, os, hashlib, zlib

token = os.environ.get('GH_TOKEN', '')
repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json',
    'Content-Type': 'application/json'
}

def api_get(url):
    req = urllib.request.Request(url, headers=headers)
    return json.loads(urllib.request.urlopen(req).read())

def api_post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method='POST', headers=headers)
    return json.loads(urllib.request.urlopen(req).read())

# 1. Get current master HEAD commit
ref = api_get(f'https://api.github.com/repos/{repo}/git/refs/heads/master')
head_sha = ref['object']['sha']
print(f'Current HEAD: {head_sha}')

# 2. Get the tree of the current HEAD
head_commit = api_get(f'https://api.github.com/repos/{repo}/git/commits/{head_sha}')
base_tree_sha = head_commit['tree']['sha']

# 3. Read the new workflow file
with open('.github/workflows/deploy.yml', 'r', encoding='utf-8') as f:
    workflow_content = f.read()

# 4. Create a blob for the new workflow file
blob = api_post(f'https://api.github.com/repos/{repo}/git/blobs', {
    'content': workflow_content,
    'encoding': 'utf-8'
})
blob_sha = blob['sha']
print(f'Created blob: {blob_sha}')

# 5. Create a new tree with the updated workflow file
tree = api_post(f'https://api.github.com/repos/{repo}/git/trees', {
    'base_tree': base_tree_sha,
    'tree': [
        {
            'path': '.github/workflows/deploy.yml',
            'mode': '100644',
            'type': 'blob',
            'sha': blob_sha
        }
    ]
})
tree_sha = tree['sha']
print(f'Created tree: {tree_sha}')

# 6. Create a new commit
commit = api_post(f'https://api.github.com/repos/{repo}/git/commits', {
    'message': 'ci: Remove Railway/VPS, add GitHub Pages deployment\n\n- Remove Railway and VPS deploy jobs\n- Add GitHub Pages frontend deployment\n- Use GITHUB_TOKEN for container registry\n- Add Telegram notifications',
    'tree': tree_sha,
    'parents': [head_sha]
})
commit_sha = commit['sha']
print(f'Created commit: {commit_sha}')

# 7. Update the ref
req = urllib.request.Request(
    f'https://api.github.com/repos/{repo}/git/refs/heads/master',
    data=json.dumps({'sha': commit_sha, 'force': False}).encode(),
    method='PATCH',
    headers=headers
)
resp = json.loads(urllib.request.urlopen(req).read())
print(f'Ref updated: {resp.get("object", {}).get("sha", "OK")}')

# 8. Enable GitHub Pages
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
    print(f'  Pages POST: {e}')
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{repo}/pages',
            data=pages_body, method='PATCH', headers=headers
        )
        resp = json.loads(urllib.request.urlopen(req).read())
        print(f'  GitHub Pages updated: {resp.get("html_url", "OK")}')
    except Exception as e2:
        print(f'  Pages PATCH: {e2}')

print('\nDone! Check: https://github.com/SaiNihal2622/cricket-trading-system/actions')