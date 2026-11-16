"""
Portfolio Advisory Cross-Reference Module
Matches Demat equity holdings against 'Equity Portfolio Advisory.xlsx'
and produces Buy/Hold/Sell/Add/Trim/Not Covered recommendations.
"""

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from casparser_isin import ISINDb

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ADVISORY_PATH = BASE_DIR / "data" / "Equity Portfolio Advisory.xlsx"


def format_indian_number(val: Any, prefix: str = "", decimals: int = 2) -> str:
    """Formats a number in Indian numbering system (Lakhs and Crores).
    e.g. 275573.41 -> 2,75,573.41, 10000000 -> 1,00,00,000.00
    """
    if val is None or val == "":
        return ""
    try:
        num = float(val)
    except (ValueError, TypeError):
        return str(val)

    is_negative = num < 0
    num = abs(num)

    fmt_str = f"{num:.{decimals}f}"
    parts = fmt_str.split(".")
    integer_part = parts[0]
    decimal_part = "." + parts[1] if len(parts) > 1 and decimals > 0 else ""

    if len(integer_part) <= 3:
        result = integer_part
    else:
        last3 = integer_part[-3:]
        rest = integer_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        result = ",".join(reversed(groups)) + "," + last3

    sign = "-" if is_negative else ""
    return f"{sign}{prefix}{result}{decimal_part}"


def normalize_review(review: Any) -> str:
    """Normalizes raw review strings to standard uppercase categories."""
    if not review or pd.isna(review):
        return "Not Covered"
    r = str(review).strip().upper()
    if r in ("BUY", "ADD"):
        return r
    if r in ("SELL", "TRIM"):
        return r
    if r == "HOLD":
        return "HOLD"
    return r


def clean_stock_name(name: str) -> str:
    """Normalizes equity company name for fuzzy matching."""
    if not name:
        return ""
    # Remove anything after # or -
    n = re.split(r"[#\-]", name)[0]
    # Remove phrases like 'AFTER SPLIT', 'WITH FACE VALUE', 'NEW EQUITY SHARES', etc.
    n = re.sub(
        r"\b(AFTER\s+SPLIT|AFTER\s+SUB|NEW\s+EQUITY\s+SHARES|WITH\s+FACE\s+VALUE|EQUITY\s+SHARES|FV\s+RE\.?\s*\d*|OF\s+RE\.?\s*\d*)\b",
        "",
        n,
        flags=re.I,
    )
    # Remove LTD, LIMITED, CORP, PVT, etc.
    n = re.sub(
        r"\b(LIMITED|LTD|CORP|CORPORATION|PVT|PRIVATE|HOLDINGS|ENTERPRISES|INDIA)\b",
        "",
        n,
        flags=re.I,
    )
    # Strip non-alphanumeric characters
    n = re.sub(r"[^A-Za-z0-9 ]+", " ", n)
    return re.sub(r"\s+", " ", n).strip().upper()


