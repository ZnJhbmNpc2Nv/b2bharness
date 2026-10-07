@echo off
title Corporate Spec-Kit Standalone
echo =========================================================
echo Starting Corporate Spec-Kit on localhost:8470...
echo Zero uv, zero venv, zero pip required.
echo =========================================================
python "%~dp0run_speckit.py" %*
pause
