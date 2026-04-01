from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
from functools import lru_cache
import threading
import time

app = Flask(__name__)

# ── Instrument Configuration ─────────────────────────────────────────────────
INSTRUMENTS = [
    # Energy
    {"id": "TFM1",   "name": "TTF Gas",    "ticker": "TTF=F",   "group": "ENERGY",     "tv": "TFM1!"},
    {"id": "LCO",    "name": "Brent Crude", "ticker": "BZ=F",    "group": "ENERGY",     "tv": "LCO1!"},
    # Metals
    {"id": "USCGC",  "name": "Gold",        "ticker": "GC=F",    "group": "METALS",     "tv": "XAUUSD"},
    {"id": "USCSI",  "name": "Silver",      "ticker": "SI=F",    "group": "METALS",     "tv": "XAGUSD"},
    {"id": "PLAT",   "name": "Platinum",    "ticker": "PL=F",    "group": "METALS",     "tv": "PLAT1!"},
    {"id": "COPPER", "name": "Copper",      "ticker": "HG=F",    "group": "METALS",     "tv": "HG1!"},
    # Forex
    {"id": "GBPJPY", "name": "GBP/JPY",    "ticker": "GBPJPY=X","group": "FOREX",      "tv": "GBPJPY"},
    {"id": "EURJPY", "name": "EUR/JPY",    "ticker": "EURJPY=X","group": "FOREX",      "tv": "EURJPY"},
    {"id": "GBPUSD", "name": "GBP/USD",    "ticker": "GBPUSD=X","group": "FOREX",      "tv": "GBPUSD"},
    {"id": "EURUSD", "name": "EUR/USD",    "ticker": "EURUSD=X","group": "FOREX",      "tv": "EURUSD"},
    {"id": "EURGBP", "name": "EUR/GBP",    "ticker": "EURGBP=X","group": "FOREX",      "tv": "EURGBP"},
    # US Index
    {"id": "NASDAQ", "name": "NASDAQ",      "ticker": "NQ=F",    "group": "US INDEX",   "tv": "NQ1!"},
    {"id": "SPTRD",  "name": "S&P 500",     "ticker": "ES=F",    "group": "US INDEX",   "tv": "ES1!"},
    {"id": "RUSSELL","name": "Russell 2000","ticker": "RTY=F",   "group": "US INDEX",   "tv": "RTY1!"},
    # Other Index
    {"id": "FTSE",   "name": "FTSE 100",    "ticker": "^FTSE",   "group": "OTHER INDEX","tv": "UK100"},
    {"id": "DAX",    "name": "DAX",         "ticker": "^GDAXI",  "group": "OTHER INDEX","tv": "GER40"},
    {"id": "NIKKEI", "name": "Nikkei 225",  "ticker": "^N225",   "group": "OTHER INDEX","tv": "NI225"},
]

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache = {"data": None, "timestamp": None, "lock": threading.Lock()}
CACHE_MINUTES = 30


def get_cached_data():
    with _cache["lock"]:
        if _cache["data"] and _cache["timestamp"]:
            age = (datetime.now() - _cache["timestamp"]).seconds / 60
            if age < CACHE_MINUTES:
                return _cache["data"]
        data = build_dashboard_data()
        _cache["data"] = data
        _cache["timestamp"] = datetime.now()
        return data


# ── Data Functions ────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker, years=6):
    """Fetch historical OHLCV data for a ticker."""
    try:
        end = datetime.now()
        start = end - timedelta(days=years * 365 + 30)
        df = yf.download(ticker, start=start, end=end, interval="1d",
                         auto_adjust=True, progress=False)
        if df.empty or len(df) < 50:
            return None
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        return df
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calc_vwap_anchored(df, lookback_days):
    """Calculate anchored VWAP over the last N calendar days."""
    cutoff = df.index[-1] - timedelta(days=lookback_days)
    subset = df[df.index >= cutoff].copy()
    if subset.empty or "Volume" not in subset.columns:
        return None
    subset["TypicalPrice"] = (subset["High"] + subset["Low"] + subset["Close"]) / 3
    subset["TPV"] = subset["TypicalPrice"] * subset["Volume"]
    cum_tpv = subset["TPV"].cumsum()
    cum_vol = subset["Volume"].cumsum()
    vwap_series = cum_tpv / cum_vol
    return float(vwap_series.iloc[-1]) if not vwap_series.empty else None


