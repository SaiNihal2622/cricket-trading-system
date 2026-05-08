"""Live trading dashboard - FastAPI web UI."""
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
import db
import live_data
from config import DASHBOARD_PORT, TRADING_MODE

app = FastAPI(title="Cricket Trading Dashboard")

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<title>Cricket Trading Dashboard</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0e17;color:#e0e0e0}
.header{background:linear-gradient(135deg,#1a1f35,#0d1220);padding:20px 30px;border-bottom:1px solid #1e2a3a;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:24px;color:#00d4aa}
.mode-badge{padding:6px 16px;border-radius:20px;font-weight:700;font-size:14px}
.mode-demo{background:#ff6b35;color:#fff}
.mode-live{background:#00d4aa;color:#000}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;padding:20px}
.card{background:#111827;border:1px solid #1e2a3a;border-radius:12px;padding:20px}
.card h3{color:#00d4aa;margin-bottom:12px;font-size:16px}
.stat-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1a2035}
.stat-label{color:#8892a4}.stat-value{font-weight:600}
.positive{color:#00d4aa}.negative{color:#ff4757}
table{width:100%;border-collapse:collapse;margin-top:10px}
th{text-align:left;padding:10px 8px;color:#8892a4;font-size:12px;text-transform:uppercase;border-bottom:1px solid #1e2a3a}
td{padding:10px 8px;border-bottom:1px solid #0f1520;font-size:14px}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-open{background:#00d4aa22;color:#00d4aa}
.badge-settled{background:#4a90d922;color:#4a90d9}
.badge-pending{background:#ff6b3522;color:#ff6b35}
.badge-win{background:#00d4aa22;color:#00d4aa}
.badge-loss{background:#ff475722;color:#ff4757}
.badge-live{background:#ff475722;color:#ff4757;animation:pulse 2s infinite}
.badge-trading{background:#00d4aa22;color:#00d4aa}
.badge-upcoming{background:#4a90d922;color:#4a90d9}
.badge-completed{background:#8892a422;color:#8892a4}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.6}}
.models-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.model-card{background:#0d1220;border:1px solid #1e2a3a;border-radius:8px;padding:12px;text-align:center}
.model-card .name{font-size:12px;color:#8892a4;margin-bottom:4px}
.model-card .accuracy{font-size:24px;font-weight:700;color:#00d4aa}
.refresh-btn{background:#00d4aa;color:#000;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;font-weight:600}
.refresh-btn:hover{background:#00b894}
#status{color:#8892a4;font-size:12px}
.full-width{grid-column:1/-1}
.match-card{background:#0d1220;border:1px solid #1e2a3a;border-radius:10px;padding:16px;margin-bottom:12px;transition:border-color 0.3s}
.match-card:hover{border-color:#00d4aa}
.match-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.match-teams{font-size:18px;font-weight:700;color:#fff}
.match-score{font-size:22px;font-weight:700;color:#00d4aa;font-family:'Courier New',monospace}
.match-details{display:flex;gap:20px;flex-wrap:wrap}
.match-detail{font-size:13px;color:#8892a4}
.match-detail span{color:#e0e0e0;font-weight:500}
.no-matches{text-align:center;padding:30px;color:#8892a4;font-size:14px}
</style>
</head><body>
<div class="header">
  <div><h1>🏏 Cricket Trading System</h1><span id="status">Connecting...</span></div>
  <div><span class="mode-badge mode-""" + TRADING_MODE + """">""" + TRADING_MODE.upper() + """ MODE</span>
  <button class="refresh-btn" onclick="refresh()">Refresh</button></div>
</div>
<div class="grid">
  <div class="card full-width"><h3>🏏 Live Matches</h3><div id="matches">Loading...</div></div>
  <div class="card"><h3>📊 Portfolio Summary</h3><div id="portfolio">Loading...</div></div>
  <div class="card"><h3>🤖 AI Models</h3><div id="models">Loading...</div></div>
  <div class="card"><h3>📈 Performance</h3><div id="performance">Loading...</div></div>
  <div class="card"><h3>🎯 Recent Decisions</h3><div id="decisions">Loading...</div></div>
  <div class="card full-width"><h3>📋 Trade History</h3><div id="trades">Loading...</div></div>
</div>
<script>
let ws;
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { document.getElementById('status').textContent = 'Live'; };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    updateDashboard(data);
  };
  ws.onclose = () => { setTimeout(connect, 3000); };
}
function updateDashboard(d) {
  // Live Matches - support both live_data format and db format
  const events = d.live_data?.events || d.matches || [];
  const liveCount = d.live_data?.live_count || 0;
  const upcomingCount = d.live_data?.upcoming_count || 0;
  const totalCount = d.live_data?.total_count || events.length;
  let matchHtml = '';
  if (events.length === 0) {
    matchHtml = '<div class="no-matches">No matches found. The system will auto-detect IPL matches when connected to Cloudbet API.</div>';
  } else {
    matchHtml += `<div style="margin-bottom:12px;color:#8892a4;font-size:13px">`;
    matchHtml += `<span class="positive">${liveCount} LIVE</span> &middot; `;
    matchHtml += `${upcomingCount} Upcoming &middot; `;
    matchHtml += `${totalCount} Total &middot; `;
    matchHtml += `Source: <span style="color:#00d4aa">Cloudbet API</span></div>`;
    events.forEach(m => {
      const status = m.status || 'unknown';
      const statusBadge = `<span class="badge badge-${status}">${status.toUpperCase()}</span>`;
      const startTime = m.start_time ? new Date(m.start_time).toLocaleString('en-IN', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : '';
      const mktCount = m.market_count || (m.markets||[]).length || 0;
      let oddsHtml = '';
      if (m.live_odds) {
        Object.entries(m.live_odds).forEach(([mkt, sels]) => {
          if (sels && sels.length > 0) {
            oddsHtml += `<div class="match-detail">Odds: `;
            sels.slice(0,4).forEach(s => {
              oddsHtml += `<span style="margin-right:8px">${s.label}: ${s.price}</span>`;
            });
            oddsHtml += `</div>`;
          }
        });
      }
      matchHtml += `
        <div class="match-card">
          <div class="match-header">
            <div class="match-teams">${m.name || (m.home||'') + ' vs ' + (m.away||'')}</div>
            ${statusBadge}
          </div>
          <div class="match-details">
            <div class="match-detail">Time: <span>${startTime}</span></div>
            <div class="match-detail">Markets: <span>${mktCount}</span></div>
            <div class="match-detail">Event ID: <span>${m.id||''}</span></div>
          </div>
          ${oddsHtml}
        </div>`;
    });
  }
  document.getElementById('matches').innerHTML = matchHtml;

  // Portfolio
  const p = d.stats?.demo || {};
  const total = p.total || 0;
  const wins = p.wins || 0;
  const losses = p.losses || 0;
  const pnl = (p.total_pnl || 0).toFixed(2);
  const acc = total > 0 ? ((wins/total)*100).toFixed(1) : '0.0';
  document.getElementById('portfolio').innerHTML = `
    <div class="stat-row"><span class="stat-label">Total Trades</span><span class="stat-value">${total}</span></div>
    <div class="stat-row"><span class="stat-label">Wins / Losses</span><span class="stat-value"><span class="positive">${wins}</span> / <span class="negative">${losses}</span></span></div>
    <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-value ${parseFloat(acc)>=50?'positive':'negative'}">${acc}%</span></div>
    <div class="stat-row"><span class="stat-label">Total P&L</span><span class="stat-value ${parseFloat(pnl)>=0?'positive':'negative'}">$${pnl}</span></div>
  `;
  // Models
  const models = d.stats?.model_performance || [];
  let mhtml = '<div class="models-grid">';
  if (models.length === 0) {
    mhtml += '<div class="model-card"><div class="name">NVIDIA Nemotron</div><div class="accuracy">--</div></div>';
    mhtml += '<div class="model-card"><div class="name">Gemini Flash</div><div class="accuracy">--</div></div>';
    mhtml += '<div class="model-card"><div class="name">Grok 3</div><div class="accuracy">--</div></div>';
    mhtml += '<div class="model-card"><div class="name">MIMO</div><div class="accuracy">--</div></div>';
  } else {
    models.forEach(m => {
      mhtml += `<div class="model-card"><div class="name">${m.model_name}</div><div class="accuracy">${(m.accuracy*100).toFixed(0)}%</div></div>`;
    });
  }
  mhtml += '</div>';
  document.getElementById('models').innerHTML = mhtml;
  // Decisions
  const decs = d.decisions || [];
  let dhtml = '';
  decs.slice(0,5).forEach(dec => {
    dhtml += `<div class="stat-row"><span class="stat-label">${dec.selection?.substring(0,30)}</span>
      <span class="stat-value">${dec.decision} | Edge: ${(dec.edge*100).toFixed(1)}%</span></div>`;
  });
  if (!dhtml) dhtml = '<div class="stat-row"><span class="stat-label">No decisions yet</span></div>';
  document.getElementById('decisions').innerHTML = dhtml;
  // Trades
  const trades = d.trades || [];
  let thead = '<table><tr><th>Time</th><th>Match</th><th>Market</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Status</th><th>P&L</th></tr>';
  trades.slice(0,20).forEach(t => {
    const cls = t.pnl > 0 ? 'win' : (t.pnl < 0 ? 'loss' : t.status);
    thead += `<tr><td>${t.created_at?.substring(11,19)||''}</td><td>${t.match_id?.substring(0,15)||''}</td><td>${t.market_type?.substring(0,20)||''}</td>
      <td>${t.selection?.substring(0,20)||''}</td><td>${t.odds}</td><td>$${t.stake}</td>
      <td><span class="badge badge-${cls}">${t.status}</span></td>
      <td class="${t.pnl>=0?'positive':'negative'}">$${(t.pnl||0).toFixed(2)}</td></tr>`;
  });
  thead += '</table>';
  if (trades.length === 0) thead = '<p style="color:#8892a4">No trades yet. Waiting for markets...</p>';
  document.getElementById('trades').innerHTML = thead;
  // Performance
  document.getElementById('performance').innerHTML = `
    <div class="stat-row"><span class="stat-label">Active Markets</span><span class="stat-value">${d.active_markets||0}</span></div>
    <div class="stat-row"><span class="stat-label">Last Scan</span><span class="stat-value">${d.last_scan||'Never'}</span></div>
    <div class="stat-row"><span class="stat-label">AI Models Active</span><span class="stat-value">${d.models_active||0}</span></div>
    <div class="stat-row"><span class="stat-label">Matches Tracked</span><span class="stat-value">${(d.matches||[]).length}</span></div>
  `;
}
function refresh() { fetch('/api/dashboard').then(r=>r.json()).then(updateDashboard); }
connect();
setInterval(refresh, 15000);
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE


@app.get("/api/dashboard")
async def api_dashboard():
    stats = db.get_trade_stats()
    trades = db.get_all_trades(limit=50)
    decisions = db.get_ensemble_decisions(limit=10)
    matches = db.get_all_matches(limit=20)
    return {
        "stats": stats,
        "trades": trades,
        "decisions": decisions,
        "matches": matches,
        "active_markets": len([t for t in trades if t.get("status") == "open"]),
        "last_scan": datetime.now().strftime("%H:%M:%S"),
        "models_active": 4,
        "mode": TRADING_MODE,
    }


@app.get("/api/trades")
async def api_trades():
    return db.get_all_trades(limit=100)


@app.get("/api/stats")
async def api_stats():
    return db.get_trade_stats()


@app.get("/api/matches")
async def api_matches():
    """Return real live matches from Cloudbet API."""
    try:
        live = live_data.get_live_match_data()
        return live
    except Exception as e:
        return {"events": [], "error": str(e), "source": "fallback"}


@app.get("/api/live")
async def api_live():
    """Return comprehensive live data from Cloudbet."""
    try:
        live = live_data.get_live_match_data()
        stats = db.get_trade_stats()
        trades = db.get_all_trades(limit=50)
        decisions = db.get_ensemble_decisions(limit=10)
        return {
            "live_data": live,
            "stats": stats,
            "trades": trades,
            "decisions": decisions,
            "active_markets": len([t for t in trades if t.get("status") == "open"]),
            "last_scan": datetime.now().strftime("%H:%M:%S"),
            "models_active": 4,
            "mode": TRADING_MODE,
        }
    except Exception as e:
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            stats = db.get_trade_stats()
            trades = db.get_all_trades(limit=50)
            decisions = db.get_ensemble_decisions(limit=10)
            matches = db.get_all_matches(limit=20)
            # Fetch live Cloudbet data
            try:
                live = live_data.get_live_match_data()
            except Exception:
                live = {"events": [], "live_count": 0, "upcoming_count": 0, "total_count": 0}
            await ws.send_json({
                "stats": stats,
                "trades": trades,
                "decisions": decisions,
                "matches": matches,
                "live_data": live,
                "active_markets": len([t for t in trades if t.get("status") == "open"]),
                "last_scan": datetime.now().strftime("%H:%M:%S"),
                "models_active": 4,
                "mode": TRADING_MODE,
            })
            await asyncio.sleep(10)
    except Exception:
        pass


def start_dashboard():
    db.init_db()
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="warning")


if __name__ == "__main__":
    start_dashboard()
