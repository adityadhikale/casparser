"""
CAS Parser Export Formatter
Produces:
1. Exact formatted stacked CSV matching casparser web format:
   - Section 1: Field,Value (Investor Info)
   - Section 2: Category,Value,Count (Portfolio Summary)
   - Section 3: folio_number,amc,registrar,scheme_name... (Mutual Funds)
   - Section 4: folio_number,amc,scheme_name... (Transactions)
   - Section 5: demat_type,dp_id,dp_name,client_id,bo_id,category,isin...
   - Section 6: Field,Value (Metadata)
2. Multi-tab Excel (.xlsx) workbook containing:
   - 'CAS_Report_Combined': The complete stacked report matching the above
   - 'Investor & Summary': Investor Info & Category Valuation
   - 'Mutual Funds': Clean spreadsheet of all MF schemes
   - 'Demat Holdings': Clean spreadsheet of all Demat equities & bonds
   - 'Transactions': Clean spreadsheet of all transactions (if present)
"""

import csv
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import openpyxl
import pypdfium2 as pdfium
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

KNOWN_AMCS = [
    ("Axis", "Axis"),
    ("Canara Robeco", "Canara Robeco"),
    ("PGIM", "PGIM India"),
    ("Parag Parikh", "PPFAS"),
    ("PPFAS", "PPFAS"),
    ("quant", "quant"),
    ("HDFC", "HDFC"),
    ("ICICI", "ICICI Prudential"),
    ("SBI", "SBI"),
    ("Mirae", "Mirae Asset"),
    ("Nippon", "Nippon India"),
    ("Kotak", "Kotak"),
    ("Tata", "Tata"),
    ("Aditya Birla", "Aditya Birla Sun Life"),
    ("ABSL", "Aditya Birla Sun Life"),
    ("DSP", "DSP"),
    ("UTI", "UTI"),
    ("Motilal", "Motilal Oswal"),
    ("Bandhan", "Bandhan"),
    ("Edelweiss", "Edelweiss"),
    ("Franklin", "Franklin Templeton"),
    ("Invesco", "Invesco"),
    ("Sundaram", "Sundaram"),
    ("HSBC", "HSBC"),
    ("WhiteOak", "WhiteOak Capital"),
    ("Navi", "Navi"),
    ("Groww", "Groww"),
    ("Zerodha", "Zerodha"),
    ("Trust", "Trust"),
    ("Samco", "Samco"),
    ("Helios", "Helios"),
    ("Bajaj", "Bajaj Finserv"),
    ("Union", "Union"),
    ("Baroda", "Baroda BNP Paribas"),
    ("Quantum", "Quantum"),
    ("JM", "JM Financial"),
    ("LIC", "LIC"),
]


def clean_excel_value(val):
    """Sanitizes text to remove non-printable/illegal OpenXML characters."""
    if isinstance(val, str):
        return ILLEGAL_CHARACTERS_RE.sub("", val).strip()
    return val


def parse_pincode(address: str) -> str:
    if not address:
        return ""
    m = re.search(r"\b([1-9][0-9]{5})\b", address)
    return m.group(1) if m else ""


def parse_cas_id(text_or_address: str, filename: str = "") -> str:
    if text_or_address:
        m = re.search(r"(?:CAS|NSDL)\s*ID\s*:\s*([A-Za-z0-9]+)", text_or_address, re.I)
        if m:
            return m.group(1)
    if filename:
        m = re.search(r"([A-Z]{2}\d{8})", filename)
        if m:
            return m.group(1)
    return ""


def extract_amc_name(scheme_name: str, fallback_amc: str = "") -> str:
    if fallback_amc and not fallback_amc.isupper() and len(fallback_amc) > 4:
        return fallback_amc
    for key, canonical in KNOWN_AMCS:
        if re.search(r"\b" + re.escape(key) + r"\b", scheme_name, re.I):
            return canonical
    return fallback_amc or (scheme_name.split()[0] if scheme_name else "")


