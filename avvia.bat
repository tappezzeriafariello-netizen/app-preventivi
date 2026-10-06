@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creo ambiente virtuale...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
echo.
echo Apri nel browser:  http://127.0.0.1:5000
echo Dalla stessa Wi-Fi (telefono/altro PC): http://TUO-IP:5000
echo.
.venv\Scripts\python app.py
pause