class AdvisoryEngine:
    """Loads and cross-references demat holdings against Equity Portfolio Advisory."""

    def __init__(self, advisory_path: Optional[Path] = None):
        self.advisory_path = Path(advisory_path) if advisory_path else DEFAULT_ADVISORY_PATH
        self.db = ISINDb()
        self.df: pd.DataFrame = pd.DataFrame()
        self.ticker_map: Dict[str, Dict[str, Any]] = {}
        self.symbol_map: Dict[str, Dict[str, Any]] = {}
        self.name_map: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if not self.advisory_path.exists():
            print(f"[!] Warning: Advisory file not found at {self.advisory_path}")
            return

        try:
            df = pd.read_excel(self.advisory_path)
            # Find column names flexibly
            sec_col = next(
                (
                    c
                    for c in df.columns
                    if "securit" in str(c).lower()
                    or "stock" in str(c).lower()
                    or "name" in str(c).lower()
                ),
                df.columns[0],
            )
            tick_col = next(
                (c for c in df.columns if "ticker" in str(c).lower() or "symbol" in str(c).lower()),
                df.columns[1] if len(df.columns) > 1 else df.columns[0],
            )
            rev_col = next(
                (
                    c
                    for c in df.columns
                    if "review" in str(c).lower()
                    or "view" in str(c).lower()
                    or "action" in str(c).lower()
                    or "recom" in str(c).lower()
                ),
                df.columns[2] if len(df.columns) > 2 else df.columns[-1],
            )

            self.df = df
            for _, row in df.iterrows():
                sec = str(row.get(sec_col, "")).strip() if pd.notna(row.get(sec_col)) else ""
                tick = str(row.get(tick_col, "")).strip() if pd.notna(row.get(tick_col)) else ""
                raw_rev = row.get(rev_col, "")
                norm_rev = normalize_review(raw_rev)

                record = {
                    "securities": sec,
                    "ticker": tick,
                    "review": norm_rev,
                    "raw_review": str(raw_rev).strip() if pd.notna(raw_rev) else "",
                }

                if tick:
                    tick_upper = tick.upper()
                    self.ticker_map[tick_upper] = record
                    # Extract bare symbol if exchange prefix exists (e.g., 'NSE:RELIANCE' -> 'RELIANCE')
                    if ":" in tick_upper:
                        bare_sym = tick_upper.split(":", 1)[1].strip()
                        if bare_sym:
                            self.symbol_map[bare_sym] = record
                    else:
                        self.symbol_map[tick_upper] = record

                if sec:
                    clean_n = clean_stock_name(sec)
                    if clean_n:
                        self.name_map[clean_n] = record

        except Exception as e:
            print(f"[!] Error loading advisory excel: {e}")

    def evaluate_holding(self, holding: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-checks an individual demat holding and returns advisory match data."""
        isin = holding.get("isin", "").strip().upper()
        demat_name = holding.get("name", "").strip()
        units = str(holding.get("units", "0"))
        val_str = str(holding.get("value", "0"))

        exchange_sym = ""
        exchange = ""
        isin_company_name = ""

        # Step 1: Query ISIN Database to get ticker / exchange
        if isin:
            try:
                isin_info = self.db.isin_lookup(isin)
                if isin_info:
                    exchange_sym = (isin_info.symbol or "").strip().upper()
                    exchange = (isin_info.exchange or "").strip().upper()
                    isin_company_name = (isin_info.name or isin_info.issuer or "").strip()
            except Exception:
                pass

        matched_record = None
        match_type = ""

        # Step 2: Try exact Ticker Match with exchange (e.g. 'NSE:ITCHOTELS')
        if exchange and exchange_sym:
            full_ticker = f"{exchange}:{exchange_sym}"
            if full_ticker in self.ticker_map:
                matched_record = self.ticker_map[full_ticker]
                match_type = "Ticker Match"
            elif f"NSE:{exchange_sym}" in self.ticker_map:
                matched_record = self.ticker_map[f"NSE:{exchange_sym}"]
                match_type = "Ticker Match (NSE)"
            elif f"BOM:{exchange_sym}" in self.ticker_map:
                matched_record = self.ticker_map[f"BOM:{exchange_sym}"]
                match_type = "Ticker Match (BOM)"

        # Step 3: Try bare symbol match (e.g. 'ITC' -> 'NSE:ITC')
        if not matched_record and exchange_sym:
            if exchange_sym in self.symbol_map:
                matched_record = self.symbol_map[exchange_sym]
                match_type = "Symbol Match"

        # Step 4: Try clean name match against ISIN company name and Demat name
        if not matched_record:
            names_to_try = [
                clean_stock_name(isin_company_name),
                clean_stock_name(demat_name),
            ]
            for clean_n in names_to_try:
                if not clean_n:
                    continue
                if clean_n in self.name_map:
                    matched_record = self.name_map[clean_n]
                    match_type = "Exact Name Match"
                    break
                # Partial token matching (e.g., 'ITC HOTELS' inside 'ITC HOTELS LTD')
                for adv_clean, rec in self.name_map.items():
                    if len(adv_clean) >= 4 and (
                        adv_clean == clean_n or adv_clean in clean_n or clean_n in adv_clean
                    ):
                        matched_record = rec
                        match_type = "Fuzzy Name Match"
                        break
                if matched_record:
                    break

        if matched_record:
            view = matched_record["review"]
            advisory_ticker = matched_record["ticker"]
            advisory_security = matched_record["securities"]
            match_status = "Covered"
        else:
            view = "Not Covered"
            advisory_ticker = f"{exchange}:{exchange_sym}" if exchange_sym else "N/A"
            advisory_security = "N/A"
            match_status = "Not Covered"

        return {
            "demat_type": holding.get("demat_type", ""),
            "dp_id": holding.get("dp_id", ""),
            "client_id": holding.get("client_id", ""),
            "isin": isin,
            "demat_stock_name": demat_name,
            "units": units,
            "value": val_str,
            "exchange_symbol": exchange_sym,
            "advisory_ticker": advisory_ticker,
            "advisory_stock_name": advisory_security,
            "advisory_view": view,
            "match_status": match_status,
            "match_type": match_type or "None",
        }

    def evaluate_holdings(self, demat_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluates all demat holdings and computes summary statistics."""
        results = []
        summary_counts = {
            "BUY": {"count": 0, "value": Decimal(0)},
            "HOLD": {"count": 0, "value": Decimal(0)},
            "SELL": {"count": 0, "value": Decimal(0)},
            "ADD": {"count": 0, "value": Decimal(0)},
            "TRIM": {"count": 0, "value": Decimal(0)},
            "Not Covered": {"count": 0, "value": Decimal(0)},
        }
        total_equity_value = Decimal(0)

        for row in demat_rows:
            # We evaluate equities
            if row.get("category", "equities") != "equities":
                continue

            evaluated = self.evaluate_holding(row)
            results.append(evaluated)

            val = Decimal(str(row.get("value") or 0))
            total_equity_value += val
            view = evaluated["advisory_view"]
            if view not in summary_counts:
                summary_counts[view] = {"count": 0, "value": Decimal(0)}
            summary_counts[view]["count"] += 1
            summary_counts[view]["value"] += val

        return {
            "holdings": results,
            "summary": summary_counts,
            "total_equities_count": len(results),
            "total_equity_value": str(total_equity_value),
        }
