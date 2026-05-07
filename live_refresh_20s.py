"""
Live refresh every 20 seconds with bet options.
Run: python live_refresh_20s.py
"""
import subprocess
import time
import sys

if __name__ == "__main__":
    print("Starting 20-second auto-refresh loop...\n")
    count = 0
    try:
        while True:
            count += 1
            print(f"\n{'='*60}")
            print(f"REFRESH #{count} | {time.strftime('%H:%M:%S')}")
            print(f"{'='*60}\n")

            # Run analysis
            subprocess.run([
                sys.executable,
                "analyze_now.py"
            ], cwd="C:/Users/saini/Desktop/iplclaude/cricket-trading-system")

            print(f"\n[Next refresh in 20 seconds... press Ctrl+C to stop]\n")
            time.sleep(20)

    except KeyboardInterrupt:
        print("\n\nAuto-refresh stopped.")
        sys.exit(0)
