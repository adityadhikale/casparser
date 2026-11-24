"""UI-agnostic service layer: parse a CAS PDF and build every output in memory.

Used by the FastAPI app (api/main.py). Holds no Streamlit dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import casparser
from advisory import DEFAULT_ADVISORY_PATH, AdvisoryEngine
from consolidate import merge_family
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


def _tag_advisory(rows: list[dict], advisory_data: dict) -> None:
    """Write advisory view/ticker/name onto demat rows, matched by ISIN."""
    eval_map = {h.get("isin", "").upper(): h for h in advisory_data.get("holdings", [])}
    for row in rows:
        m = eval_map.get(row.get("isin", "").upper())
        row["advisory_view"] = (m or {}).get("advisory_view", "Not Covered")
        row["advisory_ticker"] = (m or {}).get("advisory_ticker", "N/A")
        row["advisory_stock_name"] = (m or {}).get("advisory_stock_name", "N/A")


def _apply_advisory(export_data: dict, engine: AdvisoryEngine | None) -> None:
    if engine:
        advisory_data = engine.evaluate_holdings(export_data["demat_rows"])
        export_data["advisory_data"] = advisory_data
        _tag_advisory(export_data["demat_rows"], advisory_data)


def _read_member(pdf_bytes: bytes, password: str, engine: AdvisoryEngine | None):
    """Parse one PDF into (parsed, export_data) with advisory applied."""
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
        _apply_advisory(export_data, engine)
        return parsed, export_data
    finally:
        pdf_path.unlink(missing_ok=True)


def _build_outputs(
    parsed: dict,
    export_data: dict,
    file_export: dict | None = None,
    enriched_extra: dict | None = None,
):
    """Build (payload, xlsx_bytes, csv_bytes).

    ``file_export`` is the data the xlsx/csv are written from when it differs from the
    on-screen ``export_data`` (family view: every member's own rows with an Owner column).
    """
    enriched = build_enriched_json(parsed, export_data)
    if enriched_extra:
        enriched.update(enriched_extra)
    source = file_export or export_data
    xlsx = _file_bytes(write_formatted_excel, source, ".xlsx")
    csv = _file_bytes(write_formatted_csv, source, ".csv")

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


def parse_cas(pdf_bytes: bytes, password: str, engine: AdvisoryEngine | None):
    parsed, export_data = _read_member(pdf_bytes, password, engine)
    return _build_outputs(parsed, export_data)


def parse_family(files: list[tuple[str, bytes, str]], engine: AdvisoryEngine | None) -> dict:
    """Parse several statements (``(filename, bytes, password)``) and consolidate them.

    Returns ``{"family": (payload, xlsx, csv), "members": [(stem, payload, xlsx, csv)],
    "warnings": [...]}``. Raises ParseError naming the offending file.
    """
    members: list[dict] = []
    seen_hashes: dict[str, str] = {}
    for filename, data, password in files:
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen_hashes:
            raise ParseError(
                f"{filename} is identical to {seen_hashes[digest]}. Remove the duplicate."
            )
        seen_hashes[digest] = filename
        try:
            parsed, export_data = _read_member(data, password, engine)
        except ParseError as exc:
            raise ParseError(f"{filename}: {exc}") from exc
        stem = Path(filename).stem or "CAS_Report"
        name = (parsed.get("investor_info") or {}).get("name") or stem
        members.append(
            {
                "owner": name,
                "pan": _investor_pan(export_data.get("investor_table", [])),
                "filename": stem,
                "parsed": parsed,
                "export_data": export_data,
            }
        )

    member_outputs = []
    for m in members:
        payload, xlsx, csv = _build_outputs(m["parsed"], m["export_data"])
        member_outputs.append((m["filename"], payload, xlsx, csv))

    merged = merge_family(members)
    _apply_advisory(merged["export_data"], engine)
    if engine:
        advisory_data = merged["export_data"]["advisory_data"]
        merged["file_export"]["advisory_data"] = advisory_data
        _tag_advisory(merged["file_export"]["demat_rows"], advisory_data)
    family = _build_outputs(
        merged["parsed"],
        merged["export_data"],
        file_export=merged["file_export"],
        enriched_extra={"members": [o[1]["enriched_json"] for o in member_outputs]},
    )
    return {"family": family, "members": member_outputs, "warnings": merged["warnings"]}
