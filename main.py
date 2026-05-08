"""Main entry point - runs trading engine + dashboard together."""
import asyncio
import threading
import sys
import time
from datetime import datetime
from config import TRADING_MODE, DASHBOARD_PORT
import db


def run_dashboard_thread():
    """Run dashboard in a separate thread."""
    from dashboard import start_dashboard
    start_dashboard()


async def trading_loop():
    """Main trading loop - scans every 5 minutes during match hours."""
    from trading_engine import scan_and_trade
    
    print(f"\n{'='*60}")
    print(f"  🏏 CRICKET TRADING SYSTEM")
    print(f"  Mode: {TRADING_MODE.upper()}")
    print(f"  Dashboard: http://localhost:{DASHBOARD_PORT}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    while True:
        try:
            await scan_and_trade()
        except Exception as e:
            print(f"[ERROR] Trading loop: {e}")
        
        # Wait 5 minutes between scans
        print(f"\n  Next scan in 5 minutes...")
        await asyncio.sleep(300)


def main():
    db.init_db()
    
    # Start dashboard in background thread
    dash_thread = threading.Thread(target=run_dashboard_thread, daemon=True)
    dash_thread.start()
    print(f"  Dashboard started on http://localhost:{DASHBOARD_PORT}")
    
    # Run trading loop
    asyncio.run(trading_loop())


if __name__ == "__main__":
    main()