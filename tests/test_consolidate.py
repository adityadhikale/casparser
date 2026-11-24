"""Tests for consolidating several members' statements (consolidate.py). No PDFs needed."""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from consolidate import merge_demat, merge_family, merge_mf  # noqa: E402


def _demat(isin, units, value, owner="", **kw):
    return {
        "demat_type": "cdsl",
        "dp_id": "123",
        "dp_name": "DP",
        "client_id": "9",
        "bo_id": "1239",
        "category": "equities",
        "isin": isin,
        "name": f"Stock {isin}",
        "units": str(units),
        "value": str(value),
        "owner": owner,
        **kw,
    }


def _mf(isin, units, value, cost, owner="", folio="F1"):
    return {
        "folio_number": folio,
        "scheme_name": f"Fund {isin}",
        "isin": isin,
        "units": str(units),
        "nav": "10",
        "value": str(value),
        "cost": str(cost),
        "gain_absolute": "",
        "gain_percentage": "",
        "folio_pan": "PAN" + owner,
        "owner": owner,
    }


def _member(owner, pan, demat, mf, period=("2025-01-01", "2025-03-31"), fname=None):
    dv = sum(Decimal(r["value"]) for r in demat)
    mv = sum(Decimal(r["value"]) for r in mf)
    return {
        "owner": owner,
        "pan": pan,
        "filename": fname or owner,
        "parsed": {"statement_period": {"from": period[0], "to": period[1]}},
        "export_data": {
            "demat_rows": demat,
            "mf_rows": mf,
            "txn_rows": [{"date": "2025-02-01", "amount": "5"}],
            "category_table": [["Category", "Value", "Count"], ["Nps", "0", 0]],
            "totals": {
                "total_portfolio_value": str(dv + mv),
                "demat_value": str(dv),
                "mf_value": str(mv),
                "nps_value": "0",
            },
        },
    }


def test_merge_demat_sums_same_isin_and_tracks_owners():
    rows = [_demat("INE1", 10, 100, "A"), _demat("INE1", 5, 60, "B"), _demat("INE2", 1, 9, "A")]
    out = merge_demat(rows)
    assert len(out) == 2
    one = next(r for r in out if r["isin"] == "INE1")
    assert Decimal(one["units"]) == 15 and Decimal(one["value"]) == 160
    assert one["owner"] == "A, B"


def test_merge_demat_marks_differing_accounts_and_keeps_isinless_rows():
    a = _demat("INE1", 1, 1, "A")
    b = _demat("INE1", 1, 1, "B", dp_name="Other DP")
    out = merge_demat([a, b, _demat("", 2, 2, "A")])
    assert len(out) == 2
    assert out[0]["dp_name"] == "Multiple" and out[0]["dp_id"] == "123"


def test_merge_mf_recomputes_gain():
    out = merge_mf([_mf("INF1", 10, 150, 100, "A"), _mf("INF1", 10, 150, 100, "B", folio="F2")])
    (row,) = out
    assert Decimal(row["value"]) == 300 and Decimal(row["cost"]) == 200
    assert Decimal(row["gain_absolute"]) == 100 and Decimal(row["gain_percentage"]) == 50
    assert row["folio_number"] == "F1, F2" and row["owner"] == "A, B"


def test_merge_mf_unknown_cost_blanks_gain():
    out = merge_mf([_mf("INF1", 1, 10, 5, "A"), {**_mf("INF1", 1, 10, 5, "B"), "cost": ""}])
    assert out[0]["cost"] == "" and out[0]["gain_percentage"] == ""


def test_merge_family_totals_owner_tagging_and_file_export():
    a = _member("A", "PANA", [_demat("INE1", 10, 100)], [_mf("INF1", 1, 50, 40)])
    b = _member("B", "PANB", [_demat("INE1", 5, 60)], [])
    r = merge_family([a, b])
    assert r["export_data"]["totals"]["total_portfolio_value"] == "210"
    assert len(r["export_data"]["demat_rows"]) == 1  # display view merges same ISIN
    assert len(r["file_export"]["demat_rows"]) == 2  # download view keeps per-member rows
    assert {x["owner"] for x in r["file_export"]["demat_rows"]} == {"A", "B"}
    assert r["export_data"]["investor_table"][1] == ["Name", "A, B"]
    assert r["warnings"] == []
    # members' own data must not be mutated
    assert (
        "owner" not in a["export_data"]["demat_rows"][0]
        or a["export_data"]["demat_rows"][0]["owner"] == ""
    )


def test_merge_family_warns_on_period_mismatch_and_same_pan():
    a = _member("A", "PANX", [], [], period=("2025-01-01", "2025-03-31"), fname="a")
    b = _member("B", "PANX", [], [], period=("2025-02-01", "2025-04-30"), fname="b")
    r = merge_family([a, b])
    assert r["parsed"]["statement_period"] == {"from": "2025-01-01", "to": "2025-04-30"}
    text = " | ".join(r["warnings"])
    assert "different periods" in text and "same PAN" in text


def test_excel_export_with_transactions_does_not_crash(tmp_path):
    """Regression: the Transactions sheet used an undefined variable and crashed any statement with txns."""
    from excel_exporter import write_formatted_csv, write_formatted_excel

    m = _member("A", "PANA", [_demat("INE1", 10, 100)], [_mf("INF1", 1, 50, 40)])
    data = merge_family([m])["file_export"]
    data["txn_rows"] = [{"date": "2025-02-01", "amount": "5", "units": "1.5", "owner": "A"}]
    write_formatted_excel(data, tmp_path / "x.xlsx")
    write_formatted_csv(data, tmp_path / "x.csv")
    assert (tmp_path / "x.xlsx").stat().st_size > 0


def test_period_and_txn_order_use_real_dates_not_text():
    a = _member("A", "PA", [], [], period=("15-Jan-2026", "20-Jan-2026"), fname="a")
    b = _member("B", "PB", [], [], period=("01-Feb-2026", "28-Feb-2026"), fname="b")
    a["export_data"]["txn_rows"] = [{"date": "15-Jan-2026"}]
    b["export_data"]["txn_rows"] = [{"date": "01-Feb-2026"}]
    r = merge_family([b, a])
    assert r["parsed"]["statement_period"] == {"from": "15-Jan-2026", "to": "28-Feb-2026"}
    assert [t["date"] for t in r["export_data"]["txn_rows"]] == ["15-Jan-2026", "01-Feb-2026"]
