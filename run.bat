@echo off
title Lite-AI Hub
echo ========================================================
echo       Khoi dong Lite-AI Hub v3.0 (Local AI Hub)
echo ========================================================

REM 1. Kiem tra Ollama dang chay
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [CANH BAO] Khong the ket noi toi Ollama tai http://127.0.0.1:11434
    echo Vui long mo Ollama truoc khi chat.
    echo.
) else (
    echo [OK] Da ket noi Ollama san sang.
)

REM 2. Kiem tra moi truong ao venv
if not exist "venv\Scripts\python.exe" (
    echo [1/3] Dang tao moi truong ao Python venv...
    python -m venv venv
    echo [2/3] Dang cai dat thu vien requirements...
    venv\Scripts\python.exe -m pip install -r requirements.txt
)

REM 3. Khoi dong Lite-AI Backend Server
echo [2/3] Dang khoi chay Lite-AI Server...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
start "Lite-AI Server" venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000


REM 4. Cho server san sang qua endpoint /api/health
echo [3/3] Dang kiem tra may chu tai /api/health...
powershell -NoProfile -Command "for ($i=0; $i -lt 30; $i++) { try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 1; if ($r.status -eq 'ok') { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 }; exit 1"

if %ERRORLEVEL% EQU 0 (
    echo [OK] May chu da san sang! Dang mo trinh duyet...
    start http://127.0.0.1:8000
) else (
    echo [!] May chu phan hoi cham, dang thu mo trinh duyet...
    start http://127.0.0.1:8000
)

echo ========================================================
echo Lite-AI Hub da khoi dong!
echo Web UI: http://127.0.0.1:8000
echo Docs:   http://127.0.0.1:8000/docs
echo ========================================================
