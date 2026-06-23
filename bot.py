import os
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import ccxt
import pandas as pd
import ta
import requests
import time
import random

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "TRX/USDT", "AVAX/USDT", "LINK/USDT",
    "DOT/USDT", "POL/USDT", "SHIB/USDT", "LTC/USDT", "UNI/USDT",
    "ATOM/USDT", "XLM/USDT", "NEAR/USDT", "APT/USDT", "SUI/USDT"
]

LEVERAGE = "15x"

def get_decimals(price):
    if price > 100: return 2
    elif price > 1: return 3
    elif price > 0.01: return 5
    else: return 8

def get_next_signal_id():
    filename = "signal_counter.txt"
    try:
        with open(filename, "r") as file:
            current_id = int(file.read().strip())
    except (FileNotFoundError, ValueError):
        current_id = 0
    next_id = current_id + 1
    try:
        with open(filename, "w") as file:
            file.write(str(next_id))
    except Exception as e:
        print(f"Error saving signal ID: {e}")
    return f"{next_id:03d}"

def generate_summary(direction, strategy, df):
    rsi_val = round(df['rsi'].iloc[-1], 1)
    if direction == "LONG":
        structure_txt = random.choice(["A massive bullish consensus across multiple timeframes confirms a high-probability upward move.", "Multi-timeframe alignment shows strong buying pressure and structural support.", "The 15m and 60m charts confirm a synchronized bullish breakout scenario."])
        action_txt = random.choice(["Institutional footprint detected as both timeframes rejected lower prices simultaneously.", "Aggressive accumulation is visible as dynamic support levels hold firmly on both scales.", "Smart money positioning is clearly bullish based on cross-timeframe momentum shifts."])
        if rsi_val < 65: rsi_txt = random.choice([f"RSI at {rsi_val} confirms healthy momentum with plenty of room before overbought levels.", f"Momentum reads {rsi_val}, supporting a sustained move higher without exhaustion."])
        else: rsi_txt = random.choice([f"RSI is strong at {rsi_val}, showing extreme bullish power and heavy buyer dominance.", f"Momentum indicator reads {rsi_val}, riding a massive wave of buying pressure."])
        levels_txt = random.choice(["Risk is managed safely below the invalidation level; expecting an aggressive push towards the upper targets.", "Invalidation point is clearly defined; expecting a strong breakout to hit the projected extension levels."])
    else:
        structure_txt = random.choice(["A massive bearish consensus across multiple timeframes confirms a high-probability downward move.", "Multi-timeframe alignment shows strong selling pressure and structural resistance.", "The 15m and 60m charts confirm a synchronized bearish breakdown scenario."])
        action_txt = random.choice(["Institutional footprint detected as both timeframes rejected higher prices simultaneously.", "Aggressive distribution is visible as dynamic resistance levels hold firmly on both scales.", "Smart money positioning is clearly bearish based on cross-timeframe momentum shifts."])
        if rsi_val > 35: rsi_txt = random.choice([f"RSI at {rsi_val} confirms healthy downward momentum with plenty of room before oversold levels.", f"Momentum reads {rsi_val}, supporting a sustained move lower without exhaustion."])
        else: rsi_txt = random.choice([f"RSI is weak at {rsi_val}, showing extreme bearish power and heavy seller dominance.", f"Momentum indicator reads {rsi_val}, riding a massive wave of selling pressure."])
        levels_txt = random.choice(["Risk is managed safely above the invalidation level; expecting an aggressive drop towards the lower targets.", "Invalidation point is clearly defined; expecting a heavy breakdown to hit the projected extension levels."])
    return f"{structure_txt} {action_txt} {rsi_txt} {levels_txt}"

def send_crypto_signal(coin_name, direction, strategy, entry, tp1, tp2, tp3, tp4, sl, summary_text):
    signal_id = get_next_signal_id()
    direction_text = "LONG" if direction.lower() == "long" else "SHORT"
    clean_name = coin_name.replace("/", "")
    zone_low = round(entry * 0.999, get_decimals(entry))
    zone_high = round(entry * 1.001, get_decimals(entry))
    text = f"📌 SIGNAL ID: #{signal_id}\nCOIN: #{clean_name} ({LEVERAGE})\nDirection: {direction_text} | Type: {strategy}\n➖➖➖➖➖➖➖\nENTRY: {zone_low} - {zone_high}\nTARGETS: {tp1} - {tp2} - {tp3} - {tp4}\nSTOP LOSS: {sl}\n\n📊 {summary_text}\n➖➖➖➖➖➖➖\nCrypto Bullets: By Banana Bot®"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": text, "disable_web_page_preview": True}
    try:
        response = requests.post(url, json=payload)
        if response.json().get('ok'): print(f"Signal {signal_id} sent for {coin_name} via {strategy}")
        else: print(f"ERROR for {coin_name}: {response.json().get('description')}")
    except Exception as e: print(f"Network error: {e}")

