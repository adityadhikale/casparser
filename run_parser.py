"""
CAS Parser Runner Script
Processes CAS PDF statements (NSDL, CDSL, CAMS, KFintech).
Scans the 'input' folder by default (or takes a specific file path)
and saves structured outputs into the 'output' folder.

Supported output formats generated in 'output/':
  - <name>.xlsx           : Full Excel workbook
  - <name>_formatted.csv  : Exact multi-section CSV report
  - <name>_parsed.json    : Raw structured JSON data
"""

import argparse
import json
import sys
from pathlib import Path

import casparser
from excel_exporter import (
    build_export_data,
    write_formatted_csv,
    write_formatted_excel,
)

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"


def process_file(pdf_file: Path, password: str = "", out_dir: Path = OUTPUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    base_stem = pdf_file.stem

    print("\n==================================================")
    print(f"Processing: {pdf_file.name}")
    print(f"Password  : {'(provided)' if password else '(empty/none)'}")
    print("==================================================")

    try:
        json_str = casparser.read_cas_pdf(str(pdf_file), password=password, output="json")
        parsed = json.loads(json_str)

        json_out_path = out_dir / f"{base_stem}_parsed.json"
        json_out_path.write_text(json_str, encoding="utf-8")
        print(f"[✔] JSON Output saved: {json_out_path.name}")

        export_data = build_export_data(parsed, pdf_path=pdf_file)

        csv_out_path = out_dir / f"{base_stem}_formatted.csv"
        write_formatted_csv(export_data, csv_out_path)
        print(f"[✔] Formatted CSV saved: {csv_out_path.name}")

        xlsx_out_path = out_dir / f"{base_stem}.xlsx"
        write_formatted_excel(export_data, xlsx_out_path)
        print(f"[✔] Formatted Excel (.xlsx) saved: {xlsx_out_path.name}")

        file_type = parsed.get("file_type")
        period = parsed.get("statement_period", {})
        investor = parsed.get("investor_info", {})
        totals = export_data["totals"]
        print("\n--- Parsed Summary ---")
        print(f"Issuer Type      : {file_type}")
        print(f"Statement Period : {period.get('from')} to {period.get('to')}")
        print(f"Investor Name    : {investor.get('name')}")
        print(f"PAN              : {export_data['investor_table'][6][1]}")
        print(
            f"Demat Holdings   : {len(export_data['demat_rows'])} items (₹{totals['demat_value']})"
        )
        print(f"Mutual Funds     : {len(export_data['mf_rows'])} schemes (₹{totals['mf_value']})")
        print(f"Total Valuation  : ₹{totals['total_portfolio_value']}")
        print("----------------------")

        return True

    except casparser.exceptions.IncorrectPasswordError:
        print(
            f"[✘] Error: Password required or incorrect for '{pdf_file.name}'.",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(f"[✘] Error parsing '{pdf_file.name}': {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Parse CAS statements and export to Excel/CSV/JSON."
    )
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Specific CAS PDF path (optional)",
    )
    parser.add_argument(
        "-p",
        "--password",
        default="",
        help="Password for the PDF (optional, defaults to none)",
    )
    parser.add_argument(
        "-i",
        "--input-dir",
        default=str(INPUT_DIR),
        help="Input directory containing PDFs",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Output directory for generated results",
    )

    args = parser.parse_args()

    out_dir = Path(args.output_dir)

    if args.pdf_path:
        pdf_file = Path(args.pdf_path)
        if not pdf_file.exists():
            print(f"Error: File '{pdf_file}' not found.", file=sys.stderr)
            sys.exit(1)
        process_file(pdf_file, password=args.password, out_dir=out_dir)
    else:
        in_dir = Path(args.input_dir)
        pdf_files = list(in_dir.glob("*.pdf"))
        if not pdf_files:
            print(f"No PDF files found in '{in_dir.resolve()}'.")
            print(f"Please place your CAS PDF in the '{in_dir.name}' folder and re-run.")
            sys.exit(0)

        print(f"Found {len(pdf_files)} PDF file(s) in '{in_dir}'.")
        for pdf_file in pdf_files:
            process_file(pdf_file, password=args.password, out_dir=out_dir)


if __name__ == "__main__":
    main()
