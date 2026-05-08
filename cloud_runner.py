"""Cloud runner for GitHub Actions - runs trading engine in the cloud.

This script is designed to run inside GitHub Actions. It:
1. Runs the trading engine for a configurable duration
2. Scans for IPL matches and makes predictions
3. Logs everything to stdout (visible in Actions logs)
4. Saves results to SQLite database (uploaded as artifact)
5. Sends Telegram notifications for trades
"""
import asyncio
import os
import sys
import time
import json
import sqlite3
from datetime import datetime, timedelta

# Configuration from environment
TRADING_MODE = os.getenv("TRADING_MODE", "demo")
DURATION_HOURS = float(os.getenv("DURATION_HOURS", "4"))
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "120"))  # seconds
DB_PATH = os.getenv("DB_PATH", "cricket_trading.db")

# Telegram config
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def log(msg: str):
    """Print with timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


async def send_telegram(msg: str):
    """Send message to Telegram."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            )
    except Exception as e:
        log(f"Telegram error: {e}")


def init_cloud_db():
    """Initialize database with cloud-specific tables."""
    import db
    db.init_db()
    log(f"Database initialized at {DB_PATH}")


async def run_trading_cycle():
    """Run a single trading cycle."""
    try:
        from trading_engine import scan_and_trade
        await scan_and_trade()
    except Exception as e:
        log(f"Trading cycle error: {e}")
        import traceback
        traceback.print_exc()


def get_session_stats():
    """Get current session statistics from database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # Get trade stats
        trades = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as won, "
            "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as lost, "
            "SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) as open "
            "FROM trades WHERE mode=?", (TRADING_MODE,)
        ).fetchone()
        
        # Get P&L
        pnl_row = conn.execute(
            "SELECT SUM(CASE WHEN status='won' THEN profit ELSE -stake END) as pnl "
            "FROM trades WHERE mode=? AND status IN ('won','lost')", (TRADING_MODE,)
        ).fetchone()
        
        conn.close()
        
        total = trades["total"] or 0
        won = trades["won"] or 0
        lost = trades["lost"] or 0
        pnl = pnl_row["pnl"] or 0
        accuracy = won / (won + lost) if (won + lost) > 0 else 0
        
        return {
            "total_trades": total,
            "won": won,
            "lost": lost,
            "open": trades["open"] or 0,
            "pnl": pnl,
            "accuracy": accuracy,
        }
    except Exception as e:
        log(f"Stats error: {e}")
        return {"total_trades": 0, "won": 0, "lost": 0, "open": 0, "pnl": 0, "accuracy": 0}


async def main():
    """Main cloud runner loop."""
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=DURATION_HOURS)
    
    log("=" * 60)
    log("🏏 CRICKET TRADING SYSTEM - CLOUD RUNNER")
    log(f"   Mode: {TRADING_MODE.upper()}")
    log(f"   Duration: {DURATION_HOURS} hours")
    log(f"   Scan interval: {SCAN_INTERVAL}s")
    log(f"   Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"   Ends: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)
    
    # Initialize
    init_cloud_db()
    
    # Check available AI models
    from config import MIMO_API_KEY, GEMINI_API_KEY, GROK_API_KEY, NVIDIA_API_KEY
    models = []
    if MIMO_API_KEY:
        models.append("MIMO")
    if GEMINI_API_KEY:
        models.append("Gemini")
    if GROK_API_KEY:
        models.append("Grok")
    if NVIDIA_API_KEY:
        models.append("NVIDIA")
    log(f"🤖 AI Models available: {', '.join(models) if models else 'NONE'}")
    
    # Notify start
    await send_telegram(
        f"🏏 <b>Trading Session Started</b>\n"
        f"Mode: {TRADING_MODE.upper()}\n"
        f"Duration: {DURATION_HOURS}h\n"
        f"Models: {', '.join(models)}\n"
        f"Interval: {SCAN_INTERVAL}s"
    )
    
    cycle = 0
    total_trades = 0
    
    while datetime.now() < end_time:
        cycle += 1
        remaining = (end_time - datetime.now()).total_seconds() / 60
        
        log(f"\n--- Cycle {cycle} | {remaining:.0f} min remaining ---")
        
        try:
            await run_trading_cycle()
        except Exception as e:
            log(f"Cycle {cycle} failed: {e}")
        
        # Get stats
        stats = get_session_stats()
        if stats["total_trades"] > total_trades:
            new_trades = stats["total_trades"] - total_trades
            total_trades = stats["total_trades"]
            log(f"📊 New trades: {new_trades} | Total: {total_trades} | "
                f"Won: {stats['won']} | Lost: {stats['lost']} | "
                f"Accuracy: {stats['accuracy']:.1%}")
            
            # Notify on new trades
            await send_telegram(
                f"📊 <b>Trade Update</b>\n"
                f"Trades: {stats['total_trades']}\n"
                f"Won: {stats['won']} | Lost: {stats['lost']}\n"
                f"Accuracy: {stats['accuracy']:.1%}\n"
                f"P&L: {stats['pnl']:.2f}"
            )
        
        # Wait for next cycle
        if remaining > 1:
            wait_time = min(SCAN_INTERVAL, remaining * 60)
            log(f"⏳ Next scan in {wait_time:.0f}s...")
            await asyncio.sleep(wait_time)
        else:
            break
    
    # Final summary
    final_stats = get_session_stats()
    log("\n" + "=" * 60)
    log("🏏 TRADING SESSION COMPLETE")
    log(f"   Total trades: {final_stats['total_trades']}")
    log(f"   Won: {final_stats['won']}")
    log(f"   Lost: {final_stats['lost']}")
    log(f"   Open: {final_stats['open']}")
    log(f"   Accuracy: {final_stats['accuracy']:.1%}")
    log(f"   P&L: {final_stats['pnl']:.2f}")
    log("=" * 60)
    
    # Save final report
    report = {
        "session_start": start_time.isoformat(),
        "session_end": datetime.now().isoformat(),
        "mode": TRADING_MODE,
        "models": models,
        "stats": final_stats,
        "cycles": cycle,
    }
    with open("trading_log_" + start_time.strftime("%Y%m%d_%H%M%S") + ".json", "w") as f:
        json.dump(report, f, indent=2)
    
    # Final Telegram notification
    await send_telegram(
        f"🏏 <b>Session Complete</b>\n"
        f"Duration: {DURATION_HOURS}h\n"
        f"Trades: {final_stats['total_trades']}\n"
        f"Won: {final_stats['won']} | Lost: {final_stats['lost']}\n"
        f"Accuracy: {final_stats['accuracy']:.1%}\n"
        f"P&L: {final_stats['pnl']:.2f}\n"
        f"Cycles: {cycle}"
    )
    
    log("Done! Results saved as artifact.")


if __name__ == "__main__":
    asyncio.run(main())