def calc_ttm_squeeze(df, bb_period=20, bb_mult=2.0, kc_period=20, kc_mult=1.5):
    """
    TTM Squeeze: returns state string and histogram direction.
    State: 'squeeze' | 'fired' | 'off'
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Bollinger Bands
    bb_mid = close.rolling(bb_period).mean()
    bb_std = close.rolling(bb_period).std()
    bb_upper = bb_mid + bb_mult * bb_std
    bb_lower = bb_mid - bb_mult * bb_std

    # Keltner Channels
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(kc_period).mean()
    kc_mid = close.rolling(kc_period).mean()
    kc_upper = kc_mid + kc_mult * atr
    kc_lower = kc_mid - kc_mult * atr

    squeeze_on = (bb_upper < kc_upper) & (bb_lower > kc_lower)

    # Momentum histogram
    delta = close - ((high.rolling(kc_period).max() + low.rolling(kc_period).min()) / 2
                     + close.rolling(kc_period).mean()) / 2
    linreg = delta.rolling(kc_period).apply(
        lambda x: np.polyfit(range(len(x)), x, 1)[0] * (len(x) - 1) + np.polyfit(range(len(x)), x, 1)[1],
        raw=True
    )

    state = "squeeze" if squeeze_on.iloc[-1] else "fired"
    hist_now = float(linreg.iloc[-1]) if not np.isnan(linreg.iloc[-1]) else 0
    hist_prev = float(linreg.iloc[-2]) if len(linreg) > 1 and not np.isnan(linreg.iloc[-2]) else 0
    hist_dir = "up" if hist_now > hist_prev else "down"
    hist_growing = abs(hist_now) > abs(hist_prev)

    return {
        "state": state,
        "histogram_dir": hist_dir,
        "histogram_growing": hist_growing,
        "histogram_value": round(hist_now, 6)
    }


def calc_instrument(instrument, df):
    """Run all calculations for one instrument."""
    close = df["Close"]
    price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else price
    change_pct = ((price - prev_close) / prev_close) * 100

    ema21 = float(calc_ema(close, 21).iloc[-1])
    ema50 = float(calc_ema(close, 50).iloc[-1])
    ema200 = float(calc_ema(close, 200).iloc[-1])

    # Daily bias with 0.5% dead zone
    dead_zone_pct = 0.005
    if price > ema200 * (1 + dead_zone_pct):
        bias = "LONG"
    elif price < ema200 * (1 - dead_zone_pct):
        bias = "SHORT"
    else:
        bias = "NEUTRAL"

    # EMA stack
    if ema21 > ema50 > ema200:
        ema_stack = "BULL"
    elif ema21 < ema50 < ema200:
        ema_stack = "BEAR"
    else:
        ema_stack = "MIXED"

    # Distance from 200 EMA
    dist_200 = ((price - ema200) / ema200) * 100

    # VWAPs
    vwap_52w = calc_vwap_anchored(df, 365)
    vwap_5y = calc_vwap_anchored(df, 365 * 5)

    vwap_52w_dist = ((price - vwap_52w) / vwap_52w * 100) if vwap_52w else None
    vwap_5y_dist = ((price - vwap_5y) / vwap_5y * 100) if vwap_5y else None

    # TTM Squeeze
    try:
        squeeze = calc_ttm_squeeze(df)
    except Exception:
        squeeze = {"state": "n/a", "histogram_dir": "-", "histogram_growing": False, "histogram_value": 0}

    # Setup Tier scoring
    tier = score_setup_tier(bias, ema_stack, squeeze)

    return {
        "price": price,
        "change_pct": round(change_pct, 2),
        "ema21": round(ema21, 4),
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4),
        "bias": bias,
        "ema_stack": ema_stack,
        "dist_200": round(dist_200, 2),
        "vwap_52w": round(vwap_52w, 4) if vwap_52w else None,
        "vwap_52w_dist": round(vwap_52w_dist, 2) if vwap_52w_dist else None,
        "vwap_5y": round(vwap_5y, 4) if vwap_5y else None,
        "vwap_5y_dist": round(vwap_5y_dist, 2) if vwap_5y_dist else None,
        "squeeze": squeeze,
        "tier": tier,
    }


def score_setup_tier(bias, ema_stack, squeeze):
    """
    A-tier: bias + full EMA stack alignment + squeeze fired
    B-tier: bias + partial alignment OR squeeze in progress
    None: conflicting signals
    """
    bias_bull = bias == "LONG"
    bias_bear = bias == "SHORT"
    stack_aligned = (bias_bull and ema_stack == "BULL") or (bias_bear and ema_stack == "BEAR")
    squeeze_fired = squeeze["state"] == "fired"
    squeeze_active = squeeze["state"] == "squeeze"

    if stack_aligned and squeeze_fired:
        return "A"
    elif stack_aligned and squeeze_active:
        return "B"
    elif stack_aligned and ema_stack == "MIXED":
        return "B"
    elif not stack_aligned and squeeze_fired:
        return "B"
    else:
        return "NONE"


def fetch_econ_calendar():
    """Fetch economic calendar events from a free source."""
    try:
        # Using Trading Economics free tier or fallback static
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            events = r.json()
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            filtered = [
                e for e in events
                if e.get("impact") in ["High", "Medium"]
                and (today in e.get("date", "") or tomorrow in e.get("date", ""))
            ]
            return filtered[:12]
    except Exception as e:
        print(f"Calendar error: {e}")
    return []


def build_dashboard_data():
    """Build full dashboard payload."""
    results = {}
    for inst in INSTRUMENTS:
        df = fetch_ohlcv(inst["ticker"])
        if df is not None and len(df) >= 200:
            try:
                results[inst["id"]] = calc_instrument(inst, df)
            except Exception as e:
                print(f"Calc error for {inst['id']}: {e}")
                results[inst["id"]] = None
        else:
            results[inst["id"]] = None

    calendar = fetch_econ_calendar()
    return {
        "instruments": results,
        "calendar": calendar,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
        "groups": list(dict.fromkeys(i["group"] for i in INSTRUMENTS)),
        "instrument_config": INSTRUMENTS,
    }


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("dashboard.html", instruments=INSTRUMENTS)


@app.route("/api/data")
def api_data():
    data = get_cached_data()
    return jsonify(data)


@app.route("/api/refresh")
def api_refresh():
    with _cache["lock"]:
        _cache["data"] = None
        _cache["timestamp"] = None
    data = get_cached_data()
    return jsonify({"status": "refreshed", "updated_at": data["updated_at"]})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