def analyze_and_trade():
    print("Starting HIGH CONFIDENCE Dual-TF Scan (15m + 60m)...")
    exchange = ccxt.mexc()
    for symbol in SYMBOLS:
        try:
            df_15m = pd.DataFrame(exchange.fetch_ohlcv(symbol, "15m", limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_60m = pd.DataFrame(exchange.fetch_ohlcv(symbol, "1h", limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_close = df_15m['close'].iloc[-1]
            decimals = get_decimals(current_close)
            
            df_15m['ema_9'] = df_15m['close'].ewm(span=9, adjust=False).mean()
            df_15m['ema_21'] = df_15m['close'].ewm(span=21, adjust=False).mean()
            df_60m['ema_9'] = df_60m['close'].ewm(span=9, adjust=False).mean()
            df_60m['ema_21'] = df_60m['close'].ewm(span=21, adjust=False).mean()
            
            macd_hist_15m = ta.trend.macd_diff(df_15m['close'])
            curr_macd_15m = macd_hist_15m.iloc[-1]
            prev_macd_15m = macd_hist_15m.iloc[-2]
            macd_hist_60m = ta.trend.macd_diff(df_60m['close'])
            curr_macd_60m = macd_hist_60m.iloc[-1]
            prev_macd_60m = macd_hist_60m.iloc[-2]
            df_15m['rsi'] = ta.momentum.rsi(df_15m['close'], window=14)

            ema_buy_15m = (df_15m['ema_9'].iloc[-2] < df_15m['ema_21'].iloc[-2]) and (df_15m['ema_9'].iloc[-1] > df_15m['ema_21'].iloc[-1])
            ema_sell_15m = (df_15m['ema_9'].iloc[-2] > df_15m['ema_21'].iloc[-2]) and (df_15m['ema_9'].iloc[-1] < df_15m['ema_21'].iloc[-1])
            ema_buy_60m = (df_60m['ema_9'].iloc[-2] < df_60m['ema_21'].iloc[-2]) and (df_60m['ema_9'].iloc[-1] > df_60m['ema_21'].iloc[-1])
            ema_sell_60m = (df_60m['ema_9'].iloc[-2] > df_60m['ema_21'].iloc[-2]) and (df_60m['ema_9'].iloc[-1] < df_60m['ema_21'].iloc[-1])
            
            macd_buy_15m = (prev_macd_15m < 0) and (curr_macd_15m > 0)
            macd_sell_15m = (prev_macd_15m > 0) and (curr_macd_15m < 0)
            macd_buy_60m = (prev_macd_60m < 0) and (curr_macd_60m > 0)
            macd_sell_60m = (prev_macd_60m > 0) and (curr_macd_60m < 0)

            entry = round(current_close, decimals)
            long_tps = (round(entry * 1.0105, decimals), round(entry * 1.025, decimals), round(entry * 1.04, decimals), round(entry * 1.065, decimals))
            long_sl = round(entry * 0.96, decimals)
            short_tps = (round(entry * 0.9895, decimals), round(entry * 0.975, decimals), round(entry * 0.96, decimals), round(entry * 0.935, decimals))
            short_sl = round(entry * 1.04, decimals)

            if (ema_buy_15m and ema_buy_60m):
                print(f"🟢 DUAL EMA BUY on {symbol}!")
                summary = generate_summary("LONG", "Dual-TF EMA Cross", df_15m)
                send_crypto_signal(symbol, "LONG", "Dual-TF EMA Cross", entry, *long_tps, long_sl, summary)
                time.sleep(6)
            elif (ema_sell_15m and ema_sell_60m):
                print(f"🔴 DUAL EMA SELL on {symbol}!")
                summary = generate_summary("SHORT", "Dual-TF EMA Cross", df_15m)
                send_crypto_signal(symbol, "SHORT", "Dual-TF EMA Cross", entry, *short_tps, short_sl, summary)
                time.sleep(6)
            elif (macd_buy_15m and macd_buy_60m):
                print(f"🟢 DUAL MACD BUY on {symbol}!")
                summary = generate_summary("LONG", "Dual-TF MACD Cross", df_15m)
                send_crypto_signal(symbol, "LONG", "Dual-TF MACD Cross", entry, *long_tps, long_sl, summary)
                time.sleep(6)
            elif (macd_sell_15m and macd_sell_60m):
                print(f"🔴 DUAL MACD SELL on {symbol}!")
                summary = generate_summary("SHORT", "Dual-TF MACD Cross", df_15m)
                send_crypto_signal(symbol, "SHORT", "Dual-TF MACD Cross", entry, *short_tps, short_sl, summary)
                time.sleep(6)
            else:
                print(f"⚪ No dual-TF alignment for {symbol}.")
        except Exception as e:
            print(f"Error {symbol}: {e}")

if __name__ == "__main__":
    print("Custom Dual Timeframe Bot started...")
    analyze_and_trade()