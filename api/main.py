"""CREST CAS Parser API.

Parsing is in-memory. When Azure Blob is configured (see ``blob_store``), the
uploaded PDFs are archived there; passwords and generated reports are not.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a local .env; real env vars take precedence."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")

import blob_store  # noqa: E402
import market  # noqa: E402
import service  # noqa: E402

print(
    f"Azure Blob archive: ON (container {os.environ['AZURE_BLOB_CONTAINER'].strip()!r})"
    if blob_store.enabled()
    else "Azure Blob archive: OFF (AZURE_* settings not set)",
    flush=True,
)

MAX_PDF = 25 * 1024 * 1024
MAX_XLSX = 10 * 1024 * 1024

app = FastAPI(title="CREST CAS Parser")


@app.get("/api/advisory/status")
def advisory_status():
    return service.advisory_status(service.get_default_engine())


@app.post("/api/parse")
async def parse(
    pdf: UploadFile = File(...),
    password: str = Form(""),
    advisory: UploadFile | None = File(None),
):
    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        raise HTTPException(400, "The uploaded PDF is empty.")
    if len(pdf_bytes) > MAX_PDF:
        raise HTTPException(413, "PDF is larger than 25 MB.")

    engine = service.get_default_engine()
    if advisory is not None and advisory.filename:
        data = await advisory.read()
        if len(data) > MAX_XLSX:
            raise HTTPException(413, "Advisory file is larger than 10 MB.")
        try:
            engine = service.engine_from_bytes(data)
        except Exception as exc:
            raise HTTPException(400, f"Could not read advisory file: {exc}") from exc

    archive = [(pdf.filename, pdf_bytes)]
    try:
        payload, xlsx, csv = service.parse_cas(pdf_bytes, password, engine)
    except service.ParseError as exc:
        blob_store.save(archive, "failed", "single")
        raise HTTPException(422, str(exc)) from exc
    blob_store.save(archive, "parsed", "single")

    stem = Path(pdf.filename or "CAS_Report").stem or "CAS_Report"
    payload["filename"] = stem
    payload["advisory_status"] = service.advisory_status(engine)
    payload["exports"] = {
        "xlsx": base64.b64encode(xlsx).decode(),
        "csv": base64.b64encode(csv).decode(),
    }
    return payload


MAX_FILES = 10


def _b64_exports(xlsx: bytes, csv: bytes) -> dict:
    return {"xlsx": base64.b64encode(xlsx).decode(), "csv": base64.b64encode(csv).decode()}


@app.post("/api/parse-multi")
async def parse_multi(
    pdfs: list[UploadFile] = File(...),
    passwords: list[str] = Form(default_factory=list),
    advisory: UploadFile | None = File(None),
):
    """Parse several CAS PDFs (one per family member) and consolidate them.

    ``passwords[i]`` belongs to ``pdfs[i]``; missing entries mean no password.
    """
    if not pdfs:
        raise HTTPException(400, "Upload at least one PDF.")
    if len(pdfs) > MAX_FILES:
        raise HTTPException(400, f"Upload at most {MAX_FILES} statements at a time.")

    files: list[tuple[str, bytes, str]] = []
    for i, up in enumerate(pdfs):
        label = up.filename or f"statement {i + 1}"
        data = await up.read()
        if not data:
            raise HTTPException(400, f"{label} is empty.")
        if len(data) > MAX_PDF:
            raise HTTPException(413, f"{label} is larger than 25 MB.")
        files.append((label, data, passwords[i] if i < len(passwords) else ""))

    engine = service.get_default_engine()
    if advisory is not None and advisory.filename:
        data = await advisory.read()
        if len(data) > MAX_XLSX:
            raise HTTPException(413, "Advisory file is larger than 10 MB.")
        try:
            engine = service.engine_from_bytes(data)
        except Exception as exc:
            raise HTTPException(400, f"Could not read advisory file: {exc}") from exc

    archive = [(label, data) for label, data, _ in files]
    try:
        result = service.parse_family(files, engine)
    except service.ParseError as exc:
        blob_store.save(archive, "failed", "family")
        raise HTTPException(422, str(exc)) from exc
    blob_store.save(archive, "parsed", "family")

    status = service.advisory_status(engine)
    fam, fam_xlsx, fam_csv = result["family"]
    fam["filename"] = "Family_CAS_Report"
    fam["advisory_status"] = status
    fam["exports"] = _b64_exports(fam_xlsx, fam_csv)
    members = []
    for stem, payload, xlsx, csv in result["members"]:
        payload["filename"] = stem
        payload["advisory_status"] = status
        payload["exports"] = _b64_exports(xlsx, csv)
        members.append(payload)
    return {"family": fam, "members": members, "warnings": result["warnings"]}


class HoldingIn(BaseModel):
    isin: str = ""
    name: str = ""
    units: float | None = None
    ticker: str = ""


class HoldingsIn(BaseModel):
    holdings: list[HoldingIn]


@app.post("/api/market/holdings")
def market_holdings(body: HoldingsIn):
    if len(body.holdings) > 200:
        raise HTTPException(413, "Too many holdings.")
    return market.holdings_quotes([h.model_dump() for h in body.holdings])


class MfIn(BaseModel):
    isins: list[str]


@app.post("/api/market/mf")
def market_mf(body: MfIn):
    if len(body.isins) > 200:
        raise HTTPException(413, "Too many funds.")
    return market.mf_navs(body.isins)


@app.get("/api/market/overview")
def market_overview():
    return market.overview()


@app.get("/api/market/news")
def market_news(symbols: str = Query("^NSEI", max_length=600)):
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:10]
    return market.news(syms)


DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
