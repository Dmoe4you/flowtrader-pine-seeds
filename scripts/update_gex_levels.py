#!/usr/bin/env python3
"""
Fetches live GEX levels from the Massive API and writes Pine Seeds JSONL files.
Runs on GitHub Actions every 15 minutes during market hours.
"""

import os
import json
import time
import csv
from datetime import datetime, timezone
from collections import defaultdict
import urllib.request
import urllib.parse

MASSIVE_API_KEY = os.environ["MASSIVE_API_KEY"]
MASSIVE_BASE    = "https://api.massive.com"
DATA_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")

SYMBOLS = {
    "SPY":  {"spot_multiplier": 1.0,    "strike_step": 1},
    "SPX":  {"spot_multiplier": 10.0,   "strike_step": 5},
}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FlowTrader-PineSeeds/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def get_spot(symbol):
    url = f"{MASSIVE_BASE}/v2/last/trade/{symbol}?apiKey={MASSIVE_API_KEY}"
    try:
        data = fetch_json(url)
        return float(data["results"]["p"])
    except Exception:
        # Fallback: last agg close
        url = f"{MASSIVE_BASE}/v2/aggs/ticker/{symbol}/prev?adjusted=true&apiKey={MASSIVE_API_KEY}"
        data = fetch_json(url)
        return float(data["results"][0]["c"])

def fetch_options_chain(symbol, spot):
    """Fetch options chain and compute GEX per strike."""
    lo = round(spot * 0.90 / 5) * 5
    hi = round(spot * 1.10 / 5) * 5

    url = (
        f"{MASSIVE_BASE}/v3/snapshot/options/{symbol}"
        f"?strike_price.gte={lo}&strike_price.lte={hi}"
        f"&limit=250&apiKey={MASSIVE_API_KEY}"
    )

    rows = []
    while url:
        data = fetch_json(url)
        rows.extend(data.get("results", []))
        next_url = data.get("next_url")
        url = f"{next_url}&apiKey={MASSIVE_API_KEY}" if next_url else None

    call_gex = defaultdict(float)
    put_gex  = defaultdict(float)

    for r in rows:
        det = r.get("details", {})
        grk = r.get("greeks", {})
        otype  = det.get("contract_type", "").lower()
        strike = float(det.get("strike_price", 0))
        gamma  = float(grk.get("gamma", 0) or 0)
        oi     = float(r.get("open_interest", 0) or 0)

        if strike <= 0 or gamma <= 0 or oi <= 0:
            continue

        gex_val = gamma * oi * 100 * spot * spot * 0.01

        if otype == "call":
            call_gex[strike] += gex_val
        elif otype == "put":
            put_gex[strike]  -= gex_val  # puts negative

    return call_gex, put_gex

def compute_levels(symbol, spot, call_gex, put_gex):
    """Derive key GEX levels from raw per-strike data."""
    all_strikes = set(list(call_gex.keys()) + list(put_gex.keys()))
    net_gex_by_strike = {s: call_gex.get(s, 0) + put_gex.get(s, 0) for s in all_strikes}
    net_gex = sum(net_gex_by_strike.values())

    above = sorted([(s, v) for s, v in net_gex_by_strike.items() if s > spot], key=lambda x: x[0])
    below = sorted([(s, v) for s, v in net_gex_by_strike.items() if s < spot], key=lambda x: x[0], reverse=True)

    # Call wall: above spot, ranked by call GEX descending
    call_walls = sorted(
        [(s, call_gex[s]) for s in call_gex if s > spot and call_gex[s] > 0],
        key=lambda x: x[1], reverse=True
    )
    # Put wall: below spot, ranked by abs(put_gex) descending
    put_walls = sorted(
        [(s, abs(put_gex[s])) for s in put_gex if s < spot and put_gex[s] < 0],
        key=lambda x: x[1], reverse=True
    )

    # Gamma flip: strike where cumulative net GEX crosses zero
    cumulative = 0.0
    gamma_flip = spot  # default to spot if not found
    for s, v in sorted(net_gex_by_strike.items()):
        cumulative += v
        if cumulative >= 0:
            gamma_flip = s
            break

    return {
        "call_wall":   call_walls[0][0]  if call_walls else spot,
        "call_wall_2": call_walls[1][0]  if len(call_walls) > 1 else spot,
        "put_wall":    put_walls[0][0]   if put_walls  else spot,
        "put_wall_2":  put_walls[1][0]   if len(put_walls)  > 1 else spot,
        "gamma_flip":  gamma_flip,
        "net_gex":     net_gex,
    }

def append_jsonl(filepath, timestamp_s, value):
    """Append one Pine Seeds JSONL row. Value must be float."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    row = json.dumps({"time": int(timestamp_s), "close": float(value)})
    with open(filepath, "a") as f:
        f.write(row + "\n")

def write_symbol(sym_id, value, ts):
    path = os.path.join(DATA_DIR, f"{sym_id}.jsonl")
    append_jsonl(path, ts, value)
    print(f"  {sym_id}: {value:.2f}")

def is_market_hours():
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:  # weekend
        return False
    # Market hours: 14:30–21:15 UTC (9:30–4:15 PM ET, no DST adjustment needed — GH Actions runs UTC)
    market_open  = now_utc.replace(hour=14, minute=25, second=0, microsecond=0)
    market_close = now_utc.replace(hour=21, minute=20, second=0, microsecond=0)
    return market_open <= now_utc <= market_close

def main():
    if not is_market_hours():
        print("Outside market hours — skipping update.")
        return

    ts = int(time.time())
    print(f"Updating GEX levels at {datetime.now(timezone.utc).isoformat()}")

    for symbol in ["SPY", "SPX"]:
        print(f"\n── {symbol} ──")
        try:
            spot = get_spot(symbol)
            print(f"  Spot: {spot:.2f}")
            call_gex, put_gex = fetch_options_chain(symbol, spot)
            levels = compute_levels(symbol, spot, call_gex, put_gex)

            sym = symbol.upper()
            write_symbol(f"{sym}_CALL_WALL",  levels["call_wall"],   ts)
            write_symbol(f"{sym}_CALL_GEX_1", levels["call_wall_2"], ts)
            write_symbol(f"{sym}_PUT_WALL",   levels["put_wall"],    ts)
            write_symbol(f"{sym}_PUT_GEX_1",  levels["put_wall_2"],  ts)
            write_symbol(f"{sym}_GAMMA_FLIP", levels["gamma_flip"],  ts)
            write_symbol(f"{sym}_NET_GEX",    levels["net_gex"] / 1e6, ts)  # in millions

        except Exception as e:
            print(f"  ERROR for {symbol}: {e}")

    print("\nDone.")

if __name__ == "__main__":
    main()
