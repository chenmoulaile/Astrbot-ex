@echo off
setlocal
cd /d "%~dp0..\.."
for %%D in (.cache .cache\uv .cache\tmp vendor-cache) do if not exist "%%D" mkdir "%%D"
set "UV_CACHE_DIR=%~dp0..\..\.cache\uv"
set "PIP_CACHE_DIR=%~dp0..\..\.cache\pip"
set "TMP=%~dp0..\..\.cache\tmp"
set "TEMP=%TMP%"
call uv run python scripts\personal\install_companion.py %*
