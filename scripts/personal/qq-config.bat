@echo off
setlocal
cd /d "%~dp0..\.."
call uv run python scripts\personal\make_qq_config.py %*
