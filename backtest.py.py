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
    wins = 0
    losses = 0
    total_profit_pct = 0
    trade_log = []

    print(f"Fetching 3 months of data for {len(SYMBOLS)} coins... This might take a minute.")

    for symbol in SYMBOLS:
        try:
            # Fetch data
            ohlcv_15m = exchange.fetch_ohlcv(symbol, "15m", since=since, limit=1000)
            ohlcv_1h = exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
            
            df_15m = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            if len(df_15m) < 100 or len(df_1h) < 100: continue

            # Indicators for 15m
            df_15m['ema_9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
            df_15m['ema_21'] = df_15m['close'].ewm(span=21, adjust=False).mean()
            macd_hist_15m = ta.trend.macd_diff(df_15m['close'])
            df_15m['macd'] = macd_hist_15m

            # Indicators for 1h
            df_1h['ema_9'] = df_1h['close'].ewm(span=9, adjust=False).mean()
            df_1h['ema_21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
            macd_hist_1h = ta.trend.macd_diff(df_1h['close'])
            df_1h['macd'] = macd_hist_1h

            # Align 1h signals to 15m dataframe
            df_1h.index = pd.to_datetime(df_1h['timestamp'], unit='ms')
            df_15m.index = pd.to_datetime(df_15m['timestamp'], unit='ms')
            df_1h_aligned = df_1h.resample('15min').ffill()
            df_15m = df_15m.join(df_1h_aligned, rsuffix='_1h', how='left').fillna(method='ffill')

            # Loop through 15m data
            for i in range(100, len(df_15m) - 25): # Leave 25 candles (6 hours) to check outcome
                curr_close = df_15m['close'].iloc[i]
                dec = get_decimals(curr_close)

                # Check EMA Dual-TF
                ema_buy_15 = (df_15m['ema_9'].iloc[i-1] < df_15m['ema_21'].iloc[i-1]) and (df_15m['ema_9'].iloc[i] > df_15m['ema_21'].iloc[i])
                ema_sell_15 = (df_15m['ema_9'].iloc[i-1] > df_15m['ema_21'].iloc[i-1]) and (df_15m['ema_9'].iloc[i] < df_15m['ema_21'].iloc[i])
                ema_buy_1h = (df_15m['ema_9_1h'].iloc[i-1] < df_15m['ema_21_1h'].iloc[i-1]) and (df_15m['ema_9_1h'].iloc[i] > df_15m['ema_21_1h'].iloc[i])
                ema_sell_1h = (df_15m['ema_9_1h'].iloc[i-1] > df_15m['ema_21_1h'].iloc[i-1]) and (df_15m['ema_9_1h'].iloc[i] < df_15m['ema_21_1h'].iloc[i])

                # Check MACD Dual-TF
                macd_buy_15 = (df_15m['macd'].iloc[i-1] < 0) and (df_15m['macd'].iloc[i] > 0)
                macd_sell_15 = (df_15m['macd'].iloc[i-1] > 0) and (df_15m['macd'].iloc[i] < 0)
                macd_buy_1h = (df_15m['macd_1h'].iloc[i-1] < 0) and (df_15m['macd_1h'].iloc[i] > 0)
                macd_sell_1h = (df_15m['macd_1h'].iloc[i-1] > 0) and (df_15m['macd_1h'].iloc[i] < 0)

                direction = None
                if (ema_buy_15 and ema_buy_1h) or (macd_buy_15 and macd_buy_1h):
                    direction = "LONG"
                elif (ema_sell_15 and ema_sell_1h) or (macd_sell_15 and macd_sell_1h):
                    direction = "SHORT"

                if direction:
                    # Calculate Levels
                    tp4 = round(curr_close * 1.065, dec) if direction == "LONG" else round(curr_close * 0.935, dec)
                    sl = round(curr_close * 0.96, dec) if direction == "LONG" else round(curr_close * 1.04, dec)

                    # Look ahead up to 25 candles (6 hours) to see outcome
                    future_candles = df_15m.iloc[i+1 : i+26]
                    if len(future_candles) < 5: continue

                    hit_tp = False
                    hit_sl = False

                    for index, row in future_candles.iterrows():
                        if direction == "LONG":
                            if row['high'] >= tp4: hit_tp = True; break
                            if row['low'] <= sl: hit_sl = True; break
                        elif direction == "SHORT":
                            if row['low'] <= tp4: hit_tp = True; break
                            if row['high'] >= sl: hit_sl = True; break

                    total_trades += 1
                    if hit_tp:
                        wins += 1
                        total_profit_pct += 6.5
                        trade_log.append(f"✅ WIN  | {symbol} | {direction} | Entry: {curr_close} | TP4 Hit")
                    elif hit_sl:
                        losses += 1
                        total_profit_pct -= 4.0
                        trade_log.append(f"❌ LOSS | {symbol} | {direction} | Entry: {curr_close} | SL Hit")
                    else:
                        # Timeout (No TP4, No SL in 6 hours) - Count as small loss/scratch
                        losses += 1
                        total_profit_pct -= 0.5
                        trade_log.append(f"⏳ TIMEOUT| {symbol} | {direction} | Entry: {curr_close}")

        except Exception as e:
            print(f"Error processing {symbol}: {e}")

    # Print Final Report
    print("\n" + "="*50)
    print("📊 BACKTEST REPORT (LAST 3 MONTHS)")
    print("="*50)
    print(f"Total Signals Found: {total_trades}")
    print(f"Wins (Hit TP4): {wins}")
    print(f"Losses (Hit SL/Timeout): {losses}")
    if total_trades > 0:
        win_rate = (wins / total_trades) * 100
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Net Profit (Simulated): {total_profit_pct:.2f}% (Assuming 15x Leverage, this would be x15)")
    print("\nRecent Trade Log:")
    for log in trade_log[-10:]:
        print(log)
    print("="*50)

if __name__ == "__main__":
    run_backtest()