@echo off
title Remote Job Search Agent Launcher
echo Starting Remote Job Search Agent...

start "RJS Backend (FastAPI)" cmd /k "cd /d %~dp0backend && python main.py"
start "RJS Frontend (Next.js)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================================
echo   Backend running at: http://localhost:8000
echo   Frontend running at: http://localhost:3000
echo ========================================================
echo.
timeout /t 3 >nul
start http://localhost:3000
