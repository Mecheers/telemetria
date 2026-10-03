@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Primero ejecute INSTALAR_Y_EJECUTAR.bat
  pause
  exit /b 1
)
.venv\Scripts\python.exe run.py
if errorlevel 1 pause
