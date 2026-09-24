"""
Fetches the latest EGX session data (price, % change, volume) for every
ticker listed in data/tickers.json, and writes the result to data/latest.json.

Data source: Yahoo Finance (unofficial), via the `yfinance` package.
Egyptian Exchange tickers on Yahoo use a ".CA" suffix, e.g. COMI.CA.

This is a best-effort public source, not an official EGX feed:
- Coverage isn't 100% of EGX's 200+ listed names, only the ones Yahoo tracks.
- Yahoo occasionally changes its unofficial API; if this starts failing,
  check for a `yfinance` update first (`pip install -U yfinance`).

Two things were verified against live data and are deliberate:

1. We read daily bars from the *history* endpoint, not the quote endpoint.
   Yahoo's quote data (`Ticker.info` / `fast_info`) is badly broken for .CA
   symbols -- as of this writing it reports COMI.CA at 81.20 with a
   `regularMarketTime` from 2024 and a `quoteType` of MUTUALFUND, while the
   real close was 128.10. Do not "upgrade" this to use .info for live prices.

2. `auto_adjust=False`. yfinance defaults to back-adjusting closes for
   dividends, which silently rewrites history every time a stock goes
   ex-dividend. We want the actual traded EGP close that EGX published, so
   the % change here matches the % change on the exchange's own site.

Usage:
    python scraper/fetch_egx.py
"""

import json
import pathlib
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

ROOT = pathlib.Path(__file__).resolve().parent.parent
TICKERS_FILE = ROOT / "data" / "tickers.json"
OUTPUT_FILE = ROOT / "data" / "latest.json"

# Yahoo serves multiple symbols per request; chunking keeps URLs sane and
# avoids one bad symbol poisoning the whole batch.
CHUNK_SIZE = 40
MAX_ATTEMPTS = 3
# A name with no trades at all across this many sessions is treated as a dead
# listing rather than a real quote. Yahoo keeps serving a frozen price for
# delisted EGX names (ORAS.CA has sat at 71.05 with zero volume for months).
FROZEN_LOOKBACK = 10


def load_tickers():
    with open(TICKERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def download(symbols):
    """Fetch daily bars for a list of symbols, with retries."""
    frames = {}
    for start in range(0, len(symbols), CHUNK_SIZE):
        chunk = symbols[start:start + CHUNK_SIZE]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw = yf.download(
                    " ".join(chunk),
                    period="1mo",          # enough to survive a suspension
                    interval="1d",
                    auto_adjust=False,     # see module docstring
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )
                if raw is None or raw.empty:
                    raise RuntimeError("empty response")
                break
            except Exception as exc:
                if attempt == MAX_ATTEMPTS:
                    print(f"  chunk {start // CHUNK_SIZE + 1} failed: {exc}")
                    raw = None
                else:
                    time.sleep(2 ** attempt)
        if raw is None:
            continue
        for symbol in chunk:
            try:
                frames[symbol] = raw[symbol]
            except KeyError:
                pass  # reported as "no data returned" below
    return frames


def build_row(entry, frame):
    """Turn one symbol's daily bars into a result row, or an error row."""
    symbol = entry["symbol"]
    if frame is None:
        return {**entry, "error": "no data returned by Yahoo"}

    bars = frame.dropna(subset=["Close"])
    if len(bars) < 2:
        return {**entry, "error": f"only {len(bars)} daily bar(s) available"}

    recent = bars.tail(FROZEN_LOOKBACK)
    if float(recent["Volume"].fillna(0).sum()) <= 0:
        return {**entry, "error": "no trades in last "
                                  f"{len(recent)} sessions (delisted?)"}

    last, prev = bars.iloc[-1], bars.iloc[-2]
    prev_close = float(prev["Close"])
    if prev_close <= 0:
        return {**entry, "error": "invalid previous close"}

    last_close = float(last["Close"])
    volume = last["Volume"]

    return {
        "symbol": symbol,
        "name": entry.get("name", symbol),
        "name_ar": entry.get("name_ar", ""),
        "price": round(last_close, 3),
        "prev_close": round(prev_close, 3),
        "change_pct": round(((last_close - prev_close) / prev_close) * 100, 2),
        "volume": 0 if pd.isna(volume) else int(volume),
        "session_date": bars.index[-1].strftime("%Y-%m-%d"),
    }


def main():
    tickers = load_tickers()
    print(f"Fetching {len(tickers)} tickers from Yahoo Finance...\n")

    frames = download([t["symbol"] for t in tickers])

    results = []
    session_dates = []
    for entry in tickers:
        row = build_row(entry, frames.get(entry["symbol"]))
        results.append(row)
        if "session_date" in row:
            session_dates.append(row["session_date"])
        status = "OK" if "error" not in row else f"FAILED: {row['error']}"
        print(f"  {entry['symbol']:<10} -> {status}")

    ok_count = len(results) - sum(1 for r in results if "error" in r)
    print(f"\nFetched {ok_count}/{len(results)} tickers successfully.")

    # Yahoo publishes the day's EGX bar hours after the 14:30 Cairo close, so
    # a run that fires too early silently returns the *previous* session.
    # Record the session we actually got and let the site say how old it is,
    # rather than presenting stale closes as fresh.
    session_date = max(session_dates) if session_dates else None
    if session_date:
        stale_count = sum(1 for d in session_dates if d != session_date)
        if stale_count:
            print(f"Note: {stale_count} ticker(s) last traded before "
                  f"{session_date}.")

    payload = {
        "updated_at": datetime.now(timezone.utc)
                              .replace(microsecond=0).isoformat(),
        "session_date": session_date,
        "demo": False,
        "stocks": results,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" so a run on Windows and a run on the Linux CI runner
    # produce byte-identical files instead of a whole-file CRLF diff.
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Session date: {session_date}")
    print(f"Wrote {OUTPUT_FILE}")

    if ok_count == 0:
        # Nothing succeeded -- treat as a failure for CI purposes.
        sys.exit(1)


if __name__ == "__main__":
    main()
