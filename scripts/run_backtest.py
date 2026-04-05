#!/usr/bin/env python3
"""
Run backtesting on IPL data and print a full performance report.

Usage:
    python run_backtest.py                    # Synthetic data
    python run_backtest.py --data ipl.csv     # Real CSV
    python run_backtest.py --matches 200      # More matches
"""
import sys, os, argparse, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backtesting.backtester import Backtester, IPLDataLoader


def print_report(result):
    SEP = "─" * 52

    print(f"\n{'='*52}")
    print(f"  CRICKET TRADING SYSTEM — BACKTEST REPORT")
    print(f"{'='*52}\n")

    print(f"  PERFORMANCE SUMMARY")
    print(f"  {SEP}")
    print(f"  Total Trades     : {result.total_trades}")
    print(f"  Winning Trades   : {result.winning_trades}  ({result.win_rate*100:.1f}%)")
    print(f"  Losing Trades    : {result.losing_trades}")
    print(f"  Total P&L        : ₹{result.total_pnl:,.2f}")
    print(f"  ROI              : {result.roi_pct:.2f}%")
    print(f"  Max Drawdown     : ₹{result.max_drawdown:,.2f}")
    print(f"  Sharpe Ratio     : {result.sharpe_ratio:.4f}")

    print(f"\n  SIGNAL BREAKDOWN")
    print(f"  {SEP}")
    for sig, count in result.signal_breakdown.items():
        pct = count / max(result.total_trades, 1) * 100
        bar = '█' * int(pct / 5)
        print(f"  {sig:<12} {count:>4}  {bar:<20}  {pct:.1f}%")

    print(f"\n  EQUITY CURVE (sampled)")
    print(f"  {SEP}")
    curve = result.equity_curve
    step = max(1, len(curve) // 10)
    for i in range(0, len(curve), step):
        pnl = curve[i]
        bar = ('▓' if pnl >= 0 else '░') * int(abs(pnl) / max(abs(max(curve, key=abs)), 1) * 20)
        print(f"  [{i:>4}] ₹{pnl:>10,.2f}  {bar}")

    if result.trades:
        print(f"\n  SAMPLE TRADES (first 5)")
        print(f"  {SEP}")
        for t in result.trades[:5]:
            arrow = '▲' if t.pnl >= 0 else '▼'
            print(f"  {arrow} {t.signal:<10}  Over {t.over:.1f}  "
                  f"Conf {t.confidence*100:.0f}%  "
                  f"P&L ₹{t.pnl:>8.2f}  "
                  f"WP {t.win_probability*100:.0f}%")

    print(f"\n{'='*52}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, help='Path to IPL CSV file')
    parser.add_argument('--matches', type=int, default=100, help='Synthetic match count')
    parser.add_argument('--stake', type=float, default=1000.0, help='Stake per trade')
    parser.add_argument('--output', type=str, help='Save result JSON to file')
    args = parser.parse_args()

    loader = IPLDataLoader()

    if args.data:
        print(f"Loading data from {args.data}...")
        df = loader.load_csv(args.data)
    else:
        print(f"Generating {args.matches} synthetic IPL matches...")
        df = loader.generate_synthetic_data(n_matches=args.matches)

    print(f"Loaded {len(df):,} ball records across {df['match_id'].nunique()} matches\n")

    bt = Backtester(stake=args.stake)
    result = bt.run(df)

    print_report(result)

    if args.output:
        out = {
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'total_pnl': result.total_pnl,
            'roi_pct': result.roi_pct,
            'max_drawdown': result.max_drawdown,
            'sharpe_ratio': result.sharpe_ratio,
            'signal_breakdown': result.signal_breakdown,
            'equity_curve': result.equity_curve[-50:],
        }
        with open(args.output, 'w') as f:
            json.dump(out, f, indent=2)
        print(f"Result saved to {args.output}")


if __name__ == '__main__':
    main()
