import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import ccxt
import pandas as pd
import ta
from datetime import datetime, timedelta, timezone

TIMEFRAME = "1h"

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "TRX/USDT", "AVAX/USDT", "LINK/USDT",
    "POL/USDT", "LTC/USDT", "UNI/USDT",
    "ATOM/USDT", "XLM/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT",
    "INJ/USDT", "ARB/USDT", "OP/USDT", "FIL/USDT", "AAVE/USDT",
    "PEPE/USDT", "FET/USDT"
]

LEVERAGE = 3
FEE_PER_SIDE = 0.3  # 0.3% per side (0.1% x 3x)

CLOSE_TP1 = 0.40
CLOSE_TP2 = 0.30
CLOSE_TP3 = 0.20
CLOSE_TP4 = 0.10

TP1_PCT = 0.8
TP2_PCT = 1.5
TP3_PCT = 3.0
TP4_PCT = 5.0
SL_PCT = 2.0
BE_PCT = 0.15

COOLDOWN = 25
VOLUME_STRENGTH_THRESHOLD = 80

def fetch_all_ohlcv(exchange, symbol, timeframe, since):
    all_data = []
    current_since = since
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
        if not batch:
            break
        all_data.extend(batch)
        current_since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    return all_data


def run_backtest():
    exchange = ccxt.mexc()
    since = exchange.parse8601((datetime.now(timezone.utc) - timedelta(days=90)).isoformat())

    total = 0
    sl_count = 0
    be_after_tp1 = 0
    be_after_tp2 = 0
    be_after_tp3 = 0
    tp4_full = 0
    timeouts = 0

    sl_pnl = 0
    be_tp1_pnl = 0
    be_tp2_pnl = 0
    be_tp3_pnl = 0
    tp4_pnl = 0
    timeout_pnl = 0
    total_fees = 0

    strategy_stats = {
        "Swing Pullback": {"signals": 0, "wins": 0, "sl": 0, "pnl": 0},
        "Swing Volume":   {"signals": 0, "wins": 0, "sl": 0, "pnl": 0},
    }

    trade_log = []

    print(f"Fetching 3 months of 4H data for {len(SYMBOLS)} coins...")
    print(f"Strategies: Pullback + Volume + EMA Trend | Leverage: {LEVERAGE}x | SL: {SL_PCT}%")
    print(f"Volume Strength Threshold: {VOLUME_STRENGTH_THRESHOLD}+")
    print(f"Swing Trend: REMOVED")

    for symbol in SYMBOLS:
        try:
            ohlcv = fetch_all_ohlcv(exchange, symbol, TIMEFRAME, since)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            if len(df) < 220:
                continue

            df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
            df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            df['vol_sma'] = df['volume'].rolling(window=20).mean()

            last_signal_idx = -COOLDOWN - 1

            for i in range(200, len(df) - 1):
                if i - last_signal_idx < COOLDOWN:
                    continue

                cc = df['close'].iloc[i]
                co = df['open'].iloc[i]

                pullback_buy = (df['ema_50'].iloc[i] > df['ema_200'].iloc[i]) and \
                               (df['ema_21'].iloc[i] > df['ema_50'].iloc[i]) and \
                               (df['low'].iloc[i] <= df['ema_21'].iloc[i]) and \
                               (cc > df['ema_21'].iloc[i]) and (df['rsi'].iloc[i] < 60)
                pullback_sell = (df['ema_50'].iloc[i] < df['ema_200'].iloc[i]) and \
                                (df['ema_21'].iloc[i] < df['ema_50'].iloc[i]) and \
                                (df['high'].iloc[i] >= df['ema_21'].iloc[i]) and \
                                (cc < df['ema_21'].iloc[i]) and (df['rsi'].iloc[i] > 40)
                
                vol_buy = (df['volume'].iloc[i] > df['vol_sma'].iloc[i] * 2.5) and (cc > co)
                vol_sell = (df['volume'].iloc[i] > df['vol_sma'].iloc[i] * 2.5) and (cc < co)
                
                vol_ratio = df['volume'].iloc[i] / df['vol_sma'].iloc[i] if df['vol_sma'].iloc[i] > 0 else 0
                vol_strength = min(100, vol_ratio * 15 + 25)

                direction = None
                strategy = None
                
                if pullback_buy:
                    direction = "LONG"
                    strategy = "Swing Pullback"
                elif pullback_sell:
                    direction = "SHORT"
                    strategy = "Swing Pullback"
                elif vol_buy and vol_strength >= VOLUME_STRENGTH_THRESHOLD:
                    direction = "LONG"
                    strategy = "Swing Volume"
                elif vol_sell and vol_strength >= VOLUME_STRENGTH_THRESHOLD:
                    direction = "SHORT"
                    strategy = "Swing Volume"

                if not direction:
                    continue

                entry = cc
                last_signal_idx = i
                total += 1
                strategy_stats[strategy]["signals"] += 1

                if direction == "LONG":
                    tp1_l = entry * (1 + TP1_PCT/100)
                    tp2_l = entry * (1 + TP2_PCT/100)
                    tp3_l = entry * (1 + TP3_PCT/100)
                    tp4_l = entry * (1 + TP4_PCT/100)
                    sl_l  = entry * (1 - SL_PCT/100)
                    be_l  = entry * (1 + BE_PCT/100)
                else:
                    tp1_l = entry * (1 - TP1_PCT/100)
                    tp2_l = entry * (1 - TP2_PCT/100)
                    tp3_l = entry * (1 - TP3_PCT/100)
                    tp4_l = entry * (1 - TP4_PCT/100)
                    sl_l  = entry * (1 + SL_PCT/100)
                    be_l  = entry * (1 - BE_PCT/100)

                future = df.iloc[i+1:i+201]
                if len(future) < 10:
                    continue

                state = 0
                remaining = 1.0
                pnl = -FEE_PER_SIDE
                fees_paid = FEE_PER_SIDE
                outcome = ""
                hit_tp = 0

                for idx, row in future.iterrows():
                    if direction == "LONG":
                        if state == 0:
                            if row['low'] <= sl_l:
                                pnl += remaining * (-SL_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "SL"
                                break
                            if row['high'] >= tp1_l:
                                pnl += CLOSE_TP1 * (TP1_PCT * LEVERAGE) - CLOSE_TP1 * FEE_PER_SIDE
                                fees_paid += CLOSE_TP1 * FEE_PER_SIDE
                                remaining -= CLOSE_TP1
                                hit_tp = 1
                                state = 1
                                continue
                        if state == 1:
                            if row['low'] <= be_l:
                                pnl += remaining * (BE_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "BE SL (after TP1)"
                                break
                            if row['high'] >= tp2_l:
                                pnl += CLOSE_TP2 * (TP2_PCT * LEVERAGE) - CLOSE_TP2 * FEE_PER_SIDE
                                fees_paid += CLOSE_TP2 * FEE_PER_SIDE
                                remaining -= CLOSE_TP2
                                hit_tp = 2
                                state = 2
                                continue
                        if state == 2:
                            if row['low'] <= be_l:
                                pnl += remaining * (BE_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "BE SL (after TP2)"
                                break
                            if row['high'] >= tp3_l:
                                pnl += CLOSE_TP3 * (TP3_PCT * LEVERAGE) - CLOSE_TP3 * FEE_PER_SIDE
                                fees_paid += CLOSE_TP3 * FEE_PER_SIDE
                                remaining -= CLOSE_TP3
                                hit_tp = 3
                                state = 3
                                continue
                        if state == 3:
                            if row['low'] <= be_l:
                                pnl += remaining * (BE_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "BE SL (after TP3)"
                                break
                            if row['high'] >= tp4_l:
                                pnl += remaining * (TP4_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                remaining -= CLOSE_TP4
                                hit_tp = 4
                                outcome = "TP4 (All Targets)"
                                break
                    else:
                        if state == 0:
                            if row['high'] >= sl_l:
                                pnl += remaining * (-SL_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "SL"
                                break
                            if row['low'] <= tp1_l:
                                pnl += CLOSE_TP1 * (TP1_PCT * LEVERAGE) - CLOSE_TP1 * FEE_PER_SIDE
                                fees_paid += CLOSE_TP1 * FEE_PER_SIDE
                                remaining -= CLOSE_TP1
                                hit_tp = 1
                                state = 1
                                continue
                        if state == 1:
                            if row['high'] >= be_l:
                                pnl += remaining * (BE_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "BE SL (after TP1)"
                                break
                            if row['low'] <= tp2_l:
                                pnl += CLOSE_TP2 * (TP2_PCT * LEVERAGE) - CLOSE_TP2 * FEE_PER_SIDE
                                fees_paid += CLOSE_TP2 * FEE_PER_SIDE
                                remaining -= CLOSE_TP2
                                hit_tp = 2
                                state = 2
                                continue
                        if state == 2:
                            if row['high'] >= be_l:
                                pnl += remaining * (BE_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "BE SL (after TP2)"
                                break
                            if row['low'] <= tp3_l:
                                pnl += CLOSE_TP3 * (TP3_PCT * LEVERAGE) - CLOSE_TP3 * FEE_PER_SIDE
                                fees_paid += CLOSE_TP3 * FEE_PER_SIDE
                                remaining -= CLOSE_TP3
                                hit_tp = 3
                                state = 3
                                continue
                        if state == 3:
                            if row['high'] >= be_l:
                                pnl += remaining * (BE_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                outcome = "BE SL (after TP3)"
                                break
                            if row['low'] <= tp4_l:
                                pnl += remaining * (TP4_PCT * LEVERAGE) - remaining * FEE_PER_SIDE
                                fees_paid += remaining * FEE_PER_SIDE
                                remaining -= CLOSE_TP4
                                hit_tp = 4
                                outcome = "TP4 (All Targets)"
                                break

                if outcome == "":
                    last_c = future.iloc[-1]['close']
                    if direction == "LONG":
                        raw_move = ((last_c / entry) - 1) * 100
                    else:
                        raw_move = ((entry / last_c) - 1) * 100
                    if state == 0:
                        pnl += remaining * (raw_move * LEVERAGE) - remaining * FEE_PER_SIDE
                        fees_paid += remaining * FEE_PER_SIDE
                        outcome = "TIMEOUT (no TP)"
                    else:
                        pnl += remaining * (raw_move * LEVERAGE) - remaining * FEE_PER_SIDE
                        fees_paid += remaining * FEE_PER_SIDE
                        outcome = f"TIMEOUT (after TP{hit_tp})"
                    timeouts += 1
                    timeout_pnl += pnl
                    strategy_stats[strategy]["pnl"] += pnl
                    trade_log.append((outcome, symbol, direction, strategy, pnl))
                    total_fees += fees_paid
                    continue

                total_fees += fees_paid

                if outcome == "SL":
                    sl_count += 1
                    sl_pnl += pnl
                    strategy_stats[strategy]["sl"] += 1
                    strategy_stats[strategy]["pnl"] += pnl
                elif outcome.startswith("BE SL (after TP1)"):
                    be_after_tp1 += 1
                    be_tp1_pnl += pnl
                    strategy_stats[strategy]["wins"] += 1
                    strategy_stats[strategy]["pnl"] += pnl
                elif outcome.startswith("BE SL (after TP2)"):
                    be_after_tp2 += 1
                    be_tp2_pnl += pnl
                    strategy_stats[strategy]["wins"] += 1
                    strategy_stats[strategy]["pnl"] += pnl
                elif outcome.startswith("BE SL (after TP3)"):
                    be_after_tp3 += 1
                    be_tp3_pnl += pnl
                    strategy_stats[strategy]["wins"] += 1
                    strategy_stats[strategy]["pnl"] += pnl
                elif outcome == "TP4 (All Targets)":
                    tp4_full += 1
                    tp4_pnl += pnl
                    strategy_stats[strategy]["wins"] += 1
                    strategy_stats[strategy]["pnl"] += pnl
                elif outcome.startswith("TIMEOUT"):
                    timeout_pnl += pnl
                    strategy_stats[strategy]["pnl"] += pnl

                trade_log.append((outcome, symbol, direction, strategy, pnl))

        except Exception:
            pass

    net_total = sl_pnl + be_tp1_pnl + be_tp2_pnl + be_tp3_pnl + tp4_pnl + timeout_pnl
    wins = be_after_tp1 + be_after_tp2 + be_after_tp3 + tp4_full
    losses = sl_count + timeouts

    print("\n" + "=" * 75)
    print("  SWING BOT BACKTEST - PULLBACK + VOLUME ONLY (NO TREND)")
    print("  1H Timeframe | 3 Months | 25 Coins | Cooldown: 25")
    print("  TP1=0.8% TP2=1.5% TP3=3% TP4=5% | SL=2% | BE=+/-0.15% | EMA Trend | Vol 80+")
    print("  Leverage: 7x | Fees: 0.7% per side")
    print("  Volume Strength Threshold: 70+")
    print("=" * 75)

    print(f"\n  OVERVIEW")
    print(f"  {'Total Signals:':<35} {total}")
    print(f"  {'Win Rate (hit at least TP1):':<35} {wins}/{total} = {wins/total*100:.1f}%" if total else "")
    print(f"  {'SL Rate (SL before TP1):':<35} {sl_count}/{total} = {sl_count/total*100:.1f}%" if total else "")

    print(f"\n  OUTCOMES")
    print(f"  {'Outcome':<25} {'Count':<10} {'Rate':<10} {'Avg PnL':<12} {'Total PnL':<15}")
    print(f"  {'-'*72}")

    def safe_rate(c):
        return f"{c/total*100:.1f}%" if total > 0 else "-"

    rows = [
        ("SL (before TP1)",        sl_count,       sl_pnl),
        ("BE SL (after TP1)",     be_after_tp1,   be_tp1_pnl),
        ("BE SL (after TP2)",     be_after_tp2,   be_tp2_pnl),
        ("BE SL (after TP3)",     be_after_tp3,   be_tp3_pnl),
        ("TP4 (All Targets)",     tp4_full,       tp4_pnl),
        ("Timeout",               timeouts,        timeout_pnl),
    ]
    for label, cnt, accum in rows:
        avg = accum / cnt if cnt > 0 else 0
        print(f"  {label:<25} {cnt:<10} {safe_rate(cnt):<10} {avg:>+11.2f}%   {accum:>+14.2f}%")

    print(f"\n  FINANCIAL SUMMARY")
    print(f"  {'-'*50}")
    print(f"  {'Gross PnL (before fees):':<35} {net_total + total_fees:>+10.2f}%")
    print(f"  {'Total Fees Paid:':<35} {-total_fees:>+10.2f}%")
    print(f"  {'NET PROFIT:':<35} {net_total:>+10.2f}%")
    if total > 0:
        print(f"  {'Avg PnL per Signal:':<35} {net_total/total:>+10.2f}%")
    if wins > 0 and losses > 0:
        avg_win = (be_tp1_pnl + be_tp2_pnl + be_tp3_pnl + tp4_pnl) / wins
        avg_loss = (sl_pnl + timeout_pnl) / losses
        print(f"  {'Avg Winning Trade:':<35} {avg_win:>+10.2f}%")
        print(f"  {'Avg Losing Trade:':<35} {avg_loss:>+10.2f}%")
        rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        print(f"  {'Risk/Reward Ratio:':<35} 1 : {rr:.2f}")

    print(f"\n  PER-STRATEGY BREAKDOWN")
    print(f"  {'-'*65}")
    print(f"  {'Strategy':<20} {'Signals':<10} {'Win Rate':<12} {'SL Rate':<12} {'Net PnL':<12}")
    print(f"  {'-'*65}")
    for s, st in strategy_stats.items():
        if st["signals"] > 0:
            n = st["signals"]
            wr = st["wins"]/n*100 if n > 0 else 0
            sr = st["sl"]/n*100 if n > 0 else 0
            print(f"  {s:<20} {n:<10} {wr:.1f}%        {sr:.1f}%        {st['pnl']:>+10.2f}%")

    print(f"\n  POSITION BREAKDOWN PER OUTCOME")
    print(f"  {'-'*65}")
    print(f"  {'Outcome':<25} {'Closed At':<20} {'Remaining':<10} {'Net Effect':<15}")
    print(f"  {'-'*65}")
    print(f"  {'SL':<25} {'100% at -56%':<20} {'0%':<10} {'-56% - 1.4% fee':<15}")
    print(f"  {'BE SL (after TP1)':<25} {'50% at +8.4%':<20} {'50% at +1.75%':<10} {'+5.1% - 1.4% fee':<15}")
    print(f"  {'BE SL (after TP2)':<25} {'50%+25% at TP1/2':<20} {'25% at +1.75%':<10} {'+10.9% - 1.4% fee':<15}")
    print(f"  {'BE SL (after TP3)':<25} {'50%+25%+15%':<20} {'10% at +1.75%':<10} {'+17.4% - 1.4% fee':<15}")
    print(f"  {'TP4 (All Targets)':<25} {'50%+25%+15%+10%':<20} {'0%':<10} {'+22.75% - 1.4% fee':<15}")

    print(f"\n  RECENT TRADES")
    print(f"  {'-'*75}")
    for t in trade_log[-20:]:
        out, sym, d, st, pnl = t
        e = "+" if pnl > 0 else "-"
        print(f"  [{e}] {out:<22} | {sym:<12} | {d:<5} | {st:<15} | PnL: {pnl:+.2f}%")

    print("\n" + "=" * 75)


if __name__ == "__main__":
    run_backtest()
