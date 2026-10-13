@echo off
setlocal
cd /d "%~dp0..\.."

if "%DASHBOARD_PORT%"=="" set DASHBOARD_PORT=6185

echo Astrb-RP  WebUI: http://127.0.0.1:%DASHBOARD_PORT%

rem The core serves data/dist first; keep our build there so the roleplay
rem pages are not replaced by the upstream WebUI download.
if exist "dashboard\dist\index.html" (
  call uv run python scripts\personal\install_webui.py
) else (
  echo  [i] dashboard\dist missing: run scripts\personal\setup.bat once to
  echo      build the WebUI, or the roleplay pages will not show up.
)

echo First start prints the dashboard username and password in this log.
echo Press Ctrl+C to stop.
echo.

call uv run python main.py
