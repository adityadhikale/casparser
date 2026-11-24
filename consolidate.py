"""Consolidate several parsed CAS statements (one per family member) into one view.

Pure functions: no PDF or file I/O. Inputs are the ``export_data`` dicts produced by
``excel_exporter.build_export_data``; all numeric row values are Decimal-compatible strings.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

_DEMAT_ACCOUNT_FIELDS = ("demat_type", "dp_id", "dp_name", "client_id", "bo_id")


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal(0)


_DATE_FORMATS = ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y")


def _date_key(s) -> tuple:
    """Sort key that orders real dates chronologically (unparseable values sort last, as text)."""
    text = str(s or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return (0, datetime.strptime(text, fmt), "")
        except ValueError:
            continue
    return (1, datetime.max, text)


def _joined(values) -> str:
    seen: list[str] = []
    for v in values:
        v = str(v or "").strip()
        if v and v not in seen:
            seen.append(v)
    return ", ".join(seen)


def tag_owner(rows: list[dict], owner: str) -> list[dict]:
    """Copy rows with an ``owner`` field (the originals are left untouched)."""
    return [{**r, "owner": owner} for r in rows]


def merge_demat(rows: list[dict]) -> list[dict]:
    """Combine owner-tagged demat rows that share an ISIN and category."""
    groups: dict[tuple, dict] = {}
    out: list[dict] = []
    for r in rows:
        isin = (r.get("isin") or "").upper()
        if not isin:
            out.append(dict(r))
            continue
        key = (isin, r.get("category", ""))
        g = groups.get(key)
        if g is None:
            g = dict(r)
            g["_owners"] = [r.get("owner", "")]
            groups[key] = g
            out.append(g)
            continue
        g["units"] = str(_dec(g["units"]) + _dec(r.get("units")))
        g["value"] = str(_dec(g["value"]) + _dec(r.get("value")))
        g["_owners"].append(r.get("owner", ""))
        for f in _DEMAT_ACCOUNT_FIELDS:
            if g.get(f) != r.get(f):
                g[f] = "Multiple"
    for g in out:
        owners = g.pop("_owners", None)
        if owners is not None:
            g["owner"] = _joined(owners)
    return out


def merge_mf(rows: list[dict]) -> list[dict]:
    """Combine owner-tagged mutual fund rows that share an ISIN (or scheme name)."""
    groups: dict[str, dict] = {}
    out: list[dict] = []
    for r in rows:
        key = (r.get("isin") or "").upper() or f"name:{r.get('scheme_name', '')}"
        g = groups.get(key)
        if g is None:
            g = dict(r)
            g["_owners"] = [r.get("owner", "")]
            g["_folios"] = [r.get("folio_number", "")]
            g["_pans"] = [r.get("folio_pan", "")]
            g["_cost_known"] = r.get("cost", "") != ""
            groups[key] = g
            out.append(g)
            continue
        g["units"] = str(_dec(g["units"]) + _dec(r.get("units")))
        g["value"] = str(_dec(g["value"]) + _dec(r.get("value")))
        if g["_cost_known"] and r.get("cost", "") != "":
            g["cost"] = str(_dec(g["cost"]) + _dec(r["cost"]))
        else:
            g["_cost_known"] = False
        g["_owners"].append(r.get("owner", ""))
        g["_folios"].append(r.get("folio_number", ""))
        g["_pans"].append(r.get("folio_pan", ""))
    for g in out:
        owners = g.pop("_owners", None)
        if owners is None:
            continue
        g["owner"] = _joined(owners)
        g["folio_number"] = _joined(g.pop("_folios"))
        g["folio_pan"] = _joined(g.pop("_pans"))
        value = _dec(g["value"])
        if g.pop("_cost_known") and g.get("cost", "") != "":
            cost = _dec(g["cost"])
            g["gain_absolute"] = str(value - cost)
            g["gain_percentage"] = str((value - cost) / cost * 100) if cost > 0 else ""
            g["info_investment_value"] = g["cost"]
        else:
            g["cost"] = g["gain_absolute"] = g["gain_percentage"] = ""
            g["info_investment_value"] = ""
        g["info_close_units"] = g["units"]
        g["info_open_units"] = ""
    return out


def _nps_count(category_table: list) -> int:
    for row in category_table[1:]:
        if str(row[0]).lower() == "nps":
            try:
                return int(row[2])
            except (TypeError, ValueError):
                return 0
    return 0


def merge_family(members: list[dict]) -> dict:
    """Merge members into one family result.

    ``members``: list of ``{"owner", "pan", "filename", "parsed", "export_data"}``.

    Returns ``{"parsed", "export_data", "file_export", "warnings"}``:
    - ``export_data`` is the display view (same-ISIN holdings combined),
    - ``file_export`` is the download view (every member's own rows, tagged with owner),
    - ``parsed`` is a minimal stand-in for the raw parser output.
    Advisory data is not attached here; the caller evaluates it over the merged rows.
    """
    tagged_demat: list[dict] = []
    tagged_mf: list[dict] = []
    txns: list[dict] = []
    totals = {
        k: Decimal(0) for k in ("total_portfolio_value", "demat_value", "mf_value", "nps_value")
    }
    nps_count = 0
    for m in members:
        ed = m["export_data"]
        tagged_demat += tag_owner(ed["demat_rows"], m["owner"])
        tagged_mf += tag_owner(ed["mf_rows"], m["owner"])
        txns += tag_owner(ed["txn_rows"], m["owner"])
        for k in totals:
            totals[k] += _dec(ed["totals"].get(k))
        nps_count += _nps_count(ed["category_table"])
    txns.sort(key=lambda t: _date_key(t.get("date")))

    demat_rows = merge_demat(tagged_demat)
    mf_rows = merge_mf(tagged_mf)

    warnings: list[str] = []
    periods = {
        (
            (m["parsed"].get("statement_period") or {}).get("from", ""),
            (m["parsed"].get("statement_period") or {}).get("to", ""),
        )
        for m in members
    }
    froms = [p[0] for p in periods if p[0]]
    tos = [p[1] for p in periods if p[1]]
    period = {
        "from": min(froms, key=_date_key) if froms else "",
        "to": max(tos, key=_date_key) if tos else "",
    }
    if len(periods) > 1:
        warnings.append(
            "Statements cover different periods "
            f"({'; '.join(f'{a} to {b}' for a, b in sorted(periods))}). "
            "Combined values are as of each statement's own date."
        )

    by_pan: dict[str, list[str]] = {}
    for m in members:
        if m.get("pan") and m["pan"] != "N/A":
            by_pan.setdefault(m["pan"], []).append(m["filename"])
    for pan, files in by_pan.items():
        if len(files) > 1:
            warnings.append(
                f"{' and '.join(files)} belong to the same PAN ({pan}); their holdings were "
                "combined. Check the statements do not overlap."
            )

    owners = _joined(m["owner"] for m in members)
    pans = _joined(m.get("pan") if m.get("pan") != "N/A" else "" for m in members) or "N/A"
    investor_table = [
        ["Field", "Value"],
        ["Name", owners],
        ["Pan", pans],
        ["Members", len(members)],
    ]
    category_table = [
        ["Category", "Value", "Count"],
        ["Total Portfolio Value", str(totals["total_portfolio_value"]), ""],
        ["Demat", str(totals["demat_value"]), len(demat_rows)],
        ["Insurance", "0", 0],
        ["Mutual Funds", str(totals["mf_value"]), len(mf_rows)],
        ["Nps", str(totals["nps_value"]), nps_count],
    ]
    metadata_table = [
        ["Field", "Value"],
        ["CAS Type", "FAMILY"],
        ["Generated At", datetime.now().strftime("%Y-%m-%dT%H:%M:%S")],
        ["Period From", period["from"]],
        ["Period To", period["to"]],
    ]
    shared = {
        "investor_table": investor_table,
        "category_table": category_table,
        "metadata_table": metadata_table,
        "totals": {k: str(v) for k, v in totals.items()},
    }
    return {
        "parsed": {
            "file_type": "FAMILY",
            "statement_period": period,
            "investor_info": {"name": owners},
        },
        "export_data": {**shared, "demat_rows": demat_rows, "mf_rows": mf_rows, "txn_rows": txns},
        "file_export": {
            **shared,
            "demat_rows": tagged_demat,
            "mf_rows": tagged_mf,
            "txn_rows": txns,
        },
        "warnings": warnings,
    }
