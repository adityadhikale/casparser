"""CREST CAS Parser API. Stateless: nothing from an uploaded statement is persisted."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import market  # noqa: E402
import service  # noqa: E402

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

    try:
        payload, xlsx, csv = service.parse_cas(pdf_bytes, password, engine)
    except service.ParseError as exc:
        raise HTTPException(422, str(exc)) from exc

    stem = Path(pdf.filename or "CAS_Report").stem or "CAS_Report"
    payload["filename"] = stem
    payload["advisory_status"] = service.advisory_status(engine)
    payload["exports"] = {
        "xlsx": base64.b64encode(xlsx).decode(),
        "csv": base64.b64encode(csv).decode(),
    }
    return payload


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
