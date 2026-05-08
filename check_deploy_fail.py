import urllib.request, json, os, subprocess

env = os.environ.copy()
env.pop('GH_TOKEN', None)
result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, env=env, timeout=10)
token = result.stdout.strip()

repo = 'SaiNihal2622/cricket-trading-system'
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

# Get Run #4 jobs
run_url = 'https://api.github.com/repos/SaiNihal2622/cricket-trading-system/actions/runs/25526238016'
req = urllib.request.Request(f'{run_url}/jobs', headers=headers)
jobs = json.loads(urllib.request.urlopen(req).read())
for job in jobs.get('jobs', []):
    print(f"Job: {job['name']} - {job['status']} - {job.get('conclusion', 'pending')}")
    for step in job.get('steps', []):
        status_icon = '✓' if step.get('conclusion') == 'success' else '✗' if step.get('conclusion') == 'failure' else '...'
        print(f"  {status_icon} {step['name']} - {step.get('conclusion', 'pending')}")

# Check Pages status
print("\n--- GitHub Pages Status ---")
try:
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}/pages', headers=headers)
    resp = json.loads(urllib.request.urlopen(req).read())
    print(f"  URL: {resp.get('html_url', 'N/A')}")
    print(f"  Source: {resp.get('source', 'N/A')}")
    print(f"  Build type: {resp.get('build_type', 'N/A')}")
    print(f"  Public: {resp.get('public', 'N/A')}")
    print(f"  HTTPS: {resp.get('https_enforced', 'N/A')}")
    # Check latest build
    if 'url' in resp:
        try:
            req2 = urllib.request.Request(f"https://api.github.com/repos/{repo}/pages/builds?per_page=3", headers=headers)
            builds = json.loads(urllib.request.urlopen(req2).read())
            for b in builds:
                print(f"  Build: {b.get('status', 'N/A')} - {b.get('created_at', 'N/A')}")
        except:
            pass
except Exception as e:
    print(f"  Pages error: {e}")

# Check repo permissions
print("\n--- Repo Permissions ---")
try:
    req = urllib.request.Request(f'https://api.github.com/repos/{repo}', headers=headers)
    resp = json.loads(urllib.request.urlopen(req).read())
    perms = resp.get('permissions', {})
    print(f"  Admin: {perms.get('admin', False)}")
    print(f"  Push: {perms.get('push', False)}")
    print(f"  Pages: {resp.get('has_pages', False)}")
except Exception as e:
    print(f"  Error: {e}")