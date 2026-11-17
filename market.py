"""Yahoo Finance market-data layer (via yfinance). UI-agnostic, in-memory cached.

Yahoo data is unofficial and may be delayed ~15 min; treat it as indicative.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

INDICES = [
    ("^NSEI", "Nifty 50"),
    ("^BSESN", "Sensex"),
    ("^NSEBANK", "Bank Nifty"),
    ("^INDIAVIX", "India VIX"),
    ("USDINR=X", "USD / INR"),
    ("GC=F", "Gold (USD)"),
    ("BZ=F", "Brent crude"),
]

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}
_symbol_cache: dict[str, str | None] = {}


def _cached(key: str, ttl: float, fn):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _lock:
        _cache[key] = (now, val)
    return val


def _f(v):
    try:
        v = float(v)
        return v if v == v else None  # drop NaN
    except (TypeError, ValueError):
        return None


def resolve_symbol(isin: str, advisory_ticker: str = "") -> str | None:
    """Map a holding to a Yahoo symbol: advisory ticker first, then ISIN search (NSE preferred)."""
    key = f"{isin}|{advisory_ticker}"
    if key in _symbol_cache:
        return _symbol_cache[key]
    sym = None
    t = (advisory_ticker or "").strip()
    if ":" in t:
        ex, code = t.split(":", 1)
        sym = f"{code.strip()}{'.BO' if ex.strip().upper() == 'BSE' else '.NS'}"
    if sym is None and isin:
        try:
            quotes = yf.Search(isin, max_results=6).quotes
            syms = [q.get("symbol", "") for q in quotes]
            sym = next((s for s in syms if s.endswith(".NS")), None) or next(
                (s for s in syms if s.endswith(".BO")), None
            )
        except Exception:
            sym = None
    _symbol_cache[key] = sym
    return sym


def _quote(sym: str) -> dict:
    def load():
        try:
            fi = yf.Ticker(sym).fast_info
            price, prev = _f(fi.last_price), _f(fi.previous_close)
            return {
                "symbol": sym,
                "price": price,
                "prev_close": prev,
                "change": (price - prev) if price is not None and prev else None,
                "change_pct": ((price / prev - 1) * 100) if price is not None and prev else None,
                "year_high": _f(fi.year_high),
                "year_low": _f(fi.year_low),
                "market_cap": _f(fi.market_cap),
                "currency": fi.currency,
            }
        except Exception:
            return {"symbol": sym, "price": None}

    return _cached(f"q:{sym}", 60, load)


def holdings_quotes(holdings: list[dict]) -> list[dict]:
    """holdings: [{isin, name, units, ticker}] -> same order with live data merged in."""

    def one(h):
        sym = resolve_symbol(h.get("isin", ""), h.get("ticker", ""))
        q = _quote(sym) if sym else {"symbol": None, "price": None}
        units = _f(h.get("units")) or 0
        price, prev = q.get("price"), q.get("prev_close")
        return {
            "isin": h.get("isin"),
            **q,
            "live_value": units * price if price is not None else None,
            "day_pnl": units * (price - prev) if price is not None and prev else None,
        }

    with ThreadPoolExecutor(max_workers=10) as ex:
        return list(ex.map(one, holdings))


def overview() -> list[dict]:
    def load():
        syms = [s for s, _ in INDICES]
        try:
            hist = yf.download(
                syms,
                period="1mo",
                interval="1d",
                progress=False,
                auto_adjust=False,
                group_by="ticker",
                threads=True,
            )
        except Exception:
            hist = None

        def one(item):
            sym, name = item
            closes: list[float] = []
            try:
                closes = [c for c in (_f(x) for x in hist[sym]["Close"].tolist()) if c is not None]
            except Exception:
                pass
            q = _quote(sym)
            price = (
                q.get("price") if q.get("price") is not None else (closes[-1] if closes else None)
            )
            prev = (
                q.get("prev_close")
                if q.get("prev_close") is not None
                else (closes[-2] if len(closes) > 1 else None)
            )
            return {
                "symbol": sym,
                "name": name,
                "price": price,
                "change": (price - prev) if price is not None and prev else None,
                "change_pct": ((price / prev - 1) * 100) if price is not None and prev else None,
                "spark": closes[-22:],
            }

        with ThreadPoolExecutor(max_workers=7) as ex:
            return list(ex.map(one, INDICES))

    return _cached("overview", 120, load)


def news(symbols: list[str], limit: int = 12) -> list[dict]:
    def load():
        out, seen = [], set()

        def one(sym):
            try:
                return yf.Ticker(sym).news or []
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=6) as ex:
            batches = list(ex.map(one, symbols))
        for sym, items in zip(symbols, batches):
            for it in items:
                c = it.get("content") or it
                title = c.get("title")
                if not title or title in seen:
                    continue
                seen.add(title)
                url = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {}).get("url") or c.get(
                    "link"
                )
                out.append(
                    {
                        "title": title,
                        "publisher": (c.get("provider") or {}).get("displayName")
                        or c.get("publisher"),
                        "url": url,
                        "time": c.get("pubDate") or c.get("providerPublishTime"),
                        "symbol": sym,
                    }
                )
        out.sort(key=lambda x: str(x["time"] or ""), reverse=True)
        return out[:limit]

    return _cached("news:" + ",".join(sorted(symbols)), 300, load)