def extract_cdsl_pdf_details(pdf_path: Path):
    """Extracts CDSL MF transactions, opening balances, and CAS ID directly from PDF text."""
    txns = []
    open_balances = {}
    cas_id = ""

    if not pdf_path or not pdf_path.exists():
        return txns, open_balances, cas_id

    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        for p_idx in range(min(3, len(doc))):
            t = doc[p_idx].get_textpage().get_text_range()
            m_id = re.search(r"CAS\s*ID\s*:\s*([A-Za-z0-9]+)", t, re.I)
            if m_id:
                cas_id = m_id.group(1)
                break

        for page in doc:
            text = page.get_textpage().get_text_range()
            if "MUTUAL FUND UNITS HELD WITH MF/RTA" not in text:
                continue

            blocks = re.split(r"\n(?=[A-Za-z0-9 ]+Mutual Fund)", text)
            for b in blocks:
                if "ISIN :" not in b or "Opening Balance" not in b:
                    continue
                isin_m = re.search(r"ISIN\s*:\s*([A-Z0-9]+)", b)
                if not isin_m:
                    continue
                isin = isin_m.group(1)
                amc_m = re.search(r"^([A-Za-z0-9 ]+) Mutual Fund", b.strip())
                amc = amc_m.group(1).strip() if amc_m else ""
                lines = [x.strip() for x in b.split("\n") if x.strip()]
                scheme_name = lines[1] if len(lines) > 1 else ""

                m = re.search(
                    r"Opening Balance\s+([\d.]+)\s+(.*?)\s+Closing Balance\s+([\d.]+)",
                    b,
                    re.DOTALL,
                )
                if m:
                    open_bal, txn_block, close_bal = m.groups()
                    open_balances[isin] = open_bal

                    date_m = re.search(r"(\d{2}-\d{2}-\d{4})\s+(.*)", txn_block.strip(), re.DOTALL)
                    if date_m:
                        dt, rest = date_m.groups()
                        tokens = rest.split()
                        if len(tokens) >= 7:
                            amt, nav, price, units, stamp, inc, cap = tokens[-7:]
                            desc = " ".join(tokens[:-7])
                            d, mo, yr = dt.split("-")
                            iso_date = f"{yr}-{mo}-{d}"

                            if stamp.startswith("."):
                                stamp = "0" + stamp

                            txns.append(
                                {
                                    "isin": isin,
                                    "amc": amc or extract_amc_name(scheme_name),
                                    "scheme_name": scheme_name,
                                    "date": iso_date,
                                    "type": "PURCHASE_SIP"
                                    if ("Systematic" in desc or "SIP" in desc)
                                    else "PURCHASE",
                                    "description": desc,
                                    "amount": amt,
                                    "units": units,
                                    "nav": nav,
                                    "balance": close_bal,
                                    "dividend_rate": "",
                                    "txn_capital_withdrawal": cap if cap != "" else "0",
                                    "txn_income_distribution": inc if inc != "" else "0",
                                    "txn_price": price,
                                    "txn_stamp_duty": stamp,
                                }
                            )
        doc.close()
    except Exception as e:
        print(f"Notice: Non-critical note during secondary PDF scan: {e}")

    return txns, open_balances, cas_id


