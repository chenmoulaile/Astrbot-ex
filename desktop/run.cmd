@echo off
setlocal
cd /d "%~dp0."
rem Caches and temp stay on this drive; the system drive is nearly full.
if not exist ..\.cache\tmp mkdir ..\.cache\tmp
set "npm_config_cache=..\.cache\npm"
set "UV_CACHE_DIR=..\.cache\uv"
set "ELECTRON_CACHE=..\.cache\electron"
set "TEMP=..\.cache\tmp"
set "TMP=%TEMP%"
if not exist "node_modules" call npm install
call npm start
