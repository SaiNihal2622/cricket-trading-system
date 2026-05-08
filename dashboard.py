"""Live trading dashboard - FastAPI web UI. Shows ONLY real Cloudbet data."""
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
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px;padding:20px}
.card{background:#111827;border:1px solid #1e2a3a;border-radius:12px;padding:20px}
.card h3{color:#00d4aa;margin-bottom:12px;font-size:16px}
.stat-row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #1a2035}
.stat-label{color:#8892a4}.stat-value{font-weight:600}
.positive{color:#00d4aa}.negative{color:#ff4757}
table{width:100%;border-collapse:collapse;margin-top:10px}
th{text-align:left;padding:10px 8px;color:#8892a4;font-size:12px;text-transform:uppercase;border-bottom:1px solid #1e2a3a}
td{padding:10px 8px;border-bottom:1px solid #0f1520;font-size:14px}
.badge{padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge-live{background:#ff475722;color:#ff4757;animation:pulse 2s infinite}
.badge-trading{background:#00d4aa22;color:#00d4aa}
.badge-upcoming{background:#4a90d922;color:#4a90d9}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.6}}
.refresh-btn{background:#00d4aa;color:#000;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;font-weight:600}
.refresh-btn:hover{background:#00b894}
#status{color:#8892a4;font-size:12px}
.full-width{grid-column:1/-1}
.match-card{background:#0d1220;border:1px solid #1e2a3a;border-radius:10px;padding:16px;margin-bottom:12px;transition:border-color 0.3s}
.match-card:hover{border-color:#00d4aa}
.match-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.match-teams{font-size:18px;font-weight:700;color:#fff}
.match-details{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:10px}
.match-detail{font-size:13px;color:#8892a4}
.match-detail span{color:#e0e0e0;font-weight:500}
.market-section{margin-top:10px}
.market-title{font-size:13px;color:#00d4aa;font-weight:600;margin-bottom:6px;text-transform:uppercase}
.market-list{display:flex;flex-wrap:wrap;gap:6px}
.market-tag{background:#1a2035;border:1px solid #2a3a5a;border-radius:6px;padding:4px 10px;font-size:12px;color:#8892a4}
.odds-table{width:100%;margin-top:8px}
.odds-table td{padding:4px 8px;font-size:12px}
.odds-table .sel-name{color:#8892a4}
.odds-table .sel-price{color:#00d4aa;font-weight:700;text-align:right}
.no-data{text-align:center;padding:30px;color:#8892a4;font-size:14px}
.source-tag{font-size:11px;color:#4a90d9;margin-top:8px}
</style>
</head><body>
<div class="header">
  <div><h1>🏏 Cricket Trading System</h1><span id="status">Connecting...</span></div>
  <div><span class="mode-badge mode-""" + TRADING_MODE + """">""" + TRADING_MODE.upper() + """ MODE</span>
  <button class="refresh-btn" onclick="refresh()">Refresh</button></div>
</div>
<div class="grid">
  <div class="card full-width"><h3>🏏 Today's IPL Matches (Live from Cloudbet)</h3><div id="matches">Loading...</div></div>
  <div class="card full-width"><h3>📊 Available Markets & Odds</h3><div id="markets">Loading...</div></div>
  <div class="card"><h3>📈 System Status</h3><div id="status-panel">Loading...</div></div>
  <div class="card"><h3>🎯 Trades (Demo)</h3><div id="trades">No trades placed yet</div></div>
</div>
<script>
let ws;
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { document.getElementById('status').textContent = '🟢 Connected - Live Data'; };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    updateDashboard(data);
  };
  ws.onclose = () => { document.getElementById('status').textContent = '🔴 Disconnected - Reconnecting...'; setTimeout(connect, 3000); };
}
function updateDashboard(d) {
  const events = d.live_data?.events || [];
  const liveCount = d.live_data?.live_count || 0;
  const upcomingCount = d.live_data?.upcoming_count || 0;
  const fetchedAt = d.live_data?.fetched_at || '';
  const source = d.live_data?.source || 'unknown';

  // Matches
  let matchHtml = '';
  if (events.length === 0) {
    matchHtml = '<div class="no-data">No IPL matches found right now. Check back during match hours.</div>';
  } else {
    matchHtml += `<div style="margin-bottom:12px;color:#8892a4;font-size:13px">`;
    matchHtml += `<span class="positive">${liveCount} LIVE</span> &middot; `;
    matchHtml += `${upcomingCount} Upcoming &middot; `;
    matchHtml += `Source: <span style="color:#00d4aa">${source}</span> &middot; `;
    matchHtml += `Updated: ${fetchedAt ? new Date(fetchedAt).toLocaleTimeString('en-IN') : 'N/A'}</div>`;
    events.forEach(m => {
      const status = m.status || 'unknown';
      const statusBadge = `<span class="badge badge-${status}">${status.toUpperCase()}</span>`;
      const startTime = m.start_time ? new Date(m.start_time).toLocaleString('en-IN', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}) : '';
      const mktCount = m.market_count || (m.markets||[]).length || 0;
      matchHtml += `
        <div class="match-card">
          <div class="match-header">
            <div class="match-teams">${m.name || (m.home||'') + ' vs ' + (m.away||'')}</div>
            ${statusBadge}
          </div>
          <div class="match-details">
            <div class="match-detail">Start: <span>${startTime}</span></div>
            <div class="match-detail">Markets: <span>${mktCount}</span></div>
            <div class="match-detail">Cloudbet ID: <span>${m.id||''}</span></div>
            <div class="match-detail">Status: <span>${m.cloudbet_status||''}</span></div>
          </div>
        </div>`;
    });
  }
  document.getElementById('matches').innerHTML = matchHtml;

  // Markets detail
  let mktHtml = '';
  if (events.length === 0) {
    mktHtml = '<div class="no-data">No markets available</div>';
  } else {
    events.forEach(m => {
      const markets = m.markets || [];
      if (markets.length > 0) {
        mktHtml += `<div style="margin-bottom:16px">`;
        mktHtml += `<div class="market-title">${m.name}</div>`;
        mktHtml += `<div class="market-list">`;
        markets.forEach(mk => {
          const niceName = mk.replace('cricket.','').replace(/_/g,' ').replace('.v2',' v2');
          mktHtml += `<span class="market-tag">${niceName}</span>`;
        });
        mktHtml += `</div></div>`;
      }
    });
  }
  document.getElementById('markets').innerHTML = mktHtml;

  // Status
  const trades = d.trades || [];
  document.getElementById('status-panel').innerHTML = `
    <div class="stat-row"><span class="stat-label">Mode</span><span class="stat-value">${d.mode||'demo'}</span></div>
    <div class="stat-row"><span class="stat-label">Last Scan</span><span class="stat-value">${d.last_scan||'Never'}</span></div>
    <div class="stat-row"><span class="stat-label">Matches Found</span><span class="stat-value">${events.length}</span></div>
    <div class="stat-row"><span class="stat-label">Live Matches</span><span class="stat-value positive">${liveCount}</span></div>
    <div class="stat-row"><span class="stat-label">Upcoming</span><span class="stat-value">${upcomingCount}</span></div>
    <div class="stat-row"><span class="stat-label">Total Trades</span><span class="stat-value">${trades.length}</span></div>
    <div class="stat-row"><span class="stat-label">Data Source</span><span class="stat-value positive">Cloudbet API</span></div>
  `;

  // Trades
  if (trades.length > 0) {
    let thead = '<table><tr><th>Time</th><th>Match</th><th>Market</th><th>Selection</th><th>Odds</th><th>Stake</th><th>Status</th></tr>';
    trades.slice(0,10).forEach(t => {
      thead += `<tr><td>${t.created_at?.substring(11,19)||''}</td><td>${t.match_id?.substring(0,20)||''}</td><td>${t.market_type||''}</td>
        <td>${t.selection||''}</td><td>${t.odds}</td><td>$${t.stake}</td>
        <td><span class="badge badge-${t.status}">${t.status}</span></td></tr>`;
    });
    thead += '</table>';
    document.getElementById('trades').innerHTML = thead;
  }
}
function refresh() { fetch('/api/live').then(r=>r.json()).then(updateDashboard); }
connect();
setInterval(refresh, 10000);
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE


@app.get("/api/dashboard")
async def api_dashboard():
    """Return real Cloudbet data + any actual trades."""
    try:
        live = live_data.get_live_match_data()
    except Exception:
        live = {"events": [], "live_count": 0, "upcoming_count": 0, "total_count": 0, "source": "error"}
    trades = db.get_all_trades(limit=50)
    return {
        "live_data": live,
        "trades": trades,
        "last_scan": datetime.now().strftime("%H:%M:%S"),
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
        return live_data.get_live_match_data()
    except Exception as e:
        return {"events": [], "error": str(e), "source": "fallback"}


@app.get("/api/live")
async def api_live():
    """Return comprehensive live data from Cloudbet."""
    try:
        live = live_data.get_live_match_data()
    except Exception:
        live = {"events": [], "live_count": 0, "upcoming_count": 0, "total_count": 0, "source": "error"}
    trades = db.get_all_trades(limit=50)
    return {
        "live_data": live,
        "trades": trades,
        "last_scan": datetime.now().strftime("%H:%M:%S"),
        "mode": TRADING_MODE,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            try:
                live = live_data.get_live_match_data()
            except Exception:
                live = {"events": [], "live_count": 0, "upcoming_count": 0, "total_count": 0, "source": "error"}
            trades = db.get_all_trades(limit=50)
            await ws.send_json({
                "live_data": live,
                "trades": trades,
                "last_scan": datetime.now().strftime("%H:%M:%S"),
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