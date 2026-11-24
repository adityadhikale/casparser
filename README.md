# CASParser

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python versions](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://github.com/adityadhikale/casparser)
[![Repository](https://img.shields.io/badge/GitHub-adityadhikale%2Fcasparser-black?logo=github)](https://github.com/adityadhikale/casparser)

**CASParser** is a comprehensive Python parser and portfolio analysis toolkit for Consolidated Account Statement (CAS) PDF files issued by **CDSL**, **NSDL**, **CAMS**, and **KFintech**.

It extracts demat equities, mutual fund folios, bonds, NPS accounts, and transactions into structured **Excel (`.xlsx`)**, **CSV**, and **JSON** formats.

---

## Key Features

- **Multi-Source CAS Support**:
  - **CDSL & NSDL**: Consolidated Demat accounts, equities, mutual fund holdings, corporate/government bonds, and NPS.
  - **CAMS & KFintech**: Detailed transactions and summary mutual fund folios.
- **Automated Excel (`.xlsx`) Export**:
  - **`CAS_Report_Combined` Sheet**: Full multi-section report (Investor Info, Category Summary, Mutual Funds, Transactions, Demat Holdings, Metadata).
  - **`Demat Holdings` Sheet**: Clean, formatted spreadsheet of all equity shares and bonds.
  - **`Mutual Funds` Sheet**: Full portfolio breakdown with AMC names, folios, units, NAV, cost, and P&L.
  - **`Transactions` Sheet**: Chronological SIP and investment transactions with units, NAV, and stamp duty.
  - **`Investor & Summary` Sheet**: Investor KYC information and asset class totals.
- **Standard Stacked CSV**: Matches the original multi-section web export format.
- **OpenXML Sanitization**: Automatic cleanup of non-printable control characters from PDF streams to guarantee error-free Excel generation.
- **Batch Processing**: Drop PDFs directly into `input/` and get generated reports in `output/`.
- **Flexible Security**: Automatically parses password-free PDFs and supports password-encrypted statements.
- **High Performance**: Built on `pypdfium2` for fast native PDF object extraction without external OCR or third-party engines.

---

## Supported Inputs

| Issuer | Variant(s) | Source |
|---|---|---|
| **CAMS** | Detailed, Summary | `mailback.camsonline.com` request |
| **KFintech** | Detailed, Summary | `mfs.kfintech.com` request |
| **NSDL** | Demat consolidated | NSDL CAS email (monthly) |
| **CDSL** | Demat consolidated | CDSL CAS email (monthly) |

---

## Directory Structure

```text
casparser/
├── input/                  # Place your CAS PDF statements here
├── output/                 # Generated Excel, CSV, and JSON reports
├── casparser/              # Core library parser modules
│   ├── parsers/            # CDSL, NSDL, CAMS, and KFintech parsers
│   ├── analysis/           # Capital gains and portfolio analytics
│   └── cli.py              # Command-line interface
├── api/                    # FastAPI backend (web application)
│   └── main.py             # API routes: /api/parse, /api/parse-multi, /api/market/*, /api/advisory/status
├── web/                    # Vite + React + TypeScript frontend
│   ├── src/                # React components, hooks, and styles
│   └── dist/               # Production build output (served by FastAPI)
├── data/                   # Equity Portfolio Advisory.xlsx (advisory model)
├── service.py              # PDF parse service (UI-agnostic, used by API)
├── consolidate.py          # Merges several members' statements into one family view
├── market.py               # Yahoo Finance market data layer (stocks, indices, mutual fund NAVs)
├── excel_exporter.py       # Multi-tab Excel and formatted CSV builder
├── run_parser.py           # CLI batch / single-file runner
├── run_web.bat             # Windows one-click launcher for the web app
├── Dockerfile              # Multi-stage container build
├── requirements.txt        # Python dependencies
└── pyproject.toml          # Project configuration & dependencies
```

---

## Web Application (FastAPI + React)

A modern full-stack web dashboard that parses CAS statements in real-time, cross-references equity demat holdings against the internal CREST advisory model (`data/Equity Portfolio Advisory.xlsx`), and fetches live Yahoo Finance quotes and market indices.

### Features
- **Instant Client-Side Parsing**: Upload CAS PDFs (CDSL, NSDL, CAMS, KFintech) with optional password support. Nothing from the statement is permanently saved on the server.
- **Family Consolidation**: Upload up to 10 CAS PDFs at once (one per family member, each with its own password) to get one consolidated portfolio. Holdings with the same ISIN are merged into one line, and an Owner column plus a Family / member selector lets you switch between the combined view and each person. Combined Excel/CSV/JSON exports carry an Owner column. The app warns when statements cover different periods or share a PAN, and rejects identical files. A single PDF works exactly as before.
- **Equity Advisory Matching**: Instant BUY, ADD, HOLD, TRIM, SELL, and Not Covered badge matching by ISIN, ticker, and company name.
- **Live Market Feed**: Real-time indicative market strip (Nifty 50, Sensex, Bank Nifty, India VIX, USD/INR, Gold, Brent) with 1-month sparklines, today's P&L, day change %, and 52-week ranges via Yahoo Finance.
- **Mutual Fund NAVs**: Latest end-of-day NAV, NAV date, day change and current value for each fund, matched by ISIN on Yahoo Finance. Shown in the Live market tab and as extra columns in the Mutual funds tab. Funds do not trade intraday, so these are daily NAVs, not live prices; each row shows its own NAV date.
- **Interactive Visualizations**: Asset allocation donut chart, advisory distribution bar chart, top holdings chart, and full export capabilities (formatted multi-tab Excel, CSV, JSON).

### Running Locally

#### Windows (One-Click)
Double-click `run_web.bat` in the root folder, or run:
```bat
run_web.bat
```
This starts the backend and automatically opens `http://127.0.0.1:8000`.

#### Manual Startup
```bash
# Activate virtual environment
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000` in your web browser.

#### Building the Frontend (Vite)
If you make frontend changes inside `web/`:
```bash
cd web
npm install
npm run build
```

---

## Docker Deployment

A production-ready multi-stage Dockerfile is included:

```bash
# Build the Docker image
docker build -t crest-casparser .

# Run the container on port 8000
docker run -p 8000:8000 crest-casparser
```
Access the application at `http://localhost:8000`.

---

## Quickstart

### 1. Installation

Clone the repository and install requirements:

```bash
git clone https://github.com/adityadhikale/casparser.git
cd casparser
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -e .
```

### 2. Running the Parser (Automated)

1. Drop your CAS PDF into the `input/` folder.
2. Run the automated runner:

```bash
# If your PDF does not have a password:
python run_parser.py

# If your PDF is password-protected:
python run_parser.py -p "YOUR_PASSWORD"
```

All parsed files will be created in `output/`:
- `<filename>.xlsx` (Formatted multi-tab Excel workbook)
- `<filename>_formatted.csv` (Multi-section CSV report)
- `<filename>_parsed.json` (Full raw JSON data)

---

## Usage

```python
import casparser

# Parse statement to typed Pydantic models (CASData or NSDLCASData)
data = casparser.read_cas_pdf("input/statement.pdf", password="")

# Get data in JSON format
json_str = casparser.read_cas_pdf("input/statement.pdf", password="", output="json")

# Get transactions data in CSV format
csv_str = casparser.read_cas_pdf("input/statement.pdf", password="", output="csv")
```

---

## Data Structure

`read_cas_pdf` returns a typed Pydantic model — `CASData` for CAMS / KFintech statements, and `NSDLCASData` for NSDL / CDSL demat statements (see `casparser.types`). With `output="json"` the same shape is serialised to a JSON string.

Machine-readable JSON Schema files are generated under `schema/`.

### CAMS / KFintech — `CASData`

```ts
// decimal = a JSON string holding an exact decimal number, e.g. "4999.75"
{
  statement_period: { from: string, to: string },   // "01-Apr-2024"
  file_type: "CAMS" | "KFINTECH",
  cas_type: "DETAILED" | "SUMMARY",
  investor_info: { name: string, email: string, address: string, mobile: string },
  folios: {
    folio: string,                       // "12345678 / 90"
    amc: string,
    name: string | null,                 // folio holder's name as printed;
                                         // null on older templates that omit it
    PAN: string | null,
    KYC: "OK" | "NOT OK" | null,
    PANKYC: "OK" | "NOT OK" | null,
    schemes: {
      scheme: string,
      advisor: string | null,            // distributor ARN / RIA code
      rta_code: string,                  // scheme's per-RTA code
      rta: string,                       // registrar: "CAMS", "KFINTECH", …
      type: string | null,               // "EQUITY" | "DEBT" | …
      isin: string | null,
      amfi: string | null,
      nominees: string[],
      open: decimal,                     // opening unit balance
      close: decimal,                    // closing unit balance (as printed)
      close_calculated: decimal,         // open + sum of parsed units
      valuation: { date: string, nav: decimal, cost: decimal | null, value: decimal },
      transactions: {
        date: string,                    // ISO: "2024-04-01"
        description: string,
        amount: decimal | null,
        units: decimal | null,           // null for non-unit rows (taxes)
        nav: decimal | null,
        balance: decimal | null,         // running unit balance
        type: string,                    // see transaction types below
        dividend_rate: decimal | null,   // DIVIDEND_* rows only
        gift_folio: string | null,       // GIFT_IN/OUT only: counterparty folio
      }[],
    }[],
  }[],
  parse_warnings: string[],
}
```

### Transaction types

| `type` | Meaning |
|---|---|
| `PURCHASE` / `PURCHASE_SIP` | Lump-sum / SIP-instalment purchase |
| `REDEMPTION` | Redemption / withdrawal |
| `SWITCH_IN` / `SWITCH_IN_MERGER` | Units received from a switch (or scheme merger) |
| `SWITCH_OUT` / `SWITCH_OUT_MERGER` | Units moved out via a switch (or scheme merger) |
| `DIVIDEND_PAYOUT` / `DIVIDEND_REINVEST` | IDCW / dividend rows — these carry `dividend_rate` |
| `STT_TAX` / `STAMP_DUTY_TAX` / `TDS_TAX` | Tax rows — `amount` only, no units |
| `SEGREGATION` | Units allotted in a segregated (side-pocketed) portfolio |
| `GIFT_IN` / `GIFT_OUT` | Units gifted in / out via inter-folio transfer |
| `REVERSAL` | Reversed / rejected transaction |
| `MISC` / `UNKNOWN` | Anything that doesn't match the above |

### NSDL / CDSL — `NSDLCASData`

Demat statements return holdings grouped per demat account:

```ts
{
  statement_period: { from: string, to: string },
  file_type: "NSDL" | "CDSL",
  investor_info: { name: string, email: string, address: string, mobile: string },
  accounts: {
    name: string,                        // account / DP name
    type: string,                        // "NSDL" | "CDSL"
    dp_id: string | null,
    client_id: string | null,
    folios: number,                      // count of MF folios in the account
    balance: decimal,                    // total account valuation
    owners: { name: string, PAN: string }[],
    equities: {
      isin: string, name: string | null,
      num_shares: decimal, price: decimal, value: decimal,
      symbol: string | null, exchange: string | null,   // from the ISIN DB
    }[],
    mutual_funds: {
      isin: string, name: string | null,
      amfi: string | null, type: string | null,         // from the ISIN DB
      balance: decimal, nav: decimal, value: decimal,
      avg_cost: decimal | null, total_cost: decimal | null,
      ucc: string | null, folio: string | null,
      pnl: decimal | null, return: decimal | null,
    }[],
    bonds: {
      isin: string, name: string | null,
      num_bonds: decimal, value: decimal,
      face_value: decimal | null, coupon_rate: decimal | null,
      coupon_frequency: string | null, maturity_date: string | null,
      market_price: decimal | null,
    }[],
  }[],
  parse_warnings: string[],              // non-fatal demat data-quality warnings
  nps: {                                 // National Pension System, if present (CDSL)
    pran: string | null,                 // PRAN (as printed; often masked)
    nps_sp: string | null,               // NPS service provider / CRA, e.g. "PROT"
    value: decimal,                      // reported NPS portfolio value
    schemes: {
      scheme: string, fund_manager: string | null,
      tier: string | null,               // "I" | "II"
      asset_class: string | null,        // "E" | "C" | "G" | "A"
      units: decimal, nav: decimal, value: decimal,
    }[],
  } | null,
}
```

---

## CLI Usage

The built-in command line interface provides quick terminal summaries and capital gains reports:

```bash
# Display summary in console:
casparser path/to/statement.pdf -p "" -s

# Generate Capital Gains report:
casparser path/to/statement.pdf -p "PASSWORD" -g

# Export Schedule 112A for ITR filing:
casparser path/to/statement.pdf -p "PASSWORD" --gains-112a ask -o output.csv
```

---

## Generated Excel Structure

| Sheet Name | Content |
|---|---|
| **`CAS_Report_Combined`** | Complete consolidated statement with formatted tables for Investor KYC, Portfolio Summary, Mutual Funds, Transactions, and Demat Holdings. |
| **`Demat Holdings`** | DP ID, Client ID, BO ID, Company Name, ISIN, Category, Shares, and Closing Value. |
| **`Mutual Funds`** | Folio Number, AMC Name, Scheme Name, ISIN, Units, NAV, Valuation, Cost, and Absolute/Percentage Gains. |
| **`Transactions`** | Date, Folio, Scheme, Type (SIP/Purchase), Units, Price, Stamp Duty, and Running Balance. |
| **`Investor & Summary`** | Name, PAN, Address, Pincode, Statement Dates, and Asset Breakdown. |

---

## License

This project is licensed under the [MIT License](LICENSE).
