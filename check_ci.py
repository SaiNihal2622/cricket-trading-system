import urllib.request, json

req = urllib.request.Request('https://api.github.com/repos/SaiNihal2622/cricket-trading-system/actions/runs?per_page=3')
resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
runs = resp.get('workflow_runs', [])
for r in runs:
    print(f"Run #{r['run_number']}: {r['status']} - {r.get('conclusion', 'pending')}")
    print(f"  URL: {r['html_url']}")