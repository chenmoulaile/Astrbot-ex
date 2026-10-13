@echo off
setlocal
cd /d "%~dp0..\.."

echo ============================================
echo  Astrb-RP setup (one-time)
echo ============================================

rem Keep every download on this drive: the system drive is nearly full.
for %%D in (.cache .cache\uv .cache\pip .cache\tmp vendor-cache) do if not exist "%%D" mkdir "%%D"
set "UV_CACHE_DIR=%~dp0..\..\.cache\uv"
set "PIP_CACHE_DIR=%~dp0..\..\.cache\pip"
set "TMP=%~dp0..\..\.cache\tmp"
set "TEMP=%TMP%"

where uv >nul 2>nul
if errorlevel 1 (
  echo [!] uv not found. Install it first: pip install uv
  exit /b 1
)

echo [1/3] Python dependencies ...
call uv sync --group dev
if errorlevel 1 (
  echo [!] dependency install failed.
  exit /b 1
)

echo [2/3] WebUI build ...
where pnpm >nul 2>nul
if errorlevel 1 (
  echo  [i] pnpm not found: AstrBot downloads the WebUI on first start, but the
  echo      roleplay pages will be missing. Install Node.js + pnpm, then re-run.
) else (
  pushd dashboard
  call pnpm install --registry=https://registry.npmmirror.com
  if errorlevel 1 ( popd & echo [!] pnpm install failed. & exit /b 1 )
  call pnpm build
  if errorlevel 1 ( popd & echo [!] WebUI build failed. & exit /b 1 )
  popd
  echo [3/3] Installing WebUI into astrbot\dashboard\dist ...
  call uv run python scripts\personal\install_webui.py
)

echo.
echo Ready.
echo   1. run start.bat, then open http://127.0.0.1:6185
echo   2. WebUI: Roleplay -^> Import -^> scan your prompt directory
echo   3. QQ: run scripts\personal\qq-config.bat to print the endpoint settings
echo   4. companion plugin (optional): scripts\personal\install-companion.bat
echo.
