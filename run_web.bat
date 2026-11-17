@echo off
cd /d "%~dp0"
echo ========================================================
echo  Starting CREST CAS Parser & Equity Advisory Web App
echo ========================================================
echo.
echo Opening http://127.0.0.1:8000 in your browser...
start http://127.0.0.1:8000
echo.
echo Server running at http://127.0.0.1:8000 (Press CTRL+C to stop)
echo.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
) else (
    python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
)
pause
