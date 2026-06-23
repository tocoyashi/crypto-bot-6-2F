import os
import ssl
import pandas as pd
import ta
import ccxt
from datetime import datetime, timedelta

ssl._create_default_https_context = ssl._create_unverified_context

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "TRX/USDT", "AVAX/USDT", "LINK/USDT",
    "DOT/USDT", "POL/USDT", "SHIB/USDT", "LTC/USDT", "UNI/USDT",
    "ATOM/USDT", "XLM/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT"
]

def get_decimals(price):
    if price > 100: return 2
    elif price > 1: return 3
    elif price > 0.01: return 5
    else: return 8

def run_backtest():
    exchange = ccxt.mexc()
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=90)).isoformat())
    
    total_trades = 0
    tp1_hits = 0
    tp2_hits = 0
    tp3_hits = 0
    tp4_hits = 0
    real_losses = 0
    be_sl_hits = 0
    total_profit_pct = 0
    trade_log = []

    print(f"Fetching 3 months of data for {len(SYMBOLS)} coins...")

    for symbol in SYMBOLS:
        try:
            ohlcv_15m = exchange.fetch_ohlcv(symbol, "15m", since=since, limit=1000)
            ohlcv_1h = exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
            
            df_15m = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            if len(df_15m) < 100 or len(df_1h) < 100: continue

            df_15m['ema_9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
            df_15m['ema_21'] = df_15m['close'].ewm(span=21, adjust=False).mean()
            macd_hist_15m = ta.trend.macd_diff(df_15m['close'])
            df_15m['macd'] = macd_hist_15m

            df_1h['ema_9'] = df_1h['close'].ewm(span=9, adjust=False).mean()
            df_1h['ema_21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
            macd_hist_1h = ta.trend.macd_diff(df_1h['close'])
            df_1h['macd'] = macd_hist_1h

            df_1h.index = pd.to_datetime(df_1h['timestamp'], unit='ms')
            df_15m.index = pd.to_datetime(df_15m['timestamp'], unit='ms')
            df_1h_aligned = df_1h.resample('15min').ffill()
            df_15m = df_15m.join(df_1h_aligned, rsuffix='_1h', how='left').ffill()

            for i in range(100, len(df_15m) - 96): 
                curr_close = df_15m['close'].iloc[i]
                dec = get_decimals(curr_close)

                # 1. Check 1H Trend
                trend_1h_long = (df_15m['ema_9_1h'].iloc[i] > df_15m['ema_21_1h'].iloc[i])
                trend_1h_short = (df_15m['ema_9_1h'].iloc[i] < df_15m['ema_21_1h'].iloc[i])

                # 2. Check 15m Trigger
                trig_buy_15m = (df_15m['ema_9'].iloc[i-1] < df_15m['ema_21'].iloc[i-1]) and (df_15m['ema_9'].iloc[i] > df_15m['ema_21'].iloc[i])
                trig_sell_15m = (df_15m['ema_9'].iloc[i-1] > df_15m['ema_21'].iloc[i-1]) and (df_15m['ema_9'].iloc[i] < df_15m['ema_21'].iloc[i])
                macd_buy_15m = (df_15m['macd'].iloc[i-1] < 0) and (df_15m['macd'].iloc[i] > 0)
                macd_sell_15m = (df_15m['macd'].iloc[i-1] > 0) and (df_15m['macd'].iloc[i] < 0)

                direction = None
                if trend_1h_long and (trig_buy_15m or macd_buy_15m): direction = "LONG"
                elif trend_1h_short and (trig_sell_15m or macd_sell_15m): direction = "SHORT"

                if not direction: continue

                # Calculate Levels
                if direction == "LONG":
                    tp1, tp2, tp3, tp4 = round(curr_close * 1.0105, dec), round(curr_close * 1.025, dec), round(curr_close * 1.04, dec), round(curr_close * 1.065, dec)
                    sl = round(curr_close * 0.96, dec)
                    be_sl = round(curr_close * 1.0025, dec)
                else:
                    tp1, tp2, tp3, tp4 = round(curr_close * 0.9895, dec), round(curr_close * 0.975, dec), round(curr_close * 0.96, dec), round(curr_close * 0.935, dec)
                    sl = round(curr_close * 1.04, dec)
                    be_sl = round(curr_close * 0.9975, dec)

                future_candles = df_15m.iloc[i+1 : i+97]
                if len(future_candles) < 10: continue

                state = 0 # 0 = Waiting for TP1, 1 = Waiting for TP2/3/4 or BE_SL
                outcome = ""
                final_pnl = 0.0

                for index, row in future_candles.iterrows():
                    if direction == "LONG":
                        if state == 0:
                            if row['high'] >= tp1:
                                state = 1
                                final_pnl += 1.05
                                continue
                            if row['low'] <= sl:
                                outcome = "SL Hit (Before TP1)"
                                final_pnl -= 4.0
                                break
                        elif state == 1:
                            if row['high'] >= tp2:
                                outcome = "TP2 Hit"
                                final_pnl += 1.45
                                break
                            if row['high'] >= tp3:
                                outcome = "TP3 Hit"
                                final_pnl += 3.0
                                break
                            if row['high'] >= tp4:
                                outcome = "TP4 Hit"
                                final_pnl += 5.45
                                break
                            if row['low'] <= be_sl:
                                outcome = "BE SL Hit"
                                final_pnl -= 0.25
                                break
                                
                    elif direction == "SHORT":
                        if state == 0:
                            if row['low'] <= tp1:
                                state = 1
                                final_pnl += 1.05
                                continue
                            if row['high'] >= sl:
                                outcome = "SL Hit (Before TP1)"
                                final_pnl -= 4.0
                                break
                        elif state == 1:
                            if row['low'] <= tp2:
                                outcome = "TP2 Hit"
                                final_pnl += 1.45
                                break
                            if row['low'] <= tp3:
                                outcome = "TP3 Hit"
                                final_pnl += 3.0
                                break
                            if row['low'] <= tp4:
                                outcome = "TP4 Hit"
                                final_pnl += 5.45
                                break
                            if row['high'] >= be_sl:
                                outcome = "BE SL Hit"
                                final_pnl -= 0.25
                                break

                if outcome == "": 
                    outcome = "TIMEOUT"
                    final_pnl -= 0.5 if state == 0 else 0.0

                total_trades += 1
                total_profit_pct += final_pnl
                
                if "TP1" in outcome: tp1_hits += 1
                if "TP2" in outcome: tp2_hits += 1
                if "TP3" in outcome: tp3_hits += 1
                if "TP4" in outcome: tp4_hits += 1
                if "SL Hit (Before TP1)" in outcome: real_losses += 1
                if "BE SL Hit" in outcome: be_sl_hits += 1

                log_emoji = "🟢" if final_pnl > 0 else "🔴"
                trade_log.append(f"{log_emoji} {outcome:20s} | {symbol:10s} | {direction:5s} | PnL: {final_pnl:+.2f}%")

        except Exception as e:
            pass 

    print("\n" + "="*60)
    print("📊 ADVANCED BACKTEST REPORT (LAST 3 MONTHS)")
    print("="*60)
    print(f"Total Signals Found: {total_trades}")
    print("-" * 60)
    print(f"✅ Hit TP1 (Moved to Breakeven): {tp1_hits} ({(tp1_hits/total_trades)*100:.1f}%)")
    print(f"📈 Hit TP2: {tp2_hits}")
    print(f"🚀 Hit TP3: {tp3_hits}")
    print(f"🏆 Hit TP4 (Full Target): {tp4_hits}")
    print("-" * 60)
    print(f"❌ Real Losses (SL before TP1): {real_losses}")
    print(f"🛑 BE Stop Losses (After TP1): {be_sl_hits}")
    print("="*60)
    print(f"Net Profit (Simulated): {total_profit_pct:.2f}%")
    print("="*60)
    print("Recent Trade Log:")
    for log in trade_log[-15:]:
        print(log)
    print("="*60)

if __name__ == "__main__":
    run_backtest()