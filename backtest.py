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
    "ATOM/USDT", "XLM/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT",
    "ARB/USDT", "OP/USDT", "INJ/USDT", "TIA/USDT", "FIL/USDT",
    "AAVE/USDT", "GRT/USDT", "FET/USDT", "PEPE/USDT", "FLOKI/USDT"
]

# ✨ Updated Targets
TP1_PCT = 1.0105  # 1.05%
TP2_PCT = 1.025   # 2.5%
TP3_PCT = 1.030   # 3.0%
TP4_PCT = 1.040   # 4.0%
SL_PCT = 0.96     # -4.0%
BE_SL_PCT = 1.0025 # +0.25%

# ✨ Position Sizing (What % of the position to close at each target)
CLOSE_TP1 = 0.50 # 50%
CLOSE_TP2 = 0.25 # 25%
CLOSE_TP3 = 0.20 # 20%
CLOSE_TP4 = 0.05 # 5%

# ✨ Fees (MEXC standard is 0.1% per trade execution)
ENTRY_FEE = -0.10
CLOSE_FEE = -0.10

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
    
    last_signal_time = {}

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
                curr_time = df_15m.index[i]
                dec = get_decimals(curr_close)

                trend_1h_long = (df_15m['ema_9_1h'].iloc[i] > df_15m['ema_21_1h'].iloc[i])
                trend_1h_short = (df_15m['ema_9_1h'].iloc[i] < df_15m['ema_21_1h'].iloc[i])

                trig_buy_15m = (df_15m['ema_9'].iloc[i-1] < df_15m['ema_21'].iloc[i-1]) and (df_15m['ema_9'].iloc[i] > df_15m['ema_21'].iloc[i])
                trig_sell_15m = (df_15m['ema_9'].iloc[i-1] > df_15m['ema_21'].iloc[i-1]) and (df_15m['ema_9'].iloc[i] < df_15m['ema_21'].iloc[i])
                macd_buy_15m = (df_15m['macd'].iloc[i-1] < 0) and (df_15m['macd'].iloc[i] > 0)
                macd_sell_15m = (df_15m['macd'].iloc[i-1] > 0) and (df_15m['macd'].iloc[i] < 0)

                direction = None
                if trend_1h_long and (trig_buy_15m or macd_buy_15m): direction = "LONG"
                elif trend_1h_short and (trig_sell_15m or macd_sell_15m): direction = "SHORT"

                if not direction: continue

                if symbol in last_signal_time:
                    time_since_last = curr_time - last_signal_time[symbol]
                    if time_since_last < timedelta(hours=24):
                        continue

                # Calculate Exact Levels
                if direction == "LONG":
                    tp1 = round(curr_close * TP1_PCT, dec)
                    tp2 = round(curr_close * TP2_PCT, dec)
                    tp3 = round(curr_close * TP3_PCT, dec)
                    tp4 = round(curr_close * TP4_PCT, dec)
                    sl = round(curr_close * SL_PCT, dec)
                    be_sl = round(curr_close * BE_SL_PCT, dec)
                    tp1_raw, tp2_raw, tp3_raw, tp4_raw, sl_raw, be_raw = 1.05, 2.5, 3.0, 4.0, -4.0, 0.25
                else:
                    tp1 = round(curr_close * (2 - TP1_PCT), dec)
                    tp2 = round(curr_close * (2 - TP2_PCT), dec)
                    tp3 = round(curr_close * (2 - TP3_PCT), dec)
                    tp4 = round(curr_close * (2 - TP4_PCT), dec)
                    sl = round(curr_close * (2 - SL_PCT), dec)
                    be_sl = round(curr_close * (2 - BE_SL_PCT), dec)
                    tp1_raw, tp2_raw, tp3_raw, tp4_raw, sl_raw, be_raw = 1.05, 2.5, 3.0, 4.0, -4.0, 0.25

                last_signal_time[symbol] = curr_time

                future_candles = df_15m.iloc[i+1 : i+97]
                if len(future_candles) < 10: continue

                state = 0 
                outcome = ""
                final_pnl = ENTRY_FEE # Start with entry fee (-0.10%)

                for index, row in future_candles.iterrows():
                    if direction == "LONG":
                        if state == 0:
                            if row['high'] >= tp1:
                                # TP1 Hit: Calculate 50% close profit minus fee
                                final_pnl += (CLOSE_TP1 * tp1_raw) + (CLOSE_TP1 * CLOSE_FEE)
                                state = 1
                                continue
                            if row['low'] <= sl:
                                outcome = "SL Hit (Before TP1)"
                                final_pnl += sl_raw + CLOSE_FEE # Full loss + close fee
                                break
                        elif state == 1:
                            if row['high'] >= tp2:
                                outcome = "TP2 Hit"
                                final_pnl += (CLOSE_TP2 * tp2_raw) + (CLOSE_TP2 * CLOSE_FEE)
                                break
                            if row['high'] >= tp3:
                                outcome = "TP3 Hit"
                                final_pnl += (CLOSE_TP3 * tp3_raw) + (CLOSE_TP3 * CLOSE_FEE)
                                break
                            if row['high'] >= tp4:
                                outcome = "TP4 Hit"
                                final_pnl += (CLOSE_TP4 * tp4_raw) + (CLOSE_TP4 * CLOSE_FEE)
                                break
                            if row['low'] <= be_sl:
                                outcome = "BE SL Hit"
                                remaining_pos = 1.0 - CLOSE_TP1
                                final_pnl += (remaining_pos * be_raw) + (remaining_pos * CLOSE_FEE)
                                break
                                
                    elif direction == "SHORT":
                        if state == 0:
                            if row['low'] <= tp1:
                                final_pnl += (CLOSE_TP1 * tp1_raw) + (CLOSE_TP1 * CLOSE_FEE)
                                state = 1
                                continue
                            if row['high'] >= sl:
                                outcome = "SL Hit (Before TP1)"
                                final_pnl += sl_raw + CLOSE_FEE
                                break
                        elif state == 1:
                            if row['low'] <= tp2:
                                outcome = "TP2 Hit"
                                final_pnl += (CLOSE_TP2 * tp2_raw) + (CLOSE_TP2 * CLOSE_FEE)
                                break
                            if row['low'] <= tp3:
                                outcome = "TP3 Hit"
                                final_pnl += (CLOSE_TP3 * tp3_raw) + (CLOSE_TP3 * CLOSE_FEE)
                                break
                            if row['low'] <= tp4:
                                outcome = "TP4 Hit"
                                final_pnl += (CLOSE_TP4 * tp4_raw) + (CLOSE_TP4 * CLOSE_FEE)
                                break
                            if row['high'] >= be_sl:
                                outcome = "BE SL Hit"
                                remaining_pos = 1.0 - CLOSE_TP1
                                final_pnl += (remaining_pos * be_raw) + (remaining_pos * CLOSE_FEE)
                                break

                if outcome == "": 
                    outcome = "TIMEOUT"
                    final_pnl += -0.5 if state == 0 else 0.0 # Scratch if before TP1, 0 if after TP1

                total_trades += 1
                total_profit_pct += final_pnl
                
                if "TP1" in outcome: tp1_hits += 1
                if "TP2" in outcome: tp2_hits += 1
                if "TP3" in outcome: tp3_hits += 1
                if "TP4" in outcome: tp4_hits += 1
                if "SL Hit (Before TP1)" in outcome: real_losses += 1
                if "BE SL Hit" in outcome: be_sl_hits += 1

                log_emoji = "🟢" if final_pnl > 0 else "🔴"
                trade_log.append(f"{log_emoji} {outcome:20s} | {symbol:10s} | {direction:5s} | Net PnL: {final_pnl:+.2f}%")

        except Exception as e:
            pass 

    print("\n" + "="*60)
    print("📊 BACKTEST REPORT (PARTIAL CLOSES & FEES INCLUDED)")
    print("="*60)
    print(f"Total Clean Signals: {total_trades}")
    print("-" * 60)
    print(f"✅ Hit TP1 (Close 50%): {tp1_hits} ({(tp1_hits/total_trades)*100:.1f}%)")
    print(f"📈 Hit TP2 (Close 25%): {tp2_hits}")
    print(f"🚀 Hit TP3 (Close 20%): {tp3_hits}")
    print(f"🏆 Hit TP4 (Close 5%):  {tp4_hits}")
    print("-" * 60)
    print(f"❌ Real Losses (SL before TP1): {real_losses}")
    print(f"🛑 BE Stop Losses (After TP1): {be_sl_hits}")
    print("="*60)
    print(f"Net Profit AFTER FEES: {total_profit_pct:.2f}%")
    print("="*60)
    print("Recent Trade Log:")
    for log in trade_log[-15:]:
        print(log)
    print("="*60)

if __name__ == "__main__":
    run_backtest()