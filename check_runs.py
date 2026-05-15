import urllib.request, json

url = "https://api.github.com/repos/SaiNihal2622/cricket-trading-system/actions/runs?per_page=5"
req = urllib.request.Request(url, headers={"User-Agent": "Python"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())

for r in data.get("workflow_runs", []):
    print(f"ID: {r['id']}")
    print(f"  Status: {r['status']} | Conclusion: {r['conclusion']}")
    print(f"  Created: {r['created_at']}")
    print(f"  URL: {r['html_url']}")
    print()

print("Repo: https://github.com/SaiNihal2622/cricket-trading-system")
print("Actions: https://github.com/SaiNihal2622/cricket-trading-system/actions")