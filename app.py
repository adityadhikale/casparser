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
from advisory import DEFAULT_ADVISORY_PATH, AdvisoryEngine
from excel_exporter import (
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
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
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
            "export_data": export_data,
            "json_str": json_str,
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
        sample_path = Path(__file__).resolve().parent / "input" / "OCT2026_AA10459269.pdf"
        use_sample = False
        if sample_path.exists():
            if st.button("Load Sample Statement (CDSL)"):
                use_sample = True

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

    file_to_parse = None
    filename_to_parse = ""

    if uploaded_file is not None:
        file_to_parse = uploaded_file.read()
        filename_to_parse = uploaded_file.name
    elif use_sample and sample_path.exists():
        file_to_parse = sample_path.read_bytes()
        filename_to_parse = sample_path.name
        st.info(f"Loaded sample file: `{filename_to_parse}`")

    if file_to_parse:
        with st.spinner("Processing CAS statement and analyzing equity advisory..."):
            result = parse_cas_file(file_to_parse, filename_to_parse, password, advisory_engine)

        if result.get("error"):
            st.error(result["error"])
            return

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

        # Top KPI Metrics Cards
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Total Portfolio Value", f"₹{float(totals['total_portfolio_value']):,.2f}")
        with m2:
            st.metric(
                "Demat Holdings",
                f"₹{float(totals['demat_value']):,.2f}",
                f"{len(export_data['demat_rows'])} items",
            )
        with m3:
            st.metric(
                "Mutual Funds",
                f"₹{float(totals['mf_value']):,.2f}",
                f"{len(export_data['mf_rows'])} schemes",
            )
        with m4:
            st.metric(
                "Investor",
                investor.get("name", "N/A"),
                f"PAN: {export_data['investor_table'][6][1]}",
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
                        st.markdown(
                            f"**{emoji} {act}**<br><span style='font-size:1.3rem;font-weight:700'>{cnt}</span> stocks<br><span style='font-size:0.85rem;color:#6B7280'>₹{float(val):,.2f}</span>",
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

                # Format columns for display
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
                    lambda x: f"₹{float(x):,.2f}" if x else "₹0.00"
                )

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    height=350,
                )
            else:
                st.info("No equity holdings found to cross-reference.")

        # TAB 2: Demat Holdings
        with tab_demat:
            st.subheader("🏢 Demat Equities & Bonds")
            if export_data["demat_rows"]:
                demat_df = pd.DataFrame(export_data["demat_rows"])
                demat_display = demat_df[
                    ["name", "category", "units", "value", "isin", "dp_name", "bo_id"]
                ].copy()
                demat_display.columns = [
                    "Security Name",
                    "Category",
                    "Units",
                    "Value (₹)",
                    "ISIN",
                    "DP Name",
                    "BO ID",
                ]
                demat_display["Value (₹)"] = demat_display["Value (₹)"].apply(
                    lambda x: f"₹{float(x):,.2f}" if x else "₹0.00"
                )
                st.dataframe(demat_display, use_container_width=True, height=400)
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
                mf_display["value"] = mf_display["value"].apply(
                    lambda x: f"₹{float(x):,.2f}" if x else "₹0.00"
                )
                st.dataframe(mf_display, use_container_width=True, height=400)
            else:
                st.info("No Mutual Fund holdings present in this statement.")

        # TAB 4: Transactions
        with tab_txn:
            st.subheader("📝 Transactions")
            if export_data["txn_rows"]:
                txn_df = pd.DataFrame(export_data["txn_rows"])
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
                    export_data["category_table"][1:], columns=["Category", "Value (₹)", "Count"]
                )
                cat_df["Value (₹)"] = cat_df["Value (₹)"].apply(
                    lambda x: f"₹{float(x):,.2f}" if x else "₹0.00"
                )
                st.table(cat_df)

        # TAB 6: Raw JSON
        with tab_json:
            st.subheader("🔍 Structured JSON")
            st.json(parsed)


if __name__ == "__main__":
    main()
