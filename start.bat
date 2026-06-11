@echo off
REM MarketLens - one-click launcher
REM Double-click or run from cmd: starts FastAPI (8000) + Vite dev (5173) + auto-opens browser
REM Ctrl+C gracefully cleans up child processes

pushd "%~dp0"

echo.
echo === MarketLens Launcher ===
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv not found. Install: https://docs.astral.sh/uv/
    echo.
    pause
    exit /b 1
)

echo Starting MarketLens (Ctrl+C to stop)...
echo.
uv run python scripts/launcher.py
set EXITCODE=%errorlevel%
popd

if %EXITCODE% neq 0 (
    echo.
    echo [ERROR] MarketLens exited with code %EXITCODE%
    echo Try: uv sync
    echo.
)
pause