def build_export_data(parsed: dict, pdf_path: Optional[Path] = None) -> dict:
    """Extracts and harmonizes data from parsed CAS dict (NSDL, CDSL, CAMS, KFintech)."""
    file_type = parsed.get("file_type", "")
    investor_info = parsed.get("investor_info") or {}
    statement_period = parsed.get("statement_period") or {}

    raw_address = investor_info.get("address", "")
    clean_address = re.sub(r"[\r\n]+", ", ", raw_address).strip(", ")

    name = investor_info.get("name", "")
    email = investor_info.get("email", "")
    mobile = investor_info.get("mobile", "")
    pincode = parse_pincode(raw_address)

    pdf_txns, pdf_open_bals, extracted_cas_id = (
        extract_cdsl_pdf_details(pdf_path) if pdf_path else ([], {}, "")
    )
    cas_id = extracted_cas_id or parse_cas_id(raw_address, pdf_path.name if pdf_path else "")

    pan = ""
    accounts = parsed.get("accounts") or []
    for acc in accounts:
        for owner in acc.get("owners") or []:
            if owner.get("PAN"):
                pan = owner.get("PAN")
                break
        if pan:
            break

    if not pan:
        for folio in parsed.get("folios") or []:
            if folio.get("PAN"):
                pan = folio.get("PAN")
                break

    demat_rows = []
    total_demat_value = Decimal(0)

    for acc in accounts:
        dp_id = acc.get("dp_id") or ""
        dp_name = acc.get("name") or ""
        client_id = acc.get("client_id") or ""
        bo_id = f"{dp_id}{client_id}" if dp_id and client_id else (client_id or dp_id)
        acc_type_str = acc.get("type", "")
        if "CDSL" in acc_type_str.upper() or file_type == "CDSL":
            d_type = "cdsl"
        elif "NSDL" in acc_type_str.upper() or file_type == "NSDL":
            d_type = "nsdl"
        else:
            d_type = file_type.lower() if file_type else "demat"

        for eq in acc.get("equities") or []:
            val = Decimal(str(eq.get("value") or 0))
            units = Decimal(str(eq.get("num_shares") or 0))
            if units == 0 and val == 0:
                continue
            total_demat_value += val
            demat_rows.append(
                {
                    "demat_type": d_type,
                    "dp_id": dp_id,
                    "dp_name": dp_name,
                    "client_id": client_id,
                    "bo_id": bo_id,
                    "category": "equities",
                    "isin": eq.get("isin", ""),
                    "name": clean_excel_value(eq.get("name") or eq.get("symbol") or ""),
                    "units": str(units),
                    "value": str(val),
                }
            )

        for b in acc.get("bonds") or []:
            val = Decimal(str(b.get("value") or 0))
            units = Decimal(str(b.get("num_bonds") or 0))
            if units == 0 and val == 0:
                continue
            total_demat_value += val
            demat_rows.append(
                {
                    "demat_type": d_type,
                    "dp_id": dp_id,
                    "dp_name": dp_name,
                    "client_id": client_id,
                    "bo_id": bo_id,
                    "category": "bonds",
                    "isin": b.get("isin", ""),
                    "name": clean_excel_value(b.get("name", "")),
                    "units": str(units),
                    "value": str(val),
                }
            )

    mf_rows = []
    total_mf_value = Decimal(0)
    isin_to_folio = {}

    for acc in accounts:
        for mf in acc.get("mutual_funds") or []:
            val = Decimal(str(mf.get("value") or 0))
            total_mf_value += val
            units = Decimal(str(mf.get("balance") or 0))
            nav = Decimal(str(mf.get("nav") or 0))
            cost = (
                Decimal(str(mf.get("total_cost") or 0))
                if mf.get("total_cost") is not None
                else None
            )

            gain_abs = (val - cost) if cost is not None else (mf.get("pnl"))
            gain_pct = (
                (((val - cost) / cost) * 100)
                if (cost and cost > 0)
                else (mf.get("return") or mf.get("return_"))
            )

            scheme_name = mf.get("name") or ""
            amc = extract_amc_name(scheme_name)
            isin = mf.get("isin", "")
            f_num = mf.get("folio") or acc.get("client_id") or ""
            if isin:
                isin_to_folio[isin] = (f_num, amc, scheme_name)

            open_u = pdf_open_bals.get(isin, "")

            mf_rows.append(
                {
                    "folio_number": f_num,
                    "amc": amc,
                    "registrar": "",
                    "scheme_name": scheme_name,
                    "isin": isin,
                    "type": mf.get("type") or "EQUITY",
                    "units": str(units),
                    "nav": str(nav),
                    "value": str(val),
                    "cost": str(cost) if cost is not None else "",
                    "gain_absolute": str(gain_abs) if gain_abs is not None else "",
                    "gain_percentage": str(gain_pct) if gain_pct is not None else "",
                    "nominees": "",
                    "info_advisor": "",
                    "info_arn_code": mf.get("amfi") or "",
                    "info_close_units": str(units),
                    "info_investment_value": str(cost) if cost is not None else "",
                    "info_open_units": open_u,
                    "kyc": "",
                    "folio_pan": pan,
                }
            )

    folios = parsed.get("folios") or []
    for folio in folios:
        f_num = folio.get("folio", "")
        f_amc = folio.get("amc", "")
        f_pan = folio.get("PAN") or pan
        f_kyc = folio.get("KYC") or ""

        for scheme in folio.get("schemes") or []:
            val_obj = scheme.get("valuation") or {}
            val = Decimal(str(val_obj.get("value") or 0))
            total_mf_value += val
            units = Decimal(str(scheme.get("close") or scheme.get("close_calculated") or 0))
            nav = Decimal(str(val_obj.get("nav") or 0))
            cost = (
                Decimal(str(val_obj.get("cost") or 0)) if val_obj.get("cost") is not None else None
            )

            gain_abs = (val - cost) if cost is not None else ""
            gain_pct = (((val - cost) / cost) * 100) if (cost and cost > 0) else ""

            s_name = scheme.get("scheme", "")
            isin = scheme.get("isin") or ""
            if isin:
                isin_to_folio[isin] = (f_num, f_amc, s_name)

            mf_rows.append(
                {
                    "folio_number": f_num,
                    "amc": f_amc,
                    "registrar": scheme.get("rta", ""),
                    "scheme_name": s_name,
                    "isin": isin,
                    "type": scheme.get("type") or "EQUITY",
                    "units": str(units),
                    "nav": str(nav),
                    "value": str(val),
                    "cost": str(cost) if cost is not None else "",
                    "gain_absolute": str(gain_abs) if gain_abs != "" else "",
                    "gain_percentage": str(gain_pct) if gain_pct != "" else "",
                    "nominees": ", ".join(scheme.get("nominees") or []),
                    "info_advisor": scheme.get("advisor") or "",
                    "info_arn_code": scheme.get("rta_code") or "",
                    "info_close_units": str(units),
                    "info_investment_value": str(cost) if cost is not None else "",
                    "info_open_units": str(scheme.get("open") or ""),
                    "kyc": f_kyc,
                    "folio_pan": f_pan,
                }
            )

    txn_rows = []
    if pdf_txns:
        for t in pdf_txns:
            isin = t["isin"]
            f_num, amc_name, s_name = isin_to_folio.get(isin, ("", t["amc"], t["scheme_name"]))
            t_row = dict(t)
            t_row["folio_number"] = f_num
            t_row["amc"] = amc_name
            t_row["scheme_name"] = s_name
            txn_rows.append(t_row)

    for folio in folios:
        f_num = folio.get("folio", "")
        f_amc = folio.get("amc", "")
        for scheme in folio.get("schemes") or []:
            s_name = scheme.get("scheme", "")
            s_isin = scheme.get("isin") or ""
            for t in scheme.get("transactions") or []:
                txn_rows.append(
                    {
                        "folio_number": f_num,
                        "amc": f_amc,
                        "scheme_name": s_name,
                        "isin": s_isin,
                        "date": t.get("date", ""),
                        "type": t.get("type", ""),
                        "description": t.get("description", ""),
                        "amount": t.get("amount", ""),
                        "units": t.get("units", ""),
                        "nav": t.get("nav", ""),
                        "balance": t.get("balance", ""),
                        "dividend_rate": t.get("dividend_rate", ""),
                        "txn_capital_withdrawal": "0",
                        "txn_income_distribution": "0",
                        "txn_price": t.get("nav", ""),
                        "txn_stamp_duty": "",
                    }
                )

    total_nps_value = Decimal(0)
    nps = parsed.get("nps")
    nps_count = 0
    if nps:
        for s in nps.get("schemes") or []:
            v = Decimal(str(s.get("value") or 0))
            total_nps_value += v
            nps_count += 1

    total_portfolio_value = total_demat_value + total_mf_value + total_nps_value

    investor_table = [
        ["Field", "Value"],
        ["Address", clean_address],
        ["Cas Id", cas_id],
        ["Email", email],
        ["Mobile", mobile],
        ["Name", name],
        ["Pan", pan],
        ["Pincode", pincode],
    ]

    category_table = [
        ["Category", "Value", "Count"],
        ["Total Portfolio Value", str(total_portfolio_value), ""],
        ["Demat", str(total_demat_value), len(demat_rows)],
        ["Insurance", "0", 0],
        ["Mutual Funds", str(total_mf_value), len(mf_rows)],
        ["Nps", str(total_nps_value), nps_count],
    ]

    metadata_table = [
        ["Field", "Value"],
        ["CAS Type", file_type],
        ["Generated At", datetime.now().strftime("%Y-%m-%dT%H:%M:%S")],
        ["Period From", statement_period.get("from", "")],
        ["Period To", statement_period.get("to", "")],
    ]

    return {
        "investor_table": investor_table,
        "category_table": category_table,
        "mf_rows": mf_rows,
        "txn_rows": txn_rows,
        "demat_rows": demat_rows,
        "metadata_table": metadata_table,
        "totals": {
            "total_portfolio_value": str(total_portfolio_value),
            "demat_value": str(total_demat_value),
            "mf_value": str(total_mf_value),
            "nps_value": str(total_nps_value),
        },
    }


