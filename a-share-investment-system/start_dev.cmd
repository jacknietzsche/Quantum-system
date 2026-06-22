@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo =============================================
echo   AShare-X v5.2.0 - Development Mode (core/)
echo   Vue 3 + Element Plus | FastAPI | core/ agents
echo =============================================
echo.

set PYTHON_CMD=

if exist ".venv\Scripts\python.exe" ( set "PYTHON_CMD=.venv\Scripts\python.exe" & goto :found_python )
if exist "venv\Scripts\python.exe" ( set "PYTHON_CMD=venv\Scripts\python.exe" & goto :found_python )
where python >nul 2>&1
if %errorlevel% equ 0 ( set "PYTHON_CMD=python" & goto :found_python )

echo [ERROR] Python not found. Please install Python 3.10+
pause
exit /b 1

:found_python
where node >nul 2>&1 || ( echo [ERROR] Node.js not found. Install Node.js 18+ & pause & exit /b 1 )

echo   Python: %PYTHON_CMD%
echo.
echo   Frontend: http://localhost:5173 (hot reload)
echo   Backend:  http://127.0.0.1:8765
echo.

"%PYTHON_CMD%" launch.py --dev

pause
