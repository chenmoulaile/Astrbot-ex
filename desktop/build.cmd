@echo off
setlocal
cd /d "%~dp0."
if not exist ..\.cache\tmp mkdir ..\.cache\tmp
set "npm_config_cache=..\.cache\npm"
set "ELECTRON_CACHE=..\.cache\electron"
set "ELECTRON_BUILDER_CACHE=..\.cache\electron-builder"
if not exist "node_modules" call npm install
call npx electron-builder --win nsis
echo release output: desktop\release
