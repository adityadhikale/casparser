@echo off
cd /d "%~dp0"
echo ========================================================
echo  Starting CAS Parser & Equity Advisory Web Application
echo ========================================================
call .venv\Scripts\activate.bat
streamlit run app.py
pause
