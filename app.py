"""
CAS Parser & Portfolio Advisory Web Application
Built with Streamlit.
Allows users to upload CAS statements (CDSL, NSDL, CAMS, KFintech),
inspect holdings and mutual funds, cross-reference against Equity Portfolio Advisory,
and download the full results in Excel (.xlsx), CSV, and JSON formats.
"""

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import casparser
from advisory import DEFAULT_ADVISORY_PATH, AdvisoryEngine, format_indian_number
from excel_exporter import (
    build_enriched_json,
    build_export_data,
    write_formatted_csv,
    write_formatted_excel,
)

# Page configuration
st.set_page_config(
    page_title="CAS Parser & Equity Advisory",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    /* Custom KPI Cards – replace st.metric to prevent truncation */
    .kpi-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 0.85rem 0.75rem;
        text-align: left;
        height: 100%;
        box-sizing: border-box;
    }
    .kpi-label {
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #6B7280;
        margin-bottom: 0.3rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .kpi-value {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1E3A8A;
        white-space: normal;
        word-break: break-all;
        line-height: 1.3;
        margin-bottom: 0.25rem;
    }
    .kpi-subtext {
        font-size: 0.72rem;
        color: #6B7280;
        white-space: normal;
        word-break: break-word;
        line-height: 1.4;
    }
    /* Force Streamlit column containers to full height */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        display: flex;
        flex-direction: column;
    }
    .badge-buy {
        background-color: #DCFCE7;
        color: #166534;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 6px;
    }
    .badge-hold {
        background-color: #FEF9C3;
        color: #854D0E;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 6px;
    }
    .badge-sell {
        background-color: #FEE2E2;
        color: #991B1B;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 6px;
    }
    .badge-na {
        background-color: #F3F4F6;
        color: #4B5563;
        padding: 3px 8px;
        border-radius: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_advisory_engine(advisory_file_bytes: bytes = None):
    """Loads and caches the AdvisoryEngine."""
    if advisory_file_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(advisory_file_bytes)
            tmp_path = Path(tmp.name)
        return AdvisoryEngine(advisory_path=tmp_path)
    return AdvisoryEngine(advisory_path=DEFAULT_ADVISORY_PATH)


def parse_cas_file(pdf_bytes: bytes, filename: str, password: str, advisory_engine: AdvisoryEngine):
    """Parses CAS PDF and generates structured outputs in memory."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf_path = Path(tmp_pdf.name)

    try:
        json_str = casparser.read_cas_pdf(str(tmp_pdf_path), password=password or "", output="json")
        parsed = json.loads(json_str)

        # Build harmonized export data
        export_data = build_export_data(parsed, pdf_path=tmp_pdf_path)

        # Re-evaluate with specific advisory engine instance if needed
        if advisory_engine:
            advisory_data = advisory_engine.evaluate_holdings(export_data["demat_rows"])
            export_data["advisory_data"] = advisory_data
            eval_map = {h.get("isin", "").upper(): h for h in advisory_data.get("holdings", [])}
            for d_row in export_data["demat_rows"]:
                isin_key = d_row.get("isin", "").upper()
                matched = eval_map.get(isin_key)
                if matched:
                    d_row["advisory_view"] = matched.get("advisory_view", "Not Covered")
                    d_row["advisory_ticker"] = matched.get("advisory_ticker", "N/A")
                    d_row["advisory_stock_name"] = matched.get("advisory_stock_name", "N/A")
                else:
                    d_row["advisory_view"] = "Not Covered"
                    d_row["advisory_ticker"] = "N/A"
                    d_row["advisory_stock_name"] = "N/A"

        # Build enriched JSON with advisory evaluations and Indian-formatted values
        enriched_json = build_enriched_json(parsed, export_data)
        enriched_json_str = json.dumps(enriched_json, indent=2, default=str)

        # Generate Excel in memory
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_xlsx:
            xlsx_path = Path(tmp_xlsx.name)
        write_formatted_excel(export_data, xlsx_path)
        excel_bytes = xlsx_path.read_bytes()
        try:
            xlsx_path.unlink()
        except Exception:
            pass

        # Generate CSV in memory
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
            csv_path = Path(tmp_csv.name)
        write_formatted_csv(export_data, csv_path)
        csv_bytes = csv_path.read_bytes()
        try:
            csv_path.unlink()
        except Exception:
            pass

        return {
            "parsed": parsed,
            "enriched_json": enriched_json,
            "export_data": export_data,
            "json_str": enriched_json_str,
            "excel_bytes": excel_bytes,
            "csv_bytes": csv_bytes,
            "error": None,
        }

    except casparser.exceptions.IncorrectPasswordError:
        return {
            "error": "Incorrect password. If this CAS PDF is password protected, please enter the correct password."
        }
    except Exception as e:
        return {"error": f"Error parsing statement: {str(e)}"}
    finally:
        try:
            tmp_pdf_path.unlink()
        except Exception:
            pass


def main():
    # Sidebar
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/portfolio.png", width=64)
        st.title("CAS & Advisory")
        st.markdown("Consolidated Account Statement Parser with Equity Portfolio Advisory.")

        st.markdown("---")
        st.subheader("📚 Advisory Database")
        custom_advisory_file = st.file_uploader(
            "Upload Custom Advisory (.xlsx)",
            type=["xlsx"],
            help="Optionally upload a custom 'Equity Portfolio Advisory.xlsx'. Defaults to the data folder.",
        )

        advisory_bytes = custom_advisory_file.read() if custom_advisory_file else None
        advisory_engine = get_advisory_engine(advisory_bytes)

        if advisory_engine.df is not None and not advisory_engine.df.empty:
            st.success(f"Advisory Loaded: **{len(advisory_engine.df)} stocks**")
        else:
            st.warning("Advisory file not loaded.")

        st.markdown("---")
        st.markdown("### 💡 Quick Sample Test")
        input_dir = Path(__file__).resolve().parent / "input"
        available_samples = sorted(list(input_dir.glob("*.pdf")))
        use_sample = False
        sample_path = None

        if available_samples:
            unprotected = [f for f in available_samples if "Protected" not in f.name]
            default_sample = unprotected[0] if unprotected else available_samples[0]
            selected_sample = st.selectbox(
                "Select Sample File:",
                options=available_samples,
                format_func=lambda p: p.name,
                index=available_samples.index(default_sample),
            )
            if st.button("🚀 Load Sample Statement"):
                use_sample = True
                sample_path = selected_sample

        st.markdown("---")
        st.caption("Powered by **casparser** & **openpyxl** | © 2026 Aditya Dhikale")

    # Main Header
    st.markdown(
        "<div class='main-header'>📈 CAS Statement Parser & Portfolio Advisory</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='sub-header'>Upload your NSDL / CDSL / CAMS / KFintech CAS PDF to extract holdings, mutual funds, and cross-reference your equity portfolio against research advisory recommendations.</div>",
        unsafe_allow_html=True,
    )

    # Upload Section
    col_upload, col_pw = st.columns([3, 2])
    with col_upload:
        uploaded_file = st.file_uploader(
            "Upload CAS Statement (PDF)",
            type=["pdf"],
            help="Supports CDSL, NSDL, CAMS, and KFintech CAS PDF statements.",
        )
    with col_pw:
        password = st.text_input(
            "PDF Password (if protected)",
            type="password",
            help="Usually PAN (UPPERCASE) or DOB (DDMMYYYY) or as specified by the issuer. Leave empty if none.",
        )
        parse_btn = st.button("🚀 Parse Statement", type="primary", use_container_width=True)

    if parse_btn:
        if uploaded_file is None:
            st.warning("⚠️ Please upload a CAS PDF statement first.")
        else:
            with st.spinner("Processing CAS statement and analyzing equity advisory..."):
                file_bytes = uploaded_file.read()
                res = parse_cas_file(file_bytes, uploaded_file.name, password, advisory_engine)
                if res.get("error"):
                    st.error(res["error"])
                else:
                    st.session_state["parsed_result"] = res
                    st.session_state["filename"] = uploaded_file.name

    elif use_sample and sample_path and sample_path.exists():
        with st.spinner("Processing sample CAS statement..."):
            file_bytes = sample_path.read_bytes()
            res = parse_cas_file(file_bytes, sample_path.name, password, advisory_engine)
            if res.get("error"):
                st.error(res["error"])
            else:
                st.session_state["parsed_result"] = res
                st.session_state["filename"] = sample_path.name

    if "parsed_result" in st.session_state:
        result = st.session_state["parsed_result"]
        filename_to_parse = st.session_state.get("filename", "CAS_Statement.pdf")

        export_data = result["export_data"]
        parsed = result["parsed"]
        totals = export_data["totals"]
        investor = parsed.get("investor_info") or {}
        period = parsed.get("statement_period") or {}
        period_str = (
            f"{period.get('from', '')} to {period.get('to', '')}" if period.get("from") else ""
        )
        advisory_res = export_data.get("advisory_data") or {}

        st.success(
            f"✅ Statement parsed successfully! {f'Period: {period_str}' if period_str else ''}"
        )

        # Top KPI Cards – custom HTML to show full values without truncation
        def kpi_card(label: str, value: str, subtext: str = "") -> str:
            sub_html = f"<div class='kpi-subtext'>{subtext}</div>" if subtext else ""
            return (
                f"<div class='kpi-card'>"
                f"<div class='kpi-label'>{label}</div>"
                f"<div class='kpi-value'>{value}</div>"
                f"{sub_html}"
                f"</div>"
            )

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(
                kpi_card(
                    "Total Portfolio Value",
                    format_indian_number(totals["total_portfolio_value"], prefix="₹"),
                ),
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                kpi_card(
                    "Demat Holdings",
                    format_indian_number(totals["demat_value"], prefix="₹"),
                    f"📦 {len(export_data['demat_rows'])} items",
                ),
                unsafe_allow_html=True,
            )
        with m3:
            st.markdown(
                kpi_card(
                    "Mutual Funds",
                    format_indian_number(totals["mf_value"], prefix="₹"),
                    f"📈 {len(export_data['mf_rows'])} schemes",
                ),
                unsafe_allow_html=True,
            )
        with m4:
            pan_val = (
                export_data["investor_table"][6][1]
                if len(export_data["investor_table"]) > 6
                else "N/A"
            )
            st.markdown(
                kpi_card(
                    "Investor",
                    investor.get("name", "N/A"),
                    f"PAN: {pan_val}",
                ),
                unsafe_allow_html=True,
            )

        # Download Buttons Bar
        st.markdown("### 📥 Download Reports")
        base_name = Path(filename_to_parse).stem or "CAS_Report"
        d1, d2, d3 = st.columns(3)
        with d1:
            st.download_button(
                label="📊 Download Excel (.xlsx)",
                data=result["excel_bytes"],
                file_name=f"{base_name}_with_advisory.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                label="📄 Download Formatted CSV (.csv)",
                data=result["csv_bytes"],
                file_name=f"{base_name}_formatted.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with d3:
            st.download_button(
                label="🗂️ Download Raw JSON (.json)",
                data=result["json_str"],
                file_name=f"{base_name}_parsed.json",
                mime="application/json",
                use_container_width=True,
            )

        st.markdown("---")

        # Tabs for structured viewing
        tab_adv, tab_demat, tab_mf, tab_txn, tab_inv, tab_json = st.tabs(
            [
                "🎯 Equity Advisory",
                "🏢 Demat Holdings",
                "📈 Mutual Funds",
                "📝 Transactions",
                "👤 Investor & Summary",
                "🔍 Raw JSON",
            ]
        )

        # TAB 1: Equity Advisory
        with tab_adv:
            st.subheader("🎯 Equity Portfolio Advisory & Recommendations")
            holdings = advisory_res.get("holdings", [])
            summary = advisory_res.get("summary", {})

            if holdings:
                # Summary badges
                s_cols = st.columns(6)
                actions = [
                    ("BUY", "🟢"),
                    ("HOLD", "🟡"),
                    ("SELL", "🔴"),
                    ("ADD", "🟢"),
                    ("TRIM", "🔴"),
                    ("Not Covered", "⚪"),
                ]
                for idx, (act, emoji) in enumerate(actions):
                    with s_cols[idx]:
                        cnt = summary.get(act, {}).get("count", 0)
                        val = summary.get(act, {}).get("value", 0)
                        formatted_val = format_indian_number(val, prefix="₹")
                        st.markdown(
                            f"**{emoji} {act}**<br><span style='font-size:1.3rem;font-weight:700'>{cnt}</span> stocks<br><span style='font-size:0.85rem;color:#6B7280'>{formatted_val}</span>",
                            unsafe_allow_html=True,
                        )

                st.markdown("<br>", unsafe_allow_html=True)

                adv_df = pd.DataFrame(holdings)

                # Filter option
                filter_choice = st.selectbox(
                    "Filter by Recommendation:",
                    options=["All"] + sorted(list(adv_df["advisory_view"].unique())),
                )
                filtered_df = (
                    adv_df
                    if filter_choice == "All"
                    else adv_df[adv_df["advisory_view"] == filter_choice]
                )

                # Format columns for display (Indian Numbering System)
                display_df = filtered_df[
                    [
                        "demat_stock_name",
                        "advisory_view",
                        "advisory_ticker",
                        "advisory_stock_name",
                        "units",
                        "value",
                        "isin",
                        "match_type",
                    ]
                ].copy()
                display_df.columns = [
                    "Security (Demat)",
                    "Advisory View",
                    "Ticker",
                    "Advisory Security",
                    "Units",
                    "Value (₹)",
                    "ISIN",
                    "Match Basis",
                ]
                display_df["Value (₹)"] = display_df["Value (₹)"].apply(
                    lambda x: format_indian_number(x, prefix="₹")
                )
                display_df["Units"] = display_df["Units"].apply(
                    lambda x: format_indian_number(x, prefix="", decimals=3)
                )

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    height=350,
                    column_config={
                        "Security (Demat)": st.column_config.TextColumn(
                            "Security (Demat)", width="large"
                        ),
                        "Advisory Security": st.column_config.TextColumn(
                            "Advisory Security", width="large"
                        ),
                        "Advisory View": st.column_config.TextColumn(
                            "Advisory View", width="small"
                        ),
                        "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                        "Value (₹)": st.column_config.TextColumn("Value (₹)", width="medium"),
                        "Units": st.column_config.TextColumn("Units", width="small"),
                        "ISIN": st.column_config.TextColumn("ISIN", width="medium"),
                        "Match Basis": st.column_config.TextColumn("Match Basis", width="small"),
                    },
                )
            else:
                st.info("No equity holdings found to cross-reference.")

        # TAB 2: Demat Holdings
        with tab_demat:
            st.subheader("🏢 Demat Equities & Bonds")
            if export_data["demat_rows"]:
                demat_df = pd.DataFrame(export_data["demat_rows"])
                demat_cols = [
                    c
                    for c in [
                        "name",
                        "advisory_view",
                        "advisory_ticker",
                        "units",
                        "value",
                        "category",
                        "isin",
                        "dp_name",
                        "bo_id",
                    ]
                    if c in demat_df.columns
                ]
                demat_display = demat_df[demat_cols].copy()
                if "value" in demat_display:
                    demat_display["value"] = demat_display["value"].apply(
                        lambda x: format_indian_number(x, prefix="₹")
                    )
                if "units" in demat_display:
                    demat_display["units"] = demat_display["units"].apply(
                        lambda x: format_indian_number(x, prefix="", decimals=3)
                    )
                col_rename = {
                    "name": "Security Name",
                    "advisory_view": "Advisory View",
                    "advisory_ticker": "Ticker",
                    "units": "Units",
                    "value": "Value (₹)",
                    "category": "Category",
                    "isin": "ISIN",
                    "dp_name": "DP Name",
                    "bo_id": "BO ID",
                }
                demat_display.rename(columns=col_rename, inplace=True)
                st.dataframe(
                    demat_display,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "Security Name": st.column_config.TextColumn(
                            "Security Name", width="large"
                        ),
                        "Advisory View": st.column_config.TextColumn(
                            "Advisory View", width="small"
                        ),
                        "Ticker": st.column_config.TextColumn("Ticker", width="small"),
                        "Value (₹)": st.column_config.TextColumn("Value (₹)", width="medium"),
                        "Units": st.column_config.TextColumn("Units", width="small"),
                        "Category": st.column_config.TextColumn("Category", width="small"),
                        "ISIN": st.column_config.TextColumn("ISIN", width="medium"),
                        "DP Name": st.column_config.TextColumn("DP Name", width="medium"),
                    },
                )
            else:
                st.info("No Demat holdings present in this statement.")

        # TAB 3: Mutual Funds
        with tab_mf:
            st.subheader("📈 Mutual Fund Schemes")
            if export_data["mf_rows"]:
                mf_df = pd.DataFrame(export_data["mf_rows"])
                cols_to_show = [
                    "scheme_name",
                    "amc",
                    "units",
                    "nav",
                    "value",
                    "cost",
                    "folio_number",
                ]
                existing_cols = [c for c in cols_to_show if c in mf_df.columns]
                mf_display = mf_df[existing_cols].copy()
                if "value" in mf_display:
                    mf_display["value"] = mf_display["value"].apply(
                        lambda x: format_indian_number(x, prefix="₹")
                    )
                if "cost" in mf_display:
                    mf_display["cost"] = mf_display["cost"].apply(
                        lambda x: format_indian_number(x, prefix="₹")
                    )
                if "nav" in mf_display:
                    mf_display["nav"] = mf_display["nav"].apply(
                        lambda x: format_indian_number(x, prefix="₹")
                    )
                if "units" in mf_display:
                    mf_display["units"] = mf_display["units"].apply(
                        lambda x: format_indian_number(x, prefix="", decimals=3)
                    )
                st.dataframe(
                    mf_display,
                    use_container_width=True,
                    height=400,
                    column_config={
                        "scheme_name": st.column_config.TextColumn("Scheme Name", width="large"),
                        "amc": st.column_config.TextColumn("AMC", width="medium"),
                        "value": st.column_config.TextColumn("Value (₹)", width="medium"),
                        "cost": st.column_config.TextColumn("Cost (₹)", width="medium"),
                        "nav": st.column_config.TextColumn("NAV (₹)", width="small"),
                        "units": st.column_config.TextColumn("Units", width="small"),
                        "folio_number": st.column_config.TextColumn("Folio", width="small"),
                    },
                )
            else:
                st.info("No Mutual Fund holdings present in this statement.")

        # TAB 4: Transactions
        with tab_txn:
            st.subheader("📝 Transactions")
            if export_data["txn_rows"]:
                txn_df = pd.DataFrame(export_data["txn_rows"]).copy()
                if "amount" in txn_df:
                    txn_df["amount"] = txn_df["amount"].apply(
                        lambda x: format_indian_number(x, prefix="₹")
                    )
                if "nav" in txn_df:
                    txn_df["nav"] = txn_df["nav"].apply(
                        lambda x: format_indian_number(x, prefix="₹")
                    )
                if "units" in txn_df:
                    txn_df["units"] = txn_df["units"].apply(
                        lambda x: format_indian_number(x, prefix="", decimals=3)
                    )
                if "balance" in txn_df:
                    txn_df["balance"] = txn_df["balance"].apply(
                        lambda x: format_indian_number(x, prefix="", decimals=3)
                    )
                st.dataframe(txn_df, use_container_width=True, height=400)
            else:
                st.info("No transactions recorded in this statement period.")

        # TAB 5: Investor & Summary
        with tab_inv:
            col_i, col_c = st.columns(2)
            with col_i:
                st.subheader("Investor Details")
                inv_df = pd.DataFrame(export_data["investor_table"][1:], columns=["Field", "Value"])
                st.table(inv_df)
            with col_c:
                st.subheader("Portfolio Breakdown")
                cat_df = pd.DataFrame(
                    export_data["category_table"][1:],
                    columns=["Category", "Value (₹)", "Count"],
                )
                cat_df["Value (₹)"] = cat_df["Value (₹)"].apply(
                    lambda x: format_indian_number(x, prefix="₹")
                )
                st.table(cat_df)

        # TAB 6: Enriched JSON
        with tab_json:
            st.subheader("🔍 Structured JSON (with Equity Advisory & Indian Formatting)")
            st.json(result.get("enriched_json", parsed))


if __name__ == "__main__":
    main()
