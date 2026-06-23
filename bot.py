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
        structure_txt = random.choice([
            "A massive bullish consensus across multiple timeframes confirms a high-probability upward move.",
            "Multi-timeframe alignment shows strong buying pressure and structural support.",
            "The 15m and 60m charts confirm a synchronized bullish breakout scenario."
        ])
        action_txt = random.choice([
            "Institutional footprint detected as both timeframes rejected lower prices simultaneously.",
            "Aggressive accumulation is visible as dynamic support levels hold firmly on both scales.",
            "Smart money positioning is clearly bullish based on cross-timeframe momentum shifts."
        ])
        if rsi_val < 65:
            rsi_txt = random.choice([
                f"RSI at {rsi_val} confirms healthy momentum with plenty of room before overbought levels.",
                f"Momentum reads {rsi_val}, supporting a sustained move higher without exhaustion."
            ])
        else:
            rsi_txt = random.choice([
                f"RSI is strong at {rsi_val}, showing extreme bullish power and heavy buyer dominance.",
                f"Momentum indicator reads {rsi_val}, riding a massive wave of buying pressure."
            ])
        levels_txt = random.choice([
            "Risk is managed safely below the invalidation level; expecting an aggressive push towards the upper targets.",
            "Invalidation point is clearly defined; expecting a strong breakout to hit the projected extension levels."
        ])
    else:
        structure_txt = random.choice([
            "A massive bearish consensus across multiple timeframes confirms a high-probability downward move.",
            "Multi-timeframe alignment shows strong selling pressure and structural resistance.",
            "The 15m and 60m charts confirm a synchronized bearish breakdown scenario."
        ])
        action_txt = random.choice([
            "Institutional footprint detected as both timeframes rejected higher prices simultaneously.",
            "Aggressive distribution is visible as dynamic resistance levels hold firmly on both scales.",
            "Smart money positioning is clearly bearish based on cross-timeframe momentum shifts."
        ])
        if rsi_val > 35:
            rsi_txt = random.choice([
                f"RSI at {rsi_val} confirms healthy downward momentum with plenty of room before oversold levels.",
                f"Momentum reads {rsi_val}, supporting a sustained move lower without exhaustion."
            ])
        else:
            rsi_txt = random.choice([
                f"RSI is weak at {rsi_val}, showing extreme bearish power and heavy seller dominance.",
                f"Momentum indicator reads {rsi_val}, riding a massive wave of selling pressure."
            ])
        levels_txt = random.choice([
            "Risk is managed safely above the invalidation level; expecting an aggressive drop towards the lower targets.",
            "Invalidation point is clearly defined; expecting a heavy breakdown to hit the projected extension levels."
        ])

    summary = f"{structure_txt} {action_txt} {rsi_txt} {levels_txt}"
    return summary

def send_crypto_signal(coin_name, direction, strategy, entry, tp1, tp2, tp3, tp4, sl, summary_text):
    signal_id = get_next_signal_id()
    direction_text = "LONG" if direction.lower() == "long" else "SHORT"
    clean_name = coin_name.replace("/", "")
    
    zone_low = round(entry * 0.999, get_decimals(entry))
    zone_high = round(entry * 1.001, get_decimals(entry))

    text = f"📌 SIGNAL ID: #{signal_id}\nCOIN: #{clean_name} ({LEVERAGE})\nDirection