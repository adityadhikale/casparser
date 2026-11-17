"""UI-agnostic service layer: parse a CAS PDF and build every output in memory.

Used by the FastAPI app (api/main.py). Holds no Streamlit dependency.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import casparser
from advisory import DEFAULT_ADVISORY_PATH, AdvisoryEngine
from excel_exporter import (
    build_enriched_json,
    build_export_data,
    write_formatted_csv,
    write_formatted_excel,
)


class ParseError(Exception):
    """User-facing parse failure (message is safe to display)."""


_default_engine: AdvisoryEngine | None = None


def get_default_engine() -> AdvisoryEngine | None:
    global _default_engine
    if _default_engine is None and Path(DEFAULT_ADVISORY_PATH).exists():
        _default_engine = AdvisoryEngine(advisory_path=DEFAULT_ADVISORY_PATH)
    return _default_engine


def engine_from_bytes(data: bytes) -> AdvisoryEngine:
    """Build an engine from an uploaded xlsx; temp file is removed right after load."""
    fd, name = tempfile.mkstemp(suffix=".xlsx")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return AdvisoryEngine(advisory_path=Path(name))
    finally:
        Path(name).unlink(missing_ok=True)


def advisory_status(engine: AdvisoryEngine | None) -> dict:
    if engine is None:
        return {"loaded": False, "count": 0}
    return {"loaded": True, "count": len(engine.df)}


def _file_bytes(writer, export_data, suffix: str) -> bytes:
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    p = Path(name)
    try:
        writer(export_data, p)
        return p.read_bytes()
    finally:
        p.unlink(missing_ok=True)


def _investor_pan(investor_table: list) -> str:
    """Find PAN by label rather than by position."""
    for row in investor_table[1:]:
        if len(row) >= 2 and "pan" in str(row[0]).lower():
            return str(row[1])
    return "N/A"


_NUMERIC_FIELDS = {"value", "units", "nav", "cost", "amount", "balance"}


def _num(v):
    """'1234.50' -> 1234.5; leaves non-numeric values untouched."""
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return v
    return v


def parse_cas(pdf_bytes: bytes, password: str, engine: AdvisoryEngine | None) -> dict:
    fd, name = tempfile.mkstemp(suffix=".pdf")
    pdf_path = Path(name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(pdf_bytes)

        try:
            parsed = json.loads(
                casparser.read_cas_pdf(str(pdf_path), password=password or "", output="json")
            )
        except casparser.exceptions.IncorrectPasswordError as exc:
            raise ParseError(
                "Incorrect password. If this CAS PDF is password protected, enter the correct password."
            ) from exc
        except Exception as exc:  # parser errors are user-facing
            raise ParseError(f"Could not parse statement: {exc}") from exc

        export_data = build_export_data(parsed, pdf_path=pdf_path)

        if engine:
            advisory_data = engine.evaluate_holdings(export_data["demat_rows"])
            export_data["advisory_data"] = advisory_data
            eval_map = {h.get("isin", "").upper(): h for h in advisory_data.get("holdings", [])}
            for row in export_data["demat_rows"]:
                m = eval_map.get(row.get("isin", "").upper())
                row["advisory_view"] = (m or {}).get("advisory_view", "Not Covered")
                row["advisory_ticker"] = (m or {}).get("advisory_ticker", "N/A")
                row["advisory_stock_name"] = (m or {}).get("advisory_stock_name", "N/A")

        enriched = build_enriched_json(parsed, export_data)
        xlsx = _file_bytes(write_formatted_excel, export_data, ".xlsx")
        csv = _file_bytes(write_formatted_csv, export_data, ".csv")

        investor_table = export_data.get("investor_table", [])
        payload = {
            "statement_period": parsed.get("statement_period") or {},
            "investor": {
                "name": (parsed.get("investor_info") or {}).get("name", "N/A"),
                "pan": _investor_pan(investor_table),
                "details": investor_table[1:],
            },
            "totals": export_data["totals"],
            "demat": export_data["demat_rows"],
            "mf": export_data["mf_rows"],
            "transactions": export_data["txn_rows"],
            "categories": export_data["category_table"][1:],
            "advisory": export_data.get("advisory_data") or {"holdings": [], "summary": {}},
            "enriched_json": enriched,
        }
        # make strictly JSON-safe (dates, Decimals), then give amounts real numbers
        safe = json.loads(json.dumps(payload, default=str))
        for key in ("totals",):
            safe[key] = {k: _num(v) for k, v in safe[key].items()}
        for key in ("demat", "mf", "transactions"):
            for row in safe[key]:
                for f in _NUMERIC_FIELDS & row.keys():
                    row[f] = _num(row[f])
        for h in safe["advisory"].get("holdings", []):
            for f in _NUMERIC_FIELDS & h.keys():
                h[f] = _num(h[f])
        for v in safe["advisory"].get("summary", {}).values():
            v["value"] = _num(v.get("value"))
        safe["categories"] = [[c, _num(v), n] for c, v, n in safe["categories"]]
        return safe, xlsx, csv
    finally:
        pdf_path.unlink(missing_ok=True)