def write_formatted_csv(export_data: dict, output_path: Path):
    """Writes the exact stacked multi-section CSV."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        for row in export_data["investor_table"]:
            writer.writerow(row)

        for row in export_data["category_table"]:
            writer.writerow(row)

        mf_headers = [
            "folio_number",
            "amc",
            "registrar",
            "scheme_name",
            "isin",
            "type",
            "units",
            "nav",
            "value",
            "cost",
            "gain_absolute",
            "gain_percentage",
            "nominees",
            "info_advisor",
            "info_arn_code",
            "info_close_units",
            "info_investment_value",
            "info_open_units",
            "kyc",
            "folio_pan",
        ]
        writer.writerow(mf_headers)
        for r in export_data["mf_rows"]:
            writer.writerow([r.get(h, "") for h in mf_headers])

        txn_headers = [
            "folio_number",
            "amc",
            "scheme_name",
            "isin",
            "date",
            "type",
            "description",
            "amount",
            "units",
            "nav",
            "balance",
            "dividend_rate",
            "txn_capital_withdrawal",
            "txn_income_distribution",
            "txn_price",
            "txn_stamp_duty",
        ]
        writer.writerow(txn_headers)
        for r in export_data["txn_rows"]:
            writer.writerow([r.get(h, "") for h in txn_headers])

        demat_headers = [
            "demat_type",
            "dp_id",
            "dp_name",
            "client_id",
            "bo_id",
            "category",
            "isin",
            "name",
            "units",
            "value",
        ]
        writer.writerow(demat_headers)
        for r in export_data["demat_rows"]:
            writer.writerow([r.get(h, "") for h in demat_headers])

        for row in export_data["metadata_table"]:
            writer.writerow(row)


def style_table_header(ws, row_idx, num_cols, fill_color="1F497D", font_color="FFFFFF"):
    fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
    font = Font(name="Calibri", size=11, bold=True, color=font_color)
    border = Border(bottom=Side(style="medium", color="000000"))
    for col_idx in range(1, num_cols + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.fill = fill
        cell.font = font
        cell.border = border
        cell.alignment = Alignment(horizontal="left", vertical="center")


def auto_fit_columns(ws, min_width=12, max_width=45):
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val = str(cell.value or "")
            if "\n" in val:
                val = val.split("\n")[0]
            max_len = max(max_len, len(val))
        ws.column_dimensions[col_letter].width = max(min(max_len + 3, max_width), min_width)


def write_formatted_excel(export_data: dict, output_path: Path):
    """Generates an Excel workbook with both combined and individual sheets."""
    wb = openpyxl.Workbook()

    ws_all = wb.active
    ws_all.title = "CAS_Report_Combined"

    current_row = 1

    def append_section(headers, data_rows, header_color="1F497D"):
        nonlocal current_row
        if headers:
            for c_idx, h in enumerate(headers, 1):
                cell = ws_all.cell(row=current_row, column=c_idx, value=h)
                cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
                cell.fill = PatternFill(
                    start_color=header_color,
                    end_color=header_color,
                    fill_type="solid",
                )
            current_row += 1

        for r in data_rows:
            for c_idx, val in enumerate(r, 1):
                val = clean_excel_value(val)
                try:
                    if isinstance(val, str) and val and re.match(r"^-?\d+(\.\d+)?$", val):
                        val = float(val) if "." in val else int(val)
                except ValueError:
                    pass
                ws_all.cell(row=current_row, column=c_idx, value=val)
            current_row += 1

    append_section(["Field", "Value"], export_data["investor_table"][1:], header_color="2F5597")
    append_section(
        export_data["category_table"][0],
        export_data["category_table"][1:],
        header_color="2F5597",
    )

    mf_headers = [
        "folio_number",
        "amc",
        "registrar",
        "scheme_name",
        "isin",
        "type",
        "units",
        "nav",
        "value",
        "cost",
        "gain_absolute",
        "gain_percentage",
        "nominees",
        "info_advisor",
        "info_arn_code",
        "info_close_units",
        "info_investment_value",
        "info_open_units",
        "kyc",
        "folio_pan",
    ]
    mf_data = [[r.get(h, "") for h in mf_headers] for r in export_data["mf_rows"]]
    append_section(mf_headers, mf_data, header_color="203764")

    txn_headers = [
        "folio_number",
        "amc",
        "scheme_name",
        "isin",
        "date",
        "type",
        "description",
        "amount",
        "units",
        "nav",
        "balance",
        "dividend_rate",
        "txn_capital_withdrawal",
        "txn_income_distribution",
        "txn_price",
        "txn_stamp_duty",
    ]
    txn_data = [[r.get(h, "") for h in txn_headers] for r in export_data["txn_rows"]]
    append_section(txn_headers, txn_data, header_color="203764")

    demat_headers = [
        "demat_type",
        "dp_id",
        "dp_name",
        "client_id",
        "bo_id",
        "category",
        "isin",
        "name",
        "units",
        "value",
    ]
    demat_data = [[r.get(h, "") for h in demat_headers] for r in export_data["demat_rows"]]
    append_section(demat_headers, demat_data, header_color="1F497D")
    append_section(["Field", "Value"], export_data["metadata_table"][1:], header_color="595959")

    auto_fit_columns(ws_all)

    ws_demat = wb.create_sheet(title="Demat Holdings")
    ws_demat.append(demat_headers)
    style_table_header(ws_demat, 1, len(demat_headers), fill_color="1F497D")
    for r in demat_data:
        ws_demat.append([clean_excel_value(v) for v in r])
    auto_fit_columns(ws_demat)

    ws_mf = wb.create_sheet(title="Mutual Funds")
    ws_mf.append(mf_headers)
    style_table_header(ws_mf, 1, len(mf_headers), fill_color="203764")
    for r in mf_data:
        ws_mf.append([clean_excel_value(v) for v in r])
    auto_fit_columns(ws_mf)

    if txn_data:
        ws_txn = wb.create_sheet(title="Transactions")
        ws_txn.append(txn_headers)
        style_table_header(ws_txn, 1, len(txn_headers), fill_color="2F5597")
        for r in txn_data:
            ws_txn.append([clean_excel_value(v) for v in r])
        auto_fit_columns(ws_txn)

    ws_sum = wb.create_sheet(title="Investor & Summary")
    ws_sum.append(["INVESTOR INFORMATION", ""])
    style_table_header(ws_sum, 1, 2, fill_color="1F497D")
    for row in export_data["investor_table"][1:]:
        ws_sum.append([clean_excel_value(v) for v in row])

    ws_sum.append([])
    start_r = ws_sum.max_row + 1
    ws_sum.append(export_data["category_table"][0])
    style_table_header(ws_sum, start_r, 3, fill_color="2F5597")
    for row in export_data["category_table"][1:]:
        ws_sum.append([clean_excel_value(v) for v in row])

    ws_sum.append([])
    start_m = ws_sum.max_row + 1
    ws_sum.append(["STATEMENT METADATA", ""])
    style_table_header(ws_sum, start_m, 2, fill_color="595959")
    for row in export_data["metadata_table"][1:]:
        ws_sum.append([clean_excel_value(v) for v in row])

    auto_fit_columns(ws_sum)

    wb.save(output_path)